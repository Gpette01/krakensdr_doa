# DOA_TNA: P(theta) = 1 / (a^H R^-2 a) (thermal noise algorithm), kraken_sdr_signal_processor.py.
import numpy as np
import pytest


def hermitian_positive_definite(size, seed):
    rng = np.random.RandomState(seed)
    x = rng.standard_normal((size, 4 * size)) + 1j * rng.standard_normal((size, 4 * size))
    return x @ x.conj().T / (4 * size)


def test_tna_matches_the_definition():
    import kraken_sdr_signal_processor as ksp

    R = hermitian_positive_definite(5, seed=1)
    scanning_vectors = ksp.gen_scanning_vectors(5, 0.4, "UCA")
    R_inv_2 = np.linalg.inv(R) @ np.linalg.inv(R)
    expected = np.array(
        [1 / np.real(a.conj() @ R_inv_2 @ a) for a in scanning_vectors.T.astype(np.complex128)], dtype=np.float64
    )
    result = ksp.DOA_TNA(R, scanning_vectors)
    np.testing.assert_allclose(np.abs(result), expected, rtol=1e-5)


def test_tna_rejects_a_singular_matrix():
    """The run loop logs the exception and drops the frame (kraken_sdr_signal_processor.py:733-735)."""
    import kraken_sdr_signal_processor as ksp

    scanning_vectors = ksp.gen_scanning_vectors(5, 0.4, "UCA")
    with pytest.raises(np.linalg.LinAlgError):
        ksp.DOA_TNA(np.zeros((5, 5), dtype=np.complex128), scanning_vectors)
