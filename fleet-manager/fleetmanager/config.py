import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("FLEET_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = DATA_DIR / "fleet.db"
KEY_PATH = DATA_DIR / "secret.key"          # Fernet key for stored credentials
SSH_KEY_PATH = DATA_DIR / "manager_ed25519"  # keypair this app uses to reach VPSes
SESSION_HOURS = 12

# Frappe/ERPNext version -> toolchain. Edit here if upstream requirements change.
VERSIONS = {
    "version-14": {"label": "v14", "python": "3.10", "node": 16},
    "version-15": {"label": "v15", "python": "3.11", "node": 18},
    "version-16": {"label": "v16", "python": "3.14", "node": 24},
}
DEFAULT_VERSION = "version-15"

# Server is "busy" above these; used by the recommender.
MAX_LOAD_PER_CORE = 1.5
MAX_MEM_PCT = 90
MAX_DISK_PCT = 90


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
