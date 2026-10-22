import os
import tempfile
import unittest

from voice_hub import bench_stt, stt


class SttTests(unittest.TestCase):
    def test_parse_models(self):
        self.assertEqual(stt.parse_models("hi=/a,mr=/b"), {"hi": "/a", "mr": "/b"})
        self.assertEqual(stt.parse_models(""), {})
        with self.assertRaises(ValueError):
            stt.parse_models("hi")

    def test_detect_kind_and_int8_preference(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ["model.onnx", "model.int8.onnx", "tokens.txt"]:
                open(os.path.join(d, name), "w").close()
            self.assertEqual(stt.detect_kind(d), "nemo_ctc")
            self.assertTrue(stt._pick(d, "model*.onnx").endswith("model.int8.onnx"))
            for name in ["encoder.int8.onnx", "joiner.int8.onnx"]:
                open(os.path.join(d, name), "w").close()
            self.assertEqual(stt.detect_kind(d), "transducer")

    def test_engine_selection_errors(self):
        with self.assertRaises(ValueError):
            stt.make_transcriber("nope", env={})
        with self.assertRaises(ValueError):
            stt.make_transcriber("sherpa", env={})
        with self.assertRaises(ValueError):
            stt.make_transcriber("sherpa", env={"SHERPA_MODELS": "hi=/a", "STT_LANGUAGE": "mr"})

    def test_word_error_rate(self):
        self.assertEqual(bench_stt.word_error_rate("a b c d", "a b c d"), 0)
        self.assertEqual(bench_stt.word_error_rate("a b c d", "a x c"), 0.5)
        self.assertEqual(bench_stt.word_error_rate("", ""), 0)
