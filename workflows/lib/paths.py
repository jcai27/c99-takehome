"""Where the scraper (and later the parser) read and write raw payloads.

`DATA_DIR` is set to `/data` for the containerized worker (see
docker-compose.yaml, which bind-mounts ./data there). Falls back to the repo's
`data/` directory for a worker running on the host.
"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))

RUNS_DIR = DATA_DIR / "runs"
LATEST_POINTER = DATA_DIR / "latest.json"


def revision_dir(revision_name: str) -> Path:
    return RUNS_DIR / revision_name
