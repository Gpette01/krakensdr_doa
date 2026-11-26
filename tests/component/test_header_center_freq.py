# M2-16 (P-27): each frame is processed with the centre frequency in its header. Frames still in flight during a
# retune carry the old frequency while the UI already holds the new one; they used to be channelized at the wrong
# offset, and one such frame moved every VFO outside the band back to the centre.
import pytest
from helpers import synth
from helpers.dsp import Case, run_cases

UI_CENTER = synth.CENTER
HEADER_CENTER = synth.CENTER + 200_000  # the DAQ is tuned here for this frame
IN_BAND_OFFSET = 300_000.0  # VFO 0 relative to the UI centre: 100 kHz above the header centre, on the source
OUT_OF_BAND_OFFSET = -1_250_000.0  # VFO 1: 1.45 MHz below the header centre, outside (2.4 MHz - 12.5 kHz) / 2


@pytest.fixture(scope="module")
def retune_frame(make_sp_module):
    case = Case(
        "retune in flight",
        "UCA",
        "MUSIC",
        [(123, 0, synth.F_OFF)],  # F_OFF above the header centre, where VFO 0 listens
        header_center=HEADER_CENTER,
        vfo_offsets=(IN_BAND_OFFSET, OUT_OF_BAND_OFFSET),
    )
    holder = []
    (result,) = run_cases(make_sp_module, [case], prepare=lambda sp, receiver: holder.append(sp))
    return result, holder[0]


def test_in_band_vfo_gives_the_true_bearing(retune_frame):
    result, _ = retune_frame
    assert not result.errors, result.describe()
    assert result.packet["DoA Squelch"][0], result.describe()
    assert result.packet["DoA Max List"][0] == pytest.approx(123, abs=0.5), result.describe()


def test_out_of_band_vfo_is_skipped_and_keeps_its_frequency(retune_frame):
    result, sp = retune_frame
    assert not result.packet["DoA Squelch"][1]
    assert sp.vfo_freq[1] == UI_CENTER + OUT_OF_BAND_OFFSET
