"""Decides whether a message is a delivery OTP and extracts a label and code.

Default deny: anything not clearly a delivery OTP is rejected (returns None).
The same rules run on the phone and, again, on the Pi.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

RULES = json.loads((Path(__file__).parent / "rules.json").read_text(encoding="utf-8"))

# Order / tracking ids look like numbers but are not the code.
_ORDER_ID = re.compile(r"\b\d{3}-\d{7}-\d{7}\b|\b[A-Z]{0,4}\d{8,}\b|\b[A-Z0-9]{2,}-\d{4,}\b")
_CODE_NEAR_KEYWORD = re.compile(
    r"(?:otp|code|कोड|ओटीपी)\D{0,25}?(\d{4,6})\b|\b(\d{4,6})\b\D{0,15}?(?:is your|is the|is delivery)",
    re.IGNORECASE,
)
_ANY_CODE = re.compile(r"(?<![\d-])(\d{4,6})(?![\d-])")
_ITEM = [
    re.compile(r"(?:order|delivery|package|parcel|shipment)\s+(?:of|for|containing)\s+(.{3,40}?)(?:[.,;:(]|\s+(?:is|has|will|from|ordered|with|order)\b|$)", re.IGNORECASE),
    re.compile(r"your\s+(.{3,40}?)\s+(?:order|package|parcel|shipment)\b", re.IGNORECASE),
]


@dataclass
class Otp:
    company: str
    code: str
    label: str  # what the delivery is: item name, or order tail, or just the company
    item: str   # item name only, "" when unknown


def _has_word(text: str, word: str) -> bool:
    if word.isascii() and word.replace(" ", "").isalpha():
        return re.search(r"\b" + re.escape(word) + r"\b", text) is not None
    return word in text


def _blocked(low: str) -> bool:
    """Financial words, and account / sign-up / phone-verification wording."""
    return any(_has_word(low, w) for w in RULES["financial_words"] + RULES["non_delivery_words"])


def _company(sender: str, text: str):
    s = re.sub(r"[^A-Z0-9]", "", sender.upper())
    for name, c in RULES["companies"].items():
        if s and any(tag in s for tag in c["senders"]):
            return name
    low = text.lower()
    for name, c in RULES["companies"].items():
        if any(_has_word(low, n) for n in c["names"]):
            return name
    return None


def _extract_code(text: str):
    stripped = _ORDER_ID.sub(" ", text)
    near = {a or b for a, b in _CODE_NEAR_KEYWORD.findall(stripped)}
    cands = set(_ANY_CODE.findall(stripped))
    if len(cands) != 1:
        return None  # none, or ambiguous: more than one possible code
    code = cands.pop()
    return code if not near or near == {code} else None


def _item(text: str, company: str) -> str:
    for pat in _ITEM:
        m = pat.search(text)
        if m:
            item = m.group(1).strip(" .,'\"")
            if item and not item.isdigit() and item.lower() != company.lower() and len(item) >= 3:
                return item
    return ""


def classify(sender: str, text: str):
    """Return an Otp for a clear delivery OTP, otherwise None."""
    if not text or len(text) > 600:
        return None
    low = text.lower()
    if _blocked(low):
        return None
    if not any(_has_word(low, w) for w in RULES["delivery_words"]):
        return None
    company = _company(sender or "", text)
    if company is None:
        return None
    code = _extract_code(text)
    if code is None:
        return None
    item = _item(text, company)
    order = _ORDER_ID.search(text)
    tail = f"…{order.group(0)[-4:]}" if order else ""
    if item:
        label = f"{company}: {item}" + (f" (order {tail})" if tail else "")
    else:
        label = f"{company}" + (f" order {tail}" if tail else "")
    return Otp(company=company, code=code, label=label, item=item)


_ITEM_OK = re.compile(r"^[\w &'.,()/+-]{0,40}$", re.UNICODE)


def validate(fields: dict):
    """Pi-side check of what the phone sends: company, item, order_tail, code only.

    No message text is accepted. Default deny: any unknown company, malformed
    field, or financial word in the item rejects the whole request.
    """
    if not isinstance(fields, dict) or set(fields) - {"company", "item", "order_tail", "code"}:
        return None
    company = fields.get("company")
    item = fields.get("item", "") or ""
    tail = fields.get("order_tail", "") or ""
    code = fields.get("code")
    names = {name.lower(): name for name in RULES["companies"]}
    company = names.get(company.lower()) if isinstance(company, str) else None
    if company is None:
        return None
    if not (isinstance(code, str) and re.fullmatch(r"\d{4,6}", code)):
        return None
    if not (isinstance(item, str) and _ITEM_OK.match(item)):
        return None
    if not (isinstance(tail, str) and re.fullmatch(r"[A-Za-z0-9]{0,4}", tail)):
        return None
    if _blocked(item.lower()):
        return None
    label = company + (f": {item}" if item else "")
    if tail:
        label += f" (order …{tail})" if item else f" order …{tail}"
    return Otp(company=company, code=code, label=label, item=item)
