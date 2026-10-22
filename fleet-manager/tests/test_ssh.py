"""Exercises the real ssh.Runner against an in-process paramiko SSH server that runs commands locally."""
import os
import shutil
import socket
import subprocess
import threading

import paramiko
import pytest

from fleetmanager import db, security, ssh
from fleetmanager.ssh import Runner  # real class, imported before the autouse fake patches ssh.Runner

HOSTKEY = paramiko.RSAKey.generate(2048)


class Srv(paramiko.ServerInterface):
    def check_auth_password(self, u, p):
        return paramiko.AUTH_SUCCESSFUL if (u, p) == ("root", "pw") else paramiko.AUTH_FAILED
    def get_allowed_auths(self, u): return "password"
    def check_channel_request(self, kind, cid): return paramiko.OPEN_SUCCEEDED
    def check_channel_exec_request(self, chan, command):
        def go():
            p = subprocess.Popen(["bash", "-c", command.decode()], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)

            def feed():
                while True:
                    d = chan.recv(1024)
                    if not d:
                        break
                    p.stdin.write(d)
                    p.stdin.flush()
                p.stdin.close()
            threading.Thread(target=feed, daemon=True).start()
            for chunk in iter(lambda: p.stdout.read(64), b""):
                chan.sendall(chunk)
            chan.send_exit_status(p.wait())
            chan.close()
        threading.Thread(target=go, daemon=True).start()
        return True


@pytest.fixture
def sshd():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    port = sock.getsockname()[1]
    hostkey = [HOSTKEY]

    def serve():
        while True:
            try:
                c, _ = sock.accept()
            except OSError:
                return
            t = paramiko.Transport(c)
            t.add_server_key(hostkey[0])
            t.start_server(server=Srv())
    threading.Thread(target=serve, daemon=True).start()
    yield port, hostkey
    sock.close()


def server_row(port, pw="pw"):
    db.init()
    sid = db.x("INSERT INTO servers(name,ip,ssh_port,ssh_user,auth_type,secret_enc,version) VALUES('t','127.0.0.1',?,'root','password',?,'version-15')",
               (port, security.encrypt(pw)))
    return db.q1("SELECT * FROM servers WHERE id=?", (sid,))


def test_run_streams_and_reports_exit(sshd):
    port, _ = sshd
    out = []
    with Runner(server_row(port), out.append) as r:
        code, text = r.run("echo hello; echo err >&2; exit 3")
        assert code == 3 and "hello" in text and "err" in text and "hello" in "".join(out)
        with pytest.raises(ssh.SSHError):
            r.run("false", check=True)


@pytest.mark.skipif(os.geteuid() != 0 or not shutil.which("sudo"), reason="needs root+sudo")
def test_as_user_runs_as_other_user(sshd):
    port, _ = sshd
    with Runner(server_row(port)) as r:
        assert r.run("id -un", as_user="nobody", stream=False)[1].strip() == "nobody"
        assert r.run("echo 'a b \"c\" $HOME'", as_user="nobody", stream=False)[1].strip() == 'a b "c" $HOME'


def test_wrong_password_and_host_key_pinning(sshd):
    port, hostkey = sshd
    with pytest.raises(ssh.SSHError):
        Runner(server_row(port, "nope")).connect()
    s = server_row(port)
    Runner(s).connect().close()
    assert db.q1("SELECT host_fingerprint f FROM servers WHERE id=?", (s["id"],))["f"]
    Runner(db.q1("SELECT * FROM servers WHERE id=?", (s["id"],))).connect().close()   # same key: fine
    hostkey[0] = paramiko.RSAKey.generate(2048)                                            # VPS "re-installed"
    with pytest.raises(ssh.SSHError, match="Host key changed"):
        Runner(db.q1("SELECT * FROM servers WHERE id=?", (s["id"],))).connect()


def test_manager_key_is_stable():
    a = ssh.manager_public_key()
    assert a.startswith("ssh-") and a == ssh.manager_public_key()


def test_stdin_gets_eof_so_prompts_cannot_hang(sshd):
    port, _ = sshd
    with Runner(server_row(port)) as r:
        code, text = r.run("read -p 'Continue? [y/N]: ' a || echo EOF_SEEN", stream=False, timeout=10)
        assert "EOF_SEEN" in text


class _Chan:
    def __init__(self, out, code=0): self.out, self.code, self.sent = out, code, False
    def set_combine_stderr(self, v): pass
    def settimeout(self, t): pass
    def exec_command(self, c): pass
    def sendall(self, d): pass
    def shutdown_write(self): pass
    def recv_ready(self): return not self.sent
    def recv(self, n): self.sent = True; return self.out
    def exit_status_ready(self): return self.sent
    def recv_exit_status(self): return self.code
    def close(self): pass


class _Client:
    def __init__(self, fail): self.fail = fail
    def get_transport(self): return self
    def open_session(self):
        if self.fail:
            raise ConnectionResetError(10054, "forcibly closed")
        return _Chan(b"ok")
    def close(self): pass


def _runner(first_fails):
    r = Runner({"ip": "x", "ssh_port": 22, "ssh_user": "root", "auth_type": "password", "secret_enc": None})
    r.client = _Client(first_fails)
    calls = []
    r.connect = lambda: (calls.append(1), setattr(r, "client", _Client(False)))[0] or r
    return r, calls


def test_quiet_command_reconnects_after_connection_reset():
    r, calls = _runner(True)
    assert r.run("echo hi", stream=False) == (0, "ok") and calls == [1]


def test_streamed_command_reports_lost_connection_instead_of_retrying():
    r, calls = _runner(True)
    with pytest.raises(ssh.SSHError, match="connection to the VPS was lost"):
        r.run("long install")
    assert calls == []


def test_file_transfer_falls_back_to_cat_when_sftp_is_missing():
    import paramiko
    from fleetmanager import ssh

    class Chan:
        def __init__(c): c.sent, c.cmd, c.data = b"", None, b"hello world"
        def settimeout(c, t): pass
        def set_combine_stderr(c, v): pass
        def exec_command(c, cmd): c.cmd = cmd
        def sendall(c, d): c.sent += d if isinstance(d, bytes) else d.encode()
        def shutdown_write(c): pass
        def recv_stderr_ready(c): return False
        def recv_exit_status(c): return 0
        def recv(c, n):
            d, c.data = c.data[:n], c.data[n:]; return d

    chans = []
    class T:
        def open_session(t): chans.append(Chan()); return chans[-1]
    class Client:
        def open_sftp(c): raise paramiko.SSHException("Channel closed")
        def get_transport(c): return T()

    r = Runner({"ip": "x", "ssh_port": 22, "ssh_user": "root", "auth_type": "password", "secret_enc": None})
    r.client = Client()
    assert r.write_chunks("/tmp/x y", iter([b"ab", b"cd"])) == 4
    assert chans[0].sent == b"abcd" and "cat >" in chans[0].cmd and "/tmp/x y" in chans[0].cmd
    assert b"".join(r.read_chunks("/tmp/f", sudo=True, size=4)) == b"hello world" and chans[1].cmd == "cat /tmp/f"
