# The golden regression cases. Parameters are stored here; the IQ is regenerated from them on each run.
from helpers import synth
from helpers.dsp import Case

F_OFF = synth.F_OFF
UCA_XY_M = tuple(tuple(axis) for axis in synth.element_positions("UCA"))

# Cases whose stored output is known to be wrong today. A fix shows up as an intended change in the diff table.
KNOWN_BUGS = {
    "offset30/UCA/MUSIC/FBA/123deg": "P-03",
}

# Cases whose reduced spectrum (row 1, the measured channel) is stored too.
SPECTRUM_CASES = {
    "UCA/MUSIC/123deg/0dB",
    "UCA/MUSIC/123deg/-15dB",
    "ULA/MUSIC/65deg/0dB",
    "two VFOs/UCA/MUSIC",
    "dsp_decimation=2/UCA/MUSIC/123deg",
    "VFO 6.25 kHz/UCA/MUSIC/123deg",
}


def golden_cases():
    cases = []
    for algorithm in ("Bartlett", "Capon", "MEM", "MUSIC", "ROOT-MUSIC", "TNA"):
        for snr_db in (0, -15):
            cases.append(Case(f"UCA/{algorithm}/123deg/{snr_db}dB", "UCA", algorithm, [(123, snr_db, F_OFF)], seed=11))
        cases.append(Case(f"ULA/{algorithm}/65deg/0dB", "ULA", algorithm, [(65, 0, F_OFF)], seed=12))
    cases.append(Case("ULA/ROOT-MUSIC/250deg/0dB", "ULA", "ROOT-MUSIC", [(250, 0, F_OFF)], seed=13))
    for angle in (37, 299):
        cases.append(Case(f"UCA/MUSIC/{angle}deg/-15dB", "UCA", "MUSIC", [(angle, -15, F_OFF)], seed=14))
    # FBTOEP was removed in M2-04: a stored FBTOEP runs as "Off".
    for decorrelation in ("FBA", "TOEP", "FBSS", "FBTOEP"):
        cases.append(
            Case(
                f"UCA/MUSIC/{decorrelation}/211deg",
                "UCA",
                "MUSIC",
                [(211, 0, F_OFF)],
                seed=15,
                decorrelation=decorrelation,
            )
        )
    for algorithm in ("MUSIC", "ROOT-MUSIC"):
        cases.append(
            Case(f"ULA/{algorithm}/FBSS/65deg", "ULA", algorithm, [(65, 0, F_OFF)], seed=16, decorrelation="FBSS")
        )
    cases.append(Case("Custom/MUSIC/123deg", "Custom", "MUSIC", [(123, 0, F_OFF)], seed=17, custom_xy_m=UCA_XY_M))
    cases.append(Case("Custom/Bartlett/299deg", "Custom", "Bartlett", [(299, 0, F_OFF)], seed=17, custom_xy_m=UCA_XY_M))
    two_sources = [(60, 0, F_OFF), (200, 0, F_OFF + 2000)]
    cases.append(Case("two sources/UCA/MUSIC", "UCA", "MUSIC", two_sources, seed=18, expected_sources=2))
    cases.append(Case("two sources/ULA/MUSIC", "ULA", "MUSIC", two_sources, seed=18, expected_sources=2))
    cases.append(Case("VFO 6.25 kHz/UCA/MUSIC/123deg", "UCA", "MUSIC", [(123, 0, F_OFF)], seed=19, vfo_bw=6250))
    cases.append(
        Case(
            "two VFOs/UCA/MUSIC",
            "UCA",
            "MUSIC",
            [(123, 0, F_OFF), (240, 0, -300_000.0)],
            seed=20,
            vfo_offsets=(F_OFF, -300_000.0),
        )
    )
    cases.append(
        Case("dsp_decimation=2/UCA/MUSIC/123deg", "UCA", "MUSIC", [(123, 0, F_OFF)], seed=21, dsp_decimation=2)
    )
    cases.append(Case("offset30/UCA/MUSIC/123deg", "UCA", "MUSIC", [(123, 0, F_OFF)], seed=22, array_offset=30))
    cases.append(
        Case(
            "offset30/UCA/MUSIC/FBA/123deg",
            "UCA",
            "MUSIC",
            [(123, 0, F_OFF)],
            seed=22,
            array_offset=30,
            decorrelation="FBA",
        )
    )
    cases.append(Case("144MHz/UCA/MUSIC/123deg", "UCA", "MUSIC", [(123, 0, F_OFF)], seed=23, center=144_000_000))
    cases.append(Case("1090MHz/UCA/MUSIC/123deg", "UCA", "MUSIC", [(123, 0, F_OFF)], seed=23, center=1_090_000_000))
    return cases
