# M2-03 (P-15, T-05): after a start with no settings callback, the DSP must use the real UCA geometry. Startup
# converted the radius to a chord with the DSP channel count, which is 4 until the first frame, and the DSP turned
# that chord back into a radius with 5 channels: 1.2 times too large, and MUSIC confidence fell from 25.4 to 8.5.
import json

import pytest
from helpers import synth
from helpers.dsp import Case, run_cases
from ui import sandbox

M5_SPACING_WAVELENGTHS = 0.342810  # chord of a 5-element UCA, radius 0.21 m, at 416.588 MHz (300 m*MHz shortcut)


@pytest.fixture(scope="module")
def startup(tmp_path_factory):
    line, _ = sandbox.run_probe(tmp_path_factory.mktemp("headless"), "startup_state")
    return json.loads(line)


def test_startup_spacing_is_the_five_channel_value(startup):
    assert startup["dsp_alignment"] == "UCA"
    assert startup["dsp_geometry"]["DOA_inter_elem_space"] == pytest.approx(M5_SPACING_WAVELENGTHS, abs=5e-7)


def test_headless_start_gives_the_five_channel_scan(startup, make_sp):
    """The DSP settings of a headless start, applied to a 5-channel frame from a 123 degree source."""
    case = Case(
        "headless/UCA/MUSIC/123deg",
        startup["dsp_alignment"],
        "MUSIC",
        [(123, 0, synth.F_OFF)],
        center=int(startup["daq_center_freq"]),
        extra=dict(startup["dsp_geometry"]),
    )
    (result,) = run_cases(make_sp, [case])
    assert result.usable_estimate() == pytest.approx(123, abs=0.5), result.describe()
    confidence = float(result.packet["DoA Confidence"])
    assert confidence == pytest.approx(25.4, abs=1.0), f"confidence {confidence:.2f}. {result.describe()}"
