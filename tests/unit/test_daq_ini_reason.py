# Follow-up to M1-13: when the DAQ ini cannot be used, the reason must be reported, not just "missing or unreadable".
from conftest import TESTS_DIR

GOOD_INI = (TESTS_DIR / "data" / "daq_chain_config.ini").read_text()


def test_a_good_file_loads(tmp_path):
    import utils

    path = tmp_path / "daq_chain_config.ini"
    path.write_text(GOOD_INI)
    values, reason = utils.load_daq_ini(str(path))
    assert values["num_ch"] == 5 and reason is None


def test_missing_file(tmp_path):
    import utils

    values, reason = utils.load_daq_ini(str(tmp_path / "nothing.ini"))
    assert values is None and "not found" in reason


def test_bad_value_names_section_and_option(tmp_path):
    import utils

    path = tmp_path / "daq_chain_config.ini"
    path.write_text(GOOD_INI.replace("num_ch = 5", "num_ch = five"))
    values, reason = utils.load_daq_ini(str(path))
    assert values is None
    assert "[hw] num_ch" in reason and "five" in reason


def test_duplicate_section(tmp_path):
    import utils

    path = tmp_path / "daq_chain_config.ini"
    path.write_text(GOOD_INI + "\n[hw]\nnum_ch = 4\n")
    values, reason = utils.load_daq_ini(str(path))
    assert values is None
    assert "section 'hw' already exists" in reason


def test_read_config_file_dict_keeps_its_contract(tmp_path):
    import utils

    path = tmp_path / "daq_chain_config.ini"
    path.write_text(GOOD_INI.replace("num_ch = 5", "num_ch = five"))
    assert utils.read_config_file_dict(str(path)) is None
