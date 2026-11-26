# M2-14 (P-12): the SNR field is the array (post-beamforming) SNR: element SNR + 10*log10(M) for one source. It was
# estimated from the smallest eigenvalue alone, which a finite sample biases low, so the value read high.
import numpy as np
import pytest

M = 5
ARRAY_GAIN_DB = 10 * np.log10(M)
DRAWS = 20  # noise draws per point: the mean shows the bias, which a single draw hides in its spread
BIAS_TOLERANCE_DB = 0.1  # the old estimator was 0.23 to 0.79 dB high here


def sample_covariance(element_snr_db, samples, seed=7):
    """One constant-modulus source (exact power) in unit-power white noise, M channels."""
    rng = np.random.RandomState(seed)
    steering = np.exp(1j * np.pi * 0.6 * np.arange(M))
    tone = 10 ** (element_snr_db / 20) * np.exp(2j * np.pi * 0.0123 * np.arange(samples))
    noise = (rng.standard_normal((M, samples)) + 1j * rng.standard_normal((M, samples))) / np.sqrt(2)
    x = steering[:, None] * tone[None, :] + noise
    return (x @ x.conj().T / samples).astype(np.complex64)


@pytest.mark.parametrize("samples", [341, 2730])  # channelized samples of a 2^16 and a 2^19 frame at 12.5 kHz
@pytest.mark.parametrize("element_snr_db", [0, 10, 20, 30, 40])
def test_snr_is_element_snr_plus_array_gain(element_snr_db, samples):
    import kraken_sdr_signal_processor as ksp

    estimates = [ksp.SNR(sample_covariance(element_snr_db, samples, seed), samples) for seed in range(DRAWS)]
    assert np.mean(estimates) == pytest.approx(element_snr_db + ARRAY_GAIN_DB, abs=BIAS_TOLERANCE_DB)


def test_no_noise_gives_the_cap():
    import kraken_sdr_signal_processor as ksp

    steering = np.exp(1j * np.pi * 0.6 * np.arange(M))
    rank_one = np.outer(steering, steering.conj())  # noise eigenvalues 0 (or rounding below 0)
    assert ksp.SNR(rank_one, 341) == 100.0


def test_noise_only_gives_the_floor_or_a_low_value():
    import kraken_sdr_signal_processor as ksp

    assert ksp.SNR(np.eye(M), 341) == pytest.approx(-50.0)
