"""
ProgressionPlayer: loops a chord progression with live, musical swapping.

Design goals:
  - Beat-accurate scheduling (monotonic clock, not sleep-accumulation)
  - Swap progressions on BAR boundaries so a change never lands mid-chord
  - Framework-free: works headless, testable without MIDI hardware
  - Callbacks for UI/ESP32 so the app can follow along

Usage:
    player = ProgressionPlayer()
    player.load(progression, config, treatment)
    player.on_chord = lambda idx, chord, t: print(idx, chord.label)
    player.start()
    ...
    player.queue_next(other_progression)   # swaps at next loop boundary
    player.stop()
"""

from __future__ import annotations
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .arpeggio_engine import (
    ArpeggioEngine, ArpeggioConfig, ArpeggioEvent,
)
from .progressions import Progression
from .treatments import Treatment


@dataclass
class PlayerState:
    """Snapshot of what the player is doing right now (read-only for UI)."""
    running: bool = False
    loop_count: int = 0
    current_chord_index: int = 0
    current_chord_label: str = ""
    current_progression_name: str = ""
    elapsed_beats: float = 0.0
    pending_swap: bool = False


class ProgressionPlayer:
    """Loops a progression in real time with bar-quantized switching.

    The player pre-generates all events for the current progression, then
    schedules them against a monotonic clock. When the loop wraps, it
    re-checks for a queued progression and swaps if one is waiting.
    """

    # How far ahead to look when sending notes (seconds). Larger = safer
    # timing under load, smaller = more responsive to transport changes.
    LOOKAHEAD = 0.05

    def __init__(self, midi_output=None):
        self._midi = midi_output
        self._engine = ArpeggioEngine()
        self.bpm: int = 120

        self._progression: Optional[Progression] = None
        self._config = ArpeggioConfig()
        self._treatment = Treatment()
        self._queued: Optional[Progression] = None
        self._swing_swap = False

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_flag = False

        # Cached generated events for the current progression
        self._events: list[ArpeggioEvent] = []
        self._loop_length = 0.0     # in beats

        # Public state + callbacks
        self.state = PlayerState()
        self.on_chord: Optional[Callable[[int, object, float], None]] = None
        self.on_loop: Optional[Callable[[int], None]] = None
        self.on_swap: Optional[Callable[[Progression], None]] = None

        # Beat callback so UI/ESP32 can pulse along
        self._beat_listeners: list[Callable[[int], None]] = []
        self._last_beat_sent = -1

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def load(self, progression: Progression,
             config: Optional[ArpeggioConfig] = None,
             treatment: Optional[Treatment] = None) -> None:
        """Load a progression to play (takes effect immediately if stopped)."""
        with self._lock:
            self._progression = progression
            if config is not None:
                self._config = config
            if treatment is not None:
                self._treatment = treatment
            self._regenerate()

    def set_config(self, config: ArpeggioConfig) -> None:
        with self._lock:
            self._config = config
            self._regenerate()

    def set_treatment(self, treatment: Treatment) -> None:
        with self._lock:
            self._treatment = treatment
            self._regenerate()

    def queue_next(self, progression: Progression,
                   at_loop_boundary: bool = True) -> None:
        """Queue a progression to swap in.

        by default the swap happens when the current loop finishes, so the
        change always lands on a musically sensible boundary.

        Set at_loop_boundary=False to swap at the next chord instead.
        """
        with self._lock:
            self._queued = progression
            self._swing_swap = not at_loop_boundary
            self.state.pending_swap = True

    def cancel_queued(self) -> None:
        with self._lock:
            self._queued = None
            self.state.pending_swap = False

    def _regenerate(self) -> None:
        """Rebuild cached events for the current progression."""
        if self._progression is None:
            self._events = []
            self._loop_length = 0.0
            return
        self._events = self._engine.generate_progression(
            self._progression, self._config, self._treatment
        )
        self._loop_length = self._progression.total_duration or 4.0

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start looping in a background thread."""
        if self._running:
            return True
        if self._progression is None:
            return False

        self._running = True
        self._stop_flag = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop looping and silence all notes."""
        self._stop_flag = True
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.5)
        self._thread = None
        self._running = False
        self._stop_all_notes()
        self.state.running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def add_beat_listener(self, fn: Callable[[int], None]) -> None:
        """Register a callback fired once per beat (beat index since start)."""
        self._beat_listeners.append(fn)

    def remove_beat_listener(self, fn: Callable[[int], None]) -> None:
        if fn in self._beat_listeners:
            self._beat_listeners.remove(fn)

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Main scheduling loop: play the progression, swap on boundaries."""
        self.state.running = True
        loop_count = 0

        while not self._stop_flag:
            with self._lock:
                events = list(self._events)
                loop_len_beats = self._loop_length
                prog_name = (self._progression.name
                             if self._progression else "")

            bpm = getattr(self, "bpm", 120)
            beat_sec = 60.0 / max(1, bpm)
            loop_sec = loop_len_beats * beat_sec

            self.state.loop_count = loop_count
            self.state.current_progression_name = prog_name

            chord_starts = self._chord_start_times(loop_len_beats)
            self._schedule_loop(events, beat_sec, chord_starts, loop_sec)

            # Loop finished: swap in a queued progression if one is waiting
            with self._lock:
                queued = self._queued
                if queued is not None:
                    self._swap_locked(queued)

            loop_count += 1
            if self.on_loop:
                try:
                    self.on_loop(loop_count)
                except Exception:
                    pass

        self._stop_all_notes()
        self.state.running = False

    def _schedule_loop(self, events: list[ArpeggioEvent], beat_sec: float,
                       chord_starts: dict[int, tuple[int, float]],
                       loop_sec: float) -> None:
        """Play one pass of the loop, index-based and beat-accurate."""
        active_notes: dict[int, float] = {}
        sent = 0
        t0 = time.monotonic()

        # Sort for safety; the engine already emits in time order
        if events != sorted(events, key=lambda e: e.start_time):
            events = sorted(events, key=lambda e: e.start_time)

        fired_chords: set[int] = set()
        next_beat = 0
        beat_sec_safe = max(beat_sec, 0.05)

        while not self._stop_flag:
            elapsed = time.monotonic() - t0
            if elapsed >= loop_sec:
                break

            # --- note offs ---
            now = time.monotonic()
            for note, off_at in list(active_notes.items()):
                if off_at <= now:
                    self._send_note_off(note)
                    del active_notes[note]

            # --- note ons due within lookahead ---
            while sent < len(events):
                ev = events[sent]
                ev_time = ev.start_time * beat_sec_safe
                if ev_time > elapsed + self.LOOKAHEAD:
                    break
                self._send_note_on(ev.note.midi, ev.velocity)
                active_notes[ev.note.midi] = now + ev.duration * beat_sec_safe
                sent += 1

            # --- chord-change callbacks ---
            for chord_idx, (first_ev_idx, start_beat) in chord_starts.items():
                if chord_idx in fired_chords:
                    continue
                if elapsed >= start_beat * beat_sec_safe:
                    fired_chords.add(chord_idx)
                    chord = self._chord_for_index(chord_idx)
                    if chord is not None and self.on_chord:
                        try:
                            self.on_chord(chord_idx, chord, elapsed)
                        except Exception:
                            pass

            # --- beat pulses ---
            beat_idx = int(elapsed / beat_sec_safe)
            while next_beat <= beat_idx:
                self._emit_beat(next_beat)
                next_beat += 1

            # --- allow a mid-loop swap if requested ---
            with self._lock:
                if self._queued is not None and self._swing_swap:
                    break

            time.sleep(0.002)

        # flush remaining notes early if we broke out of the loop
        for note in list(active_notes):
            self._send_note_off(note)

    def _chord_start_times(self, loop_beats: float) -> dict[int, tuple[int, float]]:
        """Map chord index -> (first event index, start beat)."""
        if self._progression is None:
            return {}
        starts: dict[int, tuple[int, float]] = {}
        beat = 0.0
        for idx, step in enumerate(self._progression.steps):
            starts[idx] = (0, beat)
            beat += step.duration
        return starts

    def _chord_for_index(self, idx: int):
        if self._progression is None:
            return None
        if 0 <= idx < len(self._progression.steps):
            return self._progression.steps[idx].chord
        return None

    def _swap_locked(self, new_prog: Progression) -> None:
        """Swap in a queued progression (caller must hold the lock)."""
        self._progression = new_prog
        self._queued = None
        self._swing_swap = False
        self._regenerate()
        self.state.pending_swap = False
        self.state.current_progression_name = new_prog.name
        if self.on_swap:
            try:
                self.on_swap(new_prog)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # MIDI helpers
    # ------------------------------------------------------------------

    def _send_note_on(self, note: int, velocity: int) -> None:
        if self._midi is None:
            return
        port = getattr(self._midi, "_port", None)
        if port is None:
            return
        try:
            import mido
            port.send(mido.Message("note_on", note=note, velocity=velocity))
        except Exception:
            pass

    def _send_note_off(self, note: int) -> None:
        if self._midi is None:
            return
        port = getattr(self._midi, "_port", None)
        if port is None:
            return
        try:
            import mido
            port.send(mido.Message("note_off", note=note, velocity=0))
        except Exception:
            pass

    def _stop_all_notes(self) -> None:
        if self._midi is None:
            return
        port = getattr(self._midi, "_port", None)
        if port is None:
            return
        try:
            import mido
            for ch in range(16):
                port.send(mido.Message(
                    "control_change", channel=ch, control=123, value=0
                ))
        except Exception:
            pass

    def _emit_beat(self, beat_idx: int) -> None:
        if beat_idx == self._last_beat_sent:
            return
        self._last_beat_sent = beat_idx
        for fn in self._beat_listeners:
            try:
                fn(beat_idx)
            except Exception:
                pass
