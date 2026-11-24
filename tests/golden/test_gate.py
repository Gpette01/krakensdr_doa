# Checks that the cross-environment gate and the truth check of test_golden.py catch typical contract changes.
import copy
import re

import pytest
from golden import test_golden as golden
from golden.cases import golden_cases

LABEL = "UCA/MUSIC/123deg/0dB"


@pytest.fixture(scope="module")
def record():
    return golden.stored(golden.all_environments()[0])[LABEL]


def swap_csv_fields_2_and_3(text):
    lines = []
    for line in text.splitlines():
        fields = line.split(", ")
        fields[2], fields[3] = fields[3], fields[2]
        lines.append(", ".join(fields))
    return "\n".join(lines)


MUTATIONS = {
    "CSV confidence and power swapped": ("doa_value_csv", swap_csv_fields_2_and_3),
    "CSV bearing off by 1 degree": (
        "doa_value_csv",
        lambda text: re.sub(r"^(<t>, )([\d.]+)", lambda m: f"{m.group(1)}{float(m.group(2)) + 1}", text),
    ),
    "XML confidence x10": (
        "doa_xml",
        lambda text: re.sub(r"<CONF>(\d+)</CONF>", lambda m: f"<CONF>{int(m.group(1)) * 10}</CONF>", text),
    ),
    "XML element renamed": ("doa_xml", lambda text: text.replace("PWR>", "POWER>")),
    "an error was logged": ("errors", lambda errors: errors + ["ValueError: boom"]),
}


def test_gate_accepts_an_identical_record(record):
    assert golden.gate_violations(LABEL, record, record) == []


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_gate_rejects(record, mutation):
    field, change = MUTATIONS[mutation]
    mutated = copy.deepcopy(record)
    mutated[field] = change(mutated[field])
    assert golden.gate_violations(LABEL, mutated, record) != []


def test_truth_check_rejects_a_wrong_bearing(record):
    (case,) = [case for case in golden_cases() if case.label == LABEL]
    assert golden.truth_problems(case, record) == []
    wrong = copy.deepcopy(record)
    wrong["doa_max_list"] = [124.0]
    assert golden.truth_problems(case, wrong) != []


@pytest.mark.parametrize("field", ["doa_result_db", "doa_value_csv"])
def test_gate_rejects_a_moved_plot_floor(field):
    """Only ROOT-MUSIC spectra reach the -100 dB floor of DOA_plot_util in the golden cases."""
    label = "UCA/ROOT-MUSIC/123deg/0dB"
    record = golden.stored(golden.all_environments()[0])[label]
    mutated = copy.deepcopy(record)
    if field == "doa_result_db":
        mutated[field] = [max(value, -90.0) for value in record[field]]
    else:
        # The CSV array is shifted so that the floor is 0 (kraken_sdr_signal_processor.py:764-766).
        mutated[field] = re.sub(r", 0\.00\b", ", 10.00", record[field])
    assert mutated[field] != record[field]
    assert golden.gate_violations(label, mutated, record) != []
