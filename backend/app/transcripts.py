import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta


class TranscriptError(ValueError):
    pass


@dataclass
class Segment:
    speaker_label: str | None
    start_ts: str | None
    end_ts: str | None
    text: str

    def record(self, index: int):
        return {
            **asdict(self),
            "idx": index,
            "speaker_resolved": self.speaker_label is not None,
        }


STAMP = r"(?:\d{2,}:)?[0-5]\d:[0-5]\d[.,]\d{3}"
NAME = r"[^:\d<>\[\]\n][^:<>\[\]\n]{0,78}"
ATTRIBUTION = re.compile(rf"^({NAME}):\s*(.+)$", re.DOTALL)
VOICE = re.compile(rf"^<v\s+({NAME})>(.*?)(?:</v>)?$", re.DOTALL)
TEXT_STAMP = re.compile(r"^\[(\d{2,}:[0-5]\d:[0-5]\d)\]\s*")
FILE_DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")


def date_from_filename(filename: str) -> date | None:
    match = FILE_DATE.search(filename)
    try:
        return date.fromisoformat(match[1]) if match else None
    except ValueError:
        return None


def attributed(text: str, start: str | None = None, end: str | None = None) -> Segment:
    text = text.strip()
    prefix = TEXT_STAMP.match(text)
    if prefix:
        start = start or prefix[1]
        text = text[prefix.end() :].strip()
    speaker = VOICE.fullmatch(text) or ATTRIBUTION.fullmatch(text)
    if speaker and speaker[1].strip() and speaker[2].strip():
        return Segment(speaker[1].strip(), start, end, speaker[2].strip())
    return Segment(None, start, end, text)


def millis(stamp: str) -> int:
    whole, fraction = stamp.replace(",", ".").split(".")
    seconds = 0
    for component in whole.split(":"):
        seconds = seconds * 60 + int(component)
    return seconds * 1000 + int(fraction)


def parse(source: str, fmt: str, maximum: int) -> list[Segment]:
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", source):
        raise TranscriptError("Transcript contains unsupported control characters.")
    lines = source.lstrip("\ufeff").splitlines()
    if fmt == "txt":
        segments = [attributed(line) for line in lines if line.strip()]
    else:
        segments = parse_cues(lines, fmt)
    segments = [segment for segment in segments if segment.text]
    if not segments:
        raise TranscriptError("Transcript has no spoken text.")
    if len(segments) > maximum:
        raise TranscriptError(f"Transcript may contain at most {maximum} segments.")
    return segments


def parse_cues(lines: list[str], fmt: str) -> list[Segment]:
    if fmt == "vtt" and (
        not lines or not re.fullmatch(r"WEBVTT(?:[ \t].*)?", lines[0])
    ):
        raise TranscriptError("VTT must start with WEBVTT.")
    if fmt == "vtt" and len(lines) > 1 and lines[1].strip():
        raise TranscriptError("VTT header must end with a blank line.")
    segments: list[Segment] = []
    index = int(fmt == "vtt")
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        first = index
        while index < len(lines) and lines[index].strip():
            index += 1
        cue = lines[first:index]
        if fmt == "vtt" and re.match(r"^(?:NOTE(?:\s|$)|STYLE$|REGION$)", cue[0]):
            continue
        offset = int("-->" not in cue[0])
        stamp_line = cue[offset] if len(cue) > offset else ""
        timestamp = re.fullmatch(rf"({STAMP})\s+-->\s+({STAMP})(?:\s+.*)?", stamp_line)
        if not timestamp or millis(timestamp[2]) < millis(timestamp[1]):
            raise TranscriptError(
                f"{fmt.upper()} cue at line {first + offset + 1} has an invalid timestamp."
            )
        spoken = cue[offset + 1 :]
        if not spoken:
            raise TranscriptError(
                f"{fmt.upper()} cue at line {first + 1} has no spoken text."
            )
        if any(
            VOICE.fullmatch(line.strip()) or ATTRIBUTION.fullmatch(line.strip())
            for line in spoken[1:]
        ):
            segments.extend(
                attributed(line, timestamp[1], timestamp[2]) for line in spoken
            )
        else:
            segments.append(attributed("\n".join(spoken), timestamp[1], timestamp[2]))
    return segments


WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def deadline_for(raw: str | None, meeting: date) -> date | None:
    if not raw:
        return None
    raw = re.sub(r"^by\s+", "", raw.strip().casefold()).strip(" .")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    if raw in {"today", "tomorrow"}:
        return meeting + timedelta(days=int(raw == "tomorrow"))
    if raw == "next week":
        return meeting + timedelta(days=7 - meeting.weekday())
    day = raw.removeprefix("next ")
    if day in WEEKDAYS:
        offset = WEEKDAYS.index(day) - meeting.weekday()
        return meeting + timedelta(
            days=offset + 7 if raw.startswith("next ") or offset < 0 else offset
        )
    months = "jan feb mar apr may jun jul aug sep oct nov dec".split()
    match = re.fullmatch(r"([a-z]{3,9})\s+(\d{1,2})(?:,?\s+(\d{4}))?", raw)
    if match and match[1] in {
        *months,
        "january",
        "february",
        "march",
        "april",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }:
        month = months.index(match[1][:3]) + 1
        try:
            day_date = date(int(match[3] or meeting.year), month, int(match[2]))
            if not match[3] and day_date < meeting:
                day_date = day_date.replace(year=meeting.year + 1)
            return day_date
        except ValueError:
            return None
    return None
