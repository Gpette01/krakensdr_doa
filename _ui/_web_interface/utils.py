import copy
import json
import os
import queue
from configparser import ConfigParser
from math import inf
from threading import Timer

import numpy as np
import variables
from dash_devices.dependencies import Output
from kraken_web_doa import plot_doa
from kraken_web_spectrum import plot_spectrum
from variables import (
    AGC_WARNING_DISABLED_STYLE,
    AGC_WARNING_ENABLED_STYLE,
    AUTO_GAIN_VALUE,
    HZ_TO_MHZ,
    daq_config_filename,
    doa_fig,
    setting,
)

RED_COLOR = {"color": "#e74c3c"}


def read_config_file_dict(config_fname=daq_config_filename):
    parser = ConfigParser()
    found = parser.read([config_fname])
    ini_data = {}
    if not found:
        return None

    ini_data["config_name"] = parser.get("meta", "config_name")
    ini_data["num_ch"] = parser.getint("hw", "num_ch")
    ini_data["en_bias_tee"] = parser.get("hw", "en_bias_tee")
    ini_data["daq_buffer_size"] = parser.getint("daq", "daq_buffer_size")
    ini_data["sample_rate"] = parser.getint("daq", "sample_rate")
    ini_data["en_noise_source_ctr"] = parser.getint("daq", "en_noise_source_ctr")
    ini_data["cpi_size"] = parser.getint("pre_processing", "cpi_size")
    ini_data["decimation_ratio"] = parser.getint("pre_processing", "decimation_ratio")
    ini_data["fir_relative_bandwidth"] = parser.getfloat("pre_processing", "fir_relative_bandwidth")
    ini_data["fir_tap_size"] = parser.getint("pre_processing", "fir_tap_size")
    ini_data["fir_window"] = parser.get("pre_processing", "fir_window")
    ini_data["en_filter_reset"] = parser.getint("pre_processing", "en_filter_reset")
    ini_data["corr_size"] = parser.getint("calibration", "corr_size")
    ini_data["std_ch_ind"] = parser.getint("calibration", "std_ch_ind")
    ini_data["en_iq_cal"] = parser.getint("calibration", "en_iq_cal")
    ini_data["gain_lock_interval"] = parser.getint("calibration", "gain_lock_interval")
    ini_data["require_track_lock_intervention"] = parser.getint("calibration", "require_track_lock_intervention")
    ini_data["cal_track_mode"] = parser.getint("calibration", "cal_track_mode")
    ini_data["amplitude_cal_mode"] = parser.get("calibration", "amplitude_cal_mode")
    ini_data["cal_frame_interval"] = parser.getint("calibration", "cal_frame_interval")
    ini_data["cal_frame_burst_size"] = parser.getint("calibration", "cal_frame_burst_size")
    ini_data["amplitude_tolerance"] = parser.getint("calibration", "amplitude_tolerance")
    ini_data["phase_tolerance"] = parser.getint("calibration", "phase_tolerance")
    ini_data["maximum_sync_fails"] = parser.getint("calibration", "maximum_sync_fails")
    ini_data["iq_adjust_source"] = parser.get("calibration", "iq_adjust_source")
    ini_data["iq_adjust_amplitude"] = parser.get("calibration", "iq_adjust_amplitude")
    ini_data["iq_adjust_time_delay_ns"] = parser.get("calibration", "iq_adjust_time_delay_ns")

    ini_data["adpis_gains_init"] = parser.get("adpis", "adpis_gains_init")

    ini_data["out_data_iface_type"] = parser.get("data_interface", "out_data_iface_type")

    return ini_data


def set_clicked(web_interface, clickData):
    M = web_interface.module_receiver.M
    curveNumber = clickData["points"][0]["curveNumber"]

    if curveNumber >= M:
        vfo_idx = int((curveNumber - M) / 2)
        web_interface.selected_vfo = vfo_idx
        if web_interface.module_signal_processor.output_vfo >= 0:
            web_interface.module_signal_processor.output_vfo = vfo_idx
            return Output("output_vfo", "value", vfo_idx)
    else:
        idx = 0
        if web_interface.module_signal_processor.output_vfo >= 0:
            idx = max(web_interface.module_signal_processor.output_vfo, 0)
        else:
            idx = web_interface.selected_vfo
        web_interface.module_signal_processor.vfo_freq[idx] = int(clickData["points"][0]["x"])
        return Output(f"vfo_{idx}_freq", "value", web_interface.module_signal_processor.vfo_freq[idx] * HZ_TO_MHZ)
    return None


def fetch_dsp_data(app, web_interface, spectrum_fig, waterfall_fig):
    daq_status_update_flag = 0
    spectrum_update_flag = 0
    doa_update_flag = 0
    # freq_update            = 0 #no_update
    #############################################
    #      Fetch new data from back-end ques    #
    #############################################
    try:
        # Fetch new data from the receiver module
        que_data_packet = web_interface.rx_data_que.get(False)
        for data_entry in que_data_packet:
            if data_entry[0] == "conn-ok":
                web_interface.daq_conn_status = 1
                daq_status_update_flag = 1
            elif data_entry[0] == "disconn-ok":
                web_interface.daq_conn_status = 0
                daq_status_update_flag = 1
            elif data_entry[0] == "config-ok":
                web_interface.daq_cfg_iface_status = 0
                daq_status_update_flag = 1
    except queue.Empty:
        # Handle empty queue here
        web_interface.logger.debug("Receiver module que is empty")
    else:
        pass
        # Handle task here and call q.task_done()
    if web_interface.daq_restart:  # Set by the restarting script
        daq_status_update_flag = 1
    try:
        # Fetch new data from the signal processing module
        que_data_packet = web_interface.sp_data_que.get(False)
        for data_entry in que_data_packet:
            if data_entry[0] == "iq_header":
                daq_status_update_flag = 1
                web_interface.logger.debug("Iq header data fetched from signal processing que")
                iq_header = data_entry[1]
                # Unpack header
                web_interface.daq_frame_index = iq_header.cpi_index
                if iq_header.frame_type == iq_header.FRAME_TYPE_DATA:
                    web_interface.daq_frame_type = "Data"
                elif iq_header.frame_type == iq_header.FRAME_TYPE_DUMMY:
                    web_interface.daq_frame_type = "Dummy"
                elif iq_header.frame_type == iq_header.FRAME_TYPE_CAL:
                    web_interface.daq_frame_type = "Calibration"
                elif iq_header.frame_type == iq_header.FRAME_TYPE_TRIGW:
                    web_interface.daq_frame_type = "Trigger wait"
                elif iq_header.frame_type == iq_header.FRAME_TYPE_EMPTY:
                    web_interface.daq_frame_type = "Empty"
                    continue
                else:
                    web_interface.daq_frame_type = "Unknown"

                web_interface.daq_frame_sync = iq_header.check_sync_word()
                web_interface.daq_power_level = iq_header.adc_overdrive_flags
                web_interface.daq_sample_delay_sync = iq_header.delay_sync_flag
                web_interface.daq_iq_sync = iq_header.iq_sync_flag
                web_interface.daq_noise_source_state = iq_header.noise_source_state

                # if web_interface.daq_center_freq != iq_header.rf_center_freq/10**6:
                #    freq_update = 1

                web_interface.daq_center_freq = iq_header.rf_center_freq / 10**6
                web_interface.daq_adc_fs = iq_header.adc_sampling_freq / 10**6
                web_interface.daq_fs = iq_header.sampling_freq / 10**6
                web_interface.daq_cpi = (
                    int(iq_header.cpi_length * 10**3 / iq_header.sampling_freq) if iq_header.sampling_freq else 0
                )
                gain_list_str = ""

                for m in range(iq_header.active_ant_chs):
                    gain_list_str += str(iq_header.if_gains[m] / 10)
                    gain_list_str += ", "

                web_interface.daq_if_gains = gain_list_str[:-2]
            elif data_entry[0] == "update_rate":
                web_interface.daq_update_rate = data_entry[1]
            elif data_entry[0] == "latency":
                web_interface.daq_dsp_latency = data_entry[1] + web_interface.daq_cpi
            elif data_entry[0] == "max_amplitude":
                web_interface.max_amplitude = data_entry[1]
            elif data_entry[0] == "avg_powers":
                avg_powers_str = ""
                for avg_power in data_entry[1]:
                    avg_powers_str += "{:.1f}".format(avg_power)
                    avg_powers_str += ", "
                web_interface.avg_powers = avg_powers_str[:-2]
            elif data_entry[0] == "spectrum":
                web_interface.logger.debug("Spectrum data fetched from signal processing que")
                spectrum_update_flag = 1
                web_interface.spectrum = data_entry[1]
            elif data_entry[0] == "doa_thetas":
                web_interface.doa_thetas = data_entry[1]
                doa_update_flag = 1
                web_interface.doa_results = []
                web_interface.doa_labels = []
                web_interface.doas = []
                web_interface.max_doas_list = []
                web_interface.doa_confidences = []
                web_interface.logger.debug("DoA estimation data fetched from signal processing que")
            elif data_entry[0] == "DoA Result":
                web_interface.doa_results.append(data_entry[1])
                web_interface.doa_labels.append(data_entry[0])
            elif data_entry[0] == "DoA Max":
                web_interface.doas.append(data_entry[1])
            elif data_entry[0] == "DoA Confidence":
                web_interface.doa_confidences.append(data_entry[1])
            elif data_entry[0] == "DoA Max List":
                web_interface.max_doas_list = data_entry[1].copy()
            elif data_entry[0] == "DoA Squelch":
                web_interface.squelch_update = data_entry[1].copy()
            elif data_entry[0] == "VFO-0 Frequency":
                app.push_mods(
                    {
                        "vfo_0_freq": {"value": data_entry[1] * HZ_TO_MHZ},
                    }
                )
            else:
                web_interface.logger.warning("Unknown data entry: {:s}".format(data_entry[0]))
    except queue.Empty:
        # Handle empty queue here
        web_interface.logger.debug("Signal processing que is empty")
    else:
        pass
        # Handle task here and call q.task_done()

    if (
        web_interface.pathname == "/config" or web_interface.pathname == "/" or web_interface.pathname == "/init"
    ) and daq_status_update_flag:
        update_daq_status(app, web_interface)
    elif web_interface.pathname == "/spectrum" and spectrum_update_flag:
        plot_spectrum(app, web_interface, spectrum_fig, waterfall_fig)
    # or (web_interface.pathname == "/doa" and
    # web_interface.reset_doa_graph_flag):
    elif web_interface.pathname == "/doa" and doa_update_flag:
        plot_doa(app, web_interface, doa_fig)

    web_interface.dsp_timer = Timer(0.01, fetch_dsp_data, args=(app, web_interface, spectrum_fig, waterfall_fig))
    web_interface.dsp_timer.start()


def fetch_gps_data(app, web_interface):
    app.push_mods(
        {
            "body_gps_latitude": {"children": web_interface.module_signal_processor.latitude},
            "body_gps_longitude": {"children": web_interface.module_signal_processor.longitude},
            "body_gps_heading": {"children": web_interface.module_signal_processor.heading},
        }
    )

    web_interface.gps_timer = Timer(1, fetch_gps_data, args=(app, web_interface))
    web_interface.gps_timer.start()


def settings_change_watcher(web_interface, settings_file_path, last_attempt_failed=False):
    if os.path.exists(settings_file_path):
        last_changed_time = os.stat(settings_file_path).st_mtime
        time_delta = last_changed_time - variables.dsp_settings["timestamp"]
        if time_delta > 0:
            # Load settings file
            try:
                with open(settings_file_path, "r", encoding="utf-8") as file:
                    dsp_settings = json.load(file)
                    if dsp_settings is None:
                        raise RuntimeError("%s appears empty" % file)
            except Exception as ex:
                if not last_attempt_failed:
                    web_interface.logger.error("Problem loading settings file: %s", ex)
                last_attempt_failed = True
            else:
                variables.dsp_settings = dsp_settings
                variables.dsp_settings["timestamp"] = last_changed_time
                last_attempt_failed = False

                center_freq = float(setting(dsp_settings, "center_freq"))
                gain = (
                    float(setting(dsp_settings, "uniform_gain"))
                    if setting(dsp_settings, "uniform_gain") != "Auto"
                    else AUTO_GAIN_VALUE
                )

                web_interface.en_system_control = [1] if setting(dsp_settings, "en_system_control") else []
                web_interface.en_beta_features = [1] if setting(dsp_settings, "en_beta_features") else []

                web_interface.module_signal_processor.en_DOA_estimation = setting(dsp_settings, "en_doa")
                web_interface.module_signal_processor.DOA_decorrelation_method = setting(
                    dsp_settings, "doa_decorrelation_method"
                )

                web_interface.module_signal_processor.DOA_ant_alignment = setting(dsp_settings, "ant_arrangement")
                web_interface.ant_spacing_meters = float(setting(dsp_settings, "ant_spacing_meters"))

                wavelength = wavelength_m(web_interface.daq_center_freq * 1e6)
                if web_interface.module_signal_processor.DOA_ant_alignment == "UCA":
                    web_interface.module_signal_processor.DOA_UCA_radius_m = web_interface.ant_spacing_meters
                    # Convert RADIUS to INTERELEMENT SPACING
                    inter_elem_spacing = (
                        np.sqrt(2)
                        * web_interface.ant_spacing_meters
                        * np.sqrt(1 - np.cos(np.deg2rad(360 / web_interface.module_signal_processor.channel_number)))
                    )
                    web_interface.module_signal_processor.DOA_inter_elem_space = inter_elem_spacing / wavelength
                else:
                    web_interface.module_signal_processor.DOA_UCA_radius_m = np.inf
                    web_interface.module_signal_processor.DOA_inter_elem_space = (
                        web_interface.ant_spacing_meters / wavelength
                    )

                web_interface.custom_array_x_meters = np.array(
                    setting(dsp_settings, "custom_array_x_meters").split(","), dtype=np.float64
                )
                web_interface.custom_array_y_meters = np.array(
                    setting(dsp_settings, "custom_array_y_meters").split(","), dtype=np.float64
                )
                web_interface.module_signal_processor.custom_array_x = web_interface.custom_array_x_meters / wavelength
                web_interface.module_signal_processor.custom_array_y = web_interface.custom_array_y_meters / wavelength

                # Station Information
                web_interface.module_signal_processor.station_id = setting(dsp_settings, "station_id")
                web_interface.location_source = setting(dsp_settings, "location_source")
                web_interface.module_signal_processor.latitude = setting(dsp_settings, "latitude")
                web_interface.module_signal_processor.longitude = setting(dsp_settings, "longitude")
                web_interface.module_signal_processor.heading = setting(dsp_settings, "heading")
                web_interface.module_signal_processor.krakenpro_key = setting(dsp_settings, "krakenpro_key")
                web_interface.mapping_server_url = setting(dsp_settings, "mapping_server_url")
                web_interface.module_signal_processor.RDF_mapper_server = setting(dsp_settings, "rdf_mapper_server")
                web_interface.module_signal_processor.DOA_data_format = setting(dsp_settings, "doa_data_format")

                # VFO Configuration
                web_interface.module_signal_processor.spectrum_fig_type = setting(dsp_settings, "spectrum_calculation")
                web_interface.module_signal_processor.vfo_mode = setting(dsp_settings, "vfo_mode")
                web_interface.module_signal_processor.vfo_default_squelch_mode = setting(
                    dsp_settings, "vfo_default_squelch_mode"
                )
                web_interface.module_signal_processor.vfo_default_demod = setting(dsp_settings, "vfo_default_demod")
                web_interface.module_signal_processor.vfo_default_iq = setting(dsp_settings, "vfo_default_iq")
                web_interface.module_signal_processor.max_demod_timeout = int(
                    setting(dsp_settings, "max_demod_timeout")
                )
                web_interface.module_signal_processor.dsp_decimation = int(setting(dsp_settings, "dsp_decimation"))
                web_interface.module_signal_processor.active_vfos = int(setting(dsp_settings, "active_vfos"))
                web_interface.module_signal_processor.output_vfo = int(setting(dsp_settings, "output_vfo"))
                web_interface.compass_offset = setting(dsp_settings, "compass_offset")
                web_interface.module_signal_processor.compass_offset = web_interface.compass_offset
                web_interface.module_signal_processor.optimize_short_bursts = setting(
                    dsp_settings, "en_optimize_short_bursts"
                )
                web_interface.module_signal_processor.en_peak_hold = setting(dsp_settings, "en_peak_hold")

                for i in range(web_interface.module_signal_processor.max_vfos):
                    web_interface.module_signal_processor.vfo_bw[i] = int(setting(dsp_settings, "vfo_bw_" + str(i)))
                    web_interface.module_signal_processor.vfo_fir_order_factor[i] = int(
                        setting(dsp_settings, "vfo_fir_order_factor_" + str(i))
                    )
                    web_interface.module_signal_processor.vfo_freq[i] = float(
                        dsp_settings.get("vfo_freq_" + str(i), center_freq * 1e6)
                    )
                    web_interface.module_signal_processor.vfo_squelch_mode[i] = setting(
                        dsp_settings, "vfo_squelch_mode_" + str(i)
                    )
                    web_interface.module_signal_processor.vfo_squelch[i] = int(
                        setting(dsp_settings, "vfo_squelch_" + str(i))
                    )
                    web_interface.module_signal_processor.vfo_demod[i] = setting(dsp_settings, "vfo_demod_" + str(i))
                    web_interface.module_signal_processor.vfo_iq[i] = setting(dsp_settings, "vfo_iq_" + str(i))

                web_interface.module_signal_processor.DOA_algorithm = setting(dsp_settings, "doa_method")
                web_interface.module_signal_processor.DOA_expected_num_of_sources = setting(
                    dsp_settings, "expected_num_of_sources"
                )
                web_interface._doa_fig_type = setting(dsp_settings, "doa_fig_type")
                web_interface.module_signal_processor.doa_measure = web_interface._doa_fig_type
                web_interface.module_signal_processor.ula_direction = setting(dsp_settings, "ula_direction")
                web_interface.module_signal_processor.array_offset = int(setting(dsp_settings, "array_offset"))

                freq_delta = web_interface.daq_center_freq - center_freq
                gain_delta = web_interface.module_receiver.daq_rx_gain - gain

                if abs(freq_delta) > 0.001 or abs(gain_delta) > 0.001:
                    web_interface.daq_center_freq = center_freq
                    web_interface.config_daq_rf(center_freq, gain)
                    for i in range(web_interface.module_signal_processor.max_vfos):
                        half_band_width = (web_interface.module_signal_processor.vfo_bw[i] / 10**6) / 2
                        min_freq = web_interface.daq_center_freq - web_interface.daq_fs / 2 + half_band_width
                        max_freq = web_interface.daq_center_freq + web_interface.daq_fs / 2 - half_band_width
                        if min_freq > (web_interface.module_signal_processor.vfo_freq[i] / 10**6) or max_freq < (
                            web_interface.module_signal_processor.vfo_freq[i] / 10**6
                        ):
                            web_interface.module_signal_processor.vfo_freq[i] = (
                                web_interface.module_receiver.daq_center_freq
                            )

                    wavelength = wavelength_m(web_interface.daq_center_freq * 1e6)
                    web_interface.module_signal_processor.custom_array_x = (
                        web_interface.custom_array_x_meters / wavelength
                    )
                    web_interface.module_signal_processor.custom_array_y = (
                        web_interface.custom_array_y_meters / wavelength
                    )

                    if web_interface.module_signal_processor.DOA_ant_alignment == "UCA":
                        # Convert RADIUS to INTERELEMENT SPACING
                        inter_elem_spacing = (
                            np.sqrt(2)
                            * web_interface.ant_spacing_meters
                            * np.sqrt(
                                1 - np.cos(np.deg2rad(360 / web_interface.module_signal_processor.channel_number))
                            )
                        )
                        web_interface.module_signal_processor.DOA_inter_elem_space = inter_elem_spacing / wavelength
                    else:
                        web_interface.module_signal_processor.DOA_inter_elem_space = (
                            web_interface.ant_spacing_meters / wavelength
                        )

                if dsp_settings.get("ext_upd_flag", False):
                    web_interface.needs_refresh = True
                    web_interface.save_configuration()

    web_interface.settings_change_timer = Timer(
        0.5, settings_change_watcher, args=(web_interface, settings_file_path, last_attempt_failed)
    )
    web_interface.settings_change_timer.start()


def update_daq_status(app, web_interface):
    #############################################
    #      Prepare UI component properties      #
    #############################################

    if web_interface.daq_frame_type == "Empty":

        daq_frame_type_str = "Empty (likely failure)"
        frame_type_style = RED_COLOR

        daq_conn_status_str = "Unknown (likely failure)"
        conn_status_style = RED_COLOR

        daq_frame_sync_str = "-"
        frame_sync_style = RED_COLOR

        daq_delay_sync_str = "-"
        delay_sync_style = RED_COLOR

        daq_iq_sync_str = "-"
        iq_sync_style = RED_COLOR

        daq_power_level_str = "-"
        daq_power_level_style = RED_COLOR

        daq_noise_source_str = "-"
        noise_source_style = RED_COLOR

        daq_frame_index_str = "-"
        daq_dsp_latency = "-"
        daq_update_rate_str = "-"

        daq_rf_center_freq_str = "-"
        daq_sampling_freq_str = "-"
        dsp_decimated_bw_str = "-"
        vfo_range_str = "-"

        daq_cpi_str = "-"
        daq_max_amp_str = "-"
        daq_avg_powers_str = "-"
    else:
        if web_interface.daq_conn_status == 1:
            if not web_interface.daq_cfg_iface_status:
                daq_conn_status_str = "Connected"
                conn_status_style = {"color": "#7ccc63"}
            else:  # Config interface is busy
                daq_conn_status_str = "Reconfiguration.."
                conn_status_style = {"color": "#f39c12"}
        else:
            daq_conn_status_str = "Disconnected"
            conn_status_style = {"color": "#e74c3c"}

        if web_interface.daq_restart:
            daq_conn_status_str = "Restarting.."
            conn_status_style = {"color": "#f39c12"}

        if web_interface.daq_update_rate < 1:
            daq_update_rate_str = "{:d} ms".format(round(web_interface.daq_update_rate * 1000))
        else:
            daq_update_rate_str = "{:.2f} s".format(web_interface.daq_update_rate)

        daq_dsp_latency = "{:d} ms".format(web_interface.daq_dsp_latency)
        daq_frame_index_str = str(web_interface.daq_frame_index)

        daq_frame_type_str = web_interface.daq_frame_type
        if web_interface.daq_frame_type == "Data":
            frame_type_style = frame_type_style = {"color": "#7ccc63"}
        elif web_interface.daq_frame_type == "Dummy":
            frame_type_style = frame_type_style = {"color": "white"}
        elif web_interface.daq_frame_type == "Calibration":
            frame_type_style = frame_type_style = {"color": "#f39c12"}
        elif web_interface.daq_frame_type == "Trigger wait":
            frame_type_style = frame_type_style = {"color": "#f39c12"}
        else:
            frame_type_style = frame_type_style = {"color": "#e74c3c"}

        if web_interface.daq_frame_sync:
            daq_frame_sync_str = "LOSS"
            frame_sync_style = {"color": "#e74c3c"}
        else:
            daq_frame_sync_str = "Ok"
            frame_sync_style = {"color": "#7ccc63"}
        if web_interface.daq_sample_delay_sync:
            daq_delay_sync_str = "Ok"
            delay_sync_style = {"color": "#7ccc63"}
        else:
            daq_delay_sync_str = "LOSS"
            delay_sync_style = {"color": "#e74c3c"}

        if web_interface.daq_iq_sync:
            daq_iq_sync_str = "Ok"
            iq_sync_style = {"color": "#7ccc63"}
        else:
            daq_iq_sync_str = "LOSS"
            iq_sync_style = {"color": "#e74c3c"}

        if web_interface.daq_noise_source_state:
            daq_noise_source_str = "Enabled"
            noise_source_style = {"color": "#e74c3c"}
        else:
            daq_noise_source_str = "Disabled"
            noise_source_style = {"color": "#7ccc63"}

        if web_interface.daq_power_level:
            daq_power_level_str = "Overdrive"
            daq_power_level_style = {"color": "#e74c3c"}
        else:
            daq_power_level_str = "OK"
            daq_power_level_style = {"color": "#7ccc63"}

        daq_rf_center_freq_str = str(web_interface.daq_center_freq)
        daq_sampling_freq_str = str(web_interface.daq_fs)
        bw = web_interface.daq_fs / web_interface.module_signal_processor.dsp_decimation
        dsp_decimated_bw_str = "{0:.3f}".format(bw)
        vfo_range_str = (
            "{0:.3f}".format(web_interface.daq_center_freq - bw / 2)
            + " - "
            + "{0:.3f}".format(web_interface.daq_center_freq + bw / 2)
        )
        daq_cpi_str = str(web_interface.daq_cpi)
        daq_max_amp_str = "{:.1f}".format(web_interface.max_amplitude)
        daq_avg_powers_str = web_interface.avg_powers

    if web_interface.module_signal_processor.gps_status == "Connected":
        gps_en_str = "Connected"
        gps_en_str_style = {"color": "#7ccc63"}
    else:
        gps_en_str = web_interface.module_signal_processor.gps_status
        gps_en_str_style = {"color": "#e74c3c"}

    app.push_mods(
        {
            "body_daq_update_rate": {"children": daq_update_rate_str},
            "body_daq_dsp_latency": {"children": daq_dsp_latency},
            "body_daq_frame_index": {"children": daq_frame_index_str},
            "body_daq_frame_sync": {"children": daq_frame_sync_str},
            "body_daq_frame_type": {"children": daq_frame_type_str},
            "body_daq_power_level": {"children": daq_power_level_str},
            "body_daq_conn_status": {"children": daq_conn_status_str},
            "body_daq_delay_sync": {"children": daq_delay_sync_str},
            "body_daq_iq_sync": {"children": daq_iq_sync_str},
            "body_daq_noise_source": {"children": daq_noise_source_str},
            "body_daq_rf_center_freq": {"children": daq_rf_center_freq_str},
            "body_daq_sampling_freq": {"children": daq_sampling_freq_str},
            "body_dsp_decimated_bw": {"children": dsp_decimated_bw_str},
            "body_vfo_range": {"children": vfo_range_str},
            "body_daq_cpi": {"children": daq_cpi_str},
            "body_daq_if_gain": {"children": web_interface.daq_if_gains},
            "body_max_amp": {"children": daq_max_amp_str},
            "body_avg_powers": {"children": daq_avg_powers_str},
            "gps_status": {"children": gps_en_str},
        }
    )

    app.push_mods(
        {
            "body_daq_frame_sync": {"style": frame_sync_style},
            "body_daq_frame_type": {"style": frame_type_style},
            "body_daq_power_level": {"style": daq_power_level_style},
            "body_daq_conn_status": {"style": conn_status_style},
            "body_daq_delay_sync": {"style": delay_sync_style},
            "body_daq_iq_sync": {"style": iq_sync_style},
            "body_daq_noise_source": {"style": noise_source_style},
            "gps_status": {"style": gps_en_str_style},
        }
    )

    # Update local recording file size
    recording_file_size = web_interface.module_signal_processor.get_recording_filesize()
    app.push_mods({"body_file_size": {"children": recording_file_size}})


def get_agc_warning_style_from_gain(gain):
    return (
        copy.deepcopy(AGC_WARNING_ENABLED_STYLE)
        if gain == AUTO_GAIN_VALUE
        else copy.deepcopy(AGC_WARNING_DISABLED_STYLE)
    )


"""
Input validation utilities
"""


def is_float(string, minimum=-inf, maximum=inf):
    try:
        f = float(string)
        return f >= minimum and f <= maximum
    except (ValueError, TypeError):
        return False


def wavelength_m(frequency_hz):
    """Wavelength in metres. 300 m * MHz, the speed-of-light shortcut used everywhere in the UI.

    One helper for the startup path, the callbacks and the settings watcher (finding D-30: the watcher passed Hz
    where the others passed MHz, so the custom array came out about a million times too large).
    """
    return 300e6 / frequency_hz


def format_custom_array(values):
    """Text for the custom array fields and settings.json, without rounding (it used to round to 1 cm)."""
    return ",".join(str(float(value)) for value in values)


def parse_custom_array(text, element_count):
    """Coordinates in metres from the comma-separated text field, or None when the text does not give exactly one
    finite number per element (finding P-22: extra coordinates used to be written past the end of the DSP array)."""
    try:
        values = np.array([float(value) for value in text.split(",")])
    except (AttributeError, ValueError):
        return None
    if len(values) != element_count or not np.all(np.isfinite(values)):
        return None
    return values


def is_int(string, minimum=-inf, maximum=inf):
    try:
        i = int(string)
        return i >= minimum and i <= maximum
    except (ValueError, TypeError):
        return False
