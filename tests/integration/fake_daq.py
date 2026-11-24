"""Fake Heimdall DAQ, run as a subprocess by test_shmem_pipeline.py.

It writes synthetic frames through the repo's own DAQ-side classes (shmemIface.outShmemIface and
IQHeader.encode_header) and runs a control-port stub on 127.0.0.1 that logs each 128-byte message and replies
"FNSD". The working directory must hold _data_control/fw_delay_sync_iq and bw_delay_sync_iq, because
outShmemIface opens them by relative path (shmemIface.py:79-80).

usage: fake_daq.py <port_file> <control_log> <n_samples> <n_frames> <true_deg>
"""

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TESTS_DIR.parent
sys.path[:0] = [str(TESTS_DIR), str(REPO_ROOT / "_sdr/_receiver")]

from helpers import synth  # noqa: E402
from iq_header import IQHeader  # noqa: E402
from shmemIface import outShmemIface  # noqa: E402

MESSAGE_BYTES = 128


def serve_control(server, control_log):
    connection, _ = server.accept()
    messages = []
    while True:
        message = b""
        while len(message) < MESSAGE_BYTES:
            chunk = connection.recv(MESSAGE_BYTES - len(message))
            if not chunk:
                return
            message += chunk
        messages.append({"command": message[:4].decode(errors="replace"), "length": len(message)})
        Path(control_log).write_text(json.dumps(messages))
        if message[:4] != b"EXIT":
            connection.sendall(b"FNSD" + bytes(MESSAGE_BYTES - 4))


def main():
    port_file, control_log = sys.argv[1], sys.argv[2]
    n, n_frames, true_deg = int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    threading.Thread(target=serve_control, args=(server, control_log), daemon=True).start()
    Path(port_file + ".tmp").write_text(str(server.getsockname()[1]))
    os.replace(port_file + ".tmp", port_file)

    payload_bytes = n * synth.M * 8  # complex64
    iface = outShmemIface("delay_sync_iq", 1024 + payload_bytes, drop_mode=False)
    if not iface.init_ok:
        sys.exit("fake_daq: FIFOs missing")
    frame = synth.synth_frame(n, [(true_deg, 0, synth.F_OFF)], "UCA", seed=7)
    header = IQHeader()
    header.sync_word = IQHeader.SYNC_WORD
    header.frame_type = IQHeader.FRAME_TYPE_DATA
    header.hardware_id = "fake_daq"
    header.active_ant_chs = synth.M
    header.rf_center_freq = synth.CENTER
    header.adc_sampling_freq = synth.FS
    header.sampling_freq = synth.FS
    header.cpi_length = n
    header.sample_bit_depth = 32
    header.delay_sync_flag = 1
    header.iq_sync_flag = 1
    try:
        for index in range(n_frames):
            buffer_index = iface.wait_buff_free()
            if buffer_index not in (0, 1):
                sys.exit(f"fake_daq: wait_buff_free returned {buffer_index}")
            header.cpi_index = index
            header.time_stamp = int(time.time() * 1000)
            header_bytes = header.encode_header()
            buffer = iface.buffers[buffer_index]
            buffer[:1024] = memoryview(header_bytes)
            buffer[1024 : 1024 + payload_bytes] = frame.view(synth.np.uint8).reshape(-1)
            iface.send_ctr_buff_ready(buffer_index)
        time.sleep(1.0)
        iface.send_ctr_terminate()
        time.sleep(0.5)
    finally:
        iface.destory_sm_buffer()
        for memory in iface.memories:
            memory.unlink()
    print("fake_daq: done", flush=True)


if __name__ == "__main__":
    main()
