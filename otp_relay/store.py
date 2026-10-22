"""In-memory OTP store. Never written to disk; entries expire after the TTL."""
import threading
import time
from dataclasses import dataclass

from .classify import Otp, RULES


@dataclass
class Entry:
    otp: Otp
    received_at: float


class OtpStore:
    def __init__(self, ttl_seconds=None, clock=time.time, max_entries=50):
        self.ttl = ttl_seconds or RULES["ttl_seconds"]
        self._clock = clock
        self._max = max_entries
        self._lock = threading.Lock()
        self._entries = []
        self.rejected = 0

    def _purge(self):
        cutoff = self._clock() - self.ttl
        self._entries = [e for e in self._entries if e.received_at >= cutoff]

    def add(self, otp: Otp) -> Entry:
        with self._lock:
            self._purge()
            self._entries = [e for e in self._entries
                             if not (e.otp.code == otp.code and e.otp.company == otp.company)]
            entry = Entry(otp, self._clock())
            self._entries.append(entry)
            del self._entries[:-self._max]
            return entry

    def reject(self):
        with self._lock:
            self.rejected += 1  # a count only; the rejected content is never kept

    def recent(self):
        """Live entries, newest first."""
        with self._lock:
            self._purge()
            return sorted(self._entries, key=lambda e: e.received_at, reverse=True)
