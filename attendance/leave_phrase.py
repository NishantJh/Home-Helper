"""Parse a spoken leave announcement (English, Hindi, Marathi) into a maid and date range.

"Sunita is on leave from 25 October to 27 October", "सुनीता की छुट्टी कल से शुक्रवार तक",
"सुनीता उद्यापासून 3 दिवस रजेवर". Numbers must be digits (Whisper writes them that way).
Pure functions: nothing is stored here.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

LEAVE_WORDS = {
    "leave", "off", "absent", "holiday", "vacation",
    "छुट्टी", "छुट्टियां", "छुट्टियाँ", "छुट्टे", "गैरहाज़िर", "गैरहाजिर", "अनुपस्थित",
    "रजा", "रजेवर", "रजेवरच", "सुट्टी", "सुट्टीवर", "गैरहजर", "गैरहजेरी",
}
# Hindi/Marathi attach case endings; match these word starts as well.
_LEAVE_PREFIXES = ("छुट्टी", "रजे", "सुट्टी")

DAY_UNITS = {"day", "days", "दिन", "दिनों", "दिवस", "दिवसांसाठी"}
RANGE_END = {"till", "until", "to", "तक", "पर्यंत", "पर्यंत्", "ते"}
RANGE_START = {"from", "से", "पासून", "पासुन"}
AND_WORDS = {"and", "और", "आणि", "तथा"}

_MONTHS = {
    1: ["january", "jan", "जनवरी", "जानेवारी"],
    2: ["february", "feb", "फरवरी", "फेब्रुवारी"],
    3: ["march", "mar", "मार्च"],
    4: ["april", "apr", "अप्रैल", "अप्रेल", "एप्रिल"],
    5: ["may", "मई", "मे"],
    6: ["june", "jun", "जून"],
    7: ["july", "jul", "जुलाई", "जुलै"],
    8: ["august", "aug", "अगस्त", "ऑगस्ट"],
    9: ["september", "sept", "sep", "सितंबर", "सितम्बर", "सप्टेंबर"],
    10: ["october", "oct", "अक्टूबर", "अक्तूबर", "ऑक्टोबर"],
    11: ["november", "nov", "नवंबर", "नवम्बर", "नोव्हेंबर"],
    12: ["december", "dec", "दिसंबर", "दिसम्बर", "डिसेंबर"],
}
MONTH_BY_WORD = {w: m for m, words in _MONTHS.items() for w in words}
MONTH_NAMES = {
    "en": ["", "January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "hi": ["", "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त",
           "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "mr": ["", "जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट",
           "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
}

_WEEKDAYS = {  # Monday = 0
    0: ["monday", "mon", "सोमवार", "सोमवारी"],
    1: ["tuesday", "tue", "tues", "मंगलवार", "मंगळवार"],
    2: ["wednesday", "wed", "बुधवार"],
    3: ["thursday", "thu", "thurs", "गुरुवार", "गुरूवार", "बृहस्पतिवार"],
    4: ["friday", "fri", "शुक्रवार"],
    5: ["saturday", "sat", "शनिवार"],
    6: ["sunday", "sun", "रविवार"],
}
WEEKDAY_BY_WORD = {w: d for d, words in _WEEKDAYS.items() for w in words}

# "कल" means tomorrow here: leave is announced ahead, and the read-back catches a mistake.
_RELATIVE = {
    "today": 0, "आज": 0,
    "tomorrow": 1, "कल": 1, "उद्या": 1,
    "parso": 2, "परसों": 2, "परवा": 2, "परवाच्या": 2,
    "yesterday": -1, "काल": -1,
}

_ORDINAL = re.compile(r"^(\d{1,2})(?:st|nd|rd|th|वीं|वा|वी|ला)?$")
MAX_SPAN_DAYS = 31
MAX_PAST_DAYS = 31


@dataclass
class LeaveIntent:
    maid: Optional[str]
    start: Optional[date]
    end: Optional[date]
    days: Optional[list] = None  # explicit separate days ("25 and 27"); start/end are its bounds
    error: Optional[str] = None  # "no_maid" | "no_date" | "bad_range"


def normalize(text):
    return text.translate(_DEVANAGARI_DIGITS).lower()


def tokenize(text):
    return [t for t in re.split(r"[\s,.;:!?\"'()\-/]+", normalize(text)) if t]


def is_leave_request(text):
    for t in tokenize(text):
        if t in LEAVE_WORDS or t.startswith(_LEAVE_PREFIXES):
            return True
    return False


def find_maid(text, names, aliases=None):
    """Return the one maid named in the text, or None (also None when two are named)."""
    low = normalize(text)
    found = set()
    for name in names:
        candidates = [name] + list((aliases or {}).get(name, []))
        if any(normalize(c) in low for c in candidates if c):
            found.add(name)
    return found.pop() if len(found) == 1 else None


def _safe_date(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_day(day, month, today):
    """A day (and maybe month) with no year: pick the nearest sensible occurrence."""
    year = today.year
    if month is None:
        d = _safe_date(year, today.month, day)
        if d is None or d < today - timedelta(days=7):
            nm, ny = (today.month % 12) + 1, today.year + (today.month == 12)
            d = _safe_date(ny, nm, day)
        return d
    d = _safe_date(year, month, day)
    if d is not None and d < today - timedelta(days=7):
        d = _safe_date(year + 1, month, day)
    return d


def _next_weekday(weekday, today):
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _mentions(tokens, today):
    """Dates and a duration, in the order spoken: [(index, date)], duration."""
    dates, duration = [], None
    i = 0
    while i < len(tokens):
        t = tokens[i]
        m = _ORDINAL.match(t)
        if m:
            n = int(m.group(1))
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            if nxt in DAY_UNITS:
                duration = n
                i += 2
                continue
            if 1 <= n <= 31:
                month = MONTH_BY_WORD.get(nxt)
                skip = 2 if month else 1
                if month is None and nxt == "of" and i + 2 < len(tokens):
                    month = MONTH_BY_WORD.get(tokens[i + 2])
                    skip = 3 if month else 1
                d = _resolve_day(n, month, today)
                if d:
                    dates.append((i, d))
                i += skip
                continue
        elif t in MONTH_BY_WORD and i + 1 < len(tokens) and _ORDINAL.match(tokens[i + 1]):
            n = int(_ORDINAL.match(tokens[i + 1]).group(1))  # "October 25"
            d = _resolve_day(n, MONTH_BY_WORD[t], today) if 1 <= n <= 31 else None
            if d:
                dates.append((i, d))
            i += 2
            continue
        elif t in _RELATIVE:
            dates.append((i, today + timedelta(days=_RELATIVE[t])))
        elif t in WEEKDAY_BY_WORD:
            dates.append((i, _next_weekday(WEEKDAY_BY_WORD[t], today)))
        i += 1
    return dates, duration


def parse_dates(text, today):
    """Return (start, end, days, error)."""
    tokens = tokenize(text)
    dates, duration = _mentions(tokens, today)
    if duration is not None:
        start = dates[0][1] if dates else today
        end = start + timedelta(days=duration - 1)
        return _check(start, end, None, today)
    if not dates:
        return None, None, None, "no_date"
    if len(dates) == 1:
        d = dates[0][1]
        if any(t in RANGE_END for t in tokens) and d > today and not any(
                t in RANGE_START for t in tokens):
            return _check(today, d, None, today)  # "till Friday"
        return _check(d, d, None, today)
    first, second = dates[0], dates[1]
    between = tokens[first[0]:second[0]]
    if any(t in AND_WORDS for t in between) and not any(t in RANGE_END for t in between):
        days = sorted({d for _, d in dates})
        return _check(days[0], days[-1], days, today)
    start, end = sorted((first[1], second[1]))
    return _check(start, end, None, today)


def _check(start, end, days, today):
    if end < start or (end - start).days >= MAX_SPAN_DAYS or (today - start).days > MAX_PAST_DAYS:
        return None, None, None, "bad_range"
    return start, end, days, None


def parse_leave(text, maid_names, today=None, aliases=None):
    """None when the text is not a leave announcement, otherwise a LeaveIntent."""
    if not is_leave_request(text):
        return None
    today = today or date.today()
    maid = find_maid(text, maid_names, aliases)
    start, end, days, err = parse_dates(text, today)
    if maid is None and err == "no_date":
        return None  # "leave the parcel at the door": no maid and no date
    if maid is None:
        return LeaveIntent(None, start, end, days, "no_maid")
    return LeaveIntent(maid, start, end, days, err)
