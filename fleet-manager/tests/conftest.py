import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

os.environ["FLEET_DATA_DIR"] = tempfile.mkdtemp(prefix="fleet-test-")
os.environ["FLEET_NO_BACKGROUND"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from fleetmanager import db, main, provision, ssh


class FakeRunner:
    """Pretends to be a configured VPS with erpnext installed and one existing site."""
    calls = []
    apps = ["erpnext"]
    sites = ["old.example.com"]
    redis_down = 0   # number of redis probes that fail
    backups, offsite, written, relayed = {}, {}, {}, []
    backup_fail = offsite_fail = restore_fail = False
    tick = 0
    leftover = None  # None: no dir; 'failed': dir without site_config.json; 'real': working site

    def __init__(self, server, log=None):
        self.s, self.log = server, log or (lambda t: None)

    def __enter__(self): return self
    def __exit__(self, *a): pass
    def close(self): pass
    def connect(self): return self
    def write_file(self, path, content, mode=0o644):
        FakeRunner.calls.append(("write", path)); FakeRunner.written[path] = (content, mode)

    def sftp(self):
        class F:
            def __init__(f, path, mode): f.path, f.mode, f.done = path, mode, False
            def __enter__(f): return f
            def __exit__(f, *a): pass
            def read(f, n):
                if f.done or "b" not in f.mode or "w" in f.mode: return b""
                f.done = True; return b"data:" + f.path.encode()
            def write(f, data): FakeRunner.relayed.append((f.path, len(data)))
        class S:
            def open(s, path, mode="r"): return F(path, mode)
            def close(s): pass
        return S()

    def write_chunks(self, path, chunks):
        n = sum(len(c) for c in chunks)
        FakeRunner.relayed.append((path, n)); return n

    def read_chunks(self, path, sudo=False, size=262144):
        yield b"data:" + path.encode()

    def file_size(self, path): return 123

    def _files(self, dom):
        return FakeRunner.backups.setdefault(dom, [{"name": "20261018_100000-x-files.tar", "size": 4096, "mtime": 1792317601},
                                                   {"name": "20261018_100000-x_database.sql.gz", "size": 2048, "mtime": 1792317600}])

    def _rclone(self, cmd):
        if "command -v rclone" in cmd: return 0, ""
        if "rclone obscure" in cmd: return 0, "OBSCURED\n"
        if "rcat" in cmd: return (1, "AccessDenied") if FakeRunner.offsite_fail else (0, "")
        tok = shlex.split(cmd); sub = tok[3]
        if sub == "lsjson":
            dom = tok[4].rsplit("/", 1)[1]
            if dom not in FakeRunner.offsite: return 3, "directory not found"
            return 0, json.dumps([{"Name": f["name"], "Size": f["size"], "ModTime": "2027-01-01T00:00:00Z", "IsDir": False} for f in FakeRunner.offsite[dom]])
        if sub == "copyto":
            a, b = tok[4], tok[5]
            if FakeRunner.offsite_fail: return 1, "AccessDenied"
            if b.startswith("fm:"):
                dom, name = b.split("/")[-2:]
                src = next(f for f in FakeRunner.backups.get(dom, []) if f["name"] == name)
                FakeRunner.offsite.setdefault(dom, []).append(dict(src))
            else:
                dom, name = a.split("/")[-2:]
                self._files(dom).append(dict(next(f for f in FakeRunner.offsite[dom] if f["name"] == name)))
            return 0, ""
        if sub == "deletefile":
            dom, name = tok[4].split("/")[-2:]
            FakeRunner.offsite[dom] = [f for f in FakeRunner.offsite.get(dom, []) if f["name"] != name]
            return 0, ""
        return 0, ""

    def run(self, cmd, sudo=False, as_user=None, check=False, stream=True, timeout=0):
        FakeRunner.calls.append(("run", cmd, self.s.get("name")))
        out = ""
        dom = (re.search(r"sites/([A-Za-z0-9.\-]+)/private/backups", cmd) or [None, None])[1]
        if "rm -f --" in cmd and dom:
            names = set(shlex.split(cmd.split("rm -f --")[1]))
            FakeRunner.backups[dom] = [f for f in self._files(dom) if f["name"] not in names]
            return 0, ""
        if "for f in *" in cmd and dom:
            return 0, "".join(f"{f['name']}|{f['size']}|{f['mtime']}\n" for f in self._files(dom)) + "bad name|1|2\n"
        if "backup --with-files" in cmd:
            if FakeRunner.backup_fail: return 1, "disk full"
            FakeRunner.tick += 1
            d = re.search(r"--site (\S+)", cmd)[1].strip("'")
            ts = f"20270101_{FakeRunner.tick:06d}"; u = d.replace(".", "_")
            self._files(d).extend({"name": f"{ts}-{u}{suf}", "size": sz, "mtime": 1800000000 + FakeRunner.tick} for suf, sz in (("-database.sql.gz", 1000), ("-files.tar", 2000), ("-private-files.tar", 3000)))
            return 0, ""
        if cmd.startswith("rclone --config") or " | rclone " in cmd or "command -v rclone" in cmd:
            return self._rclone(cmd)
        if " restore " in cmd and "--force" in cmd:
            return (1, "restore boom") if FakeRunner.restore_fail else (0, "")
        if cmd.startswith("tail -n") or " tail -n " in cmd:
            return 0, "2026-10-18 error line one\n2026-10-18 error line two\n"
        if "/dev/tcp/127.0.0.1/" in cmd:
            if FakeRunner.redis_down > 0:
                FakeRunner.redis_down -= 1
                return 1, ""
            return 0, ""
        if cmd.startswith("test -d"):
            return (0 if FakeRunner.leftover is not None else 1), ""
        if cmd.startswith("test -f"):
            return (0 if FakeRunner.leftover == "real" else 1), ""
        if "/proc/loadavg" in cmd:
            out = "LOAD 0.30\nCORES 2\nMEM 4000 1200\nDISK 35\nOS Ubuntu 22.04 LTS\n"
        elif cmd.startswith("ls -1") and "/apps" in cmd:
            out = "\n".join(["frappe"] + FakeRunner.apps)
        elif "site_config.json" in cmd:
            out = "\n".join(FakeRunner.sites)
        elif "bench version" in cmd:
            out = "frappe 15.1.0\n" + "".join(f"{a} 15.2.0\n" for a in FakeRunner.apps)
        elif "for a in apps/*/" in cmd:
            out = "frappe|version-15|abc1234|0\n" + "".join(f"{a}|version-15|def5678|{3 if a == 'erpnext' else 0}\n" for a in FakeRunner.apps)
        elif "bench new-app" in cmd:
            n = cmd.split("bench new-app ")[1].split()[0].strip("'")
            if n not in FakeRunner.apps:
                FakeRunner.apps.append(n)
        elif "uninstall-app" in cmd:
            n = shlex.split(cmd.split("uninstall-app ")[1])[0]
            if n in FakeRunner.site_installed: FakeRunner.site_installed.remove(n)
            FakeRunner.site_uninstalled.append(n)
        elif "bench remove-app" in cmd:
            n = shlex.split(cmd.split("remove-app ")[1])[0]
            if n in FakeRunner.apps: FakeRunner.apps.remove(n)
        elif "install-app" in cmd:
            n = shlex.split(cmd.split("install-app ")[1])[0]
            FakeRunner.site_installed.append(n)
        elif "list-apps" in cmd:
            out = "frappe 15.0\nerpnext 15.0\n" + "".join(f"{a} 15.0\n" for a in FakeRunner.site_installed)
        elif "frappe.get_all" in cmd:
            out = "['Old Co']\n" if "--site old.example.com" in cmd else "[]\n"   # no Company until setup wizard
        elif "ls-remote --symref" in cmd:
            out = "ref: refs/heads/main\tHEAD\nabc\tHEAD\n"
        elif "get-app" in cmd and FakeRunner.no_branch and "--branch version-" in cmd:
            return 1, "Remote branch version-15 not found"
        elif "get-app" in cmd:
            name = cmd.split("/")[-1].split()[0].replace("'", "")
            if name not in FakeRunner.apps:
                FakeRunner.apps.append(name)
        elif "drop-site" in cmd:
            d = cmd.split("drop-site ")[1].split()[0]
            if d in FakeRunner.sites:
                FakeRunner.sites.remove(d)
            if FakeRunner.drop_exit:
                return FakeRunner.drop_exit, ""
        elif "bench new-site" in cmd:
            d = cmd.split("new-site ")[1].split()[0]
            FakeRunner.sites.append(d)
        if stream and out:
            self.log(out)
        return 0, out


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def fake_ssh(monkeypatch):
    FakeRunner.calls, FakeRunner.apps, FakeRunner.sites = [], ["erpnext"], ["old.example.com"]
    FakeRunner.leftover = None
    FakeRunner.redis_down = 0
    FakeRunner.backups, FakeRunner.offsite, FakeRunner.written, FakeRunner.relayed = {}, {}, {}, []
    FakeRunner.backup_fail = FakeRunner.offsite_fail = FakeRunner.restore_fail = False
    FakeRunner.tick = 0
    FakeRunner.site_installed = []
    FakeRunner.no_branch = False
    FakeRunner.drop_exit = 0
    FakeRunner.site_uninstalled = []
    monkeypatch.setattr(ssh, "Runner", FakeRunner)
    monkeypatch.setattr(provision.ssh, "Runner", FakeRunner)
    monkeypatch.setattr(main.ssh, "Runner", FakeRunner)
