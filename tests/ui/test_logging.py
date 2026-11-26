# Default logging: with no logging_level in settings.json, errors must reach ui.log (stderr of app.py).
from ui import sandbox


def test_errors_are_logged_with_default_settings(tmp_path):
    _, output = sandbox.run_probe(tmp_path, "logging")
    for name in ("kraken_sdr_signal_processor", "kraken_sdr_receiver", "kraken_web_interface"):
        assert f"probe error from {name}" in output
        # The default level is WARNING, so INFO stays quiet.
        assert f"probe info from {name}" not in output
