import shutil
import subprocess
from pathlib import Path


def test_service_worker_privacy_and_offline_behavior():
    node = shutil.which("node")
    assert node, "Node.js is required for service-worker regression checks"
    result = subprocess.run([node, "--test", "tests/service_worker.cjs"],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
