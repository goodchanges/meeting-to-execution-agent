from datetime import date

import pytest

from backend.app.transcripts import TranscriptError, deadline_for, parse


@pytest.mark.parametrize(
    ("fmt", "source", "speaker", "stamp"),
    [
        ("txt", "[00:01:23] Sarah: Test.\nUnattributed sentence", "Sarah", "00:01:23"),
        (
            "vtt",
            "WEBVTT\n\n00:00:05.000 --> 00:00:07.000\n<v Sarah>Test.</v>",
            "Sarah",
            "00:00:05.000",
        ),
        (
            "srt",
            "1\n00:00:05,000 --> 00:00:07,000\nSarah: Test.",
            "Sarah",
            "00:00:05,000",
        ),
        ("txt", "Unattributed sentence", None, None),
    ],
)
def test_attribution(fmt, source, speaker, stamp):
    record = parse(source, fmt, 100)[0]
    assert record.speaker_label == speaker
    assert record.start_ts == stamp
    assert record.record(0)["speaker_resolved"] == (speaker is not None)


@pytest.mark.parametrize(
    ("fmt", "source", "error"),
    [
        ("vtt", "WEBVTT\n\n00:99 --> 00:00:00.000\nText", "line 3"),
        ("txt", "abc\0def", "control characters"),
        ("txt", "\n", "no spoken text"),
        ("srt", "1\n00:00:05,000 --> 00:00:07,000", "no spoken text"),
    ],
)
def test_malformed(fmt, source, error):
    with pytest.raises(TranscriptError, match=error):
        parse(source, fmt, 100)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("by Friday", date(2026, 11, 20)),
        ("next week", date(2026, 11, 23)),
        ("Dec 2", date(2026, 12, 2)),
        ("tomorrow", date(2026, 11, 19)),
        ("sometime soon", None),
        (None, None),
        ("Feb 30", None),
    ],
)
def test_deadlines(raw, expected):
    assert deadline_for(raw, date(2026, 11, 18)) == expected
