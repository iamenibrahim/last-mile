"""Last-Mile Navigator API package."""

import os
import sys
from pathlib import Path


def _load_dotenv() -> None:
    """Read KEY=VALUE lines from the repo's .env into the environment.

    Real environment variables win. Skipped under pytest so the test suite never
    reaches live Azure services with a developer's keys.
    """
    path = Path(__file__).resolve().parents[1] / ".env"
    if "pytest" in sys.modules or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()
