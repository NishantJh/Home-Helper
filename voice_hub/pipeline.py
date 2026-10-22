"""The voice loop. Components are injected so the loop is testable without audio."""
from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass
class Reply:
    speech: str
    language: str = "en"
    # Optional follow-up: the hub listens again without the wake word and passes the
    # transcript here (used for "did I get that right?" confirmations).
    then: Optional["Handler"] = None


# A handler returns a Reply when the transcript is for it, otherwise None.
Handler = Callable[[str], Optional[Reply]]

_UNKNOWN = {"en": "Sorry, I didn't get that.", "hi": "माफ़ कीजिए, मैं समझ नहीं पाया।",
            "mr": "माफ करा, मला समजले नाही."}


class Hub:
    def __init__(self, wait_for_wake, listen, transcribe, speak, handlers: List[Handler],
                 detect_language=None):
        self.wait_for_wake = wait_for_wake    # () -> None, blocks until the wake word
        self.listen = listen                  # () -> audio or None (silence / timeout)
        self.transcribe = transcribe          # audio -> str
        self.speak = speak                    # (text, language) -> None
        self.handlers = handlers
        self.detect_language = detect_language or (lambda text: "en")

    def run_once(self) -> Optional[str]:
        """One wake-to-answer round. Returns the transcript, or None if nothing was said.

        Audio and transcripts are never stored or logged.
        """
        self.wait_for_wake()
        audio = self.listen()
        if audio is None:
            return None
        text = self.transcribe(audio).strip()
        if not text:
            return None
        for handler in self.handlers:
            try:
                reply = handler(text)
            except Exception:
                reply = None  # a broken handler must not take the hub down
            if reply is not None:
                self._deliver(reply)
                return text
        lang = self.detect_language(text)
        self.speak(_UNKNOWN.get(lang, _UNKNOWN["en"]), lang)
        return text

    def _deliver(self, reply):
        """Speak a reply; while it asks a follow-up, listen once more and answer it."""
        while reply is not None:
            self.speak(reply.speech, reply.language)
            if reply.then is None:
                return
            audio = self.listen()
            text = self.transcribe(audio).strip() if audio is not None else ""
            try:
                reply = reply.then(text)
            except Exception:
                reply = None

    def run_forever(self):
        while True:
            self.run_once()
