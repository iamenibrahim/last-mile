from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.scenarios import replay_scenarios


if __name__ == "__main__":
    result = replay_scenarios()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["failed"] == 0 else 1)
