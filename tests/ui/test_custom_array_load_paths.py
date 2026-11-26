# Follow-up to M1-06: every load path validates the custom array text. Startup keeps the defaults and the DSP
# callback keeps the previous coordinates when the text is not one finite number per channel (5 channels here).
import json

import pytest
from custom_array_cases import CASES, VALID_X, VALID_Y
from ui import sandbox

DEFAULT_X = [0.21, 0.06, -0.17, -0.17, 0.07]
DEFAULT_Y = [0.0, -0.2, -0.12, 0.12, 0.2]
PREVIOUS = [[0.3, 0.1, -0.2, -0.2, 0.1], [0.0, -0.3, -0.1, 0.1, 0.3]]


@pytest.fixture(scope="module")
def kept(tmp_path_factory):
    line, _ = sandbox.run_probe(tmp_path_factory.mktemp("custom"), "custom_array", json.dumps(CASES))
    return json.loads(line)


def parsed(text):
    return [float(value) for value in text.split(",")]


@pytest.mark.parametrize("name", CASES)
def test_startup(kept, name):
    expected = [parsed(VALID_X), parsed(VALID_Y)] if name == "valid" else [DEFAULT_X, DEFAULT_Y]
    assert kept[name]["startup"] == expected


@pytest.mark.parametrize("name", CASES)
def test_dsp_callback(kept, name):
    expected = [parsed(VALID_X), parsed(VALID_Y)] if name == "valid" else PREVIOUS
    assert kept[name]["callback"] == expected
