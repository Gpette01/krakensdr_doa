# Truth suite: the bearing estimated by the real run() loop against the true bearing of a synthetic source.
#
# This suite is never regenerated: the expected values are the physical angles used to build the frames.
# Known bugs are strict xfails that name their findings (doc/TASKS.md). When a fix lands, its xfail turns
# into an XPASS failure, and the fixing task removes the mark.
import numpy as np
import pytest
from helpers import synth
from helpers.dsp import Case, run_cases

F_OFF = synth.F_OFF
GRID_TOLERANCE_DEG = 0.5  # true angles are integers, the grid methods return integers
ROOT_MUSIC_TOLERANCE_DEG = 0.5  # largest error seen in the audit: 0.41 degrees
UCA_ANGLES = (37, 123, 211, 299)
ULA_ANGLES = (20, 65, 160, 250, 300)
ALGORITHMS = ("Bartlett", "Capon", "MEM", "TNA", "MUSIC", "ROOT-MUSIC")
UCA_XY_M = tuple(tuple(axis) for axis in synth.element_positions("UCA"))


def xfail(reason):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason)


def grid_cases():
    params = []
    for geometry, angles in (("UCA", UCA_ANGLES), ("ULA", ULA_ANGLES)):
        for algorithm in ALGORITHMS:
            for angle in angles:
                case = Case(f"{geometry}/{algorithm}/{angle}deg", geometry, algorithm, [(angle, 0, F_OFF)])
                marks = []
                if algorithm == "TNA":
                    marks.append(xfail("P-01, T-02: TNA never compiles in numba"))
                if geometry == "ULA" and algorithm == "ROOT-MUSIC" and angle in (250, 300):
                    marks.append(xfail("P-02, T-06: ULA ROOT-MUSIC folds the sign of sin(theta)"))
                params.append(pytest.param(case, marks=marks, id=case.label))
    return params


def offset_cases():
    """Array offset 30 degrees. The expected bearing is (true - offset), the sign of the grid path (assumption A5)."""
    wrong_path = xfail("P-03: array_offset is applied differently on this path")
    params = []
    for label, geometry, algorithm, decorrelation, angle, marks in (
        ("UCA/MUSIC", "UCA", "MUSIC", "Off", 123, []),
        ("ULA/MUSIC", "ULA", "MUSIC", "Off", 65, []),
        ("ULA/ROOT-MUSIC", "ULA", "ROOT-MUSIC", "Off", 65, []),
        ("UCA/MUSIC/FBA (virtual array)", "UCA", "MUSIC", "FBA", 123, [wrong_path]),
        ("UCA/ROOT-MUSIC (virtual array)", "UCA", "ROOT-MUSIC", "Off", 123, [wrong_path]),
        ("Custom/MUSIC", "Custom", "MUSIC", "Off", 123, [wrong_path]),
    ):
        custom = UCA_XY_M if geometry == "Custom" else None
        case = Case(
            f"offset30/{label}/{angle}deg",
            geometry,
            algorithm,
            [(angle, 0, F_OFF)],
            decorrelation=decorrelation,
            array_offset=30,
            custom_xy_m=custom,
        )
        params.append(pytest.param(case, marks=marks, id=case.label))
    return params


def frequency_cases():
    """Virtual array (UCA with decorrelation) against plain UCA, at four center frequencies, radius 0.21 m."""
    params = []
    for center_mhz in (144, 433, 700, 1090):
        for decorrelation in ("Off", "FBA"):
            label = f"{center_mhz}MHz/UCA/MUSIC/{decorrelation}/123deg"
            case = Case(
                label, "UCA", "MUSIC", [(123, 0, F_OFF)], decorrelation=decorrelation, center=center_mhz * 1_000_000
            )
            marks = []
            if decorrelation == "FBA" and center_mhz != 433:
                marks.append(xfail("P-04: virtual array transform used outside its validity range"))
            params.append(pytest.param(case, marks=marks, id=label))
    return params


def smoothing_cases():
    """Accuracy with spatial smoothing (FBSS) for 1 and 2 expected sources."""
    params = []
    for algorithm in ("MUSIC", "ROOT-MUSIC"):
        for expected_sources in (1, 2):
            label = f"ULA/{algorithm}/FBSS/sources={expected_sources}/65deg"
            case = Case(
                label, "ULA", algorithm, [(65, 0, F_OFF)], decorrelation="FBSS", expected_sources=expected_sources
            )
            params.append(pytest.param(case, id=label))
    return params


def smoothing_limit_cases():
    """FBSS with the largest source count the UI offers (4). A correct clamp (M1-04) changes the subspace, so only
    "a usable result and no ERROR" is required here, not accuracy."""
    params = []
    for algorithm in ("MUSIC", "ROOT-MUSIC"):
        label = f"ULA/{algorithm}/FBSS/sources=4/65deg"
        case = Case(label, "ULA", algorithm, [(65, 0, F_OFF)], decorrelation="FBSS", expected_sources=4)
        params.append(pytest.param(case, marks=[xfail("P-09: source count not clamped after FBSS")], id=label))
    return params


ULA_ROOT_MUSIC_ANGLES = (20, 70, 110, 160, 200, 250, 300, 340)


def ula_root_music_cases():
    """ROOT-MUSIC against MUSIC on the same ULA frame (the acceptance of M2-01)."""
    params = []
    for angle in ULA_ROOT_MUSIC_ANGLES:
        pair = tuple(
            Case(f"ULA pair/{algorithm}/{angle}deg", "ULA", algorithm, [(angle, 0, F_OFF)], seed=41)
            for algorithm in ("MUSIC", "ROOT-MUSIC")
        )
        mark = xfail("P-02, T-06: ULA ROOT-MUSIC folds the sign of sin(theta) and picks the other alias")
        params.append(pytest.param(pair, marks=[mark], id=f"ULA/{angle}deg"))
    return params


def custom_cases():
    """A custom array with the UCA coordinates must give the UCA answer."""
    return [
        pytest.param(
            Case(f"Custom(UCA xy)/MUSIC/{angle}deg", "Custom", "MUSIC", [(angle, 0, F_OFF)], custom_xy_m=UCA_XY_M),
            id=f"Custom/MUSIC/{angle}deg",
        )
        for angle in UCA_ANGLES
    ]


GROUPS = {
    "grid": grid_cases(),
    "offset": offset_cases(),
    "frequency": frequency_cases(),
    "smoothing": smoothing_cases(),
    "smoothing_limit": smoothing_limit_cases(),
    "custom": custom_cases(),
}
ALL_CASES = [param.values[0] for params in GROUPS.values() for param in params]
ALL_CASES += [case for param in ula_root_music_cases() for case in param.values[0]]


@pytest.fixture(scope="module")
def results(make_sp_module):
    """All cases in one run() call, keyed by label (one run() costs a fixed 1 s start-up sleep)."""
    frame_results = run_cases(make_sp_module, ALL_CASES)
    return {result.case.label: result for result in frame_results}


def expected_bearing(case):
    return (case.true_deg - case.array_offset) % 360


def assert_true_bearing(result, ula_mirror_allowed):
    """A ULA cannot tell theta from 180 - theta, so either is accepted for a ULA."""
    case = result.case
    estimate = result.usable_estimate()
    assert estimate is not None, f"no usable result. {result.describe()}"
    expected = expected_bearing(case)
    error = abs(synth.angle_error(estimate, expected))
    if ula_mirror_allowed:
        error = min(error, abs(synth.angle_error(estimate, 180 - expected)))
    tolerance = ROOT_MUSIC_TOLERANCE_DEG if case.algorithm == "ROOT-MUSIC" else GRID_TOLERANCE_DEG
    assert error <= tolerance, f"expected {expected} (ULA mirror allowed: {ula_mirror_allowed}). {result.describe()}"


@pytest.mark.parametrize("case", GROUPS["grid"] + GROUPS["custom"] + GROUPS["frequency"] + GROUPS["smoothing"])
def test_bearing_matches_truth(results, case):
    assert_true_bearing(results[case.label], ula_mirror_allowed=case.geometry == "ULA")


@pytest.mark.parametrize("case", GROUPS["offset"])
def test_array_offset_is_applied_once_with_one_sign(results, case):
    assert_true_bearing(results[case.label], ula_mirror_allowed=case.geometry == "ULA")


@pytest.mark.parametrize("case", GROUPS["smoothing_limit"])
def test_fbss_with_the_largest_source_count_gives_a_result(results, case):
    result = results[case.label]
    assert result.usable_estimate() is not None, result.describe()


@pytest.mark.parametrize("pair", ula_root_music_cases())
def test_ula_root_music_agrees_with_music(results, pair):
    """Same frame, same array: ROOT-MUSIC must report the bearing MUSIC reports, within 0.5 degrees."""
    music, root_music = (results[case.label] for case in pair)
    music_estimate, root_estimate = music.usable_estimate(), root_music.usable_estimate()
    assert music_estimate is not None and root_estimate is not None, (music.describe(), root_music.describe())
    assert (
        abs(synth.angle_error(root_estimate, music_estimate)) <= ROOT_MUSIC_TOLERANCE_DEG
    ), f"MUSIC {music_estimate}, ROOT-MUSIC {root_estimate}"


@xfail("P-16, T-07: 'F-B Toeplitz' has no code path in estimate_DOA")
def test_fb_toeplitz_option_changes_the_processing(make_sp):
    """The UI offers FBTOEP (variables.py:107). If it did anything, its spectrum would differ from an unknown name."""
    cases = [
        Case(f"UCA/MUSIC/{name}/123deg", "UCA", "MUSIC", [(123, 0, F_OFF)], decorrelation=name)
        for name in ("FBTOEP", "NOT_A_METHOD")
    ]
    fbtoep, unknown = run_cases(make_sp, cases)
    assert fbtoep.usable_estimate() is not None, fbtoep.describe()
    assert abs(synth.angle_error(fbtoep.usable_estimate(), 123)) <= GRID_TOLERANCE_DEG, fbtoep.describe()
    assert not np.array_equal(
        fbtoep.packet["DoA Result"], unknown.packet["DoA Result"]
    ), "the FBTOEP spectrum is identical to the spectrum for an unknown method name"
