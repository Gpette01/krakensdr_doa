"""Per-frame timing of the real SignalProcessor.run() loop on synthetic frames.

Usage, from the repository root (pin to one otherwise idle core):
    PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=$PWD/.numba_cache \
        taskset -c 2 .venv310/bin/python benchmarks/bench_frame.py --out benchmarks/baseline/<env>.json
    ... bench_frame.py --compare benchmarks/baseline/<env>.json

The frame time is the `update_rate` the DSP reports itself (kraken_sdr_signal_processor.py:365,906-908): from the
end of frame acquisition to just before the packet is queued. Shared-memory copy time is not included.
A change counts as real only if a median moves by more than max(5 %, 3 x MAD) (median absolute deviation).
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("NUMBA_CACHE_DIR", str(REPO_ROOT / ".numba_cache"))
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(name, "1")
sys.dont_write_bytecode = True
for source_dir in ("tests", "_ui/_web_interface", "_sdr/_receiver", "_sdr/_signal_processing"):
    sys.path.insert(0, str(REPO_ROOT / source_dir))

import numpy as np  # noqa: E402
from helpers import synth  # noqa: E402
from helpers.dsp import Case, run_cases  # noqa: E402

F_OFF = synth.F_OFF
WARMUP_FRAMES = 3  # numba compilation and lru_cache fills happen here

# name: (samples per frame, Case keyword arguments, en_spectrum)
CONFIGS = {
    "UCA MUSIC 12.5k N=2^18": (2**18, dict(geometry="UCA", algorithm="MUSIC"), False),
    "UCA MUSIC 12.5k N=2^20": (2**20, dict(geometry="UCA", algorithm="MUSIC"), False),
    "UCA ROOT-MUSIC 12.5k N=2^18": (2**18, dict(geometry="UCA", algorithm="ROOT-MUSIC"), False),
    "ULA MUSIC FBSS 12.5k N=2^18": (2**18, dict(geometry="ULA", algorithm="MUSIC", decorrelation="FBSS"), False),
    "UCA MUSIC 6.25k N=2^18": (2**18, dict(geometry="UCA", algorithm="MUSIC", vfo_bw=6250), False),
    "UCA MUSIC 4 VFOs 12.5k N=2^18": (
        2**18,
        dict(geometry="UCA", algorithm="MUSIC", vfo_offsets=(F_OFF, -300_000.0, 500_000.0, -700_000.0)),
        False,
    ),
    "UCA MUSIC 12.5k N=2^18 + spectrum": (2**18, dict(geometry="UCA", algorithm="MUSIC"), True),
}


def make_cases(name, case_kwargs, count):
    offsets = case_kwargs.get("vfo_offsets", (F_OFF,))
    angles = (123, 240, 37, 299)
    sources = [(angles[i], 0, offset) for i, offset in enumerate(offsets)]
    # Identical cases reuse one synthetic frame, so frame generation is not part of the loop.
    return [Case(name, sources=sources, seed=1, **case_kwargs) for _ in range(count)]


class StageTimer:
    """Wraps DSP functions and adds their wall time to the frame being processed."""

    def __init__(self):
        self.per_frame = {}
        self.receiver = None

    def wrap(self, stage, function):
        def timed(*args, **kwargs):
            start = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                frame = self.receiver.next_index - 1
                stages = self.per_frame.setdefault(frame, {})
                stages[stage] = stages.get(stage, 0.0) + time.perf_counter() - start

        return timed


def run_config(name, n, case_kwargs, en_spectrum, frames, workdir):
    import kraken_sdr_signal_processor as ksp
    import pytest
    from conftest import _point_sp_files_at, _sp_factory

    timer = StageTimer()
    module_patches = {
        "channelize": ksp.channelize,
        "reduce_spectrum": ksp.reduce_spectrum,
    }
    scipy_welch = ksp.signal.welch

    def prepare(sp, receiver):
        timer.receiver = receiver
        sp.estimate_DOA = timer.wrap("estimate_DOA", sp.estimate_DOA)
        sp.save_processing_status = timer.wrap("status_json", sp.save_processing_status)
        sp.wr_xml = timer.wrap("doa_xml", sp.wr_xml)

    cases = make_cases(name, case_kwargs, WARMUP_FRAMES + frames)
    with pytest.MonkeyPatch.context() as monkeypatch:
        _point_sp_files_at(workdir, monkeypatch)
        for function_name, function in module_patches.items():
            monkeypatch.setattr(ksp, function_name, timer.wrap(function_name, function))
        monkeypatch.setattr(ksp.signal, "welch", timer.wrap("welch", scipy_welch))
        with _sp_factory() as factory:
            results = run_cases(factory, cases, n=n, en_spectrum=en_spectrum, prepare=prepare)
    errors = sum(len(result.errors) for result in results)
    assert errors == 0, f"{name}: {errors} ERROR records; the timing would be meaningless"
    assert all(result.squelch_open for result in results), f"{name}: squelch closed on some frame"
    measured = range(WARMUP_FRAMES, len(results))
    frame_ms = [1e3 * results[i].packet["update_rate"] for i in measured]
    median = statistics.median(frame_ms)
    stages = sorted({stage for i in measured for stage in timer.per_frame.get(i, {})})
    stage_ms = {
        stage: statistics.median(1e3 * timer.per_frame[i].get(stage, 0.0) for i in measured) for stage in stages
    }
    return {
        "n_samples": n,
        "active_vfos": len(case_kwargs.get("vfo_offsets", (F_OFF,))),
        "en_spectrum": en_spectrum,
        "frames": len(frame_ms),
        "warmup_ms": [round(1e3 * results[i].packet["update_rate"], 2) for i in range(WARMUP_FRAMES)],
        "median_ms": round(median, 3),
        "p90_ms": round(float(np.percentile(frame_ms, 90)), 3),
        "mad_ms": round(statistics.median(abs(x - median) for x in frame_ms), 3),
        "min_ms": round(min(frame_ms), 3),
        "max_ms": round(max(frame_ms), 3),
        "stage_median_ms": {stage: round(value, 3) for stage, value in stage_ms.items()},
    }


def read_text(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return "unknown"


def machine_info():
    import numba
    import scipy

    cpu_model = "unknown"
    for line in read_text("/proc/cpuinfo").splitlines():
        if line.startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break
    cpus = sorted(os.sched_getaffinity(0))
    governors = {read_text(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor") for cpu in cpus}
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "numba": numba.__version__,
        "cpu_model": cpu_model,
        "affinity": cpus,
        "governor": sorted(governors),
        "kernel": platform.release(),
        "blas_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
        "commit": commit.stdout.strip(),
        "date": time.strftime("%Y-%m-%d %H:%M"),
    }


def compare(baseline, current):
    """Returns True when every median is within max(5 %, 3 x the larger MAD) of the baseline."""
    all_ok = True
    print(f"{'config':36s} {'baseline':>10s} {'now':>10s} {'limit':>8s}  verdict")
    for name, old in baseline["configs"].items():
        new = current["configs"].get(name)
        if new is None:
            print(f"{name:36s} missing")
            all_ok = False
            continue
        limit = max(0.05 * old["median_ms"], 3 * max(old["mad_ms"], new["mad_ms"]))
        ok = abs(new["median_ms"] - old["median_ms"]) <= limit
        all_ok = all_ok and ok
        verdict = "same" if ok else ("faster" if new["median_ms"] < old["median_ms"] else "slower")
        print(f"{name:36s} {old['median_ms']:10.2f} {new['median_ms']:10.2f} {limit:8.2f}  {verdict}")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frames", type=int, default=30, help="measured frames per config (after 3 warm-up)")
    parser.add_argument("--only", action="append", help="run only configs whose name contains this text")
    parser.add_argument("--out", help="write the result JSON here")
    parser.add_argument("--compare", help="baseline JSON to compare the medians against")
    args = parser.parse_args()

    result = {"machine": machine_info(), "configs": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for index, (name, (n, case_kwargs, en_spectrum)) in enumerate(CONFIGS.items()):
            if args.only and not any(text in name for text in args.only):
                continue
            workdir = Path(tmp) / f"config{index}"
            workdir.mkdir()
            stats = run_config(name, n, case_kwargs, en_spectrum, args.frames, workdir)
            result["configs"][name] = stats
            stage_text = ", ".join(f"{k} {v}" for k, v in stats["stage_median_ms"].items())
            print(
                f"{name:36s} median {stats['median_ms']:9.2f} ms  p90 {stats['p90_ms']:9.2f}  "
                f"MAD {stats['mad_ms']:6.2f}  | {stage_text}",
                flush=True,
            )
    print(json.dumps(result["machine"]))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1) + "\n")
    exit_code = 0
    if args.compare:
        exit_code = 0 if compare(json.loads(Path(args.compare).read_text()), result) else 1
    sys.stdout.flush()
    # SignalProcessor threads are non-daemon `while True` loops (kraken_sdr_signal_processor.py:352).
    os._exit(exit_code)


if __name__ == "__main__":
    main()
