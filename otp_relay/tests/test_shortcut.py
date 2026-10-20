import os
import plistlib
import re
import tempfile
import unittest

from otp_relay.classify import validate
from otp_relay.shortcut import build_shortcut as bs

P = bs.patterns()
AMAZON = ("Amazon: your order of Philips trimmer, order 408-1234567-7654321 is out for delivery. "
          "Share OTP 5927 with the delivery agent.")


def gate(text):
    return re.search(P["gate"], text) is not None


def first(key, text):
    m = re.search(P[key], text)
    return m.group(0) if m else ""


class PatternTests(unittest.TestCase):
    def test_gate_accepts_delivery_otps(self):
        self.assertTrue(gate(AMAZON))
        self.assertTrue(gate("Flipkart: OTP 4410 for delivery of your Boat earphones. Share with the agent."))
        self.assertTrue(gate("Swiggy: Your delivery partner needs OTP 8821 to hand over your order."))

    def test_gate_rejects_everything_else(self):
        for text in [
            "HDFC Bank: OTP 123456 for transaction of Rs 5,000 at Amazon. Do not share.",
            "Amazon: 482913 is your OTP to log in. Do not share. Order tracking inside.",
            "Use OTP 4821 to verify your phone number on Zomato and place your order.",
            "Amazon order delivery. Pay Rs 499 to the agent. OTP 5927",
            "Delivery OTP 5927 for your order.",                          # no approved company
            "Amazon: your order is out for delivery.",                    # no code
            "Amazon delivery OTP 1234 and also 5678",                     # two codes
            "Amazon order delivery OTP 5927 कार्ड",                        # Hindi finance word
            "Hello how are you",
        ]:
            self.assertFalse(gate(text), text)

    def test_extractors(self):
        self.assertEqual(first("code", AMAZON), "5927")
        self.assertEqual(first("company", AMAZON).lower(), "amazon")
        self.assertEqual(first("item", AMAZON), "Philips trimmer")
        self.assertEqual(first("tail", AMAZON), "4321")

    def test_extractors_empty_when_absent(self):
        msg = "Swiggy: Your delivery partner needs OTP 8821 to hand over your order."
        self.assertEqual(first("item", msg), "")
        self.assertEqual(first("tail", msg), "")

    def test_what_the_shortcut_extracts_passes_the_pi_check(self):
        fields = {"company": first("company", AMAZON).upper(), "item": first("item", AMAZON),
                  "order_tail": first("tail", AMAZON), "code": first("code", AMAZON)}
        otp = validate(fields)
        self.assertEqual(otp.label, "Amazon: Philips trimmer (order …4321)")

    def test_pi_normalises_company_case_but_still_rejects_unknown(self):
        self.assertEqual(validate({"company": "AMAZON", "code": "5927"}).company, "Amazon")
        self.assertIsNone(validate({"company": "HDFC", "code": "5927"}))


class FileStructureTests(unittest.TestCase):
    def setUp(self):
        self.d = bs.build()
        self.actions = self.d["WFWorkflowActions"]

    def test_round_trips_as_binary_plist(self):
        with tempfile.TemporaryDirectory() as d:  # not NamedTemporaryFile: Windows can't reopen it
            path = os.path.join(d, "x.shortcut")
            bs.main(["x", path])
            with open(path, "rb") as fh:
                loaded = plistlib.load(fh)
        self.assertEqual([a["WFWorkflowActionIdentifier"] for a in loaded["WFWorkflowActions"]],
                         [a["WFWorkflowActionIdentifier"] for a in self.actions])

    def test_every_reference_points_at_something_defined_earlier(self):
        uuids, variables = set(), {"Shortcut Input"}

        def refs(node):
            if isinstance(node, dict):
                if node.get("Type") == "ActionOutput":
                    yield ("uuid", node["OutputUUID"])
                if node.get("Type") == "Variable" and "VariableName" in node:
                    yield ("var", node["VariableName"])
                for v in node.values():
                    yield from refs(v)
            elif isinstance(node, list):
                for v in node:
                    yield from refs(v)
        for a in self.actions:
            params = a["WFWorkflowActionParameters"]
            for kind, name in refs(params):
                self.assertIn(name, uuids if kind == "uuid" else variables, (a["WFWorkflowActionIdentifier"], name))
            if "UUID" in params:
                uuids.add(params["UUID"])
            if a["WFWorkflowActionIdentifier"].endswith("setvariable"):
                variables.add(params["WFVariableName"])

    def test_if_block_is_balanced_and_stops(self):
        flow = [a["WFWorkflowActionParameters"] for a in self.actions
                if a["WFWorkflowActionIdentifier"].endswith("conditional")]
        self.assertEqual([f["WFControlFlowMode"] for f in flow], [0, 2])
        self.assertEqual(flow[0]["GroupingIdentifier"], flow[1]["GroupingIdentifier"])
        idents = [a["WFWorkflowActionIdentifier"].split(".")[-1] for a in self.actions]
        self.assertEqual(idents[idents.index("conditional") + 1], "exit")

    def test_import_questions_point_at_text_actions(self):
        qs = self.d["WFWorkflowImportQuestions"]
        self.assertEqual(len(qs), 2)
        for q in qs:
            self.assertTrue(self.actions[q["ActionIndex"]]["WFWorkflowActionIdentifier"].endswith("gettext"))

    def test_only_the_four_fields_are_sent_and_no_message_text(self):
        post = self.actions[-1]["WFWorkflowActionParameters"]
        items = post["WFJSONValues"]["Value"]["WFDictionaryFieldValueItems"]
        self.assertEqual([i["WFKey"]["Value"]["string"] for i in items],
                         ["company", "item", "order_tail", "code"])
        sent = {r["VariableName"] for i in items
                for r in i["WFValue"]["Value"]["attachmentsByRange"].values()}
        self.assertEqual(sent, {"Company", "Item", "Tail", "Code"})  # never "Msg"
        self.assertEqual(post["WFHTTPMethod"], "POST")


if __name__ == "__main__":
    unittest.main()
