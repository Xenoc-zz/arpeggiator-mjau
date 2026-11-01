"""
Mock MIDI port for testing the player without hardware.

Records every message so tests can assert on what was actually played.
"""

from __future__ import annotations
import threading
import time


class MockMidiPort:
    """A fake mido output port that records messages."""

    def __init__(self):
        self.messages: list[dict] = []
        self._lock = threading.Lock()
        self.closed = False

    def send(self, msg):
        """Record a message. Accepts anything with .type/.note/.velocity."""
        with self._lock:
            self.messages.append({
                "type": getattr(msg, "type", "unknown"),
                "note": getattr(msg, "note", None),
                "velocity": getattr(msg, "velocity", None),
                "channel": getattr(msg, "channel", None),
                "control": getattr(msg, "control", None),
                "value": getattr(msg, "value", None),
            })

    def close(self):
        self.closed = True

    # --- inspection helpers ---

    def note_ons(self) -> list[dict]:
        with self._lock:
            return [m for m in self.messages
                    if m["type"] == "note_on" and (m["velocity"] or 0) > 0]

    def note_offs(self) -> list[dict]:
        with self._lock:
            return [m for m in self.messages if m["type"] == "note_off"]

    def notes_played(self) -> list[int]:
        return [m["note"] for m in self.note_ons()]

    def clear(self):
        with self._lock:
            self.messages.clear()

    def wait_for_notes(self, count: int, timeout: float = 5.0) -> bool:
        """Block until at least `count` note-on messages arrive."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.note_ons()) >= count:
                return True
            time.sleep(0.005)
        return False


class MockMidiOutput:
    """Stands in for MidiOutput: holds a _port the player can write to."""

    def __init__(self):
        self._port = MockMidiPort()

    @property
    def port(self) -> MockMidiPort:
        return self._port
