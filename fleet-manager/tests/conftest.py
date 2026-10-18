import os
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

    def __init__(self, server, log=None):
        self.s, self.log = server, log or (lambda t: None)

    def __enter__(self): return self
    def __exit__(self, *a): pass
    def close(self): pass
    def write_file(self, path, content, mode=0o644): FakeRunner.calls.append(("write", path))

    def run(self, cmd, sudo=False, as_user=None, check=False, stream=True, timeout=0):
        FakeRunner.calls.append(("run", cmd))
        out = ""
        if "/proc/loadavg" in cmd:
            out = "LOAD 0.30\nCORES 2\nMEM 4000 1200\nDISK 35\nOS Ubuntu 22.04 LTS\n"
        elif cmd.startswith("ls -1") and "/apps" in cmd:
            out = "\n".join(["frappe"] + FakeRunner.apps)
        elif "site_config.json" in cmd:
            out = "\n".join(FakeRunner.sites)
        elif "list-apps" in cmd:
            out = "frappe 15.0\nerpnext 15.0\n"
        elif "frappe.get_all" in cmd:
            out = "['Old Co']\n" if "--site old.example.com" in cmd else "[]\n"   # no Company until setup wizard
        elif "get-app" in cmd:
            FakeRunner.apps.append(cmd.split("/")[-1].split()[0].replace("'", ""))
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
    monkeypatch.setattr(ssh, "Runner", FakeRunner)
    monkeypatch.setattr(provision.ssh, "Runner", FakeRunner)
    monkeypatch.setattr(main.ssh, "Runner", FakeRunner)
