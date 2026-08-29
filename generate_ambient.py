#!/usr/bin/env python3
"""Synthesize a soft, loopable ambient bed for sleep/hypnosis audio.
No copyrighted assets are used -- everything is generated with numpy.

Default "hypnosis" style: a slow-breathing (~15s cycle) low drone with a
gentle stereo beat, blended with a brown-noise floor for texture.
Frequencies and the LFO cycle are chosen so the clip loops perfectly
(whole numbers of cycles fit the duration), so no crossfade is needed.

Usage:
    python generate_ambient.py [output_path] [duration_seconds] [--plain]

    --plain   generate plain mono brown noise instead of the hypnosis pad
"""
import sys
from pathlib import Path

import numpy as np
from pydub import AudioSegment

SAMPLE_RATE = 44100


def make_brown_noise(duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n = int(duration_s * sample_rate)
    white = np.random.normal(0, 1, n)
    brown = np.cumsum(white)
    brown -= brown.mean()

    window = 8
    kernel = np.ones(window) / window
    brown = np.convolve(brown, kernel, mode="same")

    brown /= np.max(np.abs(brown)) + 1e-9
    return brown


def make_hypnosis_pad(
    duration_s: float,
    sample_rate: int = SAMPLE_RATE,
    base_freq: float = 174.0,
    beat_hz: float = 4.0,
    lfo_period_s: float = 15.0,
    noise_mix: float = 0.35,
) -> np.ndarray:
    """Stereo drone: left ear base_freq, right ear base_freq+beat_hz (a gentle
    ~4Hz binaural-style beat), amplitude breathing slowly in and out, blended
    with a brown-noise floor. Returns shape (n, 2) in -1..1."""
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate

    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * t / lfo_period_s - np.pi / 2)
    lfo = 0.35 + 0.65 * lfo  # keep a soft floor so the tone never fully vanishes

    left_tone = np.sin(2 * np.pi * base_freq * t) * lfo
    right_tone = np.sin(2 * np.pi * (base_freq + beat_hz) * t) * lfo

    brown = make_brown_noise(duration_s, sample_rate)

    left = (1 - noise_mix) * left_tone + noise_mix * brown
    right = (1 - noise_mix) * right_tone + noise_mix * brown

    stereo = np.stack([left, right], axis=1)
    stereo /= np.max(np.abs(stereo)) + 1e-9
    return stereo


def to_audio_segment(samples: np.ndarray, sample_rate: int, target_dbfs: float = -20.0) -> AudioSegment:
    if samples.ndim == 1:
        channels = 1
        int_samples = (samples * 32767 * 0.9).astype(np.int16)
    else:
        channels = samples.shape[1]
        int_samples = (samples * 32767 * 0.9).astype(np.int16)

    seg = AudioSegment(
        int_samples.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=channels,
    )
    return seg.apply_gain(target_dbfs - seg.dBFS)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    plain = "--plain" in sys.argv

    default_name = "brown_noise.mp3" if plain else "hypnosis_pad.mp3"
    out_path = Path(args[0]) if len(args) > 0 else Path(f"assets/ambient/{default_name}")
    duration_s = float(args[1]) if len(args) > 1 else 180.0

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if plain:
        print(f"Generating {duration_s:.0f}s of plain brown noise...")
        samples = make_brown_noise(duration_s)
    else:
        print(f"Generating {duration_s:.0f}s hypnosis pad (breathing drone + brown noise floor)...")
        samples = make_hypnosis_pad(duration_s)

    seg = to_audio_segment(samples, SAMPLE_RATE)
    seg.export(out_path, format="mp3", bitrate="128k")
    print(f"Wrote {out_path} ({len(seg) / 1000:.1f}s)")


if __name__ == "__main__":
    main()
