# M2-10: the channel of a VFO carries its mixer phase, FM filter state and last sample from frame to frame, and
# starts over when the frequency, bandwidth or rate changes, or when a DAQ frame was skipped.
from types import SimpleNamespace

import numpy as np
import pytest

FS = 2_400_000
FRAME = 2**16
FREQ = 100_000.0
RATE = 48_000.0


@pytest.fixture
def sp(make_sp):
    header = SimpleNamespace(cpi_index=0, cpi_length=FRAME, sampling_freq=FS)
    receiver = SimpleNamespace(daq_center_freq=416_588_000, iq_header=header)
    return make_sp(None, receiver)


def frame(sp, cpi_index, freq=FREQ, rate=RATE):
    sp.module_receiver.iq_header.cpi_index = cpi_index
    channel = np.ones(16, dtype=np.complex64)
    out = sp.continue_vfo_stream(0, channel, freq, rate)
    assert out.dtype == np.complex64  # the IQ recording keeps its sample format
    return out


def test_consecutive_frames_continue_the_phase(sp):
    frame(sp, 7)
    stream = sp.vfo_streams[0]
    stream.filter_state = "kept"
    cycles = (FREQ * FRAME / FS) % 1.0
    assert stream.mixer_cycles == pytest.approx(cycles)
    out = frame(sp, 8)
    assert out[0] == pytest.approx(np.exp(-2j * np.pi * cycles), abs=1e-6)
    assert stream.filter_state == "kept"


@pytest.mark.parametrize(
    "change",
    [
        {"cpi_index": 9},  # frame 8 was skipped
        {"freq": FREQ + 1000},
        {"rate": 50_000.0},
    ],
)
def test_changes_start_over(sp, change):
    frame(sp, 7)
    sp.vfo_streams[0].filter_state = "old"
    frame(sp, change.get("cpi_index", 8), change.get("freq", FREQ), change.get("rate", RATE))
    assert sp.vfo_streams[0].filter_state is None


def test_bandwidth_change_starts_over(sp):
    frame(sp, 7)
    sp.vfo_streams[0].filter_state = "old"
    sp.vfo_bw[0] = 6250
    frame(sp, 8)
    assert sp.vfo_streams[0].filter_state is None
