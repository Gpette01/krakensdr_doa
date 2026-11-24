# The real SignalProcessor.run() loop on synthetic frames.
from pathlib import Path

from helpers import synth
from helpers.dsp import Case, run_cases


def test_run_loop_finds_a_single_uca_source(make_sp, sp_paths):
    case = Case("UCA/MUSIC/123deg", "UCA", "MUSIC", [(123, 0, synth.F_OFF)])

    (result,) = run_cases(make_sp, [case])

    assert result.usable_estimate() == 123.0, result.describe()
    for key in ("iq_header", "doa_thetas", "DoA Result", "DoA Max", "DoA Confidence", "DoA Squelch", "update_rate"):
        assert key in result.packet
    share = Path(sp_paths) / "_share"
    csv_line = (share / "DOA_value.html").read_text()
    # Kraken App CSV: field 2 is 360 - theta (kraken_sdr_signal_processor.py:759)
    assert float(csv_line.split(",")[1]) == 360 - 123
    assert "<DOA>123.0</DOA>" in (share / "doa.xml").read_text()
