"""DSP side of the integration test, run as a subprocess: the real ReceiverRTLSDR in shmem mode feeds the real
SignalProcessor. Writes a JSON summary and hard-exits, because the DSP thread never ends on its own.

usage: consumer.py <workdir> <control_port> <frames_expected> <out_json>
"""

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TESTS_DIR.parent
sys.path[:0] = [str(TESTS_DIR)] + [
    str(REPO_ROOT / d) for d in ("_ui/_web_interface", "_sdr/_receiver", "_sdr/_signal_processing")
]

from helpers import synth  # noqa: E402
from helpers.dsp import Case, exception_line  # noqa: E402
from helpers.stubs import ErrorCapture, ListQueue  # noqa: E402

DEADLINE_S = 90
SETTLE_AFTER_TERMINATE_S = 3.0


def main():
    workdir, port, expected, out_json = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]

    import kraken_sdr_signal_processor as ksp
    from kraken_sdr_receiver import ReceiverRTLSDR

    share = workdir / "_share"
    share.mkdir()
    ksp.shared_path, ksp.root_path, ksp.status_file_path = str(share), str(workdir), str(share / "status.json")

    # Built in eth mode so the constructor opens nothing; then switched to shared memory in workdir.
    receiver_queue = ListQueue()
    receiver = ReceiverRTLSDR(data_que=receiver_queue, data_interface="eth", logging_level=logging.WARNING)
    receiver.data_interface = "shmem"
    receiver.daq_shmem_control_path = str(workdir / "_data_control") + "/"
    init_result = receiver.init_data_iface()
    receiver.rec_ip_addr = "127.0.0.1"
    receiver.ctr_iface_port = port
    receiver.daq_center_freq = synth.CENTER
    receiver.daq_rx_gain = 15.7

    dsp_queue = ListQueue()
    sp = ksp.SignalProcessor(data_que=dsp_queue, module_receiver=receiver, logging_level=logging.WARNING)
    for name, value in Case("integration", "UCA", "MUSIC", [(0, 0, synth.F_OFF)]).sp_settings().items():
        setattr(sp, name, value)
    sp.vfo_freq[0] = synth.CENTER + synth.F_OFF
    sp.daemon = True
    thread_exceptions = []
    # An exception that ends the DSP thread is not logged; threading reports it through this hook.
    threading.excepthook = lambda hook: thread_exceptions.append(f"{hook.exc_type.__name__}: {hook.exc_value}")
    capture = ErrorCapture()
    logging.getLogger().addHandler(capture)
    sp.start()

    deadline = time.time() + DEADLINE_S
    while time.time() < deadline:
        if sum(1 for packet in dsp_queue.items if "DoA Max" in dict(packet)) >= expected:
            break
        time.sleep(0.05)
    # The fake DAQ waits 1 s after the last frame before it sends TERMINATE, so these are the errors of the frames.
    errors_before_terminate = [exception_line(message) for _, message in capture.records]
    time.sleep(SETTLE_AFTER_TERMINATE_S)  # the fake DAQ sends TERMINATE and closes the FIFOs meanwhile

    frames = []
    for packet in (dict(p) for p in dsp_queue.items):
        if "DoA Max" in packet:
            frames.append(
                {
                    "cpi_index": packet["iq_header"].cpi_index,
                    "doa_max": float(packet["DoA Max"]),
                    "squelch_open": bool(packet["DoA Squelch"][0]),
                }
            )
    summary = {
        "init_data_iface": init_result,
        "frames": frames,
        "receiver_queue": [entry[0][0] for entry in receiver_queue.items],
        "errors_before_terminate": errors_before_terminate,
        "errors": [exception_line(message) for _, message in capture.records],
        "dsp_thread_alive": sp.is_alive(),
        "dsp_thread_exceptions": thread_exceptions,
        "channel_number": sp.channel_number,
    }
    Path(out_json).write_text(json.dumps(summary))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
