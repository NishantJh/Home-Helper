"""Real audio components. Imports are lazy so the rest of the package and the
tests need none of these libraries. Written for the Pi; not exercised in CI."""
import subprocess

RATE = 16000


def wake_word_listener(model, threshold=0.5, device=None):
    """Blocks until openWakeWord hears the wake word. `model` is either the path
    to a .onnx/.tflite file or the name of a ready-made word (alexa, hey_jarvis,
    hey_mycroft, hey_rhasspy), which is downloaded on first use."""
    import os

    import numpy as np
    import sounddevice as sd
    from openwakeword.model import Model
    from openwakeword.utils import download_models

    if not os.path.exists(model):
        download_models([model])
    model_path = model

    model = Model(wakeword_models=[model_path])
    frame = 1280  # 80 ms at 16 kHz, the size openWakeWord expects

    def wait():
        model.reset()
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                            blocksize=frame, device=device) as stream:
            while True:
                data, _ = stream.read(frame)
                scores = model.predict(np.squeeze(data))
                if any(score >= threshold for score in scores.values()):
                    return
    return wait


def recorder(device=None, speech_rms=500, silence_s=1.0, no_speech_s=4.0, max_s=10.0):
    """Records one utterance with simple energy endpointing. Returns float32
    mono audio, or None if nobody spoke. Tune `speech_rms` to your microphone."""
    import numpy as np
    import sounddevice as sd

    frame = int(RATE * 0.03)

    def record():
        chunks, started, quiet = [], False, 0.0
        elapsed = 0.0
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                            blocksize=frame, device=device) as stream:
            while elapsed < max_s:
                data, _ = stream.read(frame)
                pcm = np.squeeze(data)
                elapsed += 0.03
                loud = float(np.sqrt(np.mean(pcm.astype("float32") ** 2))) >= speech_rms
                if loud:
                    started, quiet = True, 0.0
                elif started:
                    quiet += 0.03
                if started:
                    chunks.append(pcm)
                    if quiet >= silence_s:
                        break
                elif elapsed >= no_speech_s:
                    return None
        if not chunks:
            return None
        return np.concatenate(chunks).astype("float32") / 32768.0
    return record


def whisper_transcriber(model_size="small", cpu_threads=4):
    """faster-whisper on CPU. Language is auto-detected, so English, Hindi and
    Marathi all work. Try "base" if "small" is too slow on the Pi 4."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=cpu_threads)

    def transcribe(audio):
        segments, _info = model.transcribe(audio, vad_filter=True, beam_size=1)
        return " ".join(s.text for s in segments)
    return transcribe


def espeak_speaker(voices=None, speed=130):
    """Speaks through the default audio output with espeak-ng (en, hi, mr).
    Robotic but dependable offline; swap in Piper later for nicer voices."""
    voices = voices or {"en": "en-in", "hi": "hi", "mr": "mr"}

    def speak(text, language):
        subprocess.run(["espeak-ng", "-v", voices.get(language, "en"), "-s", str(speed), text],
                       check=False)
    return speak
