# The Auto squelch (kraken_sdr_signal_processor.py:261-273, 583-588): threshold = mean of the measured spectrum
# in dB + 5 dB, compared with the strongest bin inside the VFO.
import numpy as np
import pytest
from helpers import synth
from helpers.dsp import Case, run_cases

AUTO_SQUELCH_OFFSET_DB = 5
MARGIN_DB = 2  # distance of the test tone's peak bin from the threshold
BIN_HZ = synth.FS / 4096  # Welch bin width (spectrum_window_size 4096)
TONE_OFFSET_HZ = round(synth.F_OFF / BIN_HZ) * BIN_HZ  # on a bin centre, so the peak bin holds the tone power


def run_one(make_sp, case):
    holder = []
    (result,) = run_cases(make_sp, [case], prepare=lambda sp, receiver: holder.append(sp))
    return result, holder[0]


@pytest.fixture(scope="module")
def noise_threshold_db(make_sp_module):
    """The Auto threshold for a noise-only frame (no source)."""
    _, sp = run_one(make_sp_module, Case("noise only", "UCA", "MUSIC", [], seed=5))
    return float(sp.vfo_squelch[0])


def test_auto_threshold_is_mean_spectrum_plus_5_db(make_sp):
    _, sp = run_one(make_sp, Case("UCA/MUSIC/123deg", "UCA", "MUSIC", [(123, 0, synth.F_OFF)], seed=5))
    assert sp.vfo_squelch_mode[0] == "Auto"
    assert sp.vfo_squelch[0] == pytest.approx(np.mean(sp.spectrum[1]) + AUTO_SQUELCH_OFFSET_DB, abs=1e-4)


@pytest.mark.parametrize("above, expected_open", [(False, False), (True, True)])
def test_tone_near_the_threshold(make_sp_module, noise_threshold_db, above, expected_open):
    target_peak_db = noise_threshold_db + (MARGIN_DB if above else -MARGIN_DB)
    # The peak bin holds noise plus tone power; the noise per bin is the threshold minus the offset.
    noise_per_bin = 10 ** ((noise_threshold_db - AUTO_SQUELCH_OFFSET_DB) / 10)
    snr_db = 10 * np.log10(10 ** (target_peak_db / 10) - noise_per_bin)
    case = Case(
        f"tone {'above' if above else 'below'} threshold",
        "UCA",
        "MUSIC",
        [(123, snr_db, TONE_OFFSET_HZ)],
        seed=5,
        vfo_offsets=(TONE_OFFSET_HZ,),
    )
    result, sp = run_one(make_sp_module, case)
    peak_db = float(sp.spectrum[1].max())
    threshold_db = float(sp.vfo_squelch[0])
    # The frame really is near the threshold, on the intended side.
    assert 0.5 < abs(peak_db - threshold_db) < 3 and (peak_db > threshold_db) == above, (peak_db, threshold_db)
    assert result.errors == []
    assert list(result.packet["DoA Squelch"][:1]) == [expected_open]
