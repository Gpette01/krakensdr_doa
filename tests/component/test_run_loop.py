# The real SignalProcessor.run() loop on synthetic frames.
import json
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


def test_a_frame_that_raises_does_not_stop_the_loop(make_sp, caplog):
    """Finding D-10: an exception outside the DoA block used to end the DSP thread for good."""
    import logging

    from helpers.stubs import ErrorCapture, ListQueue, StopFrames, StubReceiver

    cases = [Case(f"UCA/MUSIC/123deg/{i}", "UCA", "MUSIC", [(123, 0, synth.F_OFF)]) for i in range(3)]
    sp_holder = []

    def apply_case(case):
        for name, value in case.sp_settings().items():
            setattr(sp_holder[0], name, value)
        sp_holder[0].vfo_freq[0] = case.center + synth.F_OFF

    class FlakyReceiver(StubReceiver):
        failures = 0

        def get_iq_online(self):
            if self.next_index == 1 and self.failures == 0:
                self.failures += 1
                raise RuntimeError("stub receiver failure")
            return super().get_iq_online()

    receiver = FlakyReceiver(cases, 2**16, apply_case, ErrorCapture())
    queue = ListQueue()
    sp = make_sp(queue, receiver)
    sp_holder.append(sp)
    with caplog.at_level(logging.ERROR):
        try:
            sp.run()
        except StopFrames:
            pass
    assert [float(dict(packet)["DoA Max"]) for packet in queue.items] == [123.0, 123.0, 123.0]
    failures = [r for r in caplog.records if r.exc_info and "stub receiver failure" in str(r.exc_info[1])]
    assert len(failures) == 1
    assert sp.is_running is False


class RaisingReceiver:
    """A receiver whose frames always fail: `failures` times with RuntimeError, then with `final`."""

    def __init__(self, failures, final):
        from iq_header import IQHeader

        self.daq_center_freq = synth.CENTER
        self.iq_header = IQHeader()
        self.failures = failures
        self.final = final

    def get_iq_online(self):
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("receiver broken")
        raise self.final


def test_status_json_is_refreshed_while_frames_fail(make_sp, sp_paths):
    """Follow-up to M1-09: status.json used to be written only after a frame was acquired."""
    from helpers.stubs import ListQueue, StopFrames

    status_file = sp_paths / "_share" / "status.json"
    sp = make_sp(ListQueue(), RaisingReceiver(failures=1, final=StopFrames()))
    try:
        sp.run()
    except StopFrames:
        pass
    assert status_file.exists()
    assert json.loads(status_file.read_text())["daq_ok"] is False


def test_the_end_of_the_dsp_loop_is_logged(make_sp, caplog):
    """Follow-up to M1-09: a BaseException such as SystemExit ended the DSP thread without a log line."""
    import logging

    from helpers.stubs import ListQueue

    sp = make_sp(ListQueue(), RaisingReceiver(failures=0, final=SystemExit(3)))
    with caplog.at_level(logging.ERROR):
        try:
            sp.run()
        except SystemExit:
            pass
    stopped = [r for r in caplog.records if r.levelno >= logging.ERROR and "SystemExit" in r.getMessage()]
    assert len(stopped) == 1, [r.getMessage() for r in caplog.records]
