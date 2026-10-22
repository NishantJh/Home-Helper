"""Spoken leave commands: parse, read back, and log on a "yes".

Nothing is written until the person confirms. The transcript is not kept; only the leave
days are saved (source "voice"), so a later camera/voice "present" cannot overwrite them.
"""
import json
import os
from datetime import date, timedelta

from attendance import leave_phrase as lp
from attendance import register
from attendance.db import open_db
from otp_relay.voice import detect_language as _detect

from .pipeline import Reply

YES = {"yes", "yeah", "yep", "yup", "correct", "right", "ok", "okay", "confirm", "sure",
       "haan", "han", "हाँ", "हां", "हा", "जी", "सही", "ठीक", "होय", "हो", "बरोबर"}
NO = {"no", "nope", "cancel", "wrong", "nahi", "नहीं", "नही", "नको", "नाही", "गलत", "ग़लत",
      "रद्द"}

_T = {
    "en": {
        "which": "Which maid? I didn't catch the name.",
        "dates": "I didn't catch the dates. Please say the leave again.",
        "range": "Those dates don't look right. Please say the leave again.",
        "one": "{name} on leave on {a}. Is that right?",
        "many": "{name} on leave from {a} to {b}, {n} days. Is that right?",
        "days": "{name} on leave on {list}. Is that right?",
        "done": "Logged. {name} has used {used} of {paid} paid leaves in {month}, {unpaid} unpaid.",
        "no": "Okay, not logged.",
        "unclear": "I didn't catch yes or no, so nothing was logged.",
    },
    "hi": {
        "which": "किस की छुट्टी? मैं नाम नहीं समझ पाया।",
        "dates": "मैं तारीखें नहीं समझ पाया। कृपया फिर से बताइए।",
        "range": "ये तारीखें सही नहीं लगतीं। कृपया फिर से बताइए।",
        "one": "{name} की छुट्टी {a} को। सही है?",
        "many": "{name} की छुट्टी {a} से {b} तक, {n} दिन। सही है?",
        "days": "{name} की छुट्टी {list} को। सही है?",
        "done": "दर्ज हो गया। {month} में {name} की {paid} में से {used} सवेतन छुट्टियाँ हुईं, {unpaid} बिना वेतन।",
        "no": "ठीक है, दर्ज नहीं किया।",
        "unclear": "हाँ या नहीं समझ नहीं आया, इसलिए कुछ दर्ज नहीं हुआ।",
    },
    "mr": {
        "which": "कोणाची रजा? मला नाव समजले नाही.",
        "dates": "मला तारखा समजल्या नाहीत. कृपया पुन्हा सांगा.",
        "range": "या तारखा बरोबर वाटत नाहीत. कृपया पुन्हा सांगा.",
        "one": "{name} ची रजा {a} रोजी. बरोबर आहे का?",
        "many": "{name} ची रजा {a} ते {b}, {n} दिवस. बरोबर आहे का?",
        "days": "{name} ची रजा {list} रोजी. बरोबर आहे का?",
        "done": "नोंद झाली. {month} मध्ये {name} च्या {paid} पैकी {used} पगारी रजा झाल्या, {unpaid} बिनपगारी.",
        "no": "ठीक आहे, नोंद केली नाही.",
        "unclear": "होय किंवा नाही समजले नाही, म्हणून काही नोंदवले नाही.",
    },
}


_MR_WORDS = {"ते", "पर्यंत", "पासून", "उद्या", "परवा", "काल", "आहे", "आणि", "होय", "नको", "नाही"}


def detect_language(text):
    tokens = lp.tokenize(text)
    if any(t in _MR_WORDS or t.startswith(("रजे", "रजा", "सुट्टी")) for t in tokens):
        return "mr"
    return _detect(text)


def _fmt(d, lang, today):
    year = f" {d.year}" if d.year != today.year else ""
    return f"{d.day} {lp.MONTH_NAMES[lang][d.month]}{year}"


_NEGATIVE = NO | {"not", "never", "incorrect", "galat", "mat", "nako", "nahin", "wait", "hold",
                  "stop", "isnt", "dont", "wasnt", "didnt", "cant", "wont", "मत", "रुको", "थांबा"}
MAX_ANSWER_WORDS = 4


def _answer(text):
    """True for a short, clear yes; False for anything negative; None when unclear."""
    tokens = lp.tokenize(text.replace("'", "").replace("\u2019", ""))
    if set(tokens) & _NEGATIVE:
        return False
    if len(tokens) <= MAX_ANSWER_WORDS and set(tokens) & YES:
        return True
    return None


def load_aliases(path=None):
    path = path or os.environ.get("ATTENDANCE_ALIASES")
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_leave_handler(db_path="attendance.db", aliases=None, today=date.today):
    """Handler for voice_hub: returns None unless the transcript is a leave announcement."""
    aliases = aliases if aliases is not None else load_aliases()

    def handler(text):
        now = today()
        with open_db(db_path) as conn:
            names = [m["name"] for m in register.list_maids(conn)]
            known = {n: list(a) for n, a in register.list_aliases(conn).items()}
        for n, a in aliases.items():
            known.setdefault(n, []).extend(a)
        intent = lp.parse_leave(text, names, now, known)
        if intent is None:
            return None
        lang = detect_language(text)
        t = _T[lang]
        if intent.error == "no_maid":
            return Reply(t["which"], lang)
        if intent.error == "no_date":
            return Reply(t["dates"], lang)
        if intent.error:
            return Reply(t["range"], lang)

        days = intent.days or [intent.start + timedelta(n)
                               for n in range((intent.end - intent.start).days + 1)]
        if len(days) == 1:
            ask = t["one"].format(name=intent.maid, a=_fmt(days[0], lang, now))
        elif intent.days:
            ask = t["days"].format(name=intent.maid, list=", ".join(_fmt(d, lang, now) for d in days))
        else:
            ask = t["many"].format(name=intent.maid, a=_fmt(days[0], lang, now),
                                   b=_fmt(days[-1], lang, now), n=len(days))

        def confirm(answer_text):
            verdict = _answer(answer_text)
            if verdict is None:
                return Reply(t["unclear"], lang)
            if not verdict:
                return Reply(t["no"], lang)
            with open_db(db_path) as conn:
                for d in days:
                    register.mark(conn, intent.maid, d, "leave", source="voice")
                row = _month_row(conn, intent.maid, days[0], now)
            return Reply(t["done"].format(
                name=intent.maid, used=row["paid_leave_days"], paid=row["paid_leaves_allowed"],
                unpaid=row["unpaid_leave_days"], month=lp.MONTH_NAMES[lang][days[0].month]), lang)

        return Reply(ask, lang, then=confirm)

    return handler


def _month_row(conn, name, day, today):
    rows = register.month_summary(conn, day.year, day.month, today)
    return next(r for r in rows if r["name"] == name)
