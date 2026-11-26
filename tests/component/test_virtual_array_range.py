# Finding P-04: the virtual ULA (phase mode) transform for a UCA is only valid for 1 <= L <= (M - 1) // 2,
# with L = floor(2 pi r / lambda). Above that range the whitening inverted a singular matrix and amplified rounding
# noise by about 1e8, so the result depended on the frames processed before. Outside the range the plain UCA is used.
import logging

import numpy as np
import pytest
from helpers import synth
from helpers.dsp import Case, run_cases


def frame_at(center_mhz, decorrelation="FBA", algorithm="MUSIC", label=""):
    return Case(
        f"{label}{center_mhz}MHz/UCA/{algorithm}/{decorrelation}",
        "UCA",
        algorithm,
        [(123, 0, synth.F_OFF)],
        decorrelation=decorrelation,
        center=center_mhz * 1_000_000,
        seed=51,
    )


@pytest.mark.parametrize("center_mhz", [700, 1090])
def test_result_does_not_depend_on_the_previous_frames(make_sp, center_mhz):
    alone = run_cases(make_sp, [frame_at(center_mhz)])[-1]
    after_others = run_cases(
        make_sp, [frame_at(144, "Off", label="a"), frame_at(433, label="b"), frame_at(center_mhz, label="c")]
    )[-1]
    assert alone.errors == [] and after_others.errors == [], (alone.describe(), after_others.describe())
    assert np.array_equal(alone.packet["DoA Result"], after_others.packet["DoA Result"])


@pytest.mark.parametrize("center_mhz", [144, 1090])
@pytest.mark.parametrize("algorithm, decorrelation", [("ROOT-MUSIC", "Off"), ("MUSIC", "FBA"), ("Bartlett", "TOEP")])
def test_outside_the_range_falls_back_to_the_plain_uca_with_one_warning(
    make_sp, caplog, center_mhz, algorithm, decorrelation
):
    """At 144 MHz (L = 0) and 1090 MHz (L = 4 > 2) with r = 0.21 m, the frame still gives a plain UCA result."""
    cases = [frame_at(center_mhz, decorrelation, algorithm, label=f"{i}/") for i in range(2)]
    with caplog.at_level(logging.WARNING, logger="kraken_sdr_signal_processor"):
        results = run_cases(make_sp, cases)
    for result in results:
        assert result.usable_estimate() == 123.0, result.describe()
    warnings = [r.getMessage() for r in caplog.records if "virtual array" in r.getMessage()]
    assert len(warnings) == 1, warnings
