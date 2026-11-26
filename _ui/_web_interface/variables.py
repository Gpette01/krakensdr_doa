import json
import os
import platform
import sys

import numpy as np
import plotly.express as px
import plotly.graph_objects as go

trace_colors = px.colors.qualitative.Plotly
trace_colors[3] = "rgb(255,255,51)"

current_path = os.path.dirname(os.path.realpath(__file__))
root_path = os.path.dirname(os.path.dirname(current_path))
shared_path = os.path.join(root_path, "_share")

INVALID_SETTINGS_FILE_TIMESTAMP = -np.inf
# Load settings file
settings_file_path = os.path.join(shared_path, "settings.json")
try:
    with open(settings_file_path, "r", encoding="utf-8") as myfile:
        dsp_settings = json.load(myfile)
except Exception:
    dsp_settings = dict()
    dsp_settings["timestamp"] = INVALID_SETTINGS_FILE_TIMESTAMP
else:
    dsp_settings["timestamp"] = os.stat(settings_file_path).st_mtime

try:
    import git

    SOFTWARE_GIT_SHORT_HASH = git.Repo().head.object.hexsha[:7]
except Exception:
    SOFTWARE_GIT_SHORT_HASH = "e5df8c9"

SOFTWARE_VERSION = "1.8.1"
SYSTEM_UNAME = platform.uname()

status_file_path = os.path.join(shared_path, "status.json")

daq_subsystem_path = os.path.join(os.path.join(os.path.dirname(root_path), "heimdall_daq_fw"), "Firmware")

daq_config_filename = os.path.join(daq_subsystem_path, "daq_chain_config.ini")

# Import Kraken SDR modules
receiver_path = os.path.join(root_path, "_sdr/_receiver")
signal_processor_path = os.path.join(root_path, "_sdr/_signal_processing")
ui_path = os.path.join(root_path, "_ui")
tak_folder_exists = os.path.exists(os.path.join(os.path.dirname(root_path), "Kraken-to-TAK-Python"))

sys.path.insert(0, receiver_path)
sys.path.insert(0, signal_processor_path)
sys.path.insert(0, ui_path)

daq_preconfigs_path = os.path.join(os.path.join(os.path.dirname(root_path), "heimdall_daq_fw"), "config_files")
daq_config_filename = os.path.join(daq_subsystem_path, "daq_chain_config.ini")
daq_stop_filename = "daq_stop.sh"
daq_start_filename = "daq_start_sm.sh"
# daq_start_filename    = "daq_synthetic_start.sh"
sys.path.insert(0, daq_subsystem_path)

valid_fir_windows = [
    "boxcar",
    "triang",
    "blackman",
    "hamming",
    "hann",
    "bartlett",
    "flattop",
    "parzen",
    "bohman",
    "blackmanharris",
    "nuttall",
    "barthann",
]
valid_sample_rates = [0.25, 0.900001, 1.024, 1.4, 1.8, 1.92, 2.048, 2.4, 2.56, 3.2]
valid_daq_buffer_sizes = (2 ** np.arange(10, 21, 1)).tolist()
calibration_tack_modes = [["No tracking", 0], ["Periodic tracking", 2]]
doa_trace_colors = {
    "DoA Bartlett": "#00B5F7",
    "DoA Capon": "rgb(226,26,28)",
    "DoA MEM": "#1CA71C",
    "DoA TNA": "rgb(255, 0, 255)",
    "DoA MUSIC": "rgb(257,233,111)",
}
figure_font_size = 20

y = np.random.normal(0, 1, 2**1)
x = np.arange(2**1)

fig_layout = go.Layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    template="plotly_dark",
    showlegend=True,
    margin=go.layout.Margin(t=0),  # top margin
)
doa_fig = go.Figure(layout=fig_layout)

option = [{"label": "", "value": 1}]

DECORRELATION_OPTIONS = [
    {"label": "Off", "value": "Off"},
    {"label": "F-B Averaging", "value": "FBA"},
    {"label": "Toeplizification", "value": "TOEP"},
    {"label": "Spatial Smoothing", "value": "FBSS"},
]

DOA_METHODS = [
    {"label": "Bartlett", "value": "Bartlett"},
    {"label": "Capon", "value": "Capon"},
    {"label": "MEM", "value": "MEM"},
    {"label": "TNA", "value": "TNA"},
    {"label": "MUSIC", "value": "MUSIC"},
    {"label": "ROOT-MUSIC", "value": "ROOT-MUSIC"},
]

HZ_TO_MHZ = 1.0e-6

DEFAULT_MAPPING_SERVER_ENDPOINT = "wss://map.krakenrf.com:2096"

AUTO_GAIN_VALUE = -100.0

# settings.json "logging_level" times 10 is the Python logging level. 3 = WARNING, so errors are visible by default.
DEFAULT_LOGGING_LEVEL = 3

MAX_VFOS = 16  # SignalProcessor.max_vfos (kraken_sdr_signal_processor.py:151)
KRAKENSDR_CHANNELS = 5  # used when the DAQ ini gives no channel count
DEFAULT_CENTER_FREQ_MHZ = 416.588

# The one set of settings.json defaults, used at startup, by the settings watcher and by Reset (finding D-24).
# Where the three used to disagree, the startup value was kept. Order follows save_configuration().
DEFAULT_SETTINGS = {
    "center_freq": DEFAULT_CENTER_FREQ_MHZ,
    "uniform_gain": 15.7,
    "data_interface": "shmem",
    "default_ip": "0.0.0.0",
    "en_remote_control": False,
    "en_doa": True,
    "ant_arrangement": "UCA",
    "ula_direction": "Both",
    "ant_spacing_meters": 0.21,
    "custom_array_x_meters": "0.21,0.06,-0.17,-0.17,0.07",
    "custom_array_y_meters": "0.0,-0.2,-0.12,0.12,0.2",
    "array_offset": 0,
    "doa_method": "MUSIC",
    "doa_decorrelation_method": "Off",
    "compass_offset": 0,
    "doa_fig_type": "Linear",
    "en_peak_hold": False,
    "expected_num_of_sources": 1,
    "en_system_control": False,
    "en_beta_features": False,
    "en_hw_check": 0,
    "logging_level": DEFAULT_LOGGING_LEVEL,
    "disable_tooltips": 0,
    "doa_data_format": "Kraken App",
    "station_id": "NOCALL",
    "location_source": "None",
    "latitude": 0.0,
    "longitude": 0.0,
    "heading": 0.0,
    "krakenpro_key": "0ae4ca6b3",
    "mapping_server_url": DEFAULT_MAPPING_SERVER_ENDPOINT,
    "rdf_mapper_server": "http://MY_RDF_MAPPER_SERVER.com/save.php",
    "gps_fixed_heading": False,
    "gps_min_speed": 2,
    "gps_min_speed_duration": 3,
    "spectrum_calculation": "Single",
    "vfo_mode": "Standard",
    "vfo_default_squelch_mode": "Auto",
    "vfo_default_demod": "None",
    "vfo_default_iq": "False",
    "max_demod_timeout": 60,
    "dsp_decimation": 1,
    "active_vfos": 1,
    "output_vfo": 0,
    "en_optimize_short_bursts": False,
}
for _vfo in range(MAX_VFOS):
    DEFAULT_SETTINGS[f"vfo_bw_{_vfo}"] = 12500
    DEFAULT_SETTINGS[f"vfo_fir_order_factor_{_vfo}"] = 2
    DEFAULT_SETTINGS[f"vfo_freq_{_vfo}"] = DEFAULT_CENTER_FREQ_MHZ * 1e6  # Hz; a missing VFO frequency means center
    DEFAULT_SETTINGS[f"vfo_squelch_mode_{_vfo}"] = "Default"
    DEFAULT_SETTINGS[f"vfo_squelch_{_vfo}"] = -120
    DEFAULT_SETTINGS[f"vfo_demod_{_vfo}"] = "Default"
    DEFAULT_SETTINGS[f"vfo_iq_{_vfo}"] = "Default"


def setting(settings, key):
    """settings[key], or its default from DEFAULT_SETTINGS."""
    return settings.get(key, DEFAULT_SETTINGS[key])


AGC_WARNING = "WARNING: Automatic gain control might lead to erroneous results because (a) it can overshoot and overdrive ADC and (b) gains are controlled independently on each channel."
AGC_WARNING_DISABLED_STYLE = {"display": "none"}
AGC_WARNING_ENABLED_STYLE = {"color": "#f39c12", "display": "block"}
