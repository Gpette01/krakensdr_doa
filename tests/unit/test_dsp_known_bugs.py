# Unit-level truth tests for DSP helpers with known bugs (strict xfails name their findings).
import json
import math
import os
import subprocess
import sys

import pytest
from conftest import REPO_ROOT


@pytest.mark.parametrize(
    "sample_rate, cpi, vfo_bw",
    [
        (2_400_000, 2**16, 12_500),
        (2_400_000, 2**18, 12_500),
        (2_400_000, 2**20, 6_250),
        (1_024_000, 2**18, 12_500),
        (2_048_000, 2**16, 12_500),  # failed before M1-03 (P-10, T-04)
        (1_920_000, 2**16, 12_500),  # failed before M1-03 (P-10, T-04)
    ],
)
def test_mixing_exponential_has_the_requested_length(sample_rate, cpi, vfo_bw):
    """channelize() mixes with get_exponential(f, fs/q, L) and needs exactly L samples (sp:1323-1331)."""
    import kraken_sdr_signal_processor as ksp

    decimation = int(sample_rate // vfo_bw)
    length = math.ceil(cpi / decimation)
    assert len(ksp.get_exponential(1234.0, sample_rate / decimation, length)) == length


BOUNDS_PROBE = """
import json, sys
import numpy as np
import kraken_sdr_signal_processor as ksp
out = {}
for count in (4, 5, 6):
    x = np.linspace(0.1, 0.5, count)
    y = np.linspace(0.0, 0.4, count)
    try:
        out[count] = list(ksp.gen_scanning_vectors_custom(5, x, y).shape)
    except Exception as error:
        out[count] = f"{type(error).__name__}: {error}"
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def custom_array_bounds_probe(tmp_path_factory):
    """Runs gen_scanning_vectors_custom with NUMBA_BOUNDSCHECK=1 in a fresh process.

    The flag must be set before numba compiles, and a bounds-checked build must not share the normal cache.
    """
    env = dict(os.environ)
    env["NUMBA_BOUNDSCHECK"] = "1"
    env["NUMBA_CACHE_DIR"] = str(tmp_path_factory.mktemp("numba_boundscheck"))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        str(REPO_ROOT / d) for d in ("_sdr/_signal_processing", "_sdr/_receiver", "_ui/_web_interface")
    )
    completed = subprocess.run(
        [sys.executable, "-W", "ignore", "-c", BOUNDS_PROBE],
        env=env,
        cwd=str(tmp_path_factory.mktemp("cwd")),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode != 0:
        # Not an AssertionError, so that a broken probe can never count as an expected failure.
        raise RuntimeError(completed.stderr[-2000:])
    return json.loads(completed.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    "coordinate_count",
    [4, 5, pytest.param(6, marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason="P-22, T-08"))],
)
def test_custom_array_with_any_coordinate_count_stays_in_bounds(custom_array_bounds_probe, coordinate_count):
    """5 channels with 4, 5 or 6 coordinates: no write past the end of the 5-row buffer (sp:1654-1668)."""
    assert custom_array_bounds_probe[str(coordinate_count)] == [5, 360]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P-24")
def test_each_vfo_has_its_own_theta_list(make_sp):
    """[[]] * 16 creates one list shared by all VFOs (sp:163, 176)."""

    class Receiver:
        daq_center_freq = 416_588_000

    sp = make_sp(None, Receiver())
    sp.vfo_theta_channel[0].append(123.0)
    sp.fm_demod_channels_thetas[0].append(123.0)
    assert sp.vfo_theta_channel[1] == []
    assert sp.fm_demod_channels_thetas[1] == []
