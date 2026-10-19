"""python -m voice_hub  (settings come from environment variables)

  WAKEWORD_MODEL      path to the openWakeWord model file (required)
  OTP_RELAY_URL       default http://127.0.0.1:8765/query
  OTP_RELAY_TOKEN     same token the otp_relay server uses
  WHISPER_MODEL       default small
  AUDIO_IN_DEVICE     sounddevice input index or name (optional)
"""
import os

from otp_relay.voice import detect_language

from . import adapters
from .otp_handler import make_otp_handler
from .pipeline import Hub


def build_hub():
    device = os.environ.get("AUDIO_IN_DEVICE") or None
    if device is not None and device.isdigit():
        device = int(device)
    handlers = [make_otp_handler(os.environ.get("OTP_RELAY_URL", "http://127.0.0.1:8765/query"),
                                 os.environ.get("OTP_RELAY_TOKEN", ""))]
    # Add other handlers (for example the attendance leave commands) to this list.
    return Hub(
        wait_for_wake=adapters.wake_word_listener(os.environ["WAKEWORD_MODEL"], device=device),
        listen=adapters.recorder(device=device),
        transcribe=adapters.whisper_transcriber(os.environ.get("WHISPER_MODEL", "small")),
        speak=adapters.espeak_speaker(),
        handlers=handlers,
        detect_language=detect_language,
    )


if __name__ == "__main__":
    build_hub().run_forever()
