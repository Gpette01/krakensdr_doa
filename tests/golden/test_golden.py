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
import xml.etree.ElementTree as ET
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
POWER_TOLERANCE_DB = 0.1  # peak spectrum bin; the two environments differ by 4e-6 dB

# Kraken App CSV (kraken_sdr_signal_processor.py:759-770): field index -> kind. Fields 17 and later are the DoA array.
CSV_BEARING, CSV_CONFIDENCE, CSV_POWER, CSV_FIRST_DOA_VALUE = 1, 2, 3, 17

# Truth check of the stored bearings, so that a golden refresh cannot hide a wrong bearing.
TRUTH_TOLERANCE_DEG = 0.5
TRUTH_TOLERANCE_LOW_SNR_DEG = 2.0  # cases at -15 dB wideband SNR


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


ROOT_MUSIC_PEAK_HALF_WIDTH_DEG = 10


def root_music_spectrum_violations(name, new, old):
    """The ROOT-MUSIC display spectrum is a Gaussian drawn around theta (kraken_sdr_signal_processor.py:1016).

    Near the peak it moves with theta, which is compared on its own. Away from the peak (the -100 dB floor of
    DOA_plot_util) it must match within the loose tolerance.
    """
    if new is None or old is None:
        return [] if new is old else [f"{name}: one side is missing"]
    new, old = np.asarray(new), np.asarray(old)
    if new.shape != old.shape:
        return [f"{name}: shape {new.shape} != {old.shape}"]
    bins = np.arange(len(old))
    distance = np.abs((bins - int(np.argmax(old)) + 180) % 360 - 180)
    away = distance > ROOT_MUSIC_PEAK_HALF_WIDTH_DEG
    worst = np.abs(new - old)[away].max(initial=0)
    return [f"{name}: {worst:.4f} dB away from the peak"] if worst > FAR_TOLERANCE_DB else []


def doa_spectrum_violations(label, name, new, old):
    if "ROOT-MUSIC" in label:
        return root_music_spectrum_violations(name, new, old)
    return spectrum_violations(name, new, old)


def bearing_tolerance(label):
    return ROOT_MUSIC_TOLERANCE_DEG if "ROOT-MUSIC" in label else 0.0


def circular_difference(a, b):
    return abs((float(a) - float(b) + 180) % 360 - 180)


def csv_violations(label, new_text, old_text):
    """Field count, order and text must match; numbers within the gate tolerances."""
    if (new_text is None) or (old_text is None):
        return [] if new_text is old_text else ["doa_value_csv: one side is missing"]
    new_lines, old_lines = new_text.splitlines(), old_text.splitlines()
    if len(new_lines) != len(old_lines):
        return [f"doa_value_csv: {len(new_lines)} lines != {len(old_lines)}"]
    problems = []
    for line_number, (new_line, old_line) in enumerate(zip(new_lines, old_lines)):
        new_fields = [field.strip() for field in new_line.split(",")]
        old_fields = [field.strip() for field in old_line.split(",")]
        where = f"doa_value_csv line {line_number}"
        if len(new_fields) != len(old_fields):
            problems.append(f"{where}: {len(new_fields)} fields != {len(old_fields)}")
            continue
        for index, (a, b) in enumerate(zip(new_fields[:CSV_FIRST_DOA_VALUE], old_fields[:CSV_FIRST_DOA_VALUE])):
            if index == CSV_BEARING:
                bad = circular_difference(a, b) > bearing_tolerance(label)
            elif index == CSV_CONFIDENCE:
                bad = abs(float(a) - float(b)) > CONFIDENCE_TOLERANCE
            elif index == CSV_POWER:
                bad = abs(float(a) - float(b)) > POWER_TOLERANCE_DB
            else:
                bad = a != b
            if bad:
                problems.append(f"{where} field {index}: {a} != {b}")
        new_array = [float(value) for value in new_fields[CSV_FIRST_DOA_VALUE:]]
        old_array = [float(value) for value in old_fields[CSV_FIRST_DOA_VALUE:]]
        problems += doa_spectrum_violations(label, f"{where} DoA array", new_array, old_array)
    return problems


def xml_violations(label, new_text, old_text):
    """Element order and text must match; numbers within the gate tolerances."""
    if (new_text is None) or (old_text is None):
        return [] if new_text is old_text else ["doa_xml: one side is missing"]
    new_elements = list(ET.fromstring(new_text).iter())
    old_elements = list(ET.fromstring(old_text).iter())
    if [e.tag for e in new_elements] != [e.tag for e in old_elements]:
        return [f"doa_xml: element order {[e.tag for e in new_elements]} != {[e.tag for e in old_elements]}"]
    problems = []
    for new_element, old_element in zip(new_elements, old_elements):
        a, b = new_element.text, old_element.text
        if new_element.tag == "DOA":
            bad = circular_difference(a, b) > bearing_tolerance(label)
        elif new_element.tag == "PWR":
            bad = abs(float(a) - float(b)) > POWER_TOLERANCE_DB
        elif new_element.tag == "CONF":
            bad = abs(int(a) - int(b)) > 100 * CONFIDENCE_TOLERANCE  # CONF is int(conf * 100)
        elif new_element.tag == "SNR_DB":
            bad = abs(float(a) - float(b)) > SNR_TOLERANCE_DB
        else:
            bad = a != b
        if bad:
            problems.append(f"doa_xml {new_element.tag}: {a} != {b}")
    return problems


def gate_violations(label, new, old):
    """Tier 2: the numeric comparison used across environments."""
    problems = []
    for key in ("squelch_open", "num_corr_sources", "errors"):
        if new.get(key) != old.get(key):
            problems.append(f"{key}: {new.get(key)} != {old.get(key)}")
    if (new["doa_max"] is None) != (old["doa_max"] is None):
        problems.append(f"doa_max: {new['doa_max']} != {old['doa_max']}")
    elif new["doa_max"] is not None:
        tolerance = bearing_tolerance(label)
        for name, a, b in [("doa_max", new["doa_max"], old["doa_max"])] + [
            ("doa_max_list", x, y) for x, y in zip(new["doa_max_list"], old["doa_max_list"])
        ]:
            if abs((a - b + 180) % 360 - 180) > tolerance:
                problems.append(f"{name}: {a} != {b}")
    for key, tolerance in (("confidence", CONFIDENCE_TOLERANCE), ("snr_db", SNR_TOLERANCE_DB)):
        a, b = new.get(key), old.get(key)
        if (a is None) != (b is None) or (a is not None and abs(a - b) > tolerance):
            problems.append(f"{key}: {a} != {b}")
    problems += doa_spectrum_violations(label, "doa_result_db", new["doa_result_db"], old["doa_result_db"])
    problems += spectrum_violations("spectrum_row1_db", new.get("spectrum_row1_db"), old.get("spectrum_row1_db"))
    problems += csv_violations(label, new.get("doa_value_csv"), old.get("doa_value_csv"))
    problems += xml_violations(label, new.get("doa_xml"), old.get("doa_xml"))
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


def truth_tolerance(case):
    lowest_snr = min(snr_db for _, snr_db, _ in case.sources)
    return TRUTH_TOLERANCE_LOW_SNR_DEG if lowest_snr < 0 else TRUTH_TOLERANCE_DEG


def truth_error(case, estimate, azimuth):
    """Distance to the expected bearing (true - array offset), with the ULA mirror 180 - theta allowed."""
    expected = (azimuth - case.array_offset) % 360
    error = circular_difference(estimate, expected)
    if case.geometry == "ULA":
        error = min(error, circular_difference(estimate, 180 - expected))
    return error


def spectrum_peaks(doa_result_db, count):
    """Bearings of the `count` highest local maxima of a circular 360-point spectrum."""
    values = np.asarray(doa_result_db)
    maxima = [i for i in range(len(values)) if values[i] > values[i - 1] and values[i] >= values[(i + 1) % len(values)]]
    return sorted(maxima, key=lambda i: -values[i])[:count]


def truth_problems(case, record):
    if record["doa_max"] is None or not record["doa_max_list"]:
        return [f"no bearing stored: errors {record['errors']}"]
    tolerance = truth_tolerance(case)
    problems = []
    if len(case.sources) > len(case.vfo_offsets):
        # Several sources in one VFO: every source must be one of the strongest peaks (each source gives two peaks
        # on a ULA, its bearing and the mirror).
        peaks = spectrum_peaks(record["doa_result_db"], len(case.sources) * (2 if case.geometry == "ULA" else 1))
        for azimuth, _, _ in case.sources:
            if min(truth_error(case, peak, azimuth) for peak in peaks) > tolerance:
                problems.append(f"source {azimuth} not among peaks {peaks}")
        return problems
    for vfo, offset in enumerate(case.vfo_offsets):
        (azimuth,) = [a for a, _, f_off in case.sources if f_off == offset]
        estimate = record["doa_max_list"][vfo]
        if truth_error(case, estimate, azimuth) > tolerance:
            problems.append(f"VFO {vfo}: {estimate} for a source at {azimuth} (tolerance {tolerance})")
    return problems


def all_environments():
    return sorted(path.stem for path in DATA_DIR.glob("*.json")) if DATA_DIR.exists() else []


@pytest.mark.parametrize("env", all_environments())
@pytest.mark.parametrize(
    "case", [case for case in golden_cases() if case.label not in KNOWN_BUGS], ids=lambda case: case.label
)
def test_stored_golden_bearings_match_truth(env, case):
    """The stored bearings must agree with the synthetic truth, so a refresh cannot store a wrong bearing."""
    assert truth_problems(case, stored(env)[case.label]) == []
