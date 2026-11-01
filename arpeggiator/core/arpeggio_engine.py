"""
Arpeggio engine: generates note sequences from scales OR chord progressions.

Design:
    - `generate(config)` — legacy scale-based path (backwards compatible)
    - `generate_progression(progression, config, treatment)` — the new hotness:
        a GLOBAL pattern (direction/rate/octaves) applied over a progression,
        where only the chord tones shift as chords change.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import random

from .music_theory import Scale, Note, SCALE_PATTERNS, midi_to_note_name
from .chords import Chord
from .progressions import Progression, ProgressionStep
from .treatments import (
    Treatment, ToneSelector, OctaveMode, RhythmStep,
    parse_rhythm, rhythm_at, select_tones, apply_octave_mode,
    shape_velocity, apply_grace_notes, chromatic_approach,
)


# ---------------------------------------------------------------------------
# Enums & constants (public API)
# ---------------------------------------------------------------------------

class PatternDirection(Enum):
    """Direction patterns for arpeggios."""
    UP = "up"
    DOWN = "down"
    UP_DOWN = "up_down"
    DOWN_UP = "down_up"
    RANDOM = "random"
    RANDOM_WALK = "random_walk"
    CHORD = "chord"
    ORDERED_UP = "ordered_up"
    BLOCK = "block"


PATTERN_DIRECTION_NAMES = {
    "Up": PatternDirection.UP,
    "Down": PatternDirection.DOWN,
    "Up & Down": PatternDirection.UP_DOWN,
    "Down & Up": PatternDirection.DOWN_UP,
    "Random": PatternDirection.RANDOM,
    "Random Walk": PatternDirection.RANDOM_WALK,
    "Chord": PatternDirection.CHORD,
    "Ordered Up": PatternDirection.ORDERED_UP,
    "Block": PatternDirection.BLOCK,
}


@dataclass
class ArpeggioConfig:
    """Configuration for arpeggio generation."""
    scale_name: str = "Major"
    root_note: str = "C"
    octave: int = 3
    direction: PatternDirection = PatternDirection.UP
    octave_range: int = 2
    rate_divider: int = 4        # 4 = 16ths, 8 = 32nds, 2 = 8ths
    gate: float = 0.8
    swing: float = 0.0
    num_steps: int = 16
    humanize: float = 0.0
    velocity_min: int = 60
    velocity_max: int = 100


@dataclass
class ArpeggioEvent:
    """A single note event in an arpeggio sequence."""
    note: Note
    start_time: float
    duration: float
    velocity: int
    step_index: int
    chord_index: int = 0          # Which chord in a progression
    is_grace: bool = False        # Grace/ornament note


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ArpeggioEngine:
    """Generates arpeggio sequences from scales or progressions."""

    def __init__(self, config: Optional[ArpeggioConfig] = None):
        self.config = config or ArpeggioConfig()

    # ------------------------------------------------------------------
    # Legacy: scale-based generation (kept for compatibility)
    # ------------------------------------------------------------------

    def generate(self, config: Optional[ArpeggioConfig] = None) -> list[ArpeggioEvent]:
        """Generate arpeggio events from a scale (legacy API)."""
        cfg = config or self.config
        scale = Scale(cfg.root_note, cfg.scale_name, cfg.octave)
        return self._generate_from_note_pool(
            scale_notes=scale.notes_in_range(
                scale.notes[0].midi,
                scale.notes[0].midi + 12 * cfg.octave_range,
            ),
            cfg=cfg,
        )

    def _generate_from_note_pool(self, scale_notes: list[Note],
                                 cfg: ArpeggioConfig) -> list[ArpeggioEvent]:
        """Core legacy generator."""
        if not scale_notes:
            return []

        degrees = self._sequence_from_direction(scale_notes, cfg)
        events: list[ArpeggioEvent] = []
        step_duration = 4.0 / cfg.rate_divider

        for i, note in enumerate(degrees):
            if len(events) >= cfg.num_steps:
                break
            start = i * step_duration
            if cfg.swing > 0 and i % 2 == 1:
                start += cfg.swing * step_duration * 0.5

            vel = cfg.velocity_min
            if cfg.velocity_max > cfg.velocity_min and len(scale_notes) > 0:
                vel += int((i % len(scale_notes)) / len(scale_notes)
                           * (cfg.velocity_max - cfg.velocity_min))

            events.append(ArpeggioEvent(
                note=note,
                start_time=round(start, 4),
                duration=round(step_duration * cfg.gate, 4),
                velocity=min(127, max(1, vel)),
                step_index=i,
            ))
        return events

    def _sequence_from_direction(self, notes: list[Note],
                                 cfg: ArpeggioConfig) -> list[Note]:
        n = len(notes)
        if n == 0:
            return []
        d = cfg.direction
        steps = cfg.num_steps

        if d == PatternDirection.UP:
            return [notes[i % n] for i in range(steps)]
        if d == PatternDirection.DOWN:
            return [notes[n - 1 - (i % n)] for i in range(steps)]
        if d == PatternDirection.UP_DOWN:
            pat = list(range(n)) + list(range(n - 2, 0, -1))
            return [notes[pat[i % len(pat)]] for i in range(steps)]
        if d == PatternDirection.DOWN_UP:
            pat = list(range(n - 1, -1, -1)) + list(range(1, n - 1))
            return [notes[pat[i % len(pat)]] for i in range(steps)]
        if d == PatternDirection.RANDOM:
            return [notes[random.randint(0, n - 1)] for _ in range(steps)]
        if d == PatternDirection.RANDOM_WALK:
            seq, cur = [], 0
            for _ in range(steps):
                seq.append(notes[cur])
                cur = max(0, min(n - 1, cur + random.choice([-2, -1, 1, 2])))
            return seq
        if d in (PatternDirection.ORDERED_UP, PatternDirection.CHORD):
            reps = max(1, steps // n)
            seq = []
            for note in notes:
                seq.extend([note] * reps)
            return seq[:steps]
        return [notes[i % n] for i in range(steps)]

    # ------------------------------------------------------------------
    # NEW: progression-based generation
    # ------------------------------------------------------------------

    def generate_progression(
        self,
        progression: Progression,
        config: Optional[ArpeggioConfig] = None,
        treatment: Optional[Treatment] = None,
    ) -> list[ArpeggioEvent]:
        """Generate arpeggio events spanning a chord progression.

        A GLOBAL pattern is applied across the whole progression; only the
        chord tones shift as each chord arrives.
        """
        cfg = config or self.config
        tr = treatment or Treatment()

        if not progression.steps:
            return []

        rhythm_steps = tr.rhythm_steps
        step_beats = 4.0 / cfg.rate_divider

        events: list[ArpeggioEvent] = []
        time_cursor = 0.0

        for chord_idx, step in enumerate(progression.steps):
            chord = step.chord
            chord_duration = step.duration
            num_steps_for_chord = max(1, int(round(chord_duration / step_beats)))

            chord_events = self._generate_for_chord(
                chord=chord,
                cfg=cfg,
                tr=tr,
                rhythm_steps=rhythm_steps,
                step_beats=step_beats,
                num_steps=num_steps_for_chord,
                time_offset=time_cursor,
                chord_index=chord_idx,
                is_last_chord=(chord_idx == len(progression.steps) - 1),
                next_chord=(
                    progression.steps[chord_idx + 1].chord
                    if chord_idx + 1 < len(progression.steps) else None
                ),
            )
            events.extend(chord_events)
            time_cursor += chord_duration

        return events

    def _generate_for_chord(
        self,
        chord: Chord,
        cfg: ArpeggioConfig,
        tr: Treatment,
        rhythm_steps: list[RhythmStep],
        step_beats: float,
        num_steps: int,
        time_offset: float,
        chord_index: int,
        is_last_chord: bool,
        next_chord: Optional[Chord],
    ) -> list[ArpeggioEvent]:
        """Generate events for a single chord."""
        note_pool = self._build_chord_note_pool(chord, cfg, tr)
        if not note_pool:
            return []

        idx_sequence = self._direction_indices(
            len(note_pool), num_steps, cfg, chord_index
        )

        events: list[ArpeggioEvent] = []
        for local_step in range(num_steps):
            rhythm = rhythm_at(rhythm_steps, local_step)
            if not rhythm.active:
                continue

            pool_idx = idx_sequence[local_step % len(idx_sequence)]
            midi = note_pool[pool_idx]

            base_vel = (cfg.velocity_min + cfg.velocity_max) // 2
            vel = shape_velocity(base_vel, rhythm.accent, local_step, num_steps)
            if tr.humanize_velocity > 0:
                jitter = int(random.uniform(-1, 1) * tr.humanize_velocity * 20)
                vel = max(1, min(127, vel + jitter))

            start = time_offset + local_step * step_beats
            if cfg.swing > 0 and local_step % 2 == 1:
                start += cfg.swing * step_beats * 0.5

            duration = step_beats * cfg.gate * rhythm.gate

            # Ornament: chromatic approach into first step of a chord
            if (tr.ornament.approach_notes and local_step == 0 and midi >= 12):
                approach = chromatic_approach(midi, tr.ornament.approach_distance)
                events.append(ArpeggioEvent(
                    note=self._note_from_midi(approach),
                    start_time=round(start - step_beats * 0.5, 4),
                    duration=round(step_beats * 0.5, 4),
                    velocity=vel,
                    step_index=local_step,
                    chord_index=chord_index,
                    is_grace=True,
                ))

            # Ornament: grace notes into accented steps
            if tr.ornament.grace_notes and rhythm.accent > 1.0:
                grace_midis = apply_grace_notes(
                    midi, tr.ornament.grace_count, direction=-1
                )
                for gi, gm in enumerate(grace_midis):
                    g_start = start - (len(grace_midis) - gi) * tr.ornament.grace_duration
                    events.append(ArpeggioEvent(
                        note=self._note_from_midi(gm),
                        start_time=round(g_start, 4),
                        duration=round(tr.ornament.grace_duration, 4),
                        velocity=max(1, vel - 20),
                        step_index=local_step,
                        chord_index=chord_index,
                        is_grace=True,
                    ))

            events.append(ArpeggioEvent(
                note=self._note_from_midi(midi),
                start_time=round(start, 4),
                duration=round(duration, 4),
                velocity=vel,
                step_index=local_step,
                chord_index=chord_index,
            ))

        return events

    def _build_chord_note_pool(
        self, chord: Chord, cfg: ArpeggioConfig, tr: Treatment
    ) -> list[int]:
        """Build the MIDI note pool for a chord, applying tone selection."""
        chord_midis = chord.midi_notes()
        if not chord_midis:
            return []
        root_midi = chord_midis[0]

        intervals = list(chord.intervals)
        intervals = select_tones(intervals, tr.tone_selector)
        if not intervals:
            return []

        pool: list[int] = []
        for oct_num in range(cfg.octave_range):
            for interval in intervals:
                midi = root_midi + oct_num * 12 + interval
                if 0 <= midi <= 127:
                    pool.append(midi)

        pool = sorted(set(pool))
        pool = apply_octave_mode(pool, tr.octave_mode, cfg.octave_range)

        return [m for m in pool if 0 <= m <= 127]

    def _direction_indices(self, pool_size: int, num_steps: int,
                           cfg: ArpeggioConfig, chord_index: int) -> list[int]:
        """Build the sequence of pool indices according to direction."""
        if pool_size <= 0:
            return []
        d = cfg.direction

        if d == PatternDirection.UP:
            return [i % pool_size for i in range(num_steps)]
        if d == PatternDirection.DOWN:
            return [pool_size - 1 - (i % pool_size) for i in range(num_steps)]
        if d == PatternDirection.UP_DOWN:
            pat = list(range(pool_size)) + list(range(pool_size - 2, 0, -1))
            return [pat[i % len(pat)] for i in range(num_steps)]
        if d == PatternDirection.DOWN_UP:
            pat = list(range(pool_size - 1, -1, -1)) + list(range(1, pool_size - 1))
            return [pat[i % len(pat)] for i in range(num_steps)]
        if d == PatternDirection.RANDOM:
            return [random.randint(0, pool_size - 1) for _ in range(num_steps)]
        if d == PatternDirection.RANDOM_WALK:
            seq, cur = [], 0
            for _ in range(num_steps):
                seq.append(cur)
                cur = max(0, min(pool_size - 1, cur + random.choice([-2, -1, 1, 2])))
            return seq
        # CHORD / BLOCK / ORDERED_UP: ascending repetition
        return [i % pool_size for i in range(num_steps)]

    @staticmethod
    def _note_from_midi(midi: int) -> Note:
        """Convert a MIDI number to a Note (using sharps)."""
        name = midi_to_note_name(midi)
        for i in range(len(name) - 1, -1, -1):
            if name[i].isdigit():
                continue
            return Note(name[:i + 1], int(name[i + 1:]))
        return Note(name, 4)

    # ------------------------------------------------------------------
    # MIDI-ready output
    # ------------------------------------------------------------------

    def generate_midi_notes(self,
                            config: Optional[ArpeggioConfig] = None,
                            bpm: int = 120) -> list[dict]:
        """Generate MIDI-ready dicts from the legacy scale path."""
        events = self.generate(config)
        return self._events_to_midi(events, bpm)

    def progression_to_midi(self,
                            progression: Progression,
                            config: Optional[ArpeggioConfig] = None,
                            treatment: Optional[Treatment] = None,
                            bpm: int = 120) -> list[dict]:
        """Generate MIDI-ready dicts from a progression."""
        events = self.generate_progression(progression, config, treatment)
        return self._events_to_midi(events, bpm)

    @staticmethod
    def _events_to_midi(events: list[ArpeggioEvent], bpm: int) -> list[dict]:
        beat_duration = 60.0 / bpm
        return [
            {
                "note": e.note.midi,
                "velocity": e.velocity,
                "time": e.start_time * beat_duration,
                "duration": e.duration * beat_duration,
            }
            for e in events
        ]
