# Finding D-24: startup, the settings watcher and Reset used three different sets of defaults.
import json

import pytest
from ui import sandbox

# Reset keeps the DAQ connection of the current file, and ext_upd_flag marks who wrote the file.
NOT_DEFAULTS = {"data_interface", "default_ip", "ext_upd_flag"}


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    line, _ = sandbox.run_probe(tmp_path_factory.mktemp("defaults"), "defaults")
    return json.loads(line)


@pytest.mark.parametrize("path", ["reset", "watcher"])
def test_every_path_writes_the_startup_defaults(written, path):
    startup = written["startup"]
    other = written[path]
    assert sorted(other) == sorted(startup)
    different = {
        key: (startup[key], other[key]) for key in startup if key not in NOT_DEFAULTS and startup[key] != other[key]
    }
    assert different == {}


def test_defaults_match_the_defaults_table(written):
    import variables

    startup = written["startup"]
    different = {
        key: (value, startup.get(key)) for key, value in variables.DEFAULT_SETTINGS.items() if startup.get(key) != value
    }
    assert different == {}
