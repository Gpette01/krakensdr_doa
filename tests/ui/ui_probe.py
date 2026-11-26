"""Imports the UI in a sandbox copy and reports facts as one JSON line. Run by tests/ui (never by hand on a device).

usage: ui_probe.py <sandbox _ui/_web_interface dir> layout
       ui_probe.py <sandbox _ui/_web_interface dir> server <port>
       ui_probe.py <sandbox _ui/_web_interface dir> logging
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
    kraken_sdr_signal_processor.SignalProcessor.start = lambda self: None
    import app
    import callbacks.main

    # Callbacks run reboot, shutdown and the start scripts (callbacks/main.py:389-418,1080-1086).
    callbacks.main.subprocess = types.SimpleNamespace(Popen=blocked, call=blocked, run=blocked)
    for name in ("Popen", "call", "run", "check_call", "check_output"):
        setattr(subprocess, name, blocked)
    os.system = blocked
    return app


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
    if mode == "layout":
        print(json.dumps(layout_facts(app)), flush=True)
        os._exit(0)
    server_facts(app, int(sys.argv[3]))


if __name__ == "__main__":
    main()
