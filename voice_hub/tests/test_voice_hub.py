import unittest

from voice_hub.otp_handler import is_otp_request, make_otp_handler
from voice_hub.pipeline import Hub, Reply


def make_hub(audio="a", transcript="what's the amazon otp", handlers=None, spoken=None):
    spoken = spoken if spoken is not None else []
    return Hub(wait_for_wake=lambda: None, listen=lambda: audio,
               transcribe=lambda a: transcript,
               speak=lambda text, lang: spoken.append((text, lang)),
               handlers=handlers or []), spoken


class IntentTests(unittest.TestCase):
    def test_otp_phrases(self):
        for phrase in ["what's the Amazon OTP", "OTP batao", "o t p please", "O.T.P.",
                       "ओटीपी सांगा", "ओ टी पी बताओ", "give me the one time password",
                       "delivery code?"]:
            self.assertTrue(is_otp_request(phrase), phrase)

    def test_other_phrases(self):
        for phrase in ["Sunita is on leave till Friday", "what time is it", "", "hope you slept"]:
            self.assertFalse(is_otp_request(phrase), phrase)


class HubTests(unittest.TestCase):
    def test_routes_otp_request_and_speaks_reply(self):
        calls = []

        def post(url, token, transcript):
            calls.append((url, token, transcript))
            return {"speech": "Amazon. OTP 5 9 2 7.", "language": "en"}
        hub, spoken = make_hub(handlers=[make_otp_handler("http://x/query", "tok", post)])
        self.assertEqual(hub.run_once(), "what's the amazon otp")
        self.assertEqual(calls, [("http://x/query", "tok", "what's the amazon otp")])
        self.assertEqual(spoken, [("Amazon. OTP 5 9 2 7.", "en")])

    def test_non_otp_goes_to_next_handler(self):
        otp = make_otp_handler(post=lambda *a: self.fail("should not call the relay"))
        leave = lambda t: Reply("Noted.") if "leave" in t else None
        hub, spoken = make_hub(transcript="Sunita is on leave", handlers=[otp, leave])
        hub.run_once()
        self.assertEqual(spoken, [("Noted.", "en")])

    def test_unknown_request_gets_apology(self):
        hub, spoken = make_hub(transcript="blah", handlers=[])
        hub.run_once()
        self.assertIn("Sorry", spoken[0][0])

    def test_silence_does_nothing(self):
        hub, spoken = make_hub(audio=None)
        self.assertIsNone(hub.run_once())
        hub, spoken = make_hub(transcript="   ")
        self.assertIsNone(hub.run_once())
        self.assertEqual(spoken, [])

    def test_failing_handler_does_not_crash_hub(self):
        def boom(t):
            raise RuntimeError("relay down")
        hub, spoken = make_hub(handlers=[boom])
        hub.run_once()
        self.assertEqual(len(spoken), 1)


if __name__ == "__main__":
    unittest.main()
