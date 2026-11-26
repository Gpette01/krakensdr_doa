import shutil
from fractions import Fraction

import numpy as np
from scipy.signal import butter, firwin, lfilter, resample_poly

DEFAULT_NUM_OF_FREQ = 1024
DEFAULT_FILTER_ORDER = 5
DEFAULT_FILTER_WINDOW = "hamming"
DEFAULT_NUM_TAPS = 256

DISK_SPACE_HEADROOM = 0.1
WAV_RATE = 48_000  # Hz, the rate of every recorded WAV file


def butter_lowpass(highcut, fs, order=DEFAULT_FILTER_ORDER):
    return butter(order, highcut, fs=fs, btype="low")


def butter_lowpass_filter(signal, highcut, fs, order=DEFAULT_FILTER_ORDER):
    b, a = butter_lowpass(highcut, fs, order=order)
    rx = lfilter(b, a, signal)
    return rx


def firwin_lowpass(highcut, fs, ntaps=DEFAULT_NUM_TAPS, window=DEFAULT_FILTER_WINDOW):
    taps = firwin(ntaps, highcut, fs=fs, window=window, scale=False)
    return taps


class VfoStreamState:
    """What the channel of one VFO carries from one frame to the next, so that a recording is continuous
    (finding P-21). Each frame used to restart the mixer phase, the FM low-pass filter and the discriminator."""

    def __init__(self):
        self.reset(None)

    def reset(self, settings):
        self.settings = settings  # (frequency, bandwidth, channel rate) this state belongs to
        self.cpi_index = None  # DAQ frame index of the last frame
        self.mixer_cycles = 0.0  # mixer phase at the start of the next frame, in cycles
        self.filter_state = None  # lfilter state of the FM low-pass filter
        self.previous_sample = None  # last filtered sample, for the FM discriminator


def fm_demod(samples, sample_freq, freq_width, state):
    """Instantaneous frequency in Hz, one value per input sample once state holds the previous frame."""
    taps = firwin_lowpass(int(freq_width / 2), sample_freq)
    if state.filter_state is None:
        state.filter_state = np.zeros(len(taps) - 1, dtype=np.complex128)
    baseband, state.filter_state = lfilter(taps, 1, samples, zi=state.filter_state)
    if state.previous_sample is not None:
        baseband = np.concatenate(([state.previous_sample], baseband))
    state.previous_sample = baseband[-1]

    demod_channel = np.angle(baseband[1:] * np.conjugate(baseband[:-1]))
    return (demod_channel * sample_freq) / (2 * np.pi)


def wav_audio(demod_channel, audio_rate):
    """A whole recording as int16 at WAV_RATE: resampled from the true audio rate, then scaled once."""
    ratio = Fraction(WAV_RATE / audio_rate).limit_denominator(1000)
    audio = resample_poly(np.asarray(demod_channel, dtype=np.float64), ratio.numerator, ratio.denominator)
    peak = np.max(np.abs(audio)) if audio.size else 0.0
    if peak == 0:
        return np.zeros(audio.size, dtype=np.int16)
    return np.int16(audio / peak * 32767)


def write_wav(f, sample_freq, x):
    """
    NumPy array to WAV
    """
    from scipy.io.wavfile import write

    write(f, sample_freq, x.astype(np.int16))


def can_store_file(path: str) -> bool:
    total, _, free = shutil.disk_usage(path)
    return True if (free / total) >= DISK_SPACE_HEADROOM else False
