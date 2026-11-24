# Independent synthetic IQ for the tests. Nothing here imports repo code, so the frames are a
# reference that does not share bugs with the DSP under test.
import numpy as np

C = 299_792_458.0  # m/s. The DSP uses 300 m/us; the model uses the physical constant on purpose.
FS = 2_400_000  # IQ sample rate written into the header [Hz]
CENTER = 416_588_000  # default center frequency of the UI (kraken_web_interface.py:59) [Hz]
F_OFF = 100_000.0  # tone offset from the center frequency [Hz]
M = 5  # KrakenSDR channel count


def element_positions(geometry, spacing_m=0.21, radius_m=0.21, custom_x_m=None, custom_y_m=None):
    """Element positions in metres.

    UCA: element n at angle -2*pi*n/M (clockwise numbering, as the DSP assumes).
    ULA: element 0 at the origin, the others along -y.
    Custom: the given coordinates.
    """
    n = np.arange(M)
    if geometry == "UCA":
        angle = -2 * np.pi * n / M
        return radius_m * np.cos(angle), radius_m * np.sin(angle)
    if geometry == "ULA":
        return np.zeros(M), -n * spacing_m
    if geometry == "Custom":
        return np.asarray(custom_x_m, dtype=float), np.asarray(custom_y_m, dtype=float)
    raise ValueError(f"unknown geometry {geometry!r}")


def synth_frame(n, sources, geometry, seed, center=CENTER, spacing_m=0.21, radius_m=0.21, custom_xy_m=None):
    """One (M, n) complex64 frame: CW plane waves plus unit-power complex white noise per channel.

    sources: list of (azimuth_deg, snr_db, f_off_hz). Azimuth is counter-clockwise from +x, towards
    the source. snr_db is the wideband per-channel SNR (tone power over noise power in the full FS band).
    RandomState is used because its stream is frozen across numpy versions.
    """
    rng = np.random.RandomState(seed)
    custom_x, custom_y = (None, None) if custom_xy_m is None else custom_xy_m
    x, y = element_positions(geometry, spacing_m, radius_m, custom_x, custom_y)
    t = np.arange(n) / FS
    noise = (rng.standard_normal((M, n)) + 1j * rng.standard_normal((M, n))) / np.sqrt(2)
    frame = noise
    for azimuth_deg, snr_db, f_off in sources:
        wavelength = C / (center + f_off)
        theta = np.deg2rad(azimuth_deg)
        steering = np.exp(1j * 2 * np.pi / wavelength * (x * np.cos(theta) + y * np.sin(theta)))
        tone = 10 ** (snr_db / 20) * np.exp(1j * 2 * np.pi * f_off * t)
        frame = frame + steering[:, None] * tone[None, :]
    return np.ascontiguousarray(frame.astype(np.complex64))


def angle_error(estimate_deg, true_deg):
    """Signed difference in (-180, 180]."""
    return (estimate_deg - true_deg + 180) % 360 - 180
