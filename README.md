# subtitle-generator

> **Video or audio → SRT/VTT subtitles with speaker labels.** Uses Gemini 2.5 Flash for fast cheap transcription, Claude for cleanup. Supports multi-language, translation, and diarization.

[![PyPI](https://img.shields.io/pypi/v/subtitle-generator?style=flat)](https://pypi.org/project/subtitle-generator/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Quickstart

```bash
pip install subtitle-generator

# Generate SRT subtitles
python -m subtitle_generator video.mp4

# Generate VTT with translation to English
python -m subtitle_generator arabic_interview.mp4 --format vtt --translate en

# Audio file
python -m subtitle_generator podcast.mp3 --output podcast.srt
```

## Output (SRT)

```
1
00:00:00,000 --> 00:00:03,400
[Speaker 1] Welcome to the show.

2
00:00:03,800 --> 00:00:07,100
[Speaker 2] Thanks for having me.
I've been looking forward to this.
```

## Supported formats

**Audio:** MP3, WAV, M4A, OGG, FLAC, AAC, OPUS
**Video:** MP4, MOV, WEBM, AVI

## Setup

```bash
# For audio files (cheapest — Gemini Flash)
export GOOGLE_API_KEY="your-gemini-key"

# For video files with visual context (Claude)
export ANTHROPIC_API_KEY="your-claude-key"
```

## Python API

```python
from subtitle_generator import generate_subtitles

srt_text, meta = generate_subtitles("interview.mp4", output_format="srt")
print(f"Generated {len(meta['segments'])} subtitle segments")
print(srt_text)
```

## License
MIT © [Alper Nabil Gabra Zakher](https://github.com/AlperNab)
