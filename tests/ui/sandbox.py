# Builds a throwaway copy of the UI for a subprocess.
#
# The UI derives its paths from __file__ (variables.py:13-60) and has side effects at import time: it writes
# <root>/_share/settings.json, reads ../heimdall_daq_fw/Firmware/daq_chain_config.ini and imports ini_checker from
# there. A copy in a temp dir, with a fake sibling DAQ directory, keeps all of that out of the repository.
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TESTS_DIR.parent
PROBE = Path(__file__).resolve().parent / "ui_probe.py"

INI_CHECKER_STUB = """# Test stub for the Heimdall module. The real check needs the DAQ source, which is not in this repo.
def check_ini(parameters, en_hw_check=0):
    return []
"""


def build(tmp_path, with_daq_ini=True, daq_ini_text=None):
    root = tmp_path / "krakensdr_doa"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for part in ("_ui", "_sdr"):
        shutil.copytree(REPO_ROOT / part, root / part, ignore=ignore)
    (root / "_share").mkdir()
    firmware = tmp_path / "heimdall_daq_fw" / "Firmware"
    firmware.mkdir(parents=True)
    if daq_ini_text is not None:
        (firmware / "daq_chain_config.ini").write_text(daq_ini_text)
    elif with_daq_ini:
        shutil.copy(TESTS_DIR / "data" / "daq_chain_config.ini", firmware / "daq_chain_config.ini")
    (firmware / "ini_checker.py").write_text(INI_CHECKER_STUB)
    presets = tmp_path / "heimdall_daq_fw" / "config_files" / "test_preset"
    presets.mkdir(parents=True)
    shutil.copy(TESTS_DIR / "data" / "daq_chain_config.ini", presets / "daq_chain_config.ini")
    work = tmp_path / "work"
    work.mkdir()
    return root, work


def free_port():
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        return probe_socket.getsockname()[1]


def run_probe(tmp_path, mode, *args, timeout=120, with_daq_ini=True, daq_ini_text=None):
    """Runs ui_probe.py in the sandbox and returns its last stdout line (JSON) and the full output."""
    root, work = build(tmp_path, with_daq_ini, daq_ini_text)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.setdefault("NUMBA_CACHE_DIR", str(REPO_ROOT / ".numba_cache"))
    completed = subprocess.run(
        [sys.executable, "-W", "ignore", str(PROBE), str(root / "_ui" / "_web_interface"), mode, *map(str, args)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        # Not an AssertionError, so that a broken sandbox can never count as an expected failure.
        raise RuntimeError(output[-3000:])
    return completed.stdout.strip().splitlines()[-1], output
