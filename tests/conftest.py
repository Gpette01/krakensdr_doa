# Shared test setup. The environment variables must be set before numba is imported anywhere.
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent

# numba cache=True writes next to the sources unless redirected (kraken_sdr_signal_processor.py:1267).
os.environ.setdefault("NUMBA_CACHE_DIR", str(REPO_ROOT / ".numba_cache"))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
sys.dont_write_bytecode = True

for source_dir in ("_sdr/_signal_processing", "_sdr/_receiver", "_ui/_web_interface"):
    path = str(REPO_ROOT / source_dir)
    if path not in sys.path:
        sys.path.insert(0, path)
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Rewrite the golden files of this environment and print a per-case diff table.",
    )


@pytest.fixture
def sp_paths(tmp_path, monkeypatch):
    """Point every file the SignalProcessor writes at tmp_path.

    These module globals are read when the files are opened (kraken_sdr_signal_processor.py:96-98,228,342,1135).
    """
    import kraken_sdr_signal_processor as ksp

    share = tmp_path / "_share"
    share.mkdir()
    monkeypatch.setattr(ksp, "shared_path", str(share))
    monkeypatch.setattr(ksp, "root_path", str(tmp_path))
    monkeypatch.setattr(ksp, "status_file_path", str(share / "status.json"))
    return tmp_path


@pytest.fixture
def make_sp(sp_paths):
    """Factory for a real SignalProcessor with file output under tmp_path. Cleans up the pool and files."""
    import logging

    import kraken_sdr_signal_processor as ksp

    created = []

    def factory(queue, receiver):
        sp = ksp.SignalProcessor(data_que=queue, module_receiver=receiver, logging_level=logging.WARNING)
        created.append(sp)
        return sp

    yield factory
    for sp in created:
        sp.pool.terminate()
        sp.DOA_res_fd.close()
        sp.data_record_fd.close()
