# Contract tests: freeze every output format as the code writes it TODAY (task M2-11).
#
# Field names, order, units and the bearing convention are asserted exactly; float values are compared with
# tolerances, so these tests hold on any CPU. Today the Kraken App CSV and Kerberos send 360 - theta, every other
# format sends theta (finding P-25). Nothing reaches the network: the HTTP pool and requests.get are replaced.
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import synth
from helpers.dsp import Case, run_cases

N_SAMPLES = 2**16
LATENCY_MS = int(N_SAMPLES * 1000 / synth.FS)  # CPI length in ms (kraken_sdr_signal_processor.py:744-749)
STATION = {"station_id": "TEST-1", "latitude": 50.0, "longitude": 6.0, "heading": 10.0}
STUB_IP = "203.0.113.5"  # documentation address (RFC 5737)
FORMATS = ("Kraken App", "Kerberos App", "Kraken Pro Local", "RDF Mapper", "Full POST")
VFO_SETUPS = {
    "one VFO": ([(123, 0, synth.F_OFF)], (synth.F_OFF,)),
    "two VFOs": ([(123, 0, synth.F_OFF), (240, 0, -300_000.0)], (synth.F_OFF, -300_000.0)),
}
FLOAT_TOLERANCE = 1e-6
VFO_1_ALONE = "two VFOs, VFO 1 alone/Kraken App"

CSV_FIELDS = [
    "time_ms",
    "bearing_360_minus_theta",
    "confidence",
    "power_db",
    "freq_hz",
    "array",
    "latency_ms",
    "station_id",
    "latitude",
    "longitude",
    "heading",
    "heading_again",
    "GPS",
    "R",
    "R",
    "R",
    "R",
]  # then 360 DoA values (kraken_sdr_signal_processor.py:759-770)
XML_ELEMENTS = [
    "DATA",
    "STATION_ID",
    "TIME",
    "GPS_TIME",
    "FREQUENCY",
    "LOCATION",
    "LATITUDE",
    "LONGITUDE",
    "HEADING",
    "SPEED",
    "DOA",
    "PWR",
    "CONF",
    "LATENCY",
    "PROCESSING_TIME",
    "ADC_OVERDRIVE",
    "NUM_CORRELATED_SOURCES",
    "SNR_DB",
]
JSON_KEYS = [
    "station_id",
    "tStamp",
    "gps_timestamp",
    "latitude",
    "longitude",
    "gpsBearing",
    "speed",
    "radioBearing",
    "conf",
    "power",
    "freq",
    "antType",
    "latency",
    "processing_time",
    "doaArray",
    "adc_overdrive",
    "num_corr_sources",
    "snr_db",
]
RDF_KEYS = ["id", "time", "slat", "slng", "elat", "elng"]
FULL_POST_KEYS = [
    "id",
    "ip",
    "time",
    "gps_timestamp",
    "lat",
    "lng",
    "gpsheading",
    "speed",
    "radiobearing",
    "conf",
    "power",
    "freq",
    "anttype",
    "latency",
    "processing_time",
    "doaarray",
    "adc_overdrive",
    "num_corr_sources",
    "snr_db",
]
STATUS_KEYS = [
    "timestamp_ms",
    "station_id",
    "hardware_id",
    "unit_id",
    "host_os_type",
    "host_os_version",
    "host_os_architecture",
    "software_version",
    "software_git_short_hash",
    "uptime_ms",
    "gps_status",
    "daq_status",
    "daq_ok",
    "daq_num_dropped_frames",
]
DAQ_STATUS_KEYS = [
    "data_frame_index",
    "frame_sync",
    "sample_delay_sync",
    "iq_sync",
    "noise_source_enabled",
    "adc_overdrive",
    "sampling_frequency_hz",
    "bandwidth_hz",
    "decimated_bandwidth_hz",
    "buffer_size_ms",
]


def contract_cases():
    cases = []
    for setup, (sources, offsets) in VFO_SETUPS.items():
        for data_format in FORMATS:
            extra = dict(STATION, DOA_data_format=data_format, en_data_record=True, write_interval=-1)
            # Both POST formats send at most once per second (kraken_sdr_signal_processor.py:836-840,860-862).
            extra["rdf_mapper_last_write_time"] = 0
            cases.append(
                Case(f"{setup}/{data_format}", "UCA", "MUSIC", sources, seed=31, vfo_offsets=offsets, extra=extra)
            )
    # The frame of "two VFOs" with VFO 1 alone: its doa.xml holds the diagnostics of VFO 1 (M2-08).
    sources, offsets = VFO_SETUPS["two VFOs"]
    extra = dict(STATION, DOA_data_format="Kraken App", en_data_record=False)
    cases.append(Case(VFO_1_ALONE, "UCA", "MUSIC", sources, seed=31, vfo_offsets=offsets[1:], extra=extra))
    return cases


@pytest.fixture(scope="module")
def frames(make_sp_module):
    """Runs every contract case; returns {label: what the frame wrote and sent}."""
    import kraken_sdr_signal_processor as ksp

    captured = {}
    cases = contract_cases()

    def prepare(sp, receiver):
        original_wr_xml = sp.wr_xml
        share = Path(ksp.shared_path)
        recording = Path(ksp.root_path) / sp.data_recording_file_name
        recorded_so_far = [0]

        def record_frame(*args):
            original_wr_xml(*args)
            sp.data_record_fd.flush()
            text = recording.read_text()
            frame = captured.setdefault(cases[receiver.next_index - 1].label, {"posts": []})
            frame["doa_value"] = (share / "DOA_value.html").read_text()
            frame["doa_xml"] = (share / "doa.xml").read_text()
            frame["status"] = (share / "status.json").read_text()
            frame["recording"] = text[recorded_so_far[0] :]
            frame["header_time_ms"] = receiver.iq_header.time_stamp
            recorded_so_far[0] = len(text)

        def capture_post(function, args=(), kwds=None):
            frame = captured.setdefault(cases[receiver.next_index - 1].label, {"posts": []})
            frame["posts"].append({"function": function, "args": list(args), "kwds": dict(kwds or {})})

        sp.wr_xml = record_frame
        sp.pool.apply_async = capture_post

    def no_network(*args, **kwargs):
        if "ip.seeip.org" in str(args):
            return SimpleNamespace(text=json.dumps({"ip": STUB_IP}))
        raise AssertionError(f"unexpected network call {args!r}")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(ksp.requests, "get", no_network)
        monkeypatch.setattr(ksp.requests, "post", no_network)
        results = run_cases(make_sp_module, cases, n=N_SAMPLES, prepare=prepare)
    for result in results:
        frame = captured[result.case.label]
        frame["case"] = result.case
        frame["packet"] = result.packet
        frame["errors"] = result.errors
    return captured


def thetas(frame):
    return list(frame["packet"]["DoA Max List"][: len(frame["case"].vfo_offsets)])


def vfo_freqs(frame):
    return [int(synth.CENTER + offset) for offset in frame["case"].vfo_offsets]


def csv_lines(text):
    lines = text.split("\n")
    assert lines[-1] == "" and all(line.endswith(" ") for line in lines[:-1]), repr(text[-50:])
    return [[field.strip() for field in line.split(",")] for line in lines[:-1]]


def xml_diagnostics(frame):
    text = {element.tag: element.text for element in ET.fromstring(frame["doa_xml"]).iter()}
    return text["NUM_CORRELATED_SOURCES"], float(text["SNR_DB"])


def test_json_diagnostics_belong_to_each_vfo(frames):
    """M2-08 (D-37): each VFO's JSON message carries that VFO's correlated-source count and SNR, not VFO 0's."""
    posts = frames["two VFOs/Kraken Pro Local"]["posts"]
    expected = [xml_diagnostics(frames["two VFOs/Kraken Pro Local"]), xml_diagnostics(frames[VFO_1_ALONE])]
    assert expected[0][1] != expected[1][1], "the two VFOs need different SNRs for this test"
    sent = [(post["kwds"]["json"]["num_corr_sources"], post["kwds"]["json"]["snr_db"]) for post in posts]
    assert sent == expected


@pytest.mark.parametrize("snr_db, sent", [(math.inf, 100.0), (-math.inf, -50.0), (math.nan, -50.0), (12.5, 12.5)])
def test_json_snr_is_always_a_number(make_sp, snr_db, sent):
    """M2-08 (D-51): a noise eigenvalue of 0 gave SNR = inf, which is not valid JSON."""
    sp = make_sp(None, SimpleNamespace(daq_center_freq=synth.CENTER))
    posts = []
    sp.pool.apply_async = lambda function, args=(), kwds=None: posts.append(kwds)
    sp.wr_json("TEST-1", "123.0", "25.00", "-40.0", synth.CENTER, np.zeros(360), 0.0, 0.0, 0.0, 0.0, 0, 0, snr_db)
    body = posts[0]["json"]
    json.dumps(body, allow_nan=False)  # raises for inf and nan
    assert body["snr_db"] == sent


@pytest.mark.parametrize("setup", VFO_SETUPS)
def test_frames_are_clean_and_on_target(frames, setup):
    for data_format in FORMATS:
        frame = frames[f"{setup}/{data_format}"]
        assert frame["errors"] == []
        assert thetas(frame) == [float(azimuth) for azimuth, _, _ in frame["case"].sources]


@pytest.mark.parametrize("setup", VFO_SETUPS)
def test_kraken_app_csv(frames, setup):
    frame = frames[f"{setup}/Kraken App"]
    lines = csv_lines(frame["doa_value"])
    assert len(lines) == len(frame["case"].vfo_offsets)
    for fields, theta, freq in zip(lines, thetas(frame), vfo_freqs(frame)):
        assert len(fields) == len(CSV_FIELDS) + 360
        assert int(fields[0]) == frame["header_time_ms"]
        assert float(fields[1]) == 360 - theta
        assert fields[4:][:13] == [
            str(freq),
            "UCA",
            str(LATENCY_MS),
            "TEST-1",
            "50.0",
            "6.0",
            "10.0",
            "10.0",
            "GPS",
            "R",
            "R",
            "R",
            "R",
        ]
        doa_values = np.array([float(value) for value in fields[len(CSV_FIELDS) :]])
        assert doa_values.min() == 0.0 and doa_values.argmax() == theta  # shifted so the minimum is 0
    if setup == "one VFO":
        # Anchors for the other formats: confidence and power of the single VFO.
        assert float(lines[0][2]) == pytest.approx(
            float(np.max(frame["packet"]["DoA Confidence"])), abs=FLOAT_TOLERANCE
        )
        assert float(lines[0][3]) == pytest.approx(float(frame["packet"]["max_amplitude"]), abs=FLOAT_TOLERANCE)


@pytest.mark.parametrize("setup", VFO_SETUPS)
def test_recording_line_equals_the_csv(frames, setup):
    frame = frames[f"{setup}/Kraken App"]
    assert frame["recording"] == frame["doa_value"]


@pytest.mark.parametrize("setup", VFO_SETUPS)
def test_kerberos(frames, setup):
    frame = frames[f"{setup}/Kerberos App"]
    match = re.fullmatch(
        r"<DATA>\n<DOA>(\d+)</DOA>\n<CONF>(\d+)</CONF>\n<PWR>(-?\d+\.\d)</PWR>\n</DATA>", frame["doa_value"]
    )
    assert match, frame["doa_value"]
    # The values of the last VFO that passed the squelch, with 360 - theta (kraken_sdr_signal_processor.py:623-625).
    last_csv = csv_lines(frames[f"{setup}/Kraken App"]["doa_value"])[-1]
    assert int(match.group(1)) == int(360 - thetas(frame)[-1])
    assert int(match.group(2)) == int(float(f"{float(last_csv[2]):.2f}") * 100)
    assert float(match.group(3)) == pytest.approx(max(-100.0, float(f"{float(last_csv[3]):.1f}") + 100), abs=0.05)


@pytest.mark.parametrize("setup", VFO_SETUPS)
@pytest.mark.parametrize("data_format", FORMATS)
def test_doa_xml(frames, setup, data_format):
    frame = frames[f"{setup}/{data_format}"]
    root = ET.fromstring(frame["doa_xml"])
    assert [element.tag for element in root.iter()] == XML_ELEMENTS
    text = {element.tag: element.text for element in root.iter()}
    first_csv = csv_lines(frames[f"{setup}/Kraken App"]["doa_value"])[0]
    assert text["STATION_ID"] == "TEST-1"
    assert int(text["TIME"]) == frame["header_time_ms"]
    assert text["FREQUENCY"] == str(vfo_freqs(frame)[0] / 1e6)  # MHz
    assert (text["LATITUDE"], text["LONGITUDE"], text["HEADING"], text["SPEED"]) == ("50.0", "6.0", "10.0", "0.0")
    assert float(text["DOA"]) == thetas(frame)[0]  # raw theta of VFO 0
    assert int(text["CONF"]) == int(float(f"{float(first_csv[2]):.2f}") * 100)
    assert float(text["PWR"]) == pytest.approx(max(-100.0, float(f"{float(first_csv[3]):.1f}") + 100), abs=0.05)
    assert text["LATENCY"] == str(LATENCY_MS)
    assert (text["ADC_OVERDRIVE"], text["NUM_CORRELATED_SOURCES"]) == ("0", "0")
    assert math.isfinite(float(text["SNR_DB"]))


@pytest.mark.parametrize("setup", VFO_SETUPS)
def test_json_to_doapost(frames, setup):
    frame = frames[f"{setup}/Kraken Pro Local"]
    csv = csv_lines(frames[f"{setup}/Kraken App"]["doa_value"])
    posts = frame["posts"]
    assert len(posts) == len(frame["case"].vfo_offsets)  # one message per VFO
    for post, theta, freq, csv_fields in zip(posts, thetas(frame), vfo_freqs(frame), csv):
        assert post["kwds"]["url"] == "http://127.0.0.1:8042/doapost"
        body = post["kwds"]["json"]
        assert list(body) == JSON_KEYS
        assert body["station_id"] == "TEST-1"
        assert body["tStamp"] == frame["header_time_ms"]
        assert (body["latitude"], body["longitude"], body["gpsBearing"], body["speed"]) == (
            "50.0",
            "6.0",
            "10.0",
            "0.0",
        )
        assert body["radioBearing"] == str(theta)  # raw theta, not 360 - theta
        assert body["conf"] == f"{float(csv_fields[2]):.2f}"
        assert body["power"] == f"{float(csv_fields[3]):.1f}"
        assert body["freq"] == freq and body["antType"] == "UCA" and body["latency"] == LATENCY_MS
        values = body["doaArray"].split(",")
        assert len(values) == 361 and values[-1] == ""  # 360 values, each followed by a comma
        assert [float(v) for v in values[:-1]] == pytest.approx(
            [float(v) for v in csv_fields[len(CSV_FIELDS) :]], abs=0.006
        )


def end_point(lat_deg, lon_deg, bearing_deg, distance_km=100, radius_km=6372.795477598):
    """Great-circle destination point, written independently of calculate_end_lat_lng."""
    lat, lon, bearing = map(math.radians, (lat_deg, lon_deg, bearing_deg))
    angle = distance_km / radius_km
    end_lat = math.asin(math.sin(lat) * math.cos(angle) + math.cos(lat) * math.sin(angle) * math.cos(bearing))
    end_lon = lon + math.atan2(
        math.sin(bearing) * math.sin(angle) * math.cos(lat), math.cos(angle) - math.sin(lat) * math.sin(end_lat)
    )
    return math.degrees(end_lat), math.degrees(end_lon)


@pytest.mark.parametrize("setup", VFO_SETUPS)
def test_rdf_mapper_post(frames, setup):
    frame = frames[f"{setup}/RDF Mapper"]
    (post,) = frame["posts"]  # one POST per frame, for VFO 0 only
    url, body = post["args"]
    assert url == "http://MY_RDF_MAPPER_SERVER.com/save.php"  # SignalProcessor default (sp:213)
    assert list(body) == RDF_KEYS
    assert (body["id"], body["time"], body["slat"], body["slng"]) == (
        "TEST-1",
        str(frame["header_time_ms"]),
        "50.0",
        "6.0",
    )
    # The line points along heading + (360 - theta) on the map (kraken_sdr_signal_processor.py:841-846,1235).
    expected = end_point(50.0, 6.0, 10.0 + 360 - int(thetas(frame)[0]))
    assert (float(body["elat"]), float(body["elng"])) == pytest.approx(expected, abs=1e-5)


@pytest.mark.parametrize("setup", VFO_SETUPS)
def test_full_post(frames, setup):
    frame = frames[f"{setup}/Full POST"]
    (post,) = frame["posts"]
    url, body = post["args"]
    assert url == "http://MY_RDF_MAPPER_SERVER.com/save.php"
    assert list(body) == FULL_POST_KEYS
    first_csv = csv_lines(frames[f"{setup}/Kraken App"]["doa_value"])[0]
    assert (body["id"], body["ip"], body["time"]) == ("TEST-1", STUB_IP, str(frame["header_time_ms"]))
    assert (body["lat"], body["lng"], body["gpsheading"], body["speed"]) == ("50.0", "6.0", "10.0", "0.0")
    assert body["radiobearing"] == str(thetas(frame)[0])  # raw theta of VFO 0
    assert body["conf"] == f"{float(first_csv[2]):.2f}"
    assert body["power"] == f"{max(-100.0, float(first_csv[3])):.1f}"
    assert (body["freq"], body["anttype"], body["latency"]) == (str(vfo_freqs(frame)[0]), "UCA", str(LATENCY_MS))
    values = body["doaarray"].split(", ")
    assert values[0] == "" and len(values) == 361  # starts with ", "
    assert (body["adc_overdrive"], body["num_corr_sources"]) == (0, 0)


def test_status_json(frames):
    frame = frames["one VFO/Kraken App"]
    status = json.loads(frame["status"])
    assert list(status) == STATUS_KEYS
    assert list(status["daq_status"]) == DAQ_STATUS_KEYS
    assert status["timestamp_ms"] == frame["header_time_ms"]
    assert status["station_id"] == "TEST-1"
    daq = status["daq_status"]
    # The stub sends a correct sync word and both sync flags set (helpers/stubs.py).
    assert (daq["frame_sync"], daq["sample_delay_sync"], daq["iq_sync"]) == (True, True, True)
    assert (daq["noise_source_enabled"], daq["adc_overdrive"]) == (False, False)
    assert daq["sampling_frequency_hz"] == synth.FS and daq["bandwidth_hz"] == synth.FS
    assert daq["decimated_bandwidth_hz"] == synth.FS
    assert daq["buffer_size_ms"] == pytest.approx(N_SAMPLES / synth.FS * 1e3)
    assert status["daq_ok"] is True


def test_status_json_reports_a_bad_sync_word(make_sp):
    """frame_sync follows the header sync word (kraken_sdr_signal_processor.py:318)."""
    from iq_header import IQHeader

    receiver = SimpleNamespace(iq_header=IQHeader(), daq_center_freq=synth.CENTER)
    sp = make_sp(None, receiver)
    import kraken_sdr_signal_processor as ksp

    receiver.iq_header.frame_type = IQHeader.FRAME_TYPE_DATA
    receiver.iq_header.sync_word = 0x12345678
    sp.save_processing_status()
    status = json.loads(Path(ksp.status_file_path).read_text())
    assert status["daq_status"]["frame_sync"] is False and status["daq_ok"] is False


SETTINGS_KEYS = (
    "center_freq uniform_gain data_interface default_ip en_remote_control en_doa ant_arrangement ula_direction "
    "ant_spacing_meters custom_array_x_meters custom_array_y_meters array_offset doa_method "
    "doa_decorrelation_method compass_offset doa_fig_type en_peak_hold expected_num_of_sources en_system_control "
    "en_beta_features en_hw_check logging_level disable_tooltips doa_data_format station_id location_source "
    "latitude longitude heading krakenpro_key mapping_server_url rdf_mapper_server gps_fixed_heading gps_min_speed "
    "gps_min_speed_duration spectrum_calculation vfo_mode vfo_default_squelch_mode vfo_default_demod vfo_default_iq "
    "max_demod_timeout dsp_decimation active_vfos output_vfo en_optimize_short_bursts"
).split()
VFO_SETTINGS_KEYS = "vfo_bw vfo_fir_order_factor vfo_freq vfo_squelch_mode vfo_squelch vfo_demod vfo_iq".split()


def test_settings_json_written_by_save_configuration(tmp_path, monkeypatch, make_sp):
    """save_configuration (kraken_web_interface.py:273-354), called on a stand-in for WebInterface."""
    import kraken_web_interface

    receiver = SimpleNamespace(daq_center_freq=433_920_000, daq_rx_gain=-100.0)
    sp = make_sp(None, receiver)
    web_interface = SimpleNamespace(
        module_receiver=receiver,
        module_signal_processor=sp,
        remote_control=False,
        ant_spacing_meters=0.21,
        custom_array_x_meters=np.array([0.214, 0.06, -0.17, -0.17, 0.07]),
        custom_array_y_meters=np.array([0.0, -0.2, -0.12, 0.12, 0.2]),
        compass_offset=0,
        _doa_fig_type="Polar",
        en_system_control=[1],
        en_beta_features=[],
        location_source="Static",
        mapping_server_url="wss://example.invalid:2096",
    )
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(kraken_web_interface, "settings_file_path", str(settings_file))

    kraken_web_interface.WebInterface.save_configuration(web_interface)

    data = json.loads(settings_file.read_text())
    vfo_keys = [f"{name}_{i}" for i in range(sp.max_vfos) for name in VFO_SETTINGS_KEYS]
    assert list(data) == SETTINGS_KEYS + vfo_keys + ["ext_upd_flag"]
    assert data["center_freq"] == 433.92  # MHz, from the receiver value in Hz
    assert data["uniform_gain"] == "Auto"  # -100 means automatic gain
    # Comma-separated metres; written unrounded since M1-07 (it was rounded to 1 cm, "0.21,...").
    assert data["custom_array_x_meters"] == "0.214,0.06,-0.17,-0.17,0.07"
    assert (data["en_system_control"], data["en_beta_features"]) == (True, False)
    assert data["vfo_freq_0"] == sp.vfo_freq[0] == 433_920_000  # Hz
    assert data["ext_upd_flag"] is False
