"""SSH access to VPSes. Host keys are trusted on first use and pinned afterwards."""
import io
import shlex
import time

import paramiko

from . import config, db, security


class SSHError(Exception):
    pass


def manager_public_key():
    """Keypair this app uses; the bootstrap script authorises it on new VPSes."""
    config.ensure_dirs()
    if not config.SSH_KEY_PATH.exists():
        k = paramiko.Ed25519Key.generate() if hasattr(paramiko, "Ed25519Key") and hasattr(paramiko.Ed25519Key, "generate") else None
        if k is None:  # older paramiko: fall back to RSA
            k = paramiko.RSAKey.generate(3072)
        k.write_private_key_file(str(config.SSH_KEY_PATH))
    k = _load_key(config.SSH_KEY_PATH.read_text())
    return f"{k.get_name()} {k.get_base64()} fleet-manager"


def _load_key(text):
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(text))
        except Exception:
            continue
    raise SSHError("Unsupported or encrypted private key (passphrase keys are not supported)")


class Runner:
    def __init__(self, server, log=None):
        self.s = server
        self.log = log or (lambda _t: None)
        self.client = None
        self.secret = security.decrypt(server.get("secret_enc"))

    def connect(self):
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kw = dict(hostname=self.s["ip"], port=self.s["ssh_port"], username=self.s["ssh_user"],
                  timeout=15, banner_timeout=20, auth_timeout=20, allow_agent=False, look_for_keys=False)
        if self.s["auth_type"] == "password":
            kw["password"] = self.secret
        else:
            kw["pkey"] = _load_key(self.secret)
        last = None
        for attempt in range(3):
            try:
                c.connect(**kw)
                last = None
                break
            except paramiko.AuthenticationException as e:
                raise SSHError(f"Login to {self.s['ssh_user']}@{self.s['ip']}:{self.s['ssh_port']} was rejected: {e}. "
                               "Check the SSH user and password/key.")
            except Exception as e:  # network trouble: wait and try again
                last = e
                time.sleep(2 * (attempt + 1))
        if last is not None:
            raise SSHError(f"Cannot connect to {self.s['ssh_user']}@{self.s['ip']} on port {self.s['ssh_port']}: {last}. "
                           "Check the SSH port in the server settings and that the VPS firewall allows it.")
        c.get_transport().set_keepalive(20)  # stops idle firewalls/NAT from dropping long installs
        fp = c.get_transport().get_remote_server_key().get_fingerprint().hex()
        pinned = self.s.get("host_fingerprint")
        if pinned and pinned != fp:
            c.close()
            raise SSHError("Host key changed since first connection (possible MITM or re-installed VPS). "
                           "Edit the server and clear the fingerprint if this is expected.")
        if not pinned and self.s.get("id"):
            db.x("UPDATE servers SET host_fingerprint=? WHERE id=?", (fp, self.s["id"]))
            self.s["host_fingerprint"] = fp
        self.client = c
        return self

    def __enter__(self):
        return self.connect()

    def __exit__(self, *a):
        self.close()

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def run(self, cmd, sudo=False, as_user=None, check=False, stream=True, timeout=3600):
        """Run a shell command; sudo=True as root, as_user=<name> as that user (login shell)."""
        login = self.s["ssh_user"]
        q = shlex.quote
        if as_user and as_user != login:
            argv = f"-u {q(as_user)} -H bash -lc {q(cmd)}"
        elif sudo and login != "root":
            argv = f"bash -c {q(cmd)}"
        else:
            if as_user:  # already that user: just get a login shell (PATH, nvm, ~/.local/bin)
                cmd = f"bash -lc {q(cmd)}"
            return self._exec(cmd, None, check, stream, timeout)
        stdin_pw = None
        if login == "root":
            full = f"sudo {argv}"
        elif self.s["auth_type"] == "password":
            full, stdin_pw = f"sudo -S -p '' {argv}", self.secret
        else:
            full = f"sudo -n {argv}"
        return self._exec(full, stdin_pw, check, stream, timeout)

    def _exec(self, full, stdin_pw, check, stream, timeout):
        """Run once; if the connection drops, quiet short commands reconnect and retry once."""
        for attempt in (1, 2):
            try:
                return self._exec_once(full, stdin_pw, check, stream, timeout)
            except SSHError:
                raise
            except (OSError, EOFError, paramiko.SSHException) as e:
                if attempt == 1 and not stream:
                    self.close()
                    self.connect()
                    continue
                raise SSHError(f"The connection to the VPS was lost ({e}). If this happened during an install, "
                               "the command may still be running on the server; wait a few minutes, then retry.")

    def _exec_once(self, full, stdin_pw, check, stream, timeout):
        chan = self.client.get_transport().open_session()
        chan.set_combine_stderr(True)
        chan.settimeout(timeout)
        chan.exec_command(full)
        if stdin_pw:
            chan.sendall(stdin_pw + "\n")
        chan.shutdown_write()  # EOF on stdin so interactive prompts fail fast instead of hanging forever
        out, start = [], time.time()
        while True:
            if chan.recv_ready():
                data = chan.recv(65536).decode("utf-8", "replace")
                out.append(data)
                if stream:
                    self.log(data)
            elif chan.exit_status_ready():
                while chan.recv_ready():
                    data = chan.recv(65536).decode("utf-8", "replace")
                    out.append(data)
                    if stream:
                        self.log(data)
                break
            else:
                if time.time() - start > timeout:
                    chan.close()
                    raise SSHError("Command timed out")
                time.sleep(0.1)
        code = chan.recv_exit_status()
        text = "".join(out)
        if check and code != 0:
            raise SSHError(f"Command failed (exit {code}): {full[:200]}")
        return code, text

    def sftp(self):
        return self.client.open_sftp()

    # ---- file transfer: SFTP when the server has it, plain `cat` over an exec channel otherwise
    def _open_exec(self, cmd, sudo=False):
        login = self.s["ssh_user"]
        pw = None
        if sudo and login != "root":
            if self.s["auth_type"] == "password":
                cmd, pw = f"sudo -S -p '' {cmd}", self.secret
            else:
                cmd = f"sudo -n {cmd}"
        chan = self.client.get_transport().open_session()
        chan.set_combine_stderr(False)
        chan.settimeout(600)
        chan.exec_command(cmd)
        if pw:
            chan.sendall(pw + "\n")
        return chan

    def write_chunks(self, path, chunks):
        """Write an iterable of bytes to `path` on the server; returns bytes written."""
        total = 0
        try:
            sf = self.client.open_sftp()
        except (paramiko.SSHException, EOFError, OSError):
            sf = None
        if sf:
            try:
                with sf.open(path, "wb") as dst:
                    for c in chunks:
                        dst.write(c)
                        total += len(c)
                return total
            except (paramiko.SSHException, EOFError):
                pass            # no working sftp subsystem: fall through to cat
            finally:
                try:
                    sf.close()
                except Exception:
                    pass
        chan = self._open_exec(f"sh -c {shlex.quote('cat > ' + shlex.quote(path))}")
        total = 0
        for c in chunks:
            chan.sendall(c)
            total += len(c)
        chan.shutdown_write()
        err = b""
        while chan.recv_stderr_ready():
            err += chan.recv_stderr(4096)
        code = chan.recv_exit_status()
        if code != 0:
            raise SSHError(f"Could not write {path} on the server (exit {code}): {err.decode('utf-8', 'replace').strip()[-200:]}")
        return total

    def read_chunks(self, path, sudo=False, size=262144):
        """Yield the file's bytes. Falls back from SFTP to `cat` (with sudo if asked) when SFTP is unavailable."""
        try:
            sf = self.client.open_sftp()
            f = sf.open(path, "rb")
        except (paramiko.SSHException, EOFError, OSError):
            sf = f = None
        if f:
            try:
                while True:
                    c = f.read(size)
                    if not c:
                        return
                    yield c
            finally:
                sf.close()
        chan = self._open_exec(f"cat {shlex.quote(path)}", sudo=sudo)
        while True:
            c = chan.recv(size)
            if not c:
                break
            yield c
        code = chan.recv_exit_status()
        if code != 0:
            raise SSHError(f"Could not read {path} on the server (exit {code}); check the file exists")

    def file_size(self, path):
        code, out = self.run(f"stat -c %s {shlex.quote(path)}", sudo=True, stream=False)
        if code != 0 or not out.strip().isdigit():
            raise SSHError(f"File not found: {path}")
        return int(out.strip())

    def write_file(self, path, content, mode=0o644):
        sftp = self.client.open_sftp()
        try:
            with sftp.open(path, "w") as f:
                f.write(content)
            sftp.chmod(path, mode)
        finally:
            sftp.close()


def runner_for(server, log=None):
    return Runner(server, log)
