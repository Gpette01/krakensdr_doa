# Integration: fake DAQ -> shared memory and FIFOs -> real ReceiverRTLSDR -> real SignalProcessor.
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SHM_NAMES = ("delay_sync_iq_A", "delay_sync_iq_B")
N_SAMPLES = 2**16
N_FRAMES = 8
TRUE_DEG = 123.0
TIMEOUT_S = 150


def run_pipeline(workdir):
    control = workdir / "_data_control"
    control.mkdir()
    for name in ("fw_delay_sync_iq", "bw_delay_sync_iq"):
        os.mkfifo(control / name)
    port_file = workdir / "control_port"
    control_log = workdir / "control_log.json"
    out_json = workdir / "consumer.json"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    daq = subprocess.Popen(
        [
            sys.executable,
            "-W",
            "ignore",
            str(HERE / "fake_daq.py"),
            str(port_file),
            str(control_log),
            str(N_SAMPLES),
            str(N_FRAMES),
            str(TRUE_DEG),
        ],
        cwd=workdir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    consumer = None
    try:
        deadline = time.time() + 30
        while not port_file.exists():
            assert daq.poll() is None, f"fake DAQ exited early: {daq.stdout.read()}"
            assert time.time() < deadline, "fake DAQ never published its control port"
            time.sleep(0.05)
        consumer = subprocess.Popen(
            [
                sys.executable,
                "-W",
                "ignore",
                str(HERE / "consumer.py"),
                str(workdir),
                port_file.read_text(),
                str(N_FRAMES),
                str(out_json),
            ],
            cwd=workdir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        consumer_output, _ = consumer.communicate(timeout=TIMEOUT_S)
        daq_output, _ = daq.communicate(timeout=30)
    finally:
        for process in (daq, consumer):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        for name in SHM_NAMES:
            # Created by this test's fake DAQ: the test skips when the names existed before it started.
            Path("/dev/shm", name).unlink(missing_ok=True)
    assert out_json.exists(), f"consumer wrote no summary.\nconsumer: {consumer_output}\nfake DAQ: {daq_output}"
    summary = json.loads(out_json.read_text())
    summary["control"] = json.loads(control_log.read_text()) if control_log.exists() else []
    summary["daq_output"] = daq_output
    return summary


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    if any(Path("/dev/shm", name).exists() for name in SHM_NAMES):
        pytest.skip("a DAQ shared memory segment already exists; a real DAQ may be running")
    return run_pipeline(tmp_path_factory.mktemp("shmem"))


def test_every_frame_gives_the_true_bearing(pipeline):
    assert pipeline["init_data_iface"] == 0
    frames = pipeline["frames"]
    assert [frame["cpi_index"] for frame in frames] == list(range(N_FRAMES)), pipeline
    assert all(frame["squelch_open"] and frame["doa_max"] == TRUE_DEG for frame in frames), pipeline
    assert pipeline["channel_number"] == 5
    assert "fake_daq: done" in pipeline["daq_output"]


def test_control_port_receives_init_freq_gain(pipeline):
    commands = {message["command"]: message["length"] for message in pipeline["control"]}
    assert commands == {"INIT": 128, "FREQ": 128, "GAIN": 128}, pipeline["control"]
    assert pipeline["receiver_queue"][0] == "conn-ok"


@pytest.mark.xfail(strict=True, reason="T-03: the DSP thread dies with struct.error when the DAQ closes the FIFO")
def test_dsp_thread_survives_the_daq_going_away(pipeline):
    assert pipeline["dsp_thread_alive"], pipeline["dsp_thread_exceptions"]
