#!/usr/bin/env python3
"""Synthesize a podcast episode (mp3) from a YAML script using edge-tts.

Usage:
    python podcast_maker.py scripts/example_episode.yaml
"""
import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

import yaml
import edge_tts
from pydub import AudioSegment
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"
DEFAULT_PITCH = "+0Hz"
DEFAULT_VOLUME = "+0%"

PROJECT_ROOT = Path(__file__).resolve().parent


def resolve_path(candidate: str, script_dir: Path) -> Path:
    """Resolve a path from a script file: relative to the script's own
    directory first (per-episode assets), falling back to the project root
    (shared assets, e.g. assets/ambient/...)."""
    p = Path(candidate)
    if p.is_absolute():
        return p
    for base in (script_dir, PROJECT_ROOT):
        full = (base / p).resolve()
        if full.exists():
            return full
    return (script_dir / p).resolve()


async def synth_segment(text: str, voice: str, rate: str, pitch: str, volume: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(
        text, voice=voice, rate=rate, pitch=pitch, volume=volume
    )
    await communicate.save(str(out_path))


async def build_episode(script: dict, script_dir: Path, tmp_dir: Path) -> tuple[AudioSegment, list[tuple[int, int]]]:
    """Returns (episode audio, list of (start_ms, end_ms) silent/pause windows)
    so the caller can duck background ambience up during those windows."""
    default_voice = script.get("default_voice", DEFAULT_VOICE)
    default_rate = script.get("default_rate", DEFAULT_RATE)
    default_pitch = script.get("default_pitch", DEFAULT_PITCH)
    default_volume = script.get("default_volume", DEFAULT_VOLUME)

    episode = AudioSegment.silent(duration=0)
    pause_windows: list[tuple[int, int]] = []

    def mark_pause(duration_ms: int) -> None:
        start = len(episode)
        pause_windows.append((start, start + duration_ms))

    for i, seg in enumerate(script.get("segments", [])):
        if "pause" in seg:
            duration_ms = int(seg["pause"])
            mark_pause(duration_ms)
            episode += AudioSegment.silent(duration=duration_ms)
            continue

        if "audio" in seg:
            clip_path = resolve_path(seg["audio"], script_dir)
            clip = AudioSegment.from_file(clip_path)
            gain_db = seg.get("gain_db")
            if gain_db is not None:
                clip = clip.apply_gain(float(gain_db))
            episode += clip
            continue

        text = seg.get("text", "").strip()
        if not text:
            continue

        voice = seg.get("voice", default_voice)
        rate = seg.get("rate", default_rate)
        pitch = seg.get("pitch", default_pitch)
        volume = seg.get("volume", default_volume)

        seg_path = tmp_dir / f"seg_{i:04d}.mp3"
        print(f"  [{i}] synthesizing ({voice}, rate={rate}, pitch={pitch}): {text[:40]}...")
        await synth_segment(text, voice, rate, pitch, volume, seg_path)
        episode += AudioSegment.from_mp3(seg_path)

        gap = seg.get("gap_after")
        if gap:
            mark_pause(int(gap))
            episode += AudioSegment.silent(duration=int(gap))

    return episode, pause_windows


def loop_to_length(bg: AudioSegment, target_ms: int) -> AudioSegment:
    """Loop (crossfaded, to avoid seam clicks) or trim bg to exactly target_ms."""
    if target_ms <= 0:
        return AudioSegment.silent(duration=0)

    crossfade_ms = min(2000, max(0, len(bg) // 4))
    looped = bg
    while len(looped) < target_ms + crossfade_ms:
        looped = looped.append(bg, crossfade=crossfade_ms)
    return looped[:target_ms]


def build_ducked_background(
    raw: AudioSegment,
    target_ms: int,
    pause_windows: list[tuple[int, int]],
    base_gain_db: float,
    duck_gain_db: float,
    transition_ms: int = 400,
) -> AudioSegment:
    """Builds a background track that sits at base_gain_db under speech and
    rises to duck_gain_db (louder) during each pause window, crossfading
    smoothly at every transition so the level change isn't a hard jump."""
    windows = sorted(w for w in pause_windows if w[1] > w[0])
    pieces: list[tuple[int, int, float]] = []
    cursor = 0
    for start, end in windows:
        start = max(0, min(start, target_ms))
        end = max(0, min(end, target_ms))
        if start > cursor:
            pieces.append((cursor, start, base_gain_db))
        if end > start:
            pieces.append((start, end, duck_gain_db))
            cursor = max(cursor, end)
    if cursor < target_ms:
        pieces.append((cursor, target_ms, base_gain_db))

    result = None
    for start, end, gain_db in pieces:
        chunk = raw[start:end].apply_gain(gain_db)
        if result is None:
            result = chunk
        else:
            crossfade_ms = min(transition_ms, len(result), len(chunk))
            result = result.append(chunk, crossfade=crossfade_ms)
    return result if result is not None else AudioSegment.silent(duration=target_ms)


def apply_background(
    episode: AudioSegment,
    bg_cfg: dict,
    script_dir: Path,
    pause_windows: list[tuple[int, int]],
) -> AudioSegment:
    bg_path = resolve_path(bg_cfg["file"], script_dir)
    bg = AudioSegment.from_file(bg_path)
    bg = bg.set_channels(episode.channels).set_frame_rate(episode.frame_rate)

    raw = loop_to_length(bg, len(episode))

    base_gain_db = float(bg_cfg.get("gain_db", -28))
    duck_boost_db = float(bg_cfg.get("duck_boost_db", 12))
    mixed = build_ducked_background(
        raw,
        target_ms=len(episode),
        pause_windows=pause_windows,
        base_gain_db=base_gain_db,
        duck_gain_db=base_gain_db + duck_boost_db,
    )

    fade_in_ms = int(bg_cfg.get("fade_in_ms", 3000))
    fade_out_ms = int(bg_cfg.get("fade_out_ms", 5000))
    if fade_in_ms:
        mixed = mixed.fade_in(min(fade_in_ms, len(mixed)))
    if fade_out_ms:
        mixed = mixed.fade_out(min(fade_out_ms, len(mixed)))

    return episode.overlay(mixed)


def tag_mp3(path: Path, title: str, author: str) -> None:
    try:
        tags = EasyID3(path)
    except ID3NoHeaderError:
        tags = MP3(path)
        tags.add_tags()
        tags = EasyID3(path)
    tags["title"] = title
    tags["artist"] = author
    tags.save()


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize a podcast episode from a YAML script.")
    parser.add_argument("script", help="Path to the episode YAML script")
    parser.add_argument("-o", "--output-dir", default="output", help="Directory to write the final mp3 into")
    args = parser.parse_args()

    script_path = Path(args.script).resolve()
    if not script_path.exists():
        sys.exit(f"Script not found: {script_path}")

    with open(script_path, "r", encoding="utf-8") as f:
        script = yaml.safe_load(f)

    title = script.get("title", script_path.stem)
    author = script.get("author", "")
    out_stem = script.get("output", script_path.stem)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{out_stem}.mp3"

    print(f"Building episode: {title}")
    with tempfile.TemporaryDirectory() as tmp:
        episode, pause_windows = asyncio.run(build_episode(script, script_path.parent, Path(tmp)))

    if "background" in script:
        print("Mixing in background ambience (ducked under speech, swelling in pauses)...")
        episode = apply_background(episode, script["background"], script_path.parent, pause_windows)

    print(f"Exporting to {out_path} ...")
    episode.export(out_path, format="mp3", bitrate="192k")
    tag_mp3(out_path, title=title, author=author)

    duration_s = len(episode) / 1000
    print(f"Done. Duration: {duration_s:.1f}s -> {out_path}")


if __name__ == "__main__":
    main()
