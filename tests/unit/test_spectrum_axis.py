# M2-05 (P-20): the frequency axis of the "Auto Channel" squelch. It was the reversed, negated axis, one bin
# (586 Hz at 2.4 MHz and 4096 bins) above the true bin frequencies. Row 0 of the spectrum is float32, so the
# relative frequencies carry up to 0.0625 Hz of rounding.
import numpy as np
import pytest

CENTER = 416_588_000.0
FLOAT32_ROUNDING_HZ = 0.0625


def axis(sample_rate, bins):
    """Row 0 of the spectrum as the DSP builds it (welch, two-sided, fftshift, stored as float32)."""
    import kraken_sdr_signal_processor as ksp

    frequencies, _ = ksp.signal.welch(
        np.ones(bins), sample_rate, nperseg=bins, nfft=bins, return_onesided=False, detrend=False
    )
    return ksp.spectrum_frequencies_hz(ksp.fft.fftshift(frequencies).astype(np.float32), CENTER)


def test_single_channel_axis_values():
    frequencies = axis(2_400_000, 4096)
    assert frequencies[0] == CENTER - 1_200_000.0
    assert frequencies[2048] == CENTER
    assert frequencies[4095] == pytest.approx(CENTER + 1_199_414.0625, abs=FLOAT32_ROUNDING_HZ)


def test_a_vfo_at_the_center_maps_to_the_center_bin():
    assert int(np.abs(axis(2_400_000, 4096) - CENTER).argmin()) == 2048


def test_all_channels_axis_step():
    frequencies = axis(2_400_000, 32768)
    assert np.diff(frequencies) == pytest.approx(np.full(32767, 73.2421875), abs=2 * FLOAT32_ROUNDING_HZ)
    assert frequencies[16384] == CENTER
