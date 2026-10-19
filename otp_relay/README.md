# otp_relay

Forwards **delivery OTPs only** from your phone to people at home, and reads them out by voice.
Separate from the attendance code. Runs on the Raspberry Pi hub. Python 3.9+, standard library only.

## How it works

```
phone (SMS / WhatsApp share) --Tailscale--> Pi /ingest --> classify --> store (RAM, 30 min)
                                                              |-> Telegram / WhatsApp to chosen people
voice transcript (hub wake word) ----------> Pi /query  -----> spoken sentence (en / hi / mr)
```

## Privacy rules (enforced in code and tests)

- **Default deny.** A message is accepted only if it names an approved delivery company, uses delivery wording, has no financial word (`rules.json`, English, Hindi, Marathi) and has exactly one possible code. Anything else is rejected.
- **Two checks.** The phone filters first. The Pi runs the same `classify()` again on whatever arrives and deletes anything that fails. Rejected messages are never forwarded, read out, stored or logged; only a counter goes up.
- **Message text is used once.** The Pi keeps company, label (item, order tail), code and time. The text is dropped after classification. It is held in memory only for 30 minutes, never written to disk. The server writes no access log.
- **Send-only forwarding.** Telegram bot and the official WhatsApp Cloud API can send but cannot read your chats. The unofficial WhatsApp bridge is deliberately not supported.
- **Private transport.** Bearer token, bind to the Tailscale address, nothing exposed on the router.

## Setup (Pi)

1. Copy `config.example.json` to `otp_relay.config.json`; set `bind` to the Pi's Tailscale IP and fill in `recipients`.
2. Export `OTP_RELAY_TOKEN`, and `TELEGRAM_BOT_TOKEN` and/or `WHATSAPP_TOKEN`.
3. `python3 -m otp_relay.server`

WhatsApp needs a Meta business number and an approved template with one body parameter (default name `delivery_otp`).

## Phone side

- **iPhone, SMS:** Shortcuts automation "When I get a message", with a "Contains" filter on your approved senders and `otp`. Action: "Get contents of URL", `POST http://<pi-tailscale-ip>:8765/ingest`, header `Authorization: Bearer <token>`, JSON body `sender` and `text`.
- **iPhone, WhatsApp:** same Shortcut as a Share Sheet action ("Send OTP home"). One tap per message.
- **Android:** automate with a notification-listener tool (e.g. Tasker/MacroDroid) that calls the same endpoint for SMS and WhatsApp notifications from approved apps.

The Pi's check is the one that counts, so the phone filter can stay simple.

## Voice

`POST /query {"transcript": "..."}` returns `{"language", "speech"}`. The hub's wake-word pipeline passes the transcript and speaks the result. "What's the Amazon OTP?" reads that company's OTPs; naming the item narrows further.

## Tests

`python3 -m unittest discover -s otp_relay/tests -t .` (run from the repo root; no CI configured, run on your own machine).
