# Finding T-11: with no DAQ ini file, startup raised TypeError (kraken_web_interface.py:203) after the DSP thread
# had started, so the process hung. It must log one error and show a "DAQ configuration missing" state instead.
import json

from ui import sandbox


def test_startup_without_daq_ini(tmp_path):
    line, output = sandbox.run_probe(tmp_path, "startup_state", with_daq_ini=False, timeout=60)
    state = json.loads(line)
    assert state["active_daq_ini_cfg"] == "missing"
    assert state["dsp_thread_started"] is False
    assert "DAQ configuration missing" in state["config_page_text"]
    assert output.count("DAQ configuration file") == 1  # one clear error line


def test_startup_with_daq_ini(tmp_path):
    line, _ = sandbox.run_probe(tmp_path, "startup_state")
    state = json.loads(line)
    assert state["active_daq_ini_cfg"] == "Test fixture"
    assert state["dsp_thread_started"] is True
