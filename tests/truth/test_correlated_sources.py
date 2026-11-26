# M2-13 (P-11): "number of correlated sources" (XML NUM_CORRELATED_SOURCES, JSON num_corr_sources) was M minus
# the rank of R, which is 0 for any noisy R, coherent sources included. It is now MDL(smoothed R) - MDL(raw R):
# spatial smoothing separates coherent sources, so the difference counts the sources that were coherent.
# Expected values from the physicist's spec (ULA, 0 dB, 10 trials each).
import logging

import pytest
from helpers import synth
from helpers.dsp import Case, run_cases

F_OFF = synth.F_OFF
TRIALS = range(1, 11)
COHERENT = ((20, F_OFF), (70, F_OFF))  # the same tone from two directions
SCENARIOS = {
    "noise only": ([], 0),
    "one source": ([(65, 0, F_OFF)], 0),
    "two incoherent sources": ([(20, 0, F_OFF), (70, 0, F_OFF + 2000)], 0),
    "two coherent sources": ([(azimuth, 0, f_off) for azimuth, f_off in COHERENT], 1),
    "two coherent sources at -10 dB": ([(azimuth, -10, f_off) for azimuth, f_off in COHERENT], 1),
}
# A fixed threshold far below the noise, so that a noise-only frame is processed too.
OPEN_SQUELCH = {"vfo_default_squelch_mode": "Manual", "vfo_squelch": [-200] * 16, "vfo_squelch_mode": ["Default"] * 16}


def cases():
    return [
        Case(f"{scenario}/seed{seed}", "ULA", "MUSIC", sources, seed=seed, expected_sources=1, extra=OPEN_SQUELCH)
        for scenario, (sources, _) in SCENARIOS.items()
        for seed in TRIALS
    ]


@pytest.fixture(scope="module")
def counts(make_sp_module):
    """{label: the count written to doa.xml}."""
    written = {}
    all_cases = cases()

    def prepare(sp, receiver):
        original_wr_xml = sp.wr_xml

        def recording_wr_xml(*args):
            original_wr_xml(*args)
            written[all_cases[receiver.next_index - 1].label] = args[10]

        sp.wr_xml = recording_wr_xml

    results = run_cases(make_sp_module, all_cases, prepare=prepare)
    for result in results:
        assert not result.errors, result.describe()
    return written


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_correlated_source_count(counts, scenario):
    expected = SCENARIOS[scenario][1]
    got = [counts.get(f"{scenario}/seed{seed}") for seed in TRIALS]
    assert got == [expected] * len(TRIALS)


def test_an_overestimated_source_count_is_reported(make_sp, caplog):
    """N-02: more expected sources than the MDL estimate can move the bearing; the log names both numbers."""
    case = Case("one source, 3 expected", "ULA", "MUSIC", [(65, 0, F_OFF)], expected_sources=3)
    with caplog.at_level(logging.WARNING):
        run_cases(make_sp, [case, case])
    lines = [record.getMessage() for record in caplog.records if "MDL" in record.getMessage()]
    assert len(lines) == 1, lines  # rate-limited: two frames, one line
    assert "3" in lines[0] and "estimates 1" in lines[0]
