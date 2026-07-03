"""Unit tests for the per-track transcript assembler (pure function)."""
from api.capture.assembler import assemble_transcript, format_mmss


def seg(start, end, text, words=None):
    s = {"start": start, "end": end, "text": text}
    if words is not None:
        s["words"] = words
    return s


def test_interleaved_speakers_sorted_by_time():
    utts, text = assemble_transcript(
        [
            ("u1", "Alice", [seg(0.0, 2.0, "Hello everyone"), seg(10.0, 12.0, "Let's decide")]),
            ("u2", "Bob", [seg(3.0, 5.0, "Hi Alice")]),
        ]
    )
    assert [u["speaker_name"] for u in utts] == ["Alice", "Bob", "Alice"]
    assert text.splitlines()[0] == "[00:00] Alice: Hello everyone"


def test_same_speaker_gap_merge():
    utts, _ = assemble_transcript(
        [("u1", "Alice", [seg(0.0, 2.0, "First part"), seg(2.8, 4.0, "second part")])]
    )
    assert len(utts) == 1
    assert utts[0]["text"] == "First part second part"
    assert utts[0]["end"] == 4.0


def test_same_speaker_large_gap_not_merged():
    utts, _ = assemble_transcript(
        [("u1", "Alice", [seg(0.0, 2.0, "First"), seg(10.0, 11.0, "Later")])]
    )
    assert len(utts) == 2


def test_other_speaker_breaks_merge_run():
    utts, _ = assemble_transcript(
        [
            ("u1", "Alice", [seg(0.0, 2.0, "One"), seg(2.5, 3.5, "Two")]),
            ("u2", "Bob", [seg(2.1, 2.4, "Interject")]),
        ]
    )
    # Bob lands between Alice's segments → three utterances
    assert [u["speaker_name"] for u in utts] == ["Alice", "Bob", "Alice"]


def test_word_timestamps_refine_bounds():
    words = [
        {"word": "Hello", "start": 0.4, "end": 0.9},
        {"word": "there", "start": 1.0, "end": 1.4},
    ]
    utts, _ = assemble_transcript([("u1", "Alice", [seg(0.0, 3.0, "Hello there", words)])])
    assert utts[0]["start"] == 0.4
    assert utts[0]["end"] == 1.4


def test_empty_segments_dropped():
    utts, text = assemble_transcript([("u1", "Alice", [seg(0.0, 1.0, "  "), seg(1.0, 2.0, "")])])
    assert utts == []
    assert text == ""


def test_format_mmss():
    assert format_mmss(0) == "00:00"
    assert format_mmss(65.9) == "01:05"
    assert format_mmss(3605) == "60:05"
