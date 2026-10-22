"""Compare speech-to-text engines on the Pi with the same audio.

  python3 -m voice_hub.bench_stt --record 6 --reference "सुनीता कल छुट्टी पर है" \
      --engine whisper:small --engine whisper:base --engine sherpa:hi=/home/pi/models/hi
  python3 -m voice_hub.bench_stt --wav sample.wav --engine ...

Each engine is "whisper:<size>" or "sherpa:<lang>=<model folder>" ("sherpa:<folder>" also works).
Prints transcript, load time, decode time, real-time factor (decode / audio length; under 1 is
faster than real time), CPU use, and word error rate if --reference is given.
--record keeps the audio in memory only; nothing is written to disk.
"""
import argparse
import time
import wave

from . import adapters, stt


def word_error_rate(reference, hypothesis):
    ref, hyp = reference.split(), hypothesis.split()
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref)


def read_wav(path):
    import numpy as np

    with wave.open(path, "rb") as w:
        if w.getframerate() != adapters.RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit("use a 16 kHz, mono, 16-bit WAV (ffmpeg -i in.m4a -ar 16000 -ac 1 out.wav)")
        return np.frombuffer(w.readframes(w.getnframes()), dtype="int16").astype("float32") / 32768.0


def record(seconds, device=None):
    import numpy as np
    import sounddevice as sd

    print(f"Recording {seconds}s - speak now...")
    data = sd.rec(int(seconds * adapters.RATE), samplerate=adapters.RATE, channels=1,
                  dtype="int16", device=device)
    sd.wait()
    return np.squeeze(data).astype("float32") / 32768.0


def build(spec):
    kind, _, rest = spec.partition(":")
    if kind == "whisper":
        return adapters.whisper_transcriber(rest or "small")
    if kind == "sherpa":
        _lang, eq, path = rest.partition("=")
        return stt.sherpa_transcriber(path if eq else rest)
    raise SystemExit(f"unknown engine {spec!r}")


def run(spec, audio, reference=None):
    t0 = time.perf_counter()
    transcribe = build(spec)
    load_s = time.perf_counter() - t0
    transcribe(audio[: adapters.RATE])  # warm-up so the timing is not first-call overhead
    wall0, cpu0 = time.perf_counter(), time.process_time()
    text = transcribe(audio).strip()
    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    secs = len(audio) / adapters.RATE
    row = {"engine": spec, "text": text, "load_s": load_s, "decode_s": wall,
           "rtf": wall / secs, "cpu_pct": 100 * cpu / wall if wall else 0.0}
    if reference is not None:
        row["wer"] = word_error_rate(reference, text)
    return row


def main(argv=None):
    p = argparse.ArgumentParser(prog="voice_hub.bench_stt")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--wav")
    src.add_argument("--record", type=float, metavar="SECONDS")
    p.add_argument("--device", help="sounddevice input index or name (the USB mic)")
    p.add_argument("--engine", action="append", required=True)
    p.add_argument("--reference", help="what was actually said, to compute word error rate")
    args = p.parse_args(argv)

    device = int(args.device) if args.device and args.device.isdigit() else args.device
    audio = read_wav(args.wav) if args.wav else record(args.record, device)
    for spec in args.engine:
        r = run(spec, audio, args.reference)
        wer = f"  WER {r['wer']:.0%}" if "wer" in r else ""
        print(f"\n[{r['engine']}] load {r['load_s']:.1f}s  decode {r['decode_s']:.2f}s  "
              f"RTF {r['rtf']:.2f}  CPU {r['cpu_pct']:.0f}%{wer}\n  {r['text']}")


if __name__ == "__main__":
    main()
