# Stubs that let the real SignalProcessor.run() process synthetic frames with no DAQ.
import copy
import logging
import time

from helpers import synth


class StopFrames(BaseException):
    """Raised by the stub receiver after the last frame, to end the otherwise endless run() loop.

    A BaseException, like KeyboardInterrupt: run() keeps going after any Exception in a frame (finding D-10).
    """


class ListQueue:
    """Replaces queue.Queue(1), which drops packets silently when full (kraken_sdr_signal_processor.py:922-928).

    Packets are kept as the DSP puts them, so objects it shares across frames stay shared, as in the real UI
    (finding T-14: every packet carries the same live IQ header).
    """

    def __init__(self):
        self.items = []

    def put(self, item, block=True):
        self.items.append(item)


class FrozenPacketQueue(ListQueue):
    """A ListQueue that copies each packet when it is put.

    Only for tests that read the packets after the whole run, such as the golden and contract tests: the next
    frame changes some packet objects in place ("DoA Max List", the IQ header), while the real UI reads each packet
    before the next frame arrives.
    """

    def put(self, item, block=True):
        self.items.append(copy.deepcopy(item))


class ErrorCapture(logging.Handler):
    """Collects ERROR records from every logger, tagged with the frame index being processed.

    The DSP catches every exception of the DoA block and only logs it (kraken_sdr_signal_processor.py:733-735),
    so a logged error is the only sign that a frame lost its result.
    """

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.current_frame = -1
        self.records = []

    def emit(self, record):
        message = record.getMessage()
        if record.exc_info:
            # logger.exception() keeps the traceback out of the message.
            message += "\n" + logging.Formatter().formatException(record.exc_info)
        self.records.append((self.current_frame, message))

    def for_frame(self, index):
        return [message for frame, message in self.records if frame == index]


class StubReceiver:
    """Stands in for ReceiverRTLSDR. Each call hands out the next case as a DATA frame."""

    def __init__(self, cases, n, apply_case, error_capture):
        from iq_header import IQHeader

        self.cases = cases
        self.n = n
        self.apply_case = apply_case
        self.error_capture = error_capture
        self.daq_center_freq = synth.CENTER
        self.iq_header = IQHeader()
        self.iq_samples = None
        self.M = synth.M
        self.next_index = 0
        self._frame_key = None

    def get_iq_online(self):
        from iq_header import IQHeader

        index = self.next_index
        self.next_index += 1
        if index >= len(self.cases):
            raise StopFrames()
        case = self.cases[index]
        self.error_capture.current_frame = index
        self.apply_case(case)
        self.daq_center_freq = case.center
        if case.frame_key() != self._frame_key:
            self._frame_key = case.frame_key()
            self.iq_samples = case.make_frame(self.n)
        header = self.iq_header
        header.sync_word = IQHeader.SYNC_WORD
        header.frame_type = IQHeader.FRAME_TYPE_DATA
        header.active_ant_chs = synth.M
        header.sampling_freq = synth.FS
        header.adc_sampling_freq = synth.FS
        header.rf_center_freq = case.center
        header.cpi_length = self.n
        header.cpi_index = index
        header.time_stamp = int(time.time() * 1000)
        header.delay_sync_flag = 1
        header.iq_sync_flag = 1
        return 0
