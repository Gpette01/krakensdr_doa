# M2-07 (P-23): the bearing in the name of an FM or IQ recording is the mean of the bearings measured while it was
# recorded. An arithmetic mean put 359 and 1 at 180; the circular mean puts them at 0.
import pytest


@pytest.mark.parametrize(
    "thetas, mean, spread",
    [
        ([359, 1], 0.0, 1.0),
        ([358, 359, 0, 1], 359.5, 1.5),
        ([10, 20], 15.0, 5.0),
        ([350, 10, 30], 10.0, 20.0),
    ],
)
def test_circular_mean_and_spread(thetas, mean, spread):
    import kraken_sdr_signal_processor as ksp

    got_mean, got_spread = ksp.average_bearings(thetas)
    assert ksp.bearing_text(got_mean) == f"{mean:.1f}"
    assert got_spread == pytest.approx(spread, abs=1e-9)


def test_opposite_bearings_have_no_mean():
    """The caller then names every bearing (the list path)."""
    import kraken_sdr_signal_processor as ksp

    assert ksp.average_bearings([0, 180]) is None


@pytest.mark.parametrize("theta, text", [(359.96, "0.0"), (359.94, "359.9"), (0.04, "0.0"), (123.45, "123.5")])
def test_bearing_text_rounds_then_wraps(theta, text):
    import kraken_sdr_signal_processor as ksp

    assert ksp.bearing_text(theta) == text
