"""Imports the UI in a sandbox copy and reports facts as one JSON line. Run by tests/ui (never by hand on a device).

usage: ui_probe.py <sandbox _ui/_web_interface dir> layout
       ui_probe.py <sandbox _ui/_web_interface dir> server <port>
       ui_probe.py <sandbox _ui/_web_interface dir> logging
       ui_probe.py <sandbox _ui/_web_interface dir> defaults
       ui_probe.py <sandbox _ui/_web_interface dir> startup_state
       ui_probe.py <sandbox _ui/_web_interface dir> custom_array <cases json>
       ui_probe.py <sandbox _ui/_web_interface dir> decorrelation
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import types
import urllib.request


def blocked(*args, **kwargs):
    raise RuntimeError(f"ui_probe: blocked process call {args!r}")


def import_ui(web_interface_dir):
    sys.path.insert(0, web_interface_dir)
    # isort: off
    import variables  # noqa: F401  (adds the receiver and DSP folders to sys.path, variables.py:51-60)
    import kraken_sdr_signal_processor

    # isort: on

    # No DSP thread: it would connect to the DAQ control port and spin without a DAQ (T-09).
    kraken_sdr_signal_processor.SignalProcessor.start = lambda self: setattr(self, "start_called", True)
    import app
    import callbacks.main

    # Callbacks run reboot, shutdown and the start scripts (callbacks/main.py:389-418,1080-1086).
    callbacks.main.subprocess = types.SimpleNamespace(Popen=blocked, call=blocked, run=blocked)
    for name in ("Popen", "call", "run", "check_call", "check_output"):
        setattr(subprocess, name, blocked)
    os.system = blocked
    return app


def plotly_encoder():
    import plotly

    return plotly.utils.PlotlyJSONEncoder


def walk(component, found):
    """Collects (id, type, target) for every component in a layout tree."""
    data = component.to_plotly_json() if hasattr(component, "to_plotly_json") else component
    if isinstance(data, dict):
        props = data.get("props", {})
        if "id" in props or "target" in props:
            found.append({"id": props.get("id"), "type": data.get("type"), "target": props.get("target")})
        for value in props.values():
            children = value if isinstance(value, (list, tuple)) else [value]
            for child in children:
                if hasattr(child, "to_plotly_json") or isinstance(child, dict):
                    walk(child, found)
    return found


def layout_facts(app):
    from kraken_web_config import generate_config_page_layout
    from maindash import web_interface
    from views import generate_doa_page, spectrum_page

    pages = {
        "main": app.app.layout,
        "config": generate_config_page_layout(web_interface),
        "spectrum": spectrum_page.layout,
        "doa": generate_doa_page.layout,
    }
    callbacks = []
    for output, callback in app.app.callback_map.items():
        callbacks.append(
            {
                "output": output,
                "outputs": [item["id"] for item in callback.get("outputs", [])],
                "inputs": [item["id"] for item in callback.get("inputs", [])],
                "state": [item["id"] for item in callback.get("state", [])],
            }
        )
    return {"pages": {name: walk(layout, []) for name, layout in pages.items()}, "callbacks": callbacks}


def server_facts(app, port):
    results = {}

    def probe():
        time.sleep(1)
        for path in ("/", "/_dash-layout", "/_dash-dependencies", "/config", "/doa", "/spectrum"):
            for _ in range(40):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
                        body = response.read()
                        results[path] = {"status": response.status, "bytes": len(body)}
                        if path == "/_dash-dependencies":
                            results[path]["callbacks"] = len(json.loads(body))
                    break
                except OSError as error:
                    results[path] = {"error": f"{type(error).__name__}: {error}"}
                    time.sleep(0.25)
        print(json.dumps(results), flush=True)
        os._exit(0)

    threading.Thread(target=probe, daemon=True).start()
    # run_server must run in the main thread (it installs signal handlers).
    app.app.run_server(debug=False, host="127.0.0.1", port=port)


def custom_array_by_path(cases_json):
    """For each case: the custom array that startup and the DSP callback keep (follow-up to M1-06)."""
    import kraken_web_interface
    from callbacks.main import update_dsp_params
    from maindash import web_interface

    callback = update_dsp_params.__wrapped__  # the plain function under the dash_devices wrapper
    previous = ([0.3, 0.1, -0.2, -0.2, 0.1], [0.0, -0.3, -0.1, 0.1, 0.3])
    results = {}
    for name, (x_text, y_text) in json.loads(cases_json).items():
        kraken_web_interface.dsp_settings = {
            "timestamp": 0.0,
            "custom_array_x_meters": x_text,
            "custom_array_y_meters": y_text,
        }
        started = kraken_web_interface.WebInterface()
        started.settings_change_timer.cancel()
        web_interface.custom_array_x_meters, web_interface.custom_array_y_meters = map(np_array, previous)
        callback(None, [1], "Off", 0.21, "Custom", "Linear", "MUSIC", "Both", 1, 0, 0, x_text, y_text, [])
        results[name] = {
            "startup": [list(started.custom_array_x_meters), list(started.custom_array_y_meters)],
            "callback": [list(web_interface.custom_array_x_meters), list(web_interface.custom_array_y_meters)],
        }
    return results


def np_array(values):
    import numpy

    return numpy.array(values, dtype=numpy.float64)


def decorrelation_by_path():
    """The decorrelation options, and the method a stored "FBTOEP" loads as at startup and in the watcher (M2-04)."""
    import math

    import kraken_web_interface
    import utils
    import variables
    from maindash import web_interface

    kraken_web_interface.dsp_settings = {"timestamp": 0.0, "doa_decorrelation_method": "FBTOEP"}
    started = kraken_web_interface.WebInterface()
    started.settings_change_timer.cancel()
    with open(variables.settings_file_path, "w", encoding="utf-8") as file:
        json.dump({"doa_decorrelation_method": "FBTOEP"}, file)
    variables.dsp_settings = {"timestamp": -math.inf}
    utils.settings_change_watcher(web_interface, variables.settings_file_path)
    web_interface.settings_change_timer.cancel()
    return {
        "options": [option["value"] for option in variables.DECORRELATION_OPTIONS],
        "startup": started.module_signal_processor.DOA_decorrelation_method,
        "watcher": web_interface.module_signal_processor.DOA_decorrelation_method,
    }


def default_settings_by_path():
    """settings.json as written after a start with no settings file, after Reset, and after the watcher loaded an
    empty settings file. All three must hold the same defaults (finding D-24)."""
    import math

    import utils
    import variables
    from maindash import web_interface

    settings_path = variables.settings_file_path

    def saved():
        web_interface.save_configuration()
        with open(settings_path, encoding="utf-8") as file:
            return json.load(file)

    startup = saved()
    web_interface.load_default_configuration()
    with open(settings_path, encoding="utf-8") as file:
        reset = json.load(file)
    with open(settings_path, "w", encoding="utf-8") as file:
        file.write("{}")
    variables.dsp_settings = {"timestamp": -math.inf}
    utils.settings_change_watcher(web_interface, settings_path)
    web_interface.settings_change_timer.cancel()
    watcher = saved()
    return {"startup": startup, "reset": reset, "watcher": watcher}


def main():
    web_interface_dir, mode = sys.argv[1], sys.argv[2]
    app = import_ui(web_interface_dir)
    if mode == "logging":
        # Errors from the DSP, the receiver and the UI must reach stderr (ui.log) with default settings.
        for name in ("kraken_sdr_signal_processor", "kraken_sdr_receiver", "kraken_web_interface"):
            logging.getLogger(name).error("probe error from %s", name)
            logging.getLogger(name).info("probe info from %s", name)
        print(json.dumps({"ok": True}), flush=True)
        os._exit(0)
    if mode == "decorrelation":
        print(json.dumps(decorrelation_by_path()), flush=True)
        os._exit(0)
    if mode == "custom_array":
        print(json.dumps(custom_array_by_path(sys.argv[3])), flush=True)
        os._exit(0)
    if mode == "startup_state":
        from kraken_web_config import generate_config_page_layout
        from maindash import web_interface

        page = generate_config_page_layout(web_interface)
        facts = {
            "active_daq_ini_cfg": web_interface.active_daq_ini_cfg,
            "dsp_thread_started": getattr(web_interface.module_signal_processor, "start_called", False),
            "dsp_geometry": {
                name: float(getattr(web_interface.module_signal_processor, name))
                for name in ("DOA_UCA_radius_m", "DOA_inter_elem_space", "array_offset")
            },
            "dsp_alignment": web_interface.module_signal_processor.DOA_ant_alignment,
            "daq_center_freq": float(web_interface.module_receiver.daq_center_freq),
            "config_page_text": json.dumps(page.to_plotly_json(), cls=plotly_encoder())[:200000],
        }
        print(json.dumps(facts), flush=True)
        os._exit(0)
    if mode == "defaults":
        print(json.dumps(default_settings_by_path()), flush=True)
        os._exit(0)
    if mode == "layout":
        print(json.dumps(layout_facts(app)), flush=True)
        os._exit(0)
    server_facts(app, int(sys.argv[3]))


if __name__ == "__main__":
    main()
