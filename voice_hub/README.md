# voice_hub

Wake word -> listen -> transcribe -> handler -> spoken answer, on the Raspberry Pi.
Today it has one handler, the delivery-OTP read-out from `otp_relay`. The attendance
leave commands can plug in as another entry in the handler list (`__main__.py`).

```
mic -> openWakeWord -> record until silence -> faster-whisper (en/hi/mr, auto language)
    -> handlers in order: OTP request? -> POST /query to otp_relay -> espeak-ng speaks it
```

- Audio and transcripts are never saved or logged. The only network call is to `otp_relay` on the same Pi.
- A request is an OTP request if it says OTP / ओटीपी / one-time password / delivery code. "What's the Amazon OTP?" and naming the item both work (see `otp_relay/voice.py`).

## Run

```
sudo apt install espeak-ng libportaudio2
pip install -r voice_hub/requirements-voice.txt
export WAKEWORD_MODEL=/path/to/wakeword.onnx OTP_RELAY_TOKEN=...   # same token as otp_relay
python3 -m otp_relay.server &      # see otp_relay/README.md
python3 -m voice_hub
```

## To check on the real Pi (not testable from the cloud)

- **Wake word:** openWakeWord ships a few ready-made words; a custom word needs a model trained for it. Pick the word and set `WAKEWORD_MODEL`.
- **Speed:** Whisper `small` on a Pi 4 may take several seconds per request; set `WHISPER_MODEL=base` if so. Hindi and Marathi are less accurate than English, especially `base`.
- **Microphone level:** if it cuts off early or never stops, tune `speech_rms` in `adapters.recorder`. Set `AUDIO_IN_DEVICE` if the default input is wrong.
- **Voice:** espeak-ng speaks English, Hindi and Marathi but sounds robotic. Piper can replace `espeak_speaker` later.

## Tests

`python3 -m unittest discover -s voice_hub/tests -t .` from the repo root. They cover the loop and request routing with fake audio. The real audio code in `adapters.py` is not covered.

## Leave commands (attendance)

After the wake word, say e.g. "Sunita is on leave from 25 October to 27 October", "सुनीता की छुट्टी कल से शुक्रवार तक" or "सुनीता २५ ते २७ रजेवर" (also "for 3 days", "till Friday", "25th and 27th"). The hub reads the dates back; say yes/haan/होय within the next recording to log them, no/nahi/नको to cancel. Nothing is saved before the yes, and no audio or text is kept. Leave days are stored with source `voice`, so camera or voice "present" cannot overwrite them; the monthly summary applies the 2 paid leaves and deducts salary / days in month per unpaid day.

Set `ATTENDANCE_DB` to the register database. Hindi and Marathi speech usually comes back with the name in Devanagari, so add that spelling once per maid: `python3 -m attendance --db attendance.db add-alias Sunita सुनीता` (a JSON file named by `ATTENDANCE_ALIASES` also works). Yes must be a short, clear reply; anything negative ("not right", "wait") or unclear logs nothing. The monthly summary lists days logged by voice for review. Use `AUDIO_IN_DEVICE` to pick the USB mic. Numbers must be digits (Whisper normally writes them so); "कल" is read as tomorrow.

## Comparing speech-to-text engines (Whisper vs sherpa-onnx)

`STT_ENGINE=sherpa` swaps Whisper for sherpa-onnx (for example an IndicConformer int8 model). It does not detect the language, so give one model folder per language and pick with `STT_LANGUAGE`: `SHERPA_MODELS="hi=/home/pi/models/hi,mr=/home/pi/models/mr"`. Each folder needs `tokens.txt` plus either one `model*.onnx` or `encoder/decoder/joiner*.onnx` (int8 preferred); override the guess with `SHERPA_KIND`.

To compare on the Pi with the USB mic, say the same sentence once and run every engine on it:

```
python3 -m voice_hub.bench_stt --record 6 --device <mic> --reference "what you said" \
    --engine whisper:small --engine whisper:base --engine sherpa:hi=/home/pi/models/hi
```

It prints load time, decode time, real-time factor, CPU use and word error rate. Audio stays in memory.
