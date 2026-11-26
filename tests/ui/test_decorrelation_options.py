# M2-04 (P-16, T-07): "F-B Toeplitz" had no code path. It is removed; a settings file that still holds it loads
# as "Off".
import json

import pytest
from ui import sandbox


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    line, _ = sandbox.run_probe(tmp_path_factory.mktemp("decorrelation"), "decorrelation")
    return json.loads(line)


def test_fb_toeplitz_is_not_offered(loaded):
    assert loaded["options"] == ["Off", "FBA", "TOEP", "FBSS"]


@pytest.mark.parametrize("path", ["startup", "watcher"])
def test_a_stored_fb_toeplitz_loads_as_off(loaded, path):
    assert loaded[path] == "Off"
