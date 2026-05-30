#!/usr/bin/env python3
"""
subtitle-generator — video/audio → SRT/VTT subtitles with speaker labels
Uses Gemini 2.5 Flash for audio (cheapest/fastest), Claude for cleanup
Supports: multi-language, speaker diarization, burned-in caption export
"""
import anthropic
import base64
import json
import re
import sys
import os
from pathlib import Path
from datetime import timedelta


def format_timestamp_srt(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    total = int(td.total_seconds())
    ms = int((td.total_seconds() - total) * 1000)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    return format_timestamp_srt(seconds).replace(",", ".")


SYSTEM = """You are a professional subtitler and video accessibility specialist.
Generate accurate, readable subtitles from the provided transcript data.

Rules for good subtitles:
- Max 42 characters per line, max 2 lines per subtitle block
- Each block should be 1-7 seconds long ideally
- Break at natural speech pauses, never mid-word
- Preserve speaker labels when diarization is available
- Correct obvious transcription errors
- Format proper nouns, brand names correctly

Return ONLY valid JSON:
{
  "segments": [
    {
      "index": 1,
      "start": 0.0,
      "end": 3.5,
      "speaker": "Speaker 1 or null",
      "text": "subtitle text",
      "lines": ["line 1", "line 2 optional"]
    }
  ],
  "language": "en",
  "total_duration": 0.0,
  "word_count": 0,
  "speaker_count": 0
}"""


def transcribe_with_gemini(file_path: Path) -> dict:
    """Use Gemini 2.5 Flash for audio transcription — cheapest option."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))

        model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")

        suffix = file_path.suffix.lower()
        mime_types = {
            ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
            ".ogg": "audio/ogg", ".flac": "audio/flac", ".aac": "audio/aac",
            ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
        }
        mime = mime_types.get(suffix, "audio/mpeg")

        data = base64.standard_b64encode(file_path.read_bytes()).decode("ascii")

        prompt = """Transcribe this audio/video completely. Include timestamps and speaker labels.

Return JSON:
{
  "transcript": [
    {"start": 0.0, "end": 3.5, "speaker": "Speaker 1", "text": "what was said"}
  ],
  "language": "en",
  "total_duration": 120.0
}"""

        response = model.generate_content([
            {"inline_data": {"mime_type": mime, "data": data}},
            prompt
        ])

        raw = response.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        return json.loads(raw)

    except ImportError:
        raise ImportError("Install google-generativeai: pip install google-generativeai")


def transcribe_with_claude(file_path: Path) -> dict:
    """Fallback transcription using Claude (for video files with visual context)."""
    client = anthropic.Anthropic()
    suffix = file_path.suffix.lower()

    mime_types = {
        ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".webm": "video/webm", ".avi": "video/x-msvideo",
    }

    if suffix not in mime_types:
        raise ValueError(f"For audio-only files, use Gemini (set GOOGLE_API_KEY). Got: {suffix}")

    data = base64.standard_b64encode(file_path.read_bytes()).decode("ascii")
    mime = mime_types[suffix]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": mime, "data": data}},
                {"type": "text", "text": 'Transcribe all speech. Return JSON: {"transcript": [{"start": 0.0, "end": 3.0, "speaker": "Speaker 1", "text": "speech"}], "language": "en", "total_duration": 0.0}'}
            ]
        }]
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
    return json.loads(raw)


def format_subtitles(transcript_data: dict, translate_to: str | None = None) -> dict:
    """Use Claude to clean up and format transcript into proper subtitle segments."""
    client = anthropic.Anthropic()

    prompt = f"""Convert this transcript into properly formatted subtitles.
{"Also translate to " + translate_to if translate_to else "Keep original language."}

Transcript:
{json.dumps(transcript_data, ensure_ascii=False)}"""

    response = client.messages.create(
        model="claude-haiku-4-20250514",
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
    return json.loads(raw)


def to_srt(subtitles: dict) -> str:
    lines = []
    for seg in subtitles.get("segments", []):
        lines.append(str(seg["index"]))
        lines.append(f"{format_timestamp_srt(seg['start'])} --> {format_timestamp_srt(seg['end'])}")
        speaker = seg.get("speaker")
        text = seg.get("text", "")
        if speaker:
            lines.append(f"[{speaker}] {text}")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines)


def to_vtt(subtitles: dict) -> str:
    lines = ["WEBVTT", ""]
    for seg in subtitles.get("segments", []):
        lines.append(f"{format_timestamp_vtt(seg['start'])} --> {format_timestamp_vtt(seg['end'])}")
        speaker = seg.get("speaker")
        text = seg.get("text", "")
        if speaker:
            lines.append(f"<v {speaker}>{text}")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines)


def generate_subtitles(
    file_path: str,
    output_format: str = "srt",
    translate_to: str | None = None,
    engine: str = "auto"
) -> tuple[str, dict]:
    """Generate subtitles for a video/audio file.

    Returns (subtitle_text, metadata_dict)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Not found: {file_path}")

    # Transcribe
    suffix = path.suffix.lower()
    audio_formats = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus"}

    if engine == "gemini" or (engine == "auto" and (suffix in audio_formats or os.environ.get("GOOGLE_API_KEY"))):
        print("Transcribing with Gemini 2.5 Flash...", file=sys.stderr)
        transcript = transcribe_with_gemini(path)
    else:
        print("Transcribing with Claude...", file=sys.stderr)
        transcript = transcribe_with_claude(path)

    print("Formatting subtitles...", file=sys.stderr)
    subtitles = format_subtitles(transcript, translate_to)

    if output_format == "vtt":
        return to_vtt(subtitles), subtitles
    elif output_format == "json":
        return json.dumps(subtitles, indent=2, ensure_ascii=False), subtitles
    else:
        return to_srt(subtitles), subtitles


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate subtitles for any video or audio file")
    parser.add_argument("input", help="Video or audio file path")
    parser.add_argument("--format", "-f", choices=["srt", "vtt", "json"], default="srt")
    parser.add_argument("--output", "-o", help="Output file path (default: same name as input)")
    parser.add_argument("--translate", "-t", help="Translate to language code (e.g. en, fr, ar)")
    parser.add_argument("--engine", choices=["auto", "gemini", "claude"], default="auto")
    args = parser.parse_args()

    subtitle_text, meta = generate_subtitles(
        args.input, args.format, args.translate, args.engine
    )

    if args.output:
        Path(args.output).write_text(subtitle_text, encoding="utf-8")
        print(f"Saved to: {args.output}")
    else:
        input_path = Path(args.input)
        out_path = input_path.with_suffix(f".{args.format}")
        out_path.write_text(subtitle_text, encoding="utf-8")
        print(f"Saved to: {out_path}")
        print(f"Segments: {len(meta.get('segments', []))}")
        print(f"Language: {meta.get('language', '?')}")
        print(f"Speakers: {meta.get('speaker_count', '?')}")
        print(f"Duration: {meta.get('total_duration', 0):.1f}s")
