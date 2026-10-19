import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from otp_relay.classify import classify, validate
from otp_relay.notify import forward, format_message, recipients_for
from otp_relay.server import make_handler
from otp_relay.store import OtpStore
from otp_relay.voice import answer, detect_language

AMAZON_FIELDS = {"company": "Amazon", "item": "Philips trimmer", "order_tail": "4321", "code": "5927"}
AMAZON = ("AX-AMAZON", "Your Amazon order of Philips trimmer, order 408-1234567-7654321 is out for "
          "delivery. Share OTP 5927 with the delivery agent.")
FLIPKART = ("FLIPKT", "Flipkart: OTP 4410 for delivery of your Boat earphones. Share with the agent.")

BLOCKED = [
    ("HDFCBK", "OTP 123456 for transaction of Rs 5,000 at Amazon. Do not share with anyone."),
    ("AX-AMAZON", "Amazon: 482913 is your OTP to log in. Do not share."),
    ("ICICIB", "Your UPI OTP is 4410. Delivery of order pending."),
    ("AX-AMAZON", "Amazon order delivery. Pay Rs 499 to the agent. OTP 5927"),
    ("RANDOM", "Delivery OTP 5927 for your order."),                 # unknown company
    ("AX-AMAZON", "Amazon: your order is out for delivery."),         # no code
    ("AX-AMAZON", "Amazon delivery OTP 1234 and also 5678"),         # ambiguous
    ("AX-AMAZON", "Hello, how are you"),                              # not an OTP
    ("SBIINB", "Your bank a/c OTP 9876 for card delivery order"),
]


class ClassifyTests(unittest.TestCase):
    def test_delivery_otp_accepted_with_item_and_order_tail(self):
        otp = classify(*AMAZON)
        self.assertEqual((otp.company, otp.code, otp.item), ("Amazon", "5927", "Philips trimmer"))
        self.assertIn("order …4321", otp.label)

    def test_whatsapp_share_without_sender_uses_brand_in_text(self):
        otp = classify("", FLIPKART[1])
        self.assertEqual((otp.company, otp.code), ("Flipkart", "4410"))

    def test_everything_else_denied(self):
        for sender, text in BLOCKED:
            self.assertIsNone(classify(sender, text), text)

    def test_hindi_financial_word_blocks(self):
        self.assertIsNone(classify("AX-AMAZON", "Amazon ऑर्डर डिलीवरी OTP 5927, भुगतान बाकी"))


class ValidateTests(unittest.TestCase):
    def test_accepts_clean_fields(self):
        otp = validate({"company": "Amazon", "item": "Philips trimmer", "order_tail": "4321", "code": "5927"})
        self.assertEqual(otp.label, "Amazon: Philips trimmer (order …4321)")
        self.assertEqual(validate({"company": "Swiggy", "code": "1234"}).label, "Swiggy")

    def test_rejects_message_text_and_bad_fields(self):
        ok = {"company": "Amazon", "code": "5927"}
        self.assertIsNotNone(validate(ok))
        for bad in [
            {**ok, "text": "OTP 5927 for UPI"},          # any extra field, incl. message text
            {**ok, "company": "HDFC Bank"},              # not an approved company
            {**ok, "code": "59"}, {**ok, "code": "5927a"},
            {**ok, "item": "x" * 41},                    # too long to be an item name
            {**ok, "item": "UPI payment"},               # financial word in the label
            {**ok, "item": "a\nb"}, {**ok, "order_tail": "12345"},
            "not a dict", None,
        ]:
            self.assertIsNone(validate(bad), bad)


class StoreAndRoutingTests(unittest.TestCase):
    def test_expiry(self):
        now = [1000.0]
        store = OtpStore(ttl_seconds=1800, clock=lambda: now[0])
        store.add(classify(*AMAZON))
        now[0] += 1799
        self.assertEqual(len(store.recent()), 1)
        now[0] += 2
        self.assertEqual(store.recent(), [])

    def test_routing_by_company(self):
        cfg = {"recipients": [{"name": "A", "channel": "telegram", "address": "1", "companies": ["*"]},
                              {"name": "B", "channel": "telegram", "address": "2", "companies": ["Amazon"]}]}
        self.assertEqual([r["name"] for r in recipients_for(cfg, "Amazon")], ["A", "B"])
        self.assertEqual([r["name"] for r in recipients_for(cfg, "Swiggy")], ["A"])

    def test_forward_sends_label_and_swallows_errors(self):
        store = OtpStore()
        entry = store.add(classify(*AMAZON))
        cfg = {"whatsapp": {"phone_number_id": "p", "template": "t"},
               "recipients": [{"name": "A", "channel": "telegram", "address": "1", "companies": ["*"]},
                              {"name": "B", "channel": "whatsapp", "address": "91", "companies": ["*"]}]}
        sent = []

        def tg(token, chat, text):
            sent.append(text)

        def wa(*a):
            raise RuntimeError("down")
        names = forward(entry, cfg, {"TELEGRAM_BOT_TOKEN": "x", "WHATSAPP_TOKEN": "y"}, tg, wa)
        self.assertEqual(names, ["A"])
        self.assertIn("Amazon: Philips trimmer", sent[0])
        self.assertIn("OTP 5927", sent[0])
        self.assertEqual(sent[0], format_message(entry))


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.store = OtpStore()
        self.store.add(classify(*AMAZON))
        self.store.add(classify(*FLIPKART))

    def test_languages(self):
        self.assertEqual(detect_language("what's the amazon otp"), "en")
        self.assertEqual(detect_language("otp batao"), "hi")
        self.assertEqual(detect_language("ओटीपी सांगा"), "mr")

    def test_company_and_item_filter(self):
        _, text = answer(self.store, "what's the Amazon OTP")
        self.assertIn("5 9 2 7", text)
        self.assertNotIn("4 4 1 0", text)
        _, text = answer(self.store, "the Boat earphones OTP")
        self.assertIn("4 4 1 0", text)
        self.assertNotIn("5 9 2 7", text)

    def test_none_and_multiple(self):
        self.assertIn("2 OTPs", answer(self.store, "what are my otps")[1])
        self.assertIn("no delivery OTP", answer(OtpStore(), "otp")[1])
        self.assertIn("नहीं", answer(OtpStore(), "otp batao")[1])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.store = OtpStore()
        self.forwarded = []
        handler = make_handler(self.store, "secret", {}, {},
                               send=lambda e, c, s: self.forwarded.append(e.otp.code))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()

    def post(self, path, obj, token="secret"):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=json.dumps(obj).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_auth_required(self):
        self.assertEqual(self.post("/ingest", AMAZON_FIELDS, token="bad")[0], 401)

    def test_accept_forward_and_query(self):
        self.assertEqual(self.post("/ingest", AMAZON_FIELDS)[1], {"status": "accepted"})
        self.assertEqual(self.forwarded, ["5927"])
        self.assertIn("5 9 2 7", self.post("/query", {"transcript": "amazon otp"})[1]["speech"])

    def test_bank_otp_rejected_deleted_and_not_forwarded(self):
        sender, text = BLOCKED[0]
        # Even a bank message sent as text is refused: the Pi accepts no text at all.
        code, body = self.post("/ingest", {"sender": sender, "text": text})
        self.assertEqual(body, {"status": "rejected"})
        self.assertEqual(self.forwarded, [])
        self.assertEqual(self.store.recent(), [])
        self.assertEqual(self.store.rejected, 1)
        self.assertNotIn("123456", json.dumps(body))

    def test_oversized_and_bad_body(self):
        self.assertEqual(self.post("/ingest", {"company": "Amazon", "code": "5927", "item": "x" * 5000})[0], 400)


if __name__ == "__main__":
    unittest.main()
