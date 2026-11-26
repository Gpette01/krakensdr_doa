# M2-09 (D-47): the spectrum sent to the UI is reduced to 1024 points by taking the maximum of each group of bins.
# Row 0 is the frequency axis: its maximum is the top bin of the group, so the plot and click-to-tune were biased
# upwards by (group - 1) / 2 bins. Row 0 must hold the centre frequency of each group; the other rows keep the max.
import numpy as np
import pytest

FS = 2_400_000
PLOT_SIZE = 1024


@pytest.mark.parametrize("bins", [4096, 32768])
def test_reduced_axis_is_the_group_centre(bins):
    import kraken_sdr_signal_processor as ksp

    rows = 7
    spectrum = np.random.RandomState(0).uniform(-120, 0, (rows, bins)).astype(np.float32)
    axis = (-FS / 2 + np.arange(bins) * FS / bins).astype(np.float32)  # fftshifted welch axis, as row 0 holds it
    spectrum[0] = axis
    reduced = ksp.reduce_spectrum(spectrum, PLOT_SIZE, 5)

    group = bins // PLOT_SIZE
    groups = axis.astype(np.float64).reshape(PLOT_SIZE, group)
    assert reduced[0] == pytest.approx(groups.mean(axis=1), abs=0.5)
    assert np.array_equal(reduced[1:], spectrum[1:].reshape(rows - 1, PLOT_SIZE, group).max(axis=2))
