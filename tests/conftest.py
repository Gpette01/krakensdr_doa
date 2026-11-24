# Shared test setup. The environment variables must be set before numba is imported anywhere.
import contextlib
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


def _point_sp_files_at(directory, monkeypatch):
    """Point every file the SignalProcessor writes at directory.

    These module globals are read when the files are opened (kraken_sdr_signal_processor.py:96-98,228,342,1135).
    """
    import kraken_sdr_signal_processor as ksp

    share = Path(directory) / "_share"
    share.mkdir()
    monkeypatch.setattr(ksp, "shared_path", str(share))
    monkeypatch.setattr(ksp, "root_path", str(directory))
    monkeypatch.setattr(ksp, "status_file_path", str(share / "status.json"))


@contextlib.contextmanager
def _sp_factory():
    """Yields a factory for real SignalProcessor objects, and cleans up their pools and files afterwards."""
    import logging

    import kraken_sdr_signal_processor as ksp

    created = []

    def factory(queue, receiver):
        sp = ksp.SignalProcessor(data_que=queue, module_receiver=receiver, logging_level=logging.WARNING)
        created.append(sp)
        return sp

    try:
        yield factory
    finally:
        for sp in created:
            sp.pool.terminate()
            sp.DOA_res_fd.close()
            sp.data_record_fd.close()


@pytest.fixture
def sp_paths(tmp_path, monkeypatch):
    """tmp_path, with the SignalProcessor file output redirected into tmp_path/_share."""
    _point_sp_files_at(tmp_path, monkeypatch)
    return tmp_path


@pytest.fixture
def make_sp(sp_paths):
    """Factory for a real SignalProcessor with file output under tmp_path."""
    with _sp_factory() as factory:
        yield factory


@pytest.fixture(scope="module")
def make_sp_module(tmp_path_factory):
    """Module-scoped make_sp, so that one run() can process the frames of many tests."""
    directory = tmp_path_factory.mktemp("sp_module")
    with pytest.MonkeyPatch.context() as monkeypatch:
        _point_sp_files_at(directory, monkeypatch)
        with _sp_factory() as factory:
            yield factory


def _repository_write_marks():
    """Existence and mtime of what a test could write into the checkout by mistake.

    SignalProcessor writes <root>/_share/* and <root>/mydata.csv (kraken_sdr_signal_processor.py:97-98,228-229), the
    UI writes <root>/_share/settings.json (kraken_web_interface.py:353-354), and imports can leave __pycache__.
    """
    marks = {}
    candidates = [REPO_ROOT / "_share", REPO_ROOT / "mydata.csv"]
    candidates += list((REPO_ROOT / "_share").rglob("*")) if (REPO_ROOT / "_share").is_dir() else []
    for source_dir in ("_sdr", "_ui"):
        candidates += list((REPO_ROOT / source_dir).rglob("__pycache__"))
    for path in candidates:
        marks[str(path.relative_to(REPO_ROOT))] = path.stat().st_mtime_ns if path.exists() else None
    return marks


@pytest.fixture(scope="session", autouse=True)
def repository_is_not_written():
    """Fails the session (as a teardown error) when any test wrote into the checkout."""
    before = _repository_write_marks()
    yield
    after = _repository_write_marks()
    changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    assert not changed, f"tests wrote into the repository: {changed}"
