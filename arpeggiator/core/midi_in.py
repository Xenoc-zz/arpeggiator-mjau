"""
MIDI input: read played notes/chords from a controller (e.g. AKAI MPK261)
and turn them into progressions or arpeggio seeds.

The MPK261 sends standard MIDI over USB — mido + rtmidi handles it natively.
"""

from __future__ import annotations
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .chords import Chord, CHORD_INTERVALS
from .progressions import Progression, ProgressionStep
from .music_theory import midi_to_note_name


def _note_from_midi(midi: int) -> str:
    """Split 'C#4' into root name, keeping sharps."""
    return midi_to_note_name(midi)[:-1]


def _octave_from_midi(midi: int) -> int:
    return int(midi_to_note_name(midi)[-1])


@dataclass
class HeldNote:
    """A note currently being held on the controller."""
    midi: int
    velocity: int
    start_time: float


@dataclass
class CapturedChord:
    """A chord captured from MIDI input."""
    midi_notes: tuple[int, ...]      # Sorted MIDI numbers
    velocity: int = 100
    duration: float = 1.0            # How long it was held (beats-ish)
    timestamp: float = 0.0

    @property
    def root_midi(self) -> int:
        return self.midi_notes[0] if self.midi_notes else 60

    def to_chord(self) -> Chord:
        """Best-effort conversion to a Chord object.

        Recognizes common triad/7th shapes by matching interval sets,
        including inversions.
        """
        if not self.midi_notes:
            return Chord("C", "major")

        lowest = self.midi_notes[0]
        root_pc = lowest % 12

        # Interval set relative to the lowest note
        rel = frozenset((m - lowest) % 12 for m in self.midi_notes)

        # 1. Direct match against known chord shapes
        for quality, intervals in CHORD_INTERVALS.items():
            if frozenset(i % 12 for i in intervals) == rel:
                return Chord(_note_from_midi(lowest), quality,
                             octave=_octave_from_midi(lowest))

        # 2. Try rotations to detect inversions
        for rot in range(1, 12):
            rotated = frozenset((r - rot) % 12 for r in rel)
            for quality, intervals in CHORD_INTERVALS.items():
                if frozenset(i % 12 for i in intervals) == rotated:
                    actual_root = lowest + rot
                    return Chord(_note_from_midi(actual_root), quality,
                                 octave=_octave_from_midi(actual_root),
                                 inversion=0)

        # 3. Unknown shape: call it a major with the rest as extensions
        extensions = tuple(sorted(i for i in rel if i != 0))
        return Chord(_note_from_midi(lowest), "major",
                     octave=_octave_from_midi(lowest),
                     extensions=extensions)


class MidiInput:
    """Reads MIDI input from a connected controller.

    Usage:
        inp = MidiInput()
        inp.on_chord_captured = lambda chord: print(chord.to_chord())
        inp.start()
    """

    def __init__(self, port_name: str = ""):
        self._port_name = port_name
        self._port = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._held: dict[int, HeldNote] = {}
        self._lock = threading.Lock()
        self._chord_start = 0.0

        # Callbacks
        self.on_chord_captured: Optional[Callable[[CapturedChord], None]] = None
        self.on_note_on: Optional[Callable[[int, int], None]] = None
        self.on_note_off: Optional[Callable[[int], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def port_name(self) -> Optional[str]:
        return self._port_name

    @property
    def held_notes(self) -> list[int]:
        with self._lock:
            return sorted(self._held.keys())

    def start(self) -> bool:
        """Open the input port and begin reading."""
        if self._running:
            return True

        try:
            import mido
        except ImportError:
            return False

        try:
            if self._port_name:
                self._port = mido.open_input(self._port_name)
            else:
                names = mido.get_input_names()
                if not names:
                    return False
                self._port = mido.open_input(names[0])
                self._port_name = names[0]
        except (OSError, IOError):
            return False

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Stop reading and close the port."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._port:
            try:
                self._port.close()
            except Exception:
                pass
            self._port = None

    def _read_loop(self):
        """Background reading loop."""
        while self._running and self._port:
            try:
                for msg in self._port.iter_pending():
                    self._handle_message(msg)
            except Exception:
                break
            time.sleep(0.005)

    def _handle_message(self, msg):
        """Process a MIDI message."""
        is_note_on = msg.type == "note_on" and msg.velocity > 0
        is_note_off = msg.type == "note_off" or (
            msg.type == "note_on" and msg.velocity == 0
        )

        if is_note_on:
            with self._lock:
                if not self._held:
                    self._chord_start = time.time()
                self._held[msg.note] = HeldNote(
                    midi=msg.note,
                    velocity=msg.velocity,
                    start_time=time.time(),
                )
            if self.on_note_on:
                self.on_note_on(msg.note, msg.velocity)

        elif is_note_off:
            finished: Optional[CapturedChord] = None
            with self._lock:
                if msg.note in self._held:
                    del self._held[msg.note]
                    # Chord complete when the LAST held note is released
                    if not self._held:
                        notes = tuple(sorted(
                            h.midi for h in self._held.values()
                        ))
                        finished = None  # placeholder

            if self.on_note_off:
                self.on_note_off(msg.note)

            # NOTE: chord capture handled by ChordCapture which keeps its
            # own snapshot. MidiInput itself only tracks held notes.

    @staticmethod
    def list_ports() -> list[str]:
        """List available MIDI input ports."""
        try:
            import mido
            return mido.get_input_names()
        except ImportError:
            return []

    def capture_chord_now(self, duration_beats: float = 1.0) -> Optional[CapturedChord]:
        """Grab whatever is currently held and form a CapturedChord."""
        with self._lock:
            if not self._held:
                return None
            notes = tuple(sorted(h.midi for h in self._held.values()))
            vel = max((h.velocity for h in self._held.values()), default=100)
            return CapturedChord(midi_notes=notes, velocity=vel,
                                 duration=duration_beats,
                                 timestamp=self._chord_start)


class ChordCapture:
    """Accumulate chords played on the controller into a Progression.

    Press chord → hold → release → recorded. Repeat. Then:
        capture.to_progression()  →  Progression you can arpeggiate.
    """

    # Ignore tiny gaps between notes of the same chord (seconds)
    CHORD_GAP = 0.08

    def __init__(self, midi_input: Optional[MidiInput] = None,
                 on_capture: Optional[Callable[[CapturedChord], None]] = None):
        self.input = midi_input or MidiInput()
        self.captured: list[CapturedChord] = []
        self.on_capture = on_capture

        self._pending: dict[int, HeldNote] = {}
        self._last_chord_notes: tuple[int, ...] = ()
        self._chord_start = 0.0
        self._max_velocity = 0
        self._last_release = 0.0

        self.input.on_note_on = self._on_note_on
        self.input.on_note_off = self._on_note_off

    def _on_note_on(self, note: int, velocity: int):
        now = time.time()
        # New chord if we've been silent for a moment
        if not self._pending and (now - self._last_release) > self.CHORD_GAP:
            self._chord_start = now
            self._max_velocity = velocity
            self._last_chord_notes = ()
        self._pending[note] = HeldNote(note, velocity, now)
        self._max_velocity = max(self._max_velocity, velocity)
        # Snapshot the chord-so-far: this is what we commit on release
        self._last_chord_notes = tuple(sorted(self._pending.keys()))

    def _on_note_off(self, note: int):
        self._pending.pop(note, None)
        self._last_release = time.time()
        if not self._pending:
            self._commit()

    def _commit(self):
        """Commit the notes that were just released as a chord.

        We must read them from a snapshot taken on note_on, since
        _pending is already empty by the time the last key is released.
        """
        notes = self._last_chord_notes
        if not notes:
            return
        chord = CapturedChord(
            midi_notes=notes,
            velocity=self._max_velocity or 100,
            timestamp=self._chord_start,
        )
        self.captured.append(chord)
        self._last_chord_notes = ()
        if self.on_capture:
            self.on_capture(chord)

    def snapshot_pending(self) -> None:
        """Manually capture whatever is held right now."""
        if self._pending:
            notes = tuple(sorted(self._pending.keys()))
            self.captured.append(CapturedChord(
                midi_notes=notes,
                velocity=self._max_velocity or 100,
                timestamp=self._chord_start,
            ))
            self._pending.clear()
            self._last_chord_notes = ()

    def start(self) -> bool:
        return self.input.start()

    def stop(self):
        self.input.stop()

    def clear(self):
        self.captured.clear()
        self._pending.clear()

    def to_progression(self, beats_per_chord: float = 4.0) -> Progression:
        """Convert captured chords into a Progression."""
        steps = [
            ProgressionStep(c.to_chord(), beats_per_chord)
            for c in self.captured
        ]
        return Progression(steps, name="Captured")
