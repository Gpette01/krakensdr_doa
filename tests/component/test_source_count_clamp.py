# Finding P-09: after spatial smoothing the source count is clamped, with one warning, not one per frame.
import logging

from helpers import synth
from helpers.dsp import Case, run_cases


def test_clamp_is_logged_once(make_sp, caplog):
    cases = [
        Case(
            f"ULA/{algorithm}/FBSS/sources=4/{i}",
            "ULA",
            algorithm,
            [(65, 0, synth.F_OFF)],
            decorrelation="FBSS",
            expected_sources=4,
        )
        for i in range(2)
        for algorithm in ("MUSIC", "ROOT-MUSIC")
    ]
    with caplog.at_level(logging.WARNING, logger="kraken_sdr_signal_processor"):
        results = run_cases(make_sp, cases)
    assert all(result.usable_estimate() is not None for result in results), [r.describe() for r in results]
    clamp_messages = [r.getMessage() for r in caplog.records if "supports at most" in r.getMessage()]
    assert clamp_messages == ["Expected 4 sources, but the 4x4 correlation matrix supports at most 3; using 3."]
