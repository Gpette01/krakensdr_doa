# One test run at a time may use the fixed shared memory names delay_sync_iq_A/_B (follow-up 2 to M0-06).
import fcntl
import os
import tempfile
from pathlib import Path

LOCK_PATH = Path(tempfile.gettempdir()) / "krakensdr_doa_tests_shmem.lock"


def try_lock():
    """An open file holding the lock, or None when another process holds it."""
    handle = open(LOCK_PATH, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle
