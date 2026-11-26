# Case description and a runner that pushes cases through the real SignalProcessor.run().
import logging
from dataclasses import dataclass, field

import numpy as np
from helpers import synth
from helpers.stubs import ErrorCapture, FrozenPacketQueue, StopFrames, StubReceiver


@dataclass
class Case:
    label: str
    geometry: str  # "UCA", "ULA" or "Custom"
    algorithm: str
    sources: list  # [(azimuth_deg, snr_db, f_off_hz)]
    seed: int = 1
    center: int = synth.CENTER
    decorrelation: str = "Off"
    array_offset: int = 0
    expected_sources: int = 1
    ula_direction: str = "Both"
    radius_m: float = 0.21
    spacing_m: float = 0.21
    custom_xy_m: tuple = None
    vfo_bw: int = 12500
    vfo_offsets: tuple = (synth.F_OFF,)  # one VFO per offset, relative to the center frequency
    dsp_decimation: int = 1
    header_center: int = None  # centre frequency in the frame header when it differs from the UI value (a retune)
    extra: dict = field(default_factory=dict)

    @property
    def rf_center(self):
        """The frequency the DAQ is really tuned to: the header value."""
        return self.header_center or self.center

    @property
    def true_deg(self):
        return self.sources[0][0]

    def frame_key(self):
        return (
            self.geometry,
            tuple(self.sources),
            self.seed,
            self.rf_center,
            self.radius_m,
            self.spacing_m,
            self.custom_xy_m,
        )

    def make_frame(self, n):
        return synth.synth_frame(
            n,
            self.sources,
            self.geometry,
            self.seed,
            center=self.rf_center,
            spacing_m=self.spacing_m,
            radius_m=self.radius_m,
            custom_xy_m=self.custom_xy_m,
        )

    def sp_settings(self):
        """The SignalProcessor attributes that the UI would set for this case (kraken_web_interface.py:80-120)."""
        # The UI converts metres to wavelengths with the 300/f_MHz shortcut; this mirrors it.
        wavelength_m = 300 / (self.center / 1e6)
        settings = {
            "DOA_algorithm": self.algorithm,
            "DOA_ant_alignment": self.geometry,
            "DOA_decorrelation_method": self.decorrelation,
            "ula_direction": self.ula_direction,
            "array_offset": self.array_offset,
            "DOA_expected_num_of_sources": self.expected_sources,
            "DOA_data_format": "Kraken App",  # file output only, never a network format
            "dsp_decimation": self.dsp_decimation,
            "active_vfos": len(self.vfo_offsets),
            "output_vfo": -1 if len(self.vfo_offsets) > 1 else 0,
        }
        if self.geometry == "UCA":
            chord_m = np.sqrt(2) * self.radius_m * np.sqrt(1 - np.cos(np.deg2rad(360 / synth.M)))
            settings["DOA_UCA_radius_m"] = self.radius_m
            settings["DOA_inter_elem_space"] = chord_m / wavelength_m
        elif self.geometry == "ULA":
            settings["DOA_UCA_radius_m"] = np.inf
            settings["DOA_inter_elem_space"] = self.spacing_m / wavelength_m
        else:
            settings["DOA_UCA_radius_m"] = np.inf
            settings["DOA_inter_elem_space"] = self.spacing_m / wavelength_m
            settings["custom_array_x"] = np.asarray(self.custom_xy_m[0]) / wavelength_m
            settings["custom_array_y"] = np.asarray(self.custom_xy_m[1]) / wavelength_m
        settings.update(self.extra)
        return settings


def exception_line(message):
    """The 'SomeError: text' line of a logged traceback, or its last non-empty line."""
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    for line in reversed(lines):
        name = line.split(":", 1)[0]
        if name.replace(".", "").replace("_", "").isalnum() and name.endswith(("Error", "Exception")):
            return line[:300]
    return lines[-1][:300] if lines else ""


@dataclass
class FrameResult:
    case: Case
    packet: dict
    errors: list

    @property
    def doa_max(self):
        return float(self.packet["DoA Max"]) if "DoA Max" in self.packet else None

    @property
    def squelch_open(self):
        return bool(self.packet["DoA Squelch"][0]) if "DoA Squelch" in self.packet else False

    def usable_estimate(self):
        """The estimate, or None when it does not count.

        A result counts only when the squelch flag is open and nothing was logged at ERROR level, because the
        DSP swallows exceptions and leaves theta at its default of 0 (kraken_sdr_signal_processor.py:488).
        """
        if not self.squelch_open or self.errors:
            return None
        return self.doa_max

    def describe(self):
        last_error = exception_line(self.errors[-1]) if self.errors else "none"
        return (
            f"{self.case.label}: estimate={self.doa_max} squelch_open={self.squelch_open} "
            f"errors={len(self.errors)} last_error={last_error}"
        )


def run_cases(make_sp, cases, n=2**16, en_spectrum=False, prepare=None):
    """Process each case as one frame through SignalProcessor.run(). Returns one FrameResult per case.

    prepare(sp, receiver), when given, is called once before run(), for example to wrap an output writer.
    """
    capture = ErrorCapture()
    sp_holder = []

    def apply_case(case):
        sp = sp_holder[0]
        for name, value in case.sp_settings().items():
            setattr(sp, name, value)
        for vfo, offset in enumerate(case.vfo_offsets):
            sp.vfo_freq[vfo] = case.center + offset
            sp.vfo_bw[vfo] = case.vfo_bw

    receiver = StubReceiver(cases, n, apply_case, capture)
    # Results are read after the whole run, so each packet is frozen when it is put.
    queue = FrozenPacketQueue()
    sp = make_sp(queue, receiver)
    sp_holder.append(sp)
    sp.en_spectrum = en_spectrum
    if prepare is not None:
        prepare(sp, receiver)
    root = logging.getLogger()
    root.addHandler(capture)
    try:
        sp.run()
    except StopFrames:
        pass
    finally:
        root.removeHandler(capture)
    if len(queue.items) != len(cases):
        # Not an AssertionError, so that a broken harness can never count as an expected failure.
        raise RuntimeError(f"{len(queue.items)} packets for {len(cases)} cases")
    return [
        FrameResult(case, dict(packet), capture.for_frame(i))
        for i, (case, packet) in enumerate(zip(cases, queue.items))
    ]
