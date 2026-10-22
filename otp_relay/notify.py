"""Forwarding to chosen people. Send-only channels: neither can read your messages."""
import json
import time
import urllib.request


def format_message(entry) -> str:
    local = time.strftime("%I:%M %p", time.localtime(entry.received_at)).lstrip("0")
    return f"{entry.otp.label}, OTP {entry.otp.code}, came at {local.lower()}"


def _post_json(url, payload, headers=None):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def send_telegram(token, chat_id, text, post=_post_json):
    return post(f"https://api.telegram.org/bot{token}/sendMessage",
                {"chat_id": chat_id, "text": text})


def send_whatsapp(token, phone_number_id, to, text, template, post=_post_json):
    """WhatsApp Cloud API (official). Business-initiated messages need an approved
    template with one body parameter that receives the OTP text."""
    return post(
        f"https://graph.facebook.com/v20.0/{phone_number_id}/messages",
        {"messaging_product": "whatsapp", "to": to, "type": "template",
         "template": {"name": template, "language": {"code": "en"},
                      "components": [{"type": "body",
                                      "parameters": [{"type": "text", "text": text}]}]}},
        {"Authorization": f"Bearer {token}"})


def recipients_for(config, company):
    out = []
    for r in config.get("recipients", []):
        wanted = r.get("companies", ["*"])
        if "*" in wanted or company in wanted:
            out.append(r)
    return out


def forward(entry, config, secrets, telegram=send_telegram, whatsapp=send_whatsapp):
    """Send to everyone configured for this company. Returns names sent to."""
    text = format_message(entry)
    sent = []
    for r in recipients_for(config, entry.otp.company):
        try:
            if r["channel"] == "telegram":
                telegram(secrets["TELEGRAM_BOT_TOKEN"], r["address"], text)
            elif r["channel"] == "whatsapp":
                whatsapp(secrets["WHATSAPP_TOKEN"], config["whatsapp"]["phone_number_id"],
                         r["address"], text, config["whatsapp"]["template"])
            else:
                continue
            sent.append(r["name"])
        except Exception:
            continue  # a failed send must never log or echo the OTP
    return sent
