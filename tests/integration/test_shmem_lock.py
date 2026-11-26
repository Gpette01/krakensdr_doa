# Follow-up 2 to M0-06: two concurrent test runs used to collide on the fixed shared memory names and time out after
# 150 s. The integration module must skip with a clear reason while another run holds the lock.
import os
import subprocess
import sys
import time

from conftest import REPO_ROOT
from integration.shmem_lock import LOCK_PATH

HOLD_LOCK = f"""
import fcntl, sys, time
handle = open({str(LOCK_PATH)!r}, "a")
fcntl.flock(handle, fcntl.LOCK_EX)
print("locked", flush=True)
time.sleep(120)
"""


def test_integration_module_skips_while_another_run_holds_the_lock():
    holder = subprocess.Popen([sys.executable, "-c", HOLD_LOCK], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "locked"
        started = time.monotonic()
        inner = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-rs",
                "-p",
                "no:cacheprovider",
                "tests/integration/test_shmem_pipeline.py",
            ],
            cwd=REPO_ROOT,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        holder.kill()
        holder.wait(timeout=10)
    output = inner.stdout + inner.stderr
    assert "another test run is using the DAQ shared memory names" in output, output[-2000:]
    assert " passed" not in output and " failed" not in output, output[-2000:]
    assert time.monotonic() - started < 60
