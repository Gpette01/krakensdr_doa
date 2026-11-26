# M2-10 (P-21): FM demodulation of a VFO, recorded to a WAV file. The WAV was labelled 48 kHz while the audio rate
# is fs / int(fs / 48000) (50 kHz at DSP decimation 3), and each frame restarted the mixer phase, the low-pass filter
# and the discriminator, and rescaled its own audio. A 1 kHz tone must play at 1 kHz at every DSP decimation.
from dataclasses import dataclass

import numpy as np
import pytest
from helpers import synth
from helpers.dsp import Case, run_cases

FRAME = 2**18  # 109 ms at 2.4 MHz
FRAMES = 6
TONE_HZ = 1000.0
DEVIATION_HZ = 3000.0
SNR_DB = 30.0
AZIMUTH = 123
PITCH_TOLERANCE_HZ = 1.0
SETTLE_S = 0.01  # the start of the recording, where the filters fill


@dataclass
class FmCase(Case):
    """Frame `frame_index` of one continuous FM signal: a carrier at F_OFF modulated by a 1 kHz tone."""

    frame_index: int = 0

    def frame_key(self):
        return (self.label, self.frame_index)

    def make_frame(self, n):
        t = (self.frame_index * n + np.arange(n)) / synth.FS
        phase = 2 * np.pi * synth.F_OFF * t + (DEVIATION_HZ / TONE_HZ) * np.sin(2 * np.pi * TONE_HZ * t)
        x, y = synth.element_positions("UCA")
        wavelength = synth.C / (self.center + synth.F_OFF)
        theta = np.deg2rad(AZIMUTH)
        steering = np.exp(1j * 2 * np.pi / wavelength * (x * np.cos(theta) + y * np.sin(theta)))
        rng = np.random.RandomState(100 + self.frame_index)
        noise = (rng.standard_normal((synth.M, n)) + 1j * rng.standard_normal((synth.M, n))) / np.sqrt(2)
        frame = noise + 10 ** (SNR_DB / 20) * steering[:, None] * np.exp(1j * phase)[None, :]
        return np.ascontiguousarray(frame.astype(np.complex64))


def record(make_sp, monkeypatch, dsp_decimation):
    """Runs FRAMES frames with an FM VFO, then one frame with DoA off, which ends the recording and writes it."""
    import kraken_sdr_signal_processor as ksp

    written = []
    monkeypatch.setattr(ksp, "write_wav", lambda path, rate, samples: written.append((rate, np.array(samples))))
    monkeypatch.setattr(ksp, "can_store_file", lambda path: True)  # nothing is written; free space is irrelevant
    cases = [
        FmCase(
            f"fm/dec{dsp_decimation}/{k}",
            "UCA",
            "MUSIC",
            [],
            dsp_decimation=dsp_decimation,
            frame_index=k,
            extra={"vfo_default_demod": "FM", "en_DOA_estimation": k < FRAMES},
        )
        for k in range(FRAMES + 1)
    ]
    results = run_cases(make_sp, cases, n=FRAME)
    for result in results[:FRAMES]:
        assert result.usable_estimate() is not None, result.describe()
    assert len(written) == 1, f"{len(written)} WAV files"
    return written[0]


def pitch_hz(rate, audio):
    """Tone frequency from the rising zero crossings, interpolated between samples."""
    audio = np.asarray(audio, dtype=np.float64)
    audio = audio[int(SETTLE_S * rate) :]
    audio = audio - np.mean(audio)
    rising = np.flatnonzero((audio[:-1] < 0) & (audio[1:] >= 0))
    crossings = rising + audio[rising] / (audio[rising] - audio[rising + 1])
    return (len(crossings) - 1) / ((crossings[-1] - crossings[0]) / rate)


@pytest.mark.parametrize("dsp_decimation", [1, 3, 7])
def test_recorded_tone_plays_at_its_pitch(make_sp, monkeypatch, dsp_decimation):
    rate, audio = record(make_sp, monkeypatch, dsp_decimation)
    assert pitch_hz(rate, audio) == pytest.approx(TONE_HZ, abs=PITCH_TOLERANCE_HZ), f"WAV rate {rate}"
