"""Background jobs: run a function in a thread, stream its log into the DB."""
import threading
import traceback

from . import db

_lock = threading.Lock()


def start(kind, title, fn):
    job_id = db.x("INSERT INTO jobs(kind,title) VALUES(?,?)", (kind, title))

    def log(text):
        with _lock:
            db.x("UPDATE jobs SET log=log||? WHERE id=?", (text, job_id))

    def run():
        try:
            fn(log)
            db.x("UPDATE jobs SET status='done', finished=CURRENT_TIMESTAMP WHERE id=?", (job_id,))
        except Exception as e:
            log(f"\n!!! FAILED: {e}\n")
            if not isinstance(e, (RuntimeError, ValueError)) and e.__class__.__name__ not in ("SSHError", "CPanelError"):
                log(traceback.format_exc())
            db.x("UPDATE jobs SET status='failed', finished=CURRENT_TIMESTAMP WHERE id=?", (job_id,))

    threading.Thread(target=run, daemon=True, name=f"job-{job_id}").start()
    return job_id
