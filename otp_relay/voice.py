"""Voice read-out. Takes the transcript from the hub's wake-word pipeline and
returns the sentence to speak (text-to-speech is done by the hub)."""
import re

from .classify import RULES

_HI = re.compile(r"[ऀ-ॿ]|batao|bataiye|bata do|kya hai", re.IGNORECASE)
_MR = re.compile(r"सांग|सांगा|काय आहे|sanga|sang\b|aahe", re.IGNORECASE)

_TEXT = {
    "en": {"none": "I have no delivery OTP right now.",
           "one": "{label}. OTP {digits}. Again: {digits}.",
           "more": "I have {n} OTPs. "},
    "hi": {"none": "अभी कोई डिलीवरी ओटीपी नहीं है।",
           "one": "{label}. ओटीपी {digits}. फिर से: {digits}.",
           "more": "{n} ओटीपी हैं। "},
    "mr": {"none": "सध्या कोणताही डिलिव्हरी ओटीपी नाही.",
           "one": "{label}. ओटीपी {digits}. पुन्हा: {digits}.",
           "more": "{n} ओटीपी आहेत. "},
}


def detect_language(transcript: str) -> str:
    if _MR.search(transcript):
        return "mr"
    if _HI.search(transcript):
        return "hi"
    return "en"


def _spaced(code: str) -> str:
    return " ".join(code)


def _matches(entry, transcript):
    """A company named in the request must match the OTP's company."""
    low = transcript.lower()
    named = [n for n, c in RULES["companies"].items() if any(x in low for x in c["names"])]
    return not named or entry.otp.company in named


def answer(store, transcript: str, max_items: int = 3):
    """Return (language, sentence) for a spoken request."""
    lang = detect_language(transcript)
    t = _TEXT[lang]
    entries = [e for e in store.recent() if _matches(e, transcript)]
    # An item named in the request narrows further (e.g. "the trimmer OTP").
    low = transcript.lower()
    named = [e for e in entries if e.otp.item and
             any(w in low for w in re.findall(r"[a-z]{4,}", e.otp.item.lower()))]
    entries = named or entries
    if not entries:
        return lang, t["none"]
    parts = []
    if len(entries) > 1:
        parts.append(t["more"].format(n=len(entries)))
    for e in entries[:max_items]:
        parts.append(t["one"].format(label=e.otp.label, digits=_spaced(e.otp.code)))
    return lang, " ".join(parts).strip()
