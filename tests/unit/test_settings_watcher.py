# The settings watcher (utils.settings_change_watcher) against the startup path of kraken_web_interface.py.
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

CENTER_MHZ = 416.588
CUSTOM_X_M = [0.21, 0.06, -0.17, -0.17, 0.07]
CUSTOM_Y_M = [0.00, -0.20, -0.12, 0.12, 0.20]


def fake_web_interface():
    """The attributes settings_change_watcher reads and writes. No DAQ, no threads."""
    max_vfos = 16
    signal_processor = SimpleNamespace(
        max_vfos=max_vfos,
        channel_number=5,
        vfo_bw=[12500] * max_vfos,
        vfo_fir_order_factor=[2] * max_vfos,
        vfo_freq=[CENTER_MHZ * 1e6] * max_vfos,
        vfo_squelch_mode=["Default"] * max_vfos,
        vfo_squelch=[-80] * max_vfos,
        vfo_demod=["Default"] * max_vfos,
        vfo_iq=["Default"] * max_vfos,
    )
    return SimpleNamespace(
        module_signal_processor=signal_processor,
        # The receiver holds the center frequency in Hz (kraken_web_interface.py:64-66).
        module_receiver=SimpleNamespace(daq_center_freq=CENTER_MHZ * 1e6, daq_rx_gain=15.7),
        daq_center_freq=CENTER_MHZ,  # MHz, as fetch_dsp_data writes it (utils.py:153)
        daq_fs=2.4,
        logger=SimpleNamespace(error=lambda *args: None),
        config_daq_rf=lambda *args: None,
        save_configuration=lambda: None,
        needs_refresh=False,
    )


@pytest.mark.xfail(strict=True, reason="D-30")
def test_watcher_scales_custom_array_like_the_startup_path(tmp_path, monkeypatch):
    import utils
    import variables

    settings_file = tmp_path / "settings.json"
    settings = {
        "center_freq": CENTER_MHZ,
        "uniform_gain": 15.7,
        "ant_arrangement": "Custom",
        "custom_array_x_meters": ",".join(str(v) for v in CUSTOM_X_M),
        "custom_array_y_meters": ",".join(str(v) for v in CUSTOM_Y_M),
        "ext_upd_flag": False,
    }
    settings_file.write_text(json.dumps(settings))
    monkeypatch.setattr(variables, "dsp_settings", {"timestamp": -math.inf})
    web_interface = fake_web_interface()

    utils.settings_change_watcher(web_interface, str(settings_file))
    web_interface.settings_change_timer.cancel()

    # Startup path: metres divided by the wavelength 300 / f[MHz] (kraken_web_interface.py:111-116).
    wavelength_m = 300 / CENTER_MHZ
    np.testing.assert_allclose(
        web_interface.module_signal_processor.custom_array_x, np.array(CUSTOM_X_M) / wavelength_m
    )
    np.testing.assert_allclose(
        web_interface.module_signal_processor.custom_array_y, np.array(CUSTOM_Y_M) / wavelength_m
    )
