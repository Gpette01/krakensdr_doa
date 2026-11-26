# utils.parse_custom_array: the UI parser of the custom array text fields (finding P-22).
import numpy as np
import pytest


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0.21,0.06,-0.17,-0.17,0.07", [0.21, 0.06, -0.17, -0.17, 0.07]),
        (" 0.2105, 0.0651,-0.1703,-0.1703 ,0.0650 ", [0.2105, 0.0651, -0.1703, -0.1703, 0.065]),
    ],
)
def test_accepts_one_number_per_element(text, expected):
    import utils

    np.testing.assert_array_equal(utils.parse_custom_array(text, 5), expected)


@pytest.mark.parametrize(
    "text",
    [
        "0.1,0.2,0.3,0.4",
        "0.1,0.2,0.3,0.4,0.5,0.6",
        "0.1,0.2,x,0.4,0.5",
        "0.1,0.2,,0.4,0.5",
        "0.1,0.2,nan,0.4,0.5",
        None,
    ],
)
def test_rejects_anything_else(text):
    import utils

    assert utils.parse_custom_array(text, 5) is None
