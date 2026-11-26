# Integration: fake DAQ -> shared memory and FIFOs -> real ReceiverRTLSDR -> real SignalProcessor.
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from integration.shmem_lock import LOCK_PATH, try_lock

HERE = Path(__file__).resolve().parent
SHM_NAMES = ("delay_sync_iq_A", "delay_sync_iq_B")
N_SAMPLES = 2**16
N_FRAMES = 8
TRUE_DEG = 123.0
TIMEOUT_S = 150


def start_daq(workdir, run, n_frames, true_deg, env):
    """Starts one fake DAQ life and waits until it has published its control port."""
    port_file = workdir / f"control_port_{run}"
    daq = subprocess.Popen(
        [
            sys.executable,
            "-W",
            "ignore",
            str(HERE / "fake_daq.py"),
            str(port_file),
            str(workdir / f"control_log_{run}.json"),
            str(N_SAMPLES),
            str(n_frames),
            str(true_deg),
        ],
        cwd=workdir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 30
    while not port_file.exists():
        if daq.poll() is not None:
            raise RuntimeError(f"fake DAQ exited early: {daq.stdout.read()}")
        if time.time() > deadline:
            daq.kill()
            raise RuntimeError("fake DAQ never published its control port")
        time.sleep(0.05)
    return daq, port_file.read_text()


def run_pipeline(workdir, daq_runs=((N_FRAMES, TRUE_DEG),)):
    """One consumer; the fake DAQ runs once per (frames, bearing) entry, one after the other on the same FIFOs."""
    control = workdir / "_data_control"
    control.mkdir()
    for name in ("fw_delay_sync_iq", "bw_delay_sync_iq"):
        os.mkfifo(control / name)
    out_json = workdir / "consumer.json"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    processes = []
    consumer = None
    daq_outputs = []
    try:
        daq, port = start_daq(workdir, 0, *daq_runs[0], env)
        processes.append(daq)
        total_frames = sum(n_frames for n_frames, _ in daq_runs)
        consumer = subprocess.Popen(
            [
                sys.executable,
                "-W",
                "ignore",
                str(HERE / "consumer.py"),
                str(workdir),
                port,
                str(total_frames),
                str(out_json),
            ],
            cwd=workdir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        processes.append(consumer)
        for run, (n_frames, true_deg) in enumerate(daq_runs[1:], start=1):
            daq_outputs.append(daq.communicate(timeout=60)[0])
            daq, _ = start_daq(workdir, run, n_frames, true_deg, env)
            processes.append(daq)
        consumer_output, _ = consumer.communicate(timeout=TIMEOUT_S)
        daq_outputs.append(daq.communicate(timeout=30)[0])
        daq_output = "\n".join(daq_outputs)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        for name in SHM_NAMES:
            # Created by this test's fake DAQ: the test skips when the names existed before it started.
            Path("/dev/shm", name).unlink(missing_ok=True)
    if not out_json.exists():
        # Not an AssertionError, so that a broken pipeline can never count as an expected failure.
        raise RuntimeError(f"consumer wrote no summary.\nconsumer: {consumer_output}\nfake DAQ: {daq_output}")
    summary = json.loads(out_json.read_text())
    control_log = workdir / "control_log_0.json"
    summary["control"] = json.loads(control_log.read_text()) if control_log.exists() else []
    summary["daq_output"] = daq_output
    return summary


@pytest.fixture(scope="module", autouse=True)
def shared_memory_names_lock():
    """The DAQ shared memory names are fixed, so only one test run at a time may use them (follow-up 2 to M0-06)."""
    handle = try_lock()
    if handle is None:
        pytest.skip(f"another test run is using the DAQ shared memory names (lock {LOCK_PATH})")
    yield
    handle.close()  # closing the file releases the lock


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    if any(Path("/dev/shm", name).exists() for name in SHM_NAMES):
        pytest.skip("a DAQ shared memory segment already exists; a real DAQ may be running")
    return run_pipeline(tmp_path_factory.mktemp("shmem"))


def test_every_frame_gives_the_true_bearing(pipeline):
    assert pipeline["init_data_iface"] == 0
    frames = pipeline["frames"]
    assert len(frames) == N_FRAMES, pipeline
    assert all(frame["squelch_open"] and frame["doa_max"] == TRUE_DEG for frame in frames), pipeline
    assert pipeline["errors_before_terminate"] == []
    assert pipeline["channel_number"] == 5
    assert "fake_daq: done" in pipeline["daq_output"]


def test_control_port_receives_init_freq_gain(pipeline):
    commands = {message["command"]: message["length"] for message in pipeline["control"]}
    assert commands == {"INIT": 128, "FREQ": 128, "GAIN": 128}, pipeline["control"]
    assert pipeline["receiver_queue"][0] == "conn-ok"


def test_dsp_thread_survives_the_daq_going_away(pipeline):
    """Failed before M1-09 (T-03): struct.error on the closed FIFO ended the DSP thread."""
    assert pipeline["dsp_thread_alive"], pipeline["dsp_thread_exceptions"]


def test_a_closed_fifo_is_not_an_error(pipeline):
    """The closed FIFO must read as a disconnect, not raise struct.error inside the frame loop (T-03, M1-10)."""
    assert [error for error in pipeline["errors"] if "unpack" in error] == []


@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="T-14, D-20: every packet carries the same live IQ header"
)
def test_each_packet_carries_its_own_frame_index(pipeline):
    assert [frame["cpi_index"] for frame in pipeline["frames"]] == list(range(N_FRAMES))


RESTART_FRAMES = 4
SECOND_DAQ_DEG = 240.0


@pytest.fixture(scope="module")
def restarted_pipeline(tmp_path_factory):
    """DAQ A sends 4 frames at 123 degrees and exits; DAQ B then starts on the same FIFOs with 240 degrees."""
    if any(Path("/dev/shm", name).exists() for name in SHM_NAMES):
        pytest.skip("a DAQ shared memory segment already exists; a real DAQ may be running")
    return run_pipeline(
        tmp_path_factory.mktemp("shmem_restart"), ((RESTART_FRAMES, TRUE_DEG), (RESTART_FRAMES, SECOND_DAQ_DEG))
    )


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="N-01 / M3-05: no re-init after the DAQ restarts")
def test_frames_after_a_daq_restart_come_from_the_new_daq(restarted_pipeline):
    """DAQ B recreates the shared memory; the receiver still maps A's unlinked segments and reads stale frames."""
    bearings = [frame["doa_max"] for frame in restarted_pipeline["frames"]]
    assert bearings[-RESTART_FRAMES:] == [SECOND_DAQ_DEG] * RESTART_FRAMES, restarted_pipeline["frames"]
