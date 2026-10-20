"""Builds the iPhone Shortcut "Delivery OTP" from otp_relay/rules.json.

    python3 -m otp_relay.shortcut.build_shortcut [output.shortcut] [--no-questions]

--no-questions leaves out the import questions; edit the two text cards by hand.

The file is UNSIGNED. iOS only installs signed shortcuts, so sign it on a Mac:

    shortcuts sign --mode anyone --input "Delivery OTP (unsigned).shortcut" \\
                   --output "Delivery OTP.shortcut"

Everything the Shortcut checks lives on the phone: it sends only company, item,
order_tail and code to the Pi, never the message text.
"""
import plistlib
import re
import sys
import uuid

from otp_relay.classify import RULES

OBJ = "￼"  # placeholder character for a variable inside a Shortcuts string


def _alt(words):
    return "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))


def patterns():
    """The regexes the Shortcut runs. Case-insensitive, whole message is one string."""
    block = RULES["financial_words"] + RULES["non_delivery_words"]
    word = [w for w in block if w.isascii() and w.replace(" ", "").replace("-", "").replace("/", "").replace(".", "").isalnum()]
    other = [w for w in block if w not in word]
    names = [n for c in RULES["companies"].values() for n in c["names"]]
    delivery = [w for w in RULES["delivery_words"] if w.isascii()]
    code = r"(?<![\d-])\d{4,6}(?![\d-])"
    gate = (
        r"(?is)^"
        rf"(?!.*(?:\b(?:{_alt(word)})\b|{_alt(other)}))"        # no bank / sign-up wording
        rf"(?=.*\b(?:{_alt(delivery)})\b)"                         # delivery wording
        rf"(?=.*(?:{_alt(names)}))"                                # an approved company
        rf"(?=.*{code})"                                           # a code ...
        rf"(?!(?:.*{code}){{2}})"                                  # ... and only one
        r".*$"
    )
    kw = ["order", "delivery", "package", "parcel", "shipment"]
    behind = "|".join(f"(?<={k} {p} )" for k in kw for p in ("of", "for"))
    return {
        "gate": gate,
        "code": rf"(?i){code}",
        "company": rf"(?i)(?:{_alt(names)})",
        "item": rf"(?i)(?:{behind})[\w &'.,()/+-]{{3,40}}?(?=[.,;(]|\s(?:is|has|will|from)\b)",
        "tail": r"(?<=\d{3}-\d{7}-\d{3})\d{4}\b",
    }


def _uid():
    return str(uuid.uuid4()).upper()


def _out(uuid_, name):
    return {"Value": {"Type": "ActionOutput", "OutputUUID": uuid_, "OutputName": name},
            "WFSerializationType": "WFTextTokenAttachment"}


def _var(name):
    return {"Value": {"Type": "Variable", "VariableName": name},
            "WFSerializationType": "WFTextTokenAttachment"}


def _string(text):
    return {"Value": {"string": text, "attachmentsByRange": {}},
            "WFSerializationType": "WFTextTokenString"}


def _with_var(prefix, name, suffix=""):
    return {"Value": {"string": f"{prefix}{OBJ}{suffix}",
                      "attachmentsByRange": {f"{{{len(prefix)}, 1}}": {"Type": "Variable", "VariableName": name}}},
            "WFSerializationType": "WFTextTokenString"}


def _action(ident, **params):
    return {"WFWorkflowActionIdentifier": f"is.workflow.actions.{ident}",
            "WFWorkflowActionParameters": params}


def _dict_field(pairs):
    """A Shortcuts dictionary: pairs of (key, value-as-string-token)."""
    return {"Value": {"WFDictionaryFieldValueItems": [
        {"WFItemType": 0, "WFKey": _string(k), "WFValue": v} for k, v in pairs]},
        "WFSerializationType": "WFDictionaryFieldValue"}


def build(ask=True):
    pat = patterns()
    actions, questions = [], []

    def add(a):
        actions.append(a)
        return len(actions) - 1

    # 0, 1: the two values asked for at import
    i = add(_action("gettext", WFTextActionText=_string("http://100.x.y.z:8765/ingest")))
    questions.append({"Category": "Parameter", "ParameterKey": "WFTextActionText", "ActionIndex": i,
                      "Text": "Address of your Pi (http://<Pi Tailscale IP>:8765/ingest)",
                      "DefaultValue": "http://100.x.y.z:8765/ingest"})
    add(_action("setvariable", WFVariableName="PiUrl", WFInput=_out_of(actions, i)))
    i = add(_action("gettext", WFTextActionText=_string("PASTE-OTP_RELAY_TOKEN-HERE")))
    questions.append({"Category": "Parameter", "ParameterKey": "WFTextActionText", "ActionIndex": i,
                      "Text": "OTP_RELAY_TOKEN (the secret you set on the Pi)",
                      "DefaultValue": "PASTE-OTP_RELAY_TOKEN-HERE"})
    add(_action("setvariable", WFVariableName="Token", WFInput=_out_of(actions, i)))

    # the message text, as the shortcut's input
    i = add(_action("gettext", WFTextActionText={
        "Value": {"string": OBJ, "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}}},
        "WFSerializationType": "WFTextTokenString"}))
    add(_action("setvariable", WFVariableName="Msg", WFInput=_out_of(actions, i)))

    # the guard: stop unless this is clearly a delivery OTP
    gate_id = _uid()
    add(_action("text.match", UUID=gate_id, CustomOutputName="Gate", WFMatchTextPattern=pat["gate"],
                WFMatchTextCaseSensitive=False, text=_var("Msg")))
    group = _uid()
    add(_action("conditional", WFControlFlowMode=0, GroupingIdentifier=group,
                WFCondition="Does Not Have Any Value",
                WFInput={"Type": "Variable", "Variable": _out(gate_id, "Gate")}))
    add(_action("exit"))
    add(_action("conditional", WFControlFlowMode=2, GroupingIdentifier=group, UUID=_uid()))

    def extract(var, key):
        mid, fid = _uid(), _uid()
        add(_action("text.match", UUID=mid, CustomOutputName=f"{var} matches", WFMatchTextPattern=pat[key],
                    WFMatchTextCaseSensitive=False, text=_var("Msg")))
        add(_action("getitemfromlist", UUID=fid, CustomOutputName=f"{var} first", WFItemSpecifier="First Item",
                    WFInput=_out(mid, f"{var} matches")))
        add(_action("setvariable", WFVariableName=var, WFInput=_out(fid, f"{var} first")))

    for var, key in (("Code", "code"), ("Company", "company"), ("Item", "item"), ("Tail", "tail")):
        extract(var, key)

    add(_action("downloadurl", WFURL=_with_var("", "PiUrl"), WFHTTPMethod="POST", WFHTTPBodyType="JSON",
                ShowHeaders=True,
                WFHTTPHeaders=_dict_field([("Authorization", _with_var("Bearer ", "Token"))]),
                WFJSONValues=_dict_field([(k, _with_var("", v)) for k, v in (
                    ("company", "Company"), ("item", "Item"), ("order_tail", "Tail"), ("code", "Code"))])))

    return {
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "900",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4282601983, "WFWorkflowIconGlyphNumber": 59511},
        "WFWorkflowImportQuestions": questions if ask else [],
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowHasShortcutInputVariables": True,
    }


def _out_of(actions, index):
    """Reference to the output of an action that has no UUID yet: give it one."""
    params = actions[index]["WFWorkflowActionParameters"]
    params.setdefault("UUID", _uid())
    return _out(params["UUID"], "Text")


def main(argv):
    args = [a for a in argv[1:] if a != "--no-questions"]
    path = args[0] if args else "Delivery OTP (unsigned).shortcut"
    with open(path, "wb") as f:
        plistlib.dump(build(ask="--no-questions" not in argv), f, fmt=plistlib.FMT_BINARY)
    print(f"wrote {path} (unsigned: sign it on a Mac, see the README)")


if __name__ == "__main__":
    main(sys.argv)
