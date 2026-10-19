# otp_relay

Forwards **delivery OTPs only** from your phone to people at home, and reads them out by voice.
Separate from the attendance code. Runs on the Raspberry Pi hub. Python 3.9+, standard library only.

## How it works

```
phone (SMS / WhatsApp share) --Tailscale--> Pi /ingest --> validate --> store (RAM, 30 min)
                                                              |-> Telegram / WhatsApp to chosen people
voice transcript (hub wake word) ----------> Pi /query  -----> spoken sentence (en / hi / mr)
```

## Privacy rules (enforced in code and tests)

- **Default deny.** A message is accepted only if it names an approved delivery company, uses delivery wording, has no financial word (`rules.json`, English, Hindi, Marathi) and has exactly one possible code. Anything else is rejected.
- **Two checks, no message text.** The phone reads the message, applies `classify()`'s rules (the reference for the Shortcut or Android rules) and sends **only** `company`, `item`, `order_tail` (last 4 characters) and `code`. The Pi never receives message text: `validate()` rejects any request with other fields, an unapproved company, a malformed code, an over-long or unusual item, or a financial word in the label. Rejected requests are never forwarded, read out or stored; only a counter goes up.
- **Short-lived, in memory.** The Pi keeps those four fields and the time, in memory only, for 30 minutes. The server writes no access log.
- **Send-only forwarding.** Telegram bot and the official WhatsApp Cloud API can send but cannot read your chats. The unofficial WhatsApp bridge is deliberately not supported.
- **Private transport.** Bearer token, bind to the Tailscale address, nothing exposed on the router.

## Setup (Pi)

1. Copy `config.example.json` to `otp_relay.config.json`; set `bind` to the Pi's Tailscale IP and fill in `recipients`.
2. Export `OTP_RELAY_TOKEN`, and `TELEGRAM_BOT_TOKEN` and/or `WHATSAPP_TOKEN`.
3. `python3 -m otp_relay.server`

WhatsApp needs a Meta business number and an approved template with one body parameter (default name `delivery_otp`).

## Phone side

- **iPhone, SMS:** Shortcuts automation "When I get a message", filtered to your approved senders. The Shortcut applies the rules in `rules.json` / `classify.py` (Match Text actions: delivery and financial words, the code, the item) and stops if anything fails. Then "Get contents of URL": `POST http://<pi-tailscale-ip>:8765/ingest`, header `Authorization: Bearer <token>`, JSON body `company`, `item`, `order_tail`, `code`.
- **iPhone, WhatsApp:** same Shortcut as a Share Sheet action ("Send OTP home"). One tap per message.
- **Android:** automate with a notification-listener tool (e.g. Tasker/MacroDroid) that calls the same endpoint for SMS and WhatsApp notifications from approved apps.

The phone filter is the main guard for bank OTPs, since the Pi no longer sees the text. Keep it strict; the Pi only checks the fields it receives.

## Voice

`POST /query {"transcript": "..."}` returns `{"language", "speech"}`. The hub's wake-word pipeline passes the transcript and speaks the result. "What's the Amazon OTP?" reads that company's OTPs; naming the item narrows further.

## Tests

`python3 -m unittest discover -s otp_relay/tests -t .` (run from the repo root; no CI configured, run on your own machine).
