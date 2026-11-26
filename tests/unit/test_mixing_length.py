# Property test for finding P-10/T-04: the mixing exponentials must have exactly the requested length for every
# valid configuration, or channelize() raises and the frame is dropped (kraken_sdr_signal_processor.py:1287-1331).
import math

import pytest

# variables.py:76 (MHz), and VFO bandwidths a user can type; "FM" uses the 48 kHz demodulator decimation (sp:591-593).
SAMPLE_RATES_HZ = [int(rate * 1e6) for rate in (0.25, 0.900001, 1.024, 1.4, 1.8, 1.92, 2.048, 2.4, 2.56, 3.2)]
CPI_SIZES = [2**exponent for exponent in range(16, 21)]
VFO_BANDWIDTHS = [
    1000,
    2500,
    3000,
    5000,
    6250,
    10000,
    12500,
    15000,
    20000,
    25000,
    44000,
    50000,
    100000,
    200000,
    300000,
    "FM",
]
DSP_DECIMATIONS = (1, 2)
FIR_ORDER_FACTORS = (2, 3, 4, 8)


def channel_decimation(sample_rate, bandwidth):
    if bandwidth == "FM":
        return int(sample_rate / 48_000)
    return int(max(sample_rate // bandwidth, 1))


def test_output_mixing_has_the_requested_length():
    import kraken_sdr_signal_processor as ksp

    wrong = []
    for sample_rate in SAMPLE_RATES_HZ:
        for decimation in DSP_DECIMATIONS:
            rate = sample_rate // decimation
            for bandwidth in VFO_BANDWIDTHS:
                q = channel_decimation(rate, bandwidth)
                for cpi in CPI_SIZES:
                    length = math.ceil(math.ceil(cpi / decimation) / q)
                    if len(ksp.get_exponential(1234.0, rate / q, length)) != length:
                        wrong.append((rate, bandwidth, cpi))
    assert wrong == []


@pytest.mark.parametrize("fir_order_factor", FIR_ORDER_FACTORS)
def test_filter_taps_are_shifted_without_error(fir_order_factor):
    import kraken_sdr_signal_processor as ksp

    failing = []
    for sample_rate in SAMPLE_RATES_HZ:
        for decimation in DSP_DECIMATIONS:
            rate = sample_rate // decimation
            for bandwidth in VFO_BANDWIDTHS:
                q = channel_decimation(rate, bandwidth)
                try:
                    ksp.shift_filter(q, fir_order_factor, 1234.0, rate, 1.1)
                except ValueError as error:
                    failing.append((rate, bandwidth, str(error)[:60]))
    assert failing == []
