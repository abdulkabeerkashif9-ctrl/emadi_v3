"""Background loop: uptime checks, server health, scheduled backups, certificate and housekeeping tasks."""
import threading
import time
import traceback

from . import backups, db, monitor, provision


class Scheduler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="scheduler")
        now = time.time()
        # start the first rounds soon after launch instead of waiting a full interval
        self.last = {"sites": now - 45, "servers": now - 270, "backups": now - 30, "ssl": now - 86400 + 120, "overdue": now - 3500, "prune": now - 86000, "refresh": now - 3000}
        self.running, self.stop_event, self.lock = set(), threading.Event(), threading.Lock()

    def _go(self, name, every, fn):
        if time.time() - self.last[name] < every:
            return False
        with self.lock:
            if name in self.running:
                return False
            self.running.add(name)
        self.last[name] = time.time()

        def work():
            try:
                fn()
            except Exception:
                traceback.print_exc()
            finally:
                with self.lock:
                    self.running.discard(name)
        threading.Thread(target=work, daemon=True, name=f"task-{name}").start()
        return True

    def tick(self):
        if monitor.settings()["enabled"]:
            self._go("sites", 60, monitor.run_site_checks)
            self._go("servers", 300, monitor.run_server_checks)
            self._go("ssl", 86400, monitor.run_ssl_checks)
            self._go("prune", 86400, monitor.prune)
        self._go("backups", 60, backups.run_due)
        self._go("overdue", 3600, backups.check_overdue)
        self._go("refresh", 3600, self._refresh_servers)

    @staticmethod
    def _refresh_servers():
        for s in db.q("SELECT id FROM servers WHERE status='ready'"):
            try:
                provision.refresh_server(s["id"])
            except Exception:
                pass

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                traceback.print_exc()
            self.stop_event.wait(15)
