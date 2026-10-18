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
            p = subprocess.Popen(["bash", "-c", command.decode()], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
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
