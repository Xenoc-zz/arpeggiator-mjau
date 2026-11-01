"""
ChordCaptureSession: capture chords live from a MIDI keyboard and feed them
to the ProgressionPlayer.

Unlike the low-level ChordCapture in midi_in.py (which just records chords),
this session is wired for performance:

    - Debounces "chord finished" so rolled chords count as one chord
    - Emits each completed chord to a callback (or to the player)
    - Can accumulate a whole progression, then hand it over on a boundary
    - Handles sustain pedals (CC64) and note-off by velocity-0 note-on
"""

from __future__ import annotations
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .chords import Chord
from .progressions import Progression, ProgressionStep
from .midi_in import CapturedChord, MidiInput, _note_from_midi, _octave_from_midi


@dataclass
class CaptureConfig:
    """Tuning for live chord capture."""
    # Wait this long after the last key release before declaring the chord done
    release_gap: float = 0.15
    # Ignore chords with fewer notes than this (filters stray notes)
    min_notes: int = 2
    # How long each captured chord lasts in the resulting progression
    beats_per_chord: float = 4.0
    # Auto-replace the progression after this many chords (0 = never)
    auto_build_at: int = 3


class ChordCaptureSession:
    """Captures chords from a keyboard into a Progression, live.

    Usage:
        from arpeggiator.core import MidiInput
        session = ChordCaptureSession(MidiInput("MPK261"))
        session.on_chord = lambda chord, idx: print(idx, chord.label)
        session.on_progression = lambda prog: player.queue_next(prog)
        session.start()
    """

    def __init__(self, midi_input: MidiInput,
                 config: Optional[CaptureConfig] = None):
        self.input = midi_input
        self.config = config or CaptureConfig()

        self.captured: list[Chord] = []
        self._held: dict[int, tuple[int, float]] = {}   # note -> (velocity, t)
        self._lock = threading.Lock()
        self._sustain = False
        self._last_release = 0.0
        self._flush_timer: Optional[threading.Timer] = None
        self._running = False

        # Rolling snapshot of every note seen since the last committed chord
        self._gesture_notes: set[int] = set()
        self._gesture_velocity: int = 0
        self._gesture_start: float = 0.0

        # Callbacks
        self.on_chord: Optional[Callable[[Chord, int], None]] = None
        self.on_progression: Optional[Callable[[Progression], None]] = None
        self.on_held: Optional[Callable[[list[int]], None]] = None

        # Hook into the raw input
        self.input.on_note_on = self._handle_note_on
        self.input.on_note_off = self._handle_note_off
        self._hook_raw_messages()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _hook_raw_messages(self) -> None:
        """Intercept sustain pedal (CC64) from the raw port."""
        original = self.input._handle_message

        def wrapper(msg):
            if getattr(msg, "type", None) == "control_change" \
                    and getattr(msg, "control", None) == 64:
                self._sustain = msg.value >= 64
                if not self._sustain and not self._held:
                    self._schedule_flush()
                return
            original(msg)

        self.input._handle_message = wrapper

    def start(self) -> bool:
        if self._running:
            return True
        ok = self.input.start()
        self._running = ok
        return ok

    def stop(self) -> None:
        self._cancel_flush()
        self.input.stop()
        self._running = False

    def clear(self) -> None:
        with self._lock:
            self.captured.clear()
            self._held.clear()

    # ------------------------------------------------------------------
    # Note handling
    # ------------------------------------------------------------------

    def _handle_note_on(self, note: int, velocity: int) -> None:
        now = time.monotonic()
        with self._lock:
            # New gesture begins when nothing was held and enough time passed
            if not self._held and (now - self._last_release) > 0.5:
                self._gesture_notes = set()
                self._gesture_velocity = 0
                self._gesture_start = now
            self._held[note] = (velocity, now)
            self._gesture_notes.add(note)
            self._gesture_velocity = max(self._gesture_velocity, velocity)
            if not self._gesture_start:
                self._gesture_start = now
            held = sorted(self._held.keys())
        self._cancel_flush()
        if self.on_held:
            try:
                self.on_held(held)
            except Exception:
                pass

    def _handle_note_off(self, note: int) -> None:
        with self._lock:
            self._held.pop(note, None)
            self._last_release = time.monotonic()
            still_held = bool(self._held)

        if self._sustain:
            return   # pedal down: defer until pedal up
        if not still_held:
            self._schedule_flush()

    # ------------------------------------------------------------------
    # Chord finalisation
    # ------------------------------------------------------------------

    def _schedule_flush(self) -> None:
        """Wait a beat before committing, so rolled chords stay together."""
        self._cancel_flush()
        timer = threading.Timer(self.config.release_gap, self._flush)
        timer.daemon = True
        self._flush_timer = timer
        timer.start()

    def _cancel_flush(self) -> None:
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None

    def _flush(self) -> None:
        """Commit the notes we saw as a chord."""
        with self._lock:
            notes = tuple(sorted(self._gesture_notes))
            velocity = self._gesture_velocity or 100
            start = self._gesture_start
            # Reset the gesture; a new one starts on the next note-on
            self._gesture_notes = set()
            self._gesture_velocity = 0
            self._gesture_start = 0.0

        if not notes or len(notes) < self.config.min_notes:
            return

        captured = CapturedChord(midi_notes=notes, velocity=velocity,
                                 timestamp=start)
        chord = captured.to_chord()

        with self._lock:
            self.captured.append(chord)
            idx = len(self.captured) - 1

        if self.on_chord:
            try:
                self.on_chord(chord, idx)
            except Exception:
                pass

        if (self.config.auto_build_at > 0
                and idx + 1 >= self.config.auto_build_at):
            self._emit_progression()

    # ------------------------------------------------------------------
    # Progression building
    # ------------------------------------------------------------------

    def _emit_progression(self) -> None:
        if not self.captured:
            return
        prog = self.to_progression()
        if self.on_progression:
            try:
                self.on_progression(prog)
            except Exception:
                pass
        with self._lock:
            self.captured.clear()

    def to_progression(self, name: str = "Captured") -> Progression:
        with self._lock:
            chords = list(self.captured)
        steps = [
            ProgressionStep(c, self.config.beats_per_chord)
            for c in chords
        ]
        return Progression(steps, name=name)

    def build_now(self) -> Optional[Progression]:
        """Manually hand over whatever has been captured so far."""
        with self._lock:
            if not self.captured:
                return None
        prog = self.to_progression()
        with self._lock:
            self.captured.clear()
        return prog
