"""Transcript assembler — merge per-track STT segments into the canonical transcript.

Pure functions, stdlib only, no I/O — unit-testable in isolation (tests/test_assembler.py).

Contract (CONTRACTS.md, "Provided by meetings-capture"):
  utterances = [{"speaker_identity": str, "speaker_name": str,
                 "start": float, "end": float, "text": str}, ...]  sorted by start
  canonical_text = lines of "[mm:ss] Name: text"

Because capture is per-participant track (plan §2), speaker attribution is a fact:
each track belongs to exactly one participant, so merging is a pure timestamp sort.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

# Adjacent same-speaker segments closer than this gap (seconds) are merged into
# one utterance. Overlapping segments (negative gap) merge too.
MERGE_GAP_S = 1.5

# A single track's transcription: (participant_identity, participant_name, segments).
# Each segment is a mapping with "start", "end", "text" and optionally "words"
# (list of {"word", "start", "end"}) — the shape produced by stt.transcribe.
TrackSegments = tuple[str, str, Sequence[Mapping[str, Any]]]


def assemble_transcript(
    tracks: Sequence[TrackSegments],
    merge_gap_s: float = MERGE_GAP_S,
) -> tuple[list[dict[str, Any]], str]:
    """Merge per-track segments into (utterances, canonical_text).

    - Utterances are sorted by start time (ties broken by end time).
    - Adjacent utterances from the same speaker with a gap < ``merge_gap_s``
      are merged; an interleaved utterance from another speaker breaks the run.
    - Word timestamps, when present, refine each segment's start/end bounds.
    - Empty/whitespace-only segments are dropped.
    """
    raw: list[dict[str, Any]] = []
    for identity, name, segments in tracks:
        for seg in segments:
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            words = seg.get("words") or []
            if words:
                start = float(words[0]["start"])
                end = float(words[-1]["end"])
            else:
                start = float(seg["start"])
                end = float(seg["end"])
            raw.append(
                {
                    "speaker_identity": identity,
                    "speaker_name": name,
                    "start": start,
                    "end": end,
                    "text": text,
                }
            )

    raw.sort(key=lambda u: (u["start"], u["end"]))

    merged: list[dict[str, Any]] = []
    for utt in raw:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and prev["speaker_identity"] == utt["speaker_identity"]
            and (utt["start"] - prev["end"]) < merge_gap_s
        ):
            prev["text"] = f"{prev['text']} {utt['text']}"
            prev["end"] = max(prev["end"], utt["end"])
        else:
            merged.append(dict(utt))

    for utt in merged:
        utt["start"] = round(utt["start"], 3)
        utt["end"] = round(utt["end"], 3)

    canonical_text = "\n".join(
        f"[{format_mmss(u['start'])}] {u['speaker_name']}: {u['text']}" for u in merged
    )
    return merged, canonical_text


def format_mmss(seconds: float) -> str:
    """Format a positive offset in seconds as zero-padded mm:ss (minutes may exceed 59)."""
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"
