"""Speech-to-text engines. Each factory returns transcribe(audio) -> str, where audio is
16 kHz mono float32, so the hub and the benchmark can swap engines freely.

  STT_ENGINE=whisper  (default)  faster-whisper, language auto-detected
  STT_ENGINE=sherpa              sherpa-onnx with an Indic model such as IndicConformer int8

sherpa needs a model folder per language (it does not auto-detect the language):
  SHERPA_MODELS="hi=/home/pi/models/hi,mr=/home/pi/models/mr"   STT_LANGUAGE=hi
  SHERPA_KIND=transducer|nemo_ctc|dolphin_ctc   (optional; guessed from the files)
Imports are lazy; nothing here stores audio or text.
"""
import glob
import os

from . import adapters


def parse_models(spec):
    """'hi=/a,mr=/b' -> {'hi': '/a', 'mr': '/b'}"""
    out = {}
    for part in filter(None, (spec or "").split(",")):
        lang, _, path = part.partition("=")
        if not lang.strip() or not path.strip():
            raise ValueError(f"bad SHERPA_MODELS entry: {part!r} (use lang=/path)")
        out[lang.strip()] = path.strip()
    return out


def _pick(folder, pattern):
    """Prefer the int8 file when both exist."""
    files = sorted(glob.glob(os.path.join(folder, pattern)))
    int8 = [f for f in files if "int8" in os.path.basename(f)]
    return (int8 or files or [None])[0]


def detect_kind(folder):
    if _pick(folder, "encoder*.onnx") and _pick(folder, "joiner*.onnx"):
        return "transducer"
    return "nemo_ctc"


def sherpa_transcriber(model_dir, kind=None, threads=4):
    import sherpa_onnx

    tokens = os.path.join(model_dir, "tokens.txt")
    kind = kind or detect_kind(model_dir)
    if kind == "transducer":
        rec = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=_pick(model_dir, "encoder*.onnx"), decoder=_pick(model_dir, "decoder*.onnx"),
            joiner=_pick(model_dir, "joiner*.onnx"), tokens=tokens, num_threads=threads)
    else:
        model = _pick(model_dir, "model*.onnx")
        make = (sherpa_onnx.OfflineRecognizer.from_dolphin_ctc if kind == "dolphin_ctc"
                else sherpa_onnx.OfflineRecognizer.from_nemo_ctc)
        rec = make(model=model, tokens=tokens, num_threads=threads)

    def transcribe(audio):
        stream = rec.create_stream()
        stream.accept_waveform(adapters.RATE, audio)
        rec.decode_stream(stream)
        return stream.result.text
    return transcribe


def make_transcriber(engine=None, env=os.environ):
    engine = (engine or env.get("STT_ENGINE") or "whisper").lower()
    if engine == "whisper":
        return adapters.whisper_transcriber(env.get("WHISPER_MODEL", "small"))
    if engine == "sherpa":
        models = parse_models(env.get("SHERPA_MODELS"))
        if not models:
            raise ValueError("STT_ENGINE=sherpa needs SHERPA_MODELS=hi=/path,mr=/path")
        lang = env.get("STT_LANGUAGE") or next(iter(models))
        if lang not in models:
            raise ValueError(f"STT_LANGUAGE={lang} is not in SHERPA_MODELS ({', '.join(models)})")
        return sherpa_transcriber(models[lang], env.get("SHERPA_KIND"))
    raise ValueError(f"unknown STT_ENGINE: {engine}")
