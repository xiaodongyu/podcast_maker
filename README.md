# Podcast Maker

Turn a text script (with per-line voice/tone/pacing instructions) into a finished
mp3 episode, ready to upload to Ximalaya (喜马拉雅) or any other podcast platform.

Uses [edge-tts](https://github.com/rany2/edge-tts) (free, Microsoft neural voices)
for synthesis, and pydub/ffmpeg to stitch segments, silences, and sound clips
into one final track.

## Setup

```bash
# 1. Create a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install Python deps
pip install -r requirements.txt

# 3. Install ffmpeg (required by pydub for mp3 encoding/decoding)
sudo apt-get update && sudo apt-get install -y ffmpeg
```

## Writing an episode script

Episodes are plain YAML files in `scripts/`. See
[scripts/example_episode.yaml](scripts/example_episode.yaml) for a full example.

```yaml
title: "第一期：欢迎收听"
author: "我的播客"
output: "ep01_welcome"          # -> output/ep01_welcome.mp3

default_voice: "zh-CN-XiaoxiaoNeural"
default_rate: "+0%"
default_pitch: "+0Hz"

segments:
  - voice: "zh-CN-YunxiNeural"   # override per segment
    rate: "+5%"
    text: |
      大家好，欢迎收听本期节目。

  - pause: 500                   # silence, in milliseconds

  - voice: "zh-CN-XiaoxiaoNeural"
    text: |
      今天我们要聊的话题是……

  - audio: "intro_music.mp3"     # insert a pre-recorded clip (path relative to the script file)
    gain_db: -6                  # optional volume adjustment
```

Each item in `segments` is one of:
- **A text line** — `text` (required), plus optional `voice`, `rate`, `pitch`,
  `volume` overrides, and `gap_after` (ms of silence appended after this line).
- **A pause** — `pause: <ms>`.
- **An existing audio clip** — `audio: <path>` (e.g. intro/outro music or sound
  effects), with optional `gain_db`.

Top-level `default_voice` / `default_rate` / `default_pitch` / `default_volume`
apply to any segment that doesn't override them.

### Background ambience

Add a top-level `background` block to mix a quiet ambient bed under the whole
episode (looped/trimmed and faded to match its length automatically):

```yaml
background:
  file: "assets/ambient/brown_noise.mp3"   # relative to the script file, or the project root
  gain_db: -24                              # how far below the voice to sit (more negative = quieter)
  fade_in_ms: 3000
  fade_out_ms: 5000
```

A royalty-free brown-noise bed is generated (not downloaded) via:

```bash
python generate_ambient.py assets/ambient/brown_noise.mp3 90
```

This synthesizes soft, non-tonal brown noise with numpy — no licensing concerns.
Regenerate it any time (e.g. with a longer duration) since `podcast_maker.py`
loops it (crossfaded, so there's no audible seam) to fit any episode length.

### Rate / pitch / volume syntax

These follow edge-tts's SSML-style prosody format:
- `rate`: `"+10%"`, `"-15%"` (speed)
- `pitch`: `"+2Hz"`, `"-3Hz"`
- `volume`: `"+0%"`, `"-10%"`

### Multi-voice dialogue

Just alternate `voice` across segments — each segment is synthesized
independently, so you can have two "hosts" talk back and forth by assigning
them different `zh-CN-*` voices.

## Finding voices

List all Mandarin voices:

```bash
python list_voices.py zh-CN
```

Common choices:
| Voice | Gender | Style |
|---|---|---|
| `zh-CN-XiaoxiaoNeural` | Female | Warm, general narration |
| `zh-CN-YunxiNeural` | Male | Lively, younger male host |
| `zh-CN-YunyangNeural` | Male | News/formal |
| `zh-CN-XiaoyiNeural` | Female | Expressive |
| `zh-CN-YunjianNeural` | Male | Deep, storytelling |

## Generating an episode

```bash
python podcast_maker.py scripts/example_episode.yaml
```

This writes `output/<output>.mp3` (filename from the `output` field in the
script), tagged with the episode `title` and `author` as ID3 metadata.

## Uploading to Ximalaya

Ximalaya doesn't offer a public API for individual creators, so upload is
manual:
1. Open the Ximalaya app or [创作者后台](https://www.ximalaya.com) creator
   dashboard on the web.
2. Create/select your album (专辑), then "上传声音" (upload track).
3. Upload the generated mp3 from `output/`, fill in the episode title/description,
   and publish.

## Workflow

1. Give me the script text and reading instructions (tone, pacing, which
   speaker, pauses, etc.) for an episode.
2. I'll write it into a new YAML file under `scripts/`.
3. Run `python podcast_maker.py scripts/<your_episode>.yaml` to synthesize it.
4. Listen to `output/<name>.mp3`, tell me what to adjust (voice, speed, pauses),
   and I'll regenerate.
5. Upload the final mp3 to Ximalaya.
