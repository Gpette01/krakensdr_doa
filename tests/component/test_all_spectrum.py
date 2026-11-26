# M2-06 (P-19): the "All" spectrum mode (32768 bins per channel) looked only at the first 32768 samples of the
# frame, so a burst later in the frame was invisible to the squelch. It now averages Welch segments over the
# whole frame, on the same scale (a bin-centred unit tone reads 0 dB).
from dataclasses import dataclass

import numpy as np
import pytest
from helpers import synth
from helpers.dsp import Case, run_cases

BINS = 32768
FRAME = 2**18
BURST_BIN = 1000
BURST_START, BURST_LENGTH = 100_000, 5000


def bin_tone(bin_index, n):
    """Unit complex tone on the centre of a bin of the fftshifted 32768-bin axis."""
    frequency = -synth.FS / 2 + bin_index * synth.FS / BINS
    return np.exp(2j * np.pi * frequency * np.arange(n) / synth.FS)


@dataclass
class ToneCase(Case):
    """The same noise-free tone on every channel, on samples [start, start + length)."""

    start: int = 0
    length: int = FRAME

    def frame_key(self):
        return (self.label,)

    def make_frame(self, n):
        tone = np.zeros(n, dtype=np.complex128)
        tone[self.start : self.start + self.length] = bin_tone(BURST_BIN, n)[self.start : self.start + self.length]
        return np.ascontiguousarray(np.tile(tone, (synth.M, 1)).astype(np.complex64))


def channel_spectrum(make_sp, case):
    holder = []
    run_cases(make_sp, [case], n=FRAME, prepare=lambda sp, receiver: holder.append(sp))
    return holder[0].spectrum[1]


def all_mode_case(label, **kwargs):
    return ToneCase(label, "UCA", "MUSIC", [], extra={"spectrum_fig_type": "All"}, **kwargs)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")  # log10 of the empty bins of a noise-free frame
def test_a_late_burst_is_seen(make_sp):
    spectrum = channel_spectrum(make_sp, all_mode_case("late burst", start=BURST_START, length=BURST_LENGTH))
    assert spectrum[BURST_BIN] == pytest.approx(-39.36, abs=0.01)
    assert int(np.argmax(spectrum)) == BURST_BIN


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_a_continuous_unit_tone_reads_0_db(make_sp):
    spectrum = channel_spectrum(make_sp, all_mode_case("continuous tone"))
    assert spectrum[BURST_BIN] == pytest.approx(0.0, abs=0.01)
