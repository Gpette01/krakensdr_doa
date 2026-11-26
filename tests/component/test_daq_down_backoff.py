# Task M3-06 (findings T-09, D-18): with no DAQ the DSP loop retried the control connection with no pause and,
# since M1-01, logged every "Connection refused" (about 9000 lines per second).
import logging
import socket
import threading
import time

from conftest import REPO_ROOT  # noqa: F401  (source paths)
from helpers.stubs import ListQueue
from ui.sandbox import free_port

OBSERVE_S = 3.0
STARTUP_PAUSE_S = 1.0  # SignalProcessor.run() sleeps 1 s before the first frame
BACKOFF_CAP_S = 2.0
MAX_ITERATIONS_PER_S = 10
MAX_LOG_LINES_PER_S = 1


class CountingHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def serve_control_port(server, accepted):
    connection, _ = server.accept()
    accepted.append(time.monotonic())
    while True:
        message = connection.recv(128)
        if not message:
            return
        connection.sendall(b"FNSD" + bytes(124))


def test_no_daq_backs_off_logs_little_and_reconnects(make_sp):
    from kraken_sdr_receiver import ReceiverRTLSDR

    port = free_port()  # nothing listens here yet
    receiver = ReceiverRTLSDR(data_que=ListQueue(), data_interface="eth", logging_level=logging.WARNING)
    receiver.data_interface = "shmem"  # only the control port is used to connect; no FIFOs are opened
    receiver.rec_ip_addr = "127.0.0.1"
    receiver.ctr_iface_port = port
    attempts = []
    original_get_iq_online = receiver.get_iq_online

    def counted_get_iq_online():
        attempts.append(time.monotonic())
        return original_get_iq_online()

    receiver.get_iq_online = counted_get_iq_online
    sp = make_sp(ListQueue(), receiver)
    sp.daemon = True
    handler = CountingHandler()
    logging.getLogger().addHandler(handler)
    try:
        start = time.monotonic()
        sp.start()
        time.sleep(STARTUP_PAUSE_S + OBSERVE_S)
        down_attempts = len(attempts)
        down_messages = list(handler.messages)
        dropped_while_down = sp.dropped_frames

        server = socket.socket()
        server.bind(("127.0.0.1", port))
        server.listen(1)
        accepted = []
        threading.Thread(target=serve_control_port, args=(server, accepted), daemon=True).start()
        daq_up = time.monotonic()
        deadline = daq_up + BACKOFF_CAP_S + 1.0
        while not accepted and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        sp.run_processing = False
        logging.getLogger().removeHandler(handler)
    elapsed = time.monotonic() - start
    assert down_attempts / OBSERVE_S <= MAX_ITERATIONS_PER_S, f"{down_attempts} attempts in {elapsed:.1f} s"
    assert len(down_messages) / OBSERVE_S <= MAX_LOG_LINES_PER_S, down_messages[:5]
    assert dropped_while_down == 0  # a missing DAQ is not a dropped frame
    assert accepted, "no connection within the backoff cap after the DAQ appeared"
    assert accepted[0] - daq_up <= BACKOFF_CAP_S + 0.5
    server.close()
