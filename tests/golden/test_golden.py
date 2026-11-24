# Golden regression: stored outputs of the run() loop, keyed by environment.
#
# Tiers:
#  1. Same environment: bit-identical to the stored file of this environment when the CPU model is the one that
#     recorded it. On another CPU (for example a CI runner) BLAS may take other code paths, so tier 2 applies.
#  2. Other environments: within the gate tolerances below (numeric fields only).
#  3. The truth suite (tests/truth) checks against physical truth and is never regenerated.
#
# `pytest tests/golden --update-golden` rewrites the file of this environment and prints a per-case diff table.
# Change a golden file only in a task whose purpose is numeric, and give a reason for each changed case.
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from golden.cases import KNOWN_BUGS, SPECTRUM_CASES, golden_cases
from helpers.dsp import exception_line, run_cases

DATA_DIR = Path(__file__).resolve().parent / "data"
N_SAMPLES = 2**16

ROOT_MUSIC_TOLERANCE_DEG = 0.05
NEAR_PEAK_DB = 20.0  # spectrum bins within this distance of the peak use the tight tolerance
NEAR_PEAK_TOLERANCE_DB = 0.1
FAR_TOLERANCE_DB = 1.0
CONFIDENCE_TOLERANCE = 0.05
SNR_TOLERANCE_DB = 0.05


def environment_id():
    import numba
    import scipy

    version = f"{sys.version_info.major}{sys.version_info.minor}"
    return f"py{version}-numpy{np.__version__}-scipy{scipy.__version__}-numba{numba.__version__}"


def cpu_model():
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def golden_path(env_id):
    return DATA_DIR / f"{env_id}.json"


def mask_csv(text):
    """The first CSV field is the frame timestamp (kraken_sdr_signal_processor.py:759)."""
    return "\n".join(re.sub(r"^[^,]*", "<t>", line) if line.strip() else line for line in text.splitlines())


def mask_xml(text):
    for tag in ("TIME", "GPS_TIME", "PROCESSING_TIME"):
        text = re.sub(rf"<{tag}>[^<]*</{tag}>", f"<{tag}>*</{tag}>", text)
    return text


def as_floats(values):
    return [float(v) for v in np.asarray(values, dtype=np.float64).ravel()]


def collect():
    """Runs every golden case once through run() and returns {label: record}."""
    import kraken_sdr_signal_processor as ksp

    outputs = {}

    def prepare(sp, receiver):
        original_wr_xml = sp.wr_xml

        def recording_wr_xml(*args):
            original_wr_xml(*args)
            share = ksp.shared_path
            frame = receiver.next_index - 1
            outputs[frame] = {
                "num_corr_sources": int(args[10]),
                "snr_db": float(args[11]),
                "doa_value_csv": mask_csv(Path(share, "DOA_value.html").read_text()),
                "doa_xml": mask_xml(Path(share, "doa.xml").read_text()),
            }

        sp.wr_xml = recording_wr_xml

    return prepare, outputs


@pytest.fixture(scope="module")
def current(make_sp_module):
    cases = golden_cases()
    prepare, outputs = collect()
    results = run_cases(make_sp_module, cases, n=N_SAMPLES, en_spectrum=True, prepare=prepare)
    records = {}
    for index, result in enumerate(results):
        packet = result.packet
        record = {
            "known_bug": KNOWN_BUGS.get(result.case.label),
            "doa_max": result.doa_max,
            "squelch_open": result.squelch_open,
            "errors": [exception_line(error) for error in result.errors],
            "doa_max_list": as_floats(packet.get("DoA Max List", [])[: len(result.case.vfo_offsets)]),
            "confidence": float(np.max(packet["DoA Confidence"])) if "DoA Confidence" in packet else None,
            "doa_result_db": as_floats(packet["DoA Result"]) if "DoA Result" in packet else None,
        }
        record.update(outputs.get(index, {}))
        if result.case.label in SPECTRUM_CASES:
            record["spectrum_row1_db"] = as_floats(packet["spectrum"][1])
        records[result.case.label] = record
    return records


def stored(env_id):
    with open(golden_path(env_id), encoding="utf-8") as file:
        return json.load(file)["cases"]


def recorded_cpu(env_id):
    with open(golden_path(env_id), encoding="utf-8") as file:
        return json.load(file)["cpu"]


def write(env_id, records):
    DATA_DIR.mkdir(exist_ok=True)
    document = {"environment": env_id, "cpu": cpu_model(), "n_samples": N_SAMPLES, "cases": records}
    with open(golden_path(env_id), "w", encoding="utf-8") as file:
        json.dump(document, file, indent=1, sort_keys=True)
        file.write("\n")


def spectrum_violations(name, new, old):
    """Tight tolerance near the peak, loose elsewhere. Returns a list of messages."""
    if new is None or old is None:
        return [] if new is old else [f"{name}: one side is missing"]
    new = np.asarray(new)
    old = np.asarray(old)
    if new.shape != old.shape:
        return [f"{name}: shape {new.shape} != {old.shape}"]
    near_peak = old >= old.max() - NEAR_PEAK_DB
    difference = np.abs(new - old)
    problems = []
    if difference[near_peak].max(initial=0) > NEAR_PEAK_TOLERANCE_DB:
        problems.append(f"{name}: {difference[near_peak].max():.4f} dB near the peak")
    if difference[~near_peak].max(initial=0) > FAR_TOLERANCE_DB:
        problems.append(f"{name}: {difference[~near_peak].max():.4f} dB away from the peak")
    return problems


def gate_violations(label, new, old):
    """Tier 2: the numeric comparison used across environments."""
    problems = []
    for key in ("squelch_open", "num_corr_sources"):
        if new.get(key) != old.get(key):
            problems.append(f"{key}: {new.get(key)} != {old.get(key)}")
    if (new["doa_max"] is None) != (old["doa_max"] is None):
        problems.append(f"doa_max: {new['doa_max']} != {old['doa_max']}")
    elif new["doa_max"] is not None:
        tolerance = ROOT_MUSIC_TOLERANCE_DEG if "ROOT-MUSIC" in label else 0.0
        for name, a, b in [("doa_max", new["doa_max"], old["doa_max"])] + [
            ("doa_max_list", x, y) for x, y in zip(new["doa_max_list"], old["doa_max_list"])
        ]:
            if abs((a - b + 180) % 360 - 180) > tolerance:
                problems.append(f"{name}: {a} != {b}")
    for key, tolerance in (("confidence", CONFIDENCE_TOLERANCE), ("snr_db", SNR_TOLERANCE_DB)):
        a, b = new.get(key), old.get(key)
        if (a is None) != (b is None) or (a is not None and abs(a - b) > tolerance):
            problems.append(f"{key}: {a} != {b}")
    if "ROOT-MUSIC" not in label:
        # The ROOT-MUSIC display spectrum is a Gaussian drawn around theta (kraken_sdr_signal_processor.py:1016),
        # so it carries no information beyond doa_max, which is compared above.
        problems += spectrum_violations("doa_result_db", new["doa_result_db"], old["doa_result_db"])
    problems += spectrum_violations("spectrum_row1_db", new.get("spectrum_row1_db"), old.get("spectrum_row1_db"))
    return problems


def diff_table(new_records, old_records):
    lines = [f"{'case':45s} {'status':10s} {'doa_max old -> new':28s} known_bug"]
    for label in sorted(set(new_records) | set(old_records)):
        new, old = new_records.get(label), old_records.get(label)
        if old is None or new is None:
            status = "added" if old is None else "removed"
            lines.append(f"{label:45s} {status}")
            continue
        status = "same" if new == old else ("changed" if gate_violations(label, new, old) else "within gate")
        change = f"{old['doa_max']} -> {new['doa_max']}"
        lines.append(f"{label:45s} {status:10s} {change:28s} {new.get('known_bug') or ''}")
    return "\n".join(lines)


def test_golden_matches_this_environment(current, request):
    env_id = environment_id()
    if request.config.getoption("--update-golden"):
        old_records = stored(env_id) if golden_path(env_id).exists() else {}
        write(env_id, current)
        reporter = request.config.pluginmanager.get_plugin("terminalreporter")
        reporter.write_line(f"\nGolden file rewritten: {golden_path(env_id).name}")
        reporter.write_line(diff_table(current, old_records))
        return
    assert golden_path(env_id).exists(), f"no golden file for {env_id}; run with --update-golden in a numeric task"
    expected = stored(env_id)
    assert sorted(current) == sorted(expected), "the case list differs from the golden file"
    if recorded_cpu(env_id) != cpu_model():
        problems = {label: gate_violations(label, current[label], expected[label]) for label in expected}
        problems = {label: violations for label, violations in problems.items() if violations}
        assert not problems, json.dumps(problems, indent=1)
        return
    changed = [label for label in expected if current[label] != expected[label]]
    assert not changed, "not bit-identical:\n" + diff_table(
        {k: current[k] for k in changed}, {k: expected[k] for k in changed}
    )


def other_environments():
    if not DATA_DIR.exists():
        return []
    return sorted(path.stem for path in DATA_DIR.glob("*.json") if path.stem != environment_id())


@pytest.mark.parametrize("other_env", other_environments())
def test_golden_agrees_with_other_environments(current, other_env):
    expected = stored(other_env)
    problems = {}
    for label, old in expected.items():
        violations = gate_violations(label, current[label], old)
        if violations:
            problems[label] = violations
    assert not problems, json.dumps(problems, indent=1)


def test_golden_case_labels_are_unique():
    labels = [case.label for case in golden_cases()]
    assert len(labels) == len(set(labels))
    assert set(KNOWN_BUGS) <= set(labels) and set(SPECTRUM_CASES) <= set(labels)
