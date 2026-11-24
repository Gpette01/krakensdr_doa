# The comparison rule of benchmarks/bench_frame.py (used as the "before/after" gate of every speed task).
import importlib.util

import pytest
from conftest import REPO_ROOT


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("bench_frame", REPO_ROOT / "benchmarks" / "bench_frame.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stats(median, mad):
    return {"median_ms": median, "mad_ms": mad}


@pytest.mark.parametrize(
    "new, expected",
    [
        (stats(104.9, 1.0), "same"),  # inside 5 % of 100 ms
        (stats(105.1, 1.0), "slower"),
        (stats(94.0, 1.0), "faster"),
        (stats(100.0, 2.1), "invalid"),  # noisier than 2 x the baseline MAD
        (stats(100.0, 2.0), "same"),
    ],
)
def test_five_percent_limit(bench, new, expected):
    assert bench.verdict(stats(100.0, 1.0), new) == (expected, 5.0)


def test_mad_limit_uses_the_baseline_mad_only(bench):
    baseline = stats(100.0, 4.0)  # 3 x 4 ms = 12 ms is larger than 5 ms
    assert bench.verdict(baseline, stats(111.9, 4.0)) == ("same", 12.0)
    assert bench.verdict(baseline, stats(112.1, 4.0)) == ("slower", 12.0)
    # A noisy new run does not widen the limit; it is declared invalid instead.
    assert bench.verdict(stats(100.0, 1.0), stats(110.0, 6.0))[0] == "invalid"


MACHINE = {"python": "3.10.20", "numpy": "1.23.5", "scipy": "1.9.3", "numba": "0.56.4", "cpu_model": "CPU X"}


def test_runs_from_different_environments_are_not_compared(bench):
    bench.check_comparable(MACHINE, dict(MACHINE, governor="performance"))
    for field in ("python", "numpy", "scipy", "numba", "cpu_model"):
        with pytest.raises(ValueError, match=field):
            bench.check_comparable(MACHINE, dict(MACHINE, **{field: "other"}))


def test_compare_fails_on_any_non_same_config(bench, capsys):
    baseline = {"machine": MACHINE, "configs": {"a": stats(10.0, 0.1), "b": stats(20.0, 0.1)}}
    assert bench.compare(baseline, {"machine": MACHINE, "configs": {"a": stats(10.1, 0.1), "b": stats(20.0, 0.1)}})
    assert not bench.compare(baseline, {"machine": MACHINE, "configs": {"a": stats(12.0, 0.1), "b": stats(20.0, 0.1)}})
    assert not bench.compare(baseline, {"machine": MACHINE, "configs": {"a": stats(10.0, 0.1)}})
