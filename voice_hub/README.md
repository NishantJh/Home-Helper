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
