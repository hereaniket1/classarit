import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
# Set this to a persistent disk mount on hosted deployments.
DATA_DIR = Path(os.environ.get("CLASSARIT_DATA_DIR", str(PROJECT_DIR))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
