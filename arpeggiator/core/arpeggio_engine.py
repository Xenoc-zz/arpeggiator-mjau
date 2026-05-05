"""
Arpeggio engine: generates sequences of notes from scales + patterns.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from .music_theory import Scale, Note, SCALE_PATTERNS


class PatternDirection(Enum):
    """Direction patterns for arpeggios."""
    UP = "up"                    # 1 2 3 4 5 6 7 8
    DOWN = "down"                # 8 7 6 5 4 3 2 1
    UP_DOWN = "up_down"          # 1 2 3 4 5 6 7 8 7 6 5 4 3 2 1
    DOWN_UP = "down_up"          # 8 7 6 5 4 3 2 1 2 3 4 5 6 7 8
    RANDOM = "random"            # random order
    RANDOM_WALK = "random_walk"  # random but steps by interval
    CHORD = "chord"              # play all at once (not really arpeggio but useful)
    ORDERED_UP = "ordered_up"    # play each note in order, repeating each N times


PATTERN_DIRECTION_NAMES = {
    "Up": PatternDirection.UP,
    "Down": PatternDirection.DOWN,
    "Up & Down": PatternDirection.UP_DOWN,
    "Down & Up": PatternDirection.DOWN_UP,
    "Random": PatternDirection.RANDOM,
    "Random Walk": PatternDirection.RANDOM_WALK,
    "Chord": PatternDirection.CHORD,
    "Ordered Up": PatternDirection.ORDERED_UP,
}


@dataclass
class ArpeggioConfig:
    """Configuration for arpeggio generation."""
    scale_name: str = "Major"
    root_note: str = "C"
    octave: int = 3
    direction: PatternDirection = PatternDirection.UP
    octave_range: int = 2        # How many octaves to span
    rate_divider: int = 4        # 4 = 16th notes, 8 = 32nd, 2 = 8th
    gate: float = 0.8            # Note length as fraction of step
    swing: float = 0.0           # 0.0 = straight, 0.5 = dotted
    num_steps: int = 16          # Steps per pattern
    humanize: float = 0.0        # Random timing variation (ms)
    velocity_min: int = 60
    velocity_max: int = 100


@dataclass
class ArpeggioEvent:
    """A single note event in an arpeggio sequence."""
    note: Note
    start_time: float       # In beats from start
    duration: float         # In beats
    velocity: int           # 0-127 MIDI velocity
    step_index: int         # Which step in the pattern


class ArpeggioEngine:
    """Generates arpeggio sequences from scales + patterns."""

    def __init__(self, config: Optional[ArpeggioConfig] = None):
        self.config = config or ArpeggioConfig()

    def generate(self, config: Optional[ArpeggioConfig] = None) -> list[ArpeggioEvent]:
        """Generate a list of arpeggio events based on config."""
        cfg = config or self.config
        scale = Scale(cfg.root_note, cfg.scale_name, cfg.octave)

        # Get all notes in the scale across the desired range
        root_midi = scale.notes[0].midi
        low = root_midi
        high = root_midi + 12 * cfg.octave_range
        available_notes = scale.notes_in_range(low, high)

        if not available_notes:
            return []

        # Generate the degree sequence based on direction
        degrees = self._generate_degree_sequence(available_notes, cfg)
        if not degrees:
            return []

        # Create events
        events = []
        step_duration = 4.0 / cfg.rate_divider  # In beats (4 = quarter note)

        for i, note in enumerate(degrees):
            start = i * step_duration
            # Apply swing on even steps
            if cfg.swing > 0 and i % 2 == 1:
                start += cfg.swing * step_duration * 0.5

            vel = cfg.velocity_min
            if cfg.velocity_max > cfg.velocity_min:
                vel = cfg.velocity_min + ((i % len(available_notes)) /
                                          len(available_notes) *
                                          (cfg.velocity_max - cfg.velocity_min))
                vel = int(vel)

            events.append(ArpeggioEvent(
                note=note,
                start_time=round(start, 4),
                duration=round(step_duration * cfg.gate, 4),
                velocity=min(127, max(1, vel)),
                step_index=i,
            ))

            if len(events) >= cfg.num_steps:
                break

        return events

    def _generate_degree_sequence(self,
                                  notes: list[Note],
                                  cfg: ArpeggioConfig) -> list[Note]:
        """Generate a sequence of notes based on direction pattern."""
        import random
        random.seed()  # fresh seed each time

        n_notes = len(notes)
        if n_notes == 0:
            return []

        direction = cfg.direction
        sequence: list[Note] = []

        if direction == PatternDirection.UP:
            sequence = [notes[i % n_notes] for i in range(cfg.num_steps)]

        elif direction == PatternDirection.DOWN:
            sequence = [notes[n_notes - 1 - (i % n_notes)]
                        for i in range(cfg.num_steps)]

        elif direction == PatternDirection.UP_DOWN:
            pattern = list(range(n_notes)) + list(range(n_notes - 2, 0, -1))
            sequence = [notes[pattern[i % len(pattern)]]
                        for i in range(cfg.num_steps)]

        elif direction == PatternDirection.DOWN_UP:
            pattern = list(range(n_notes - 1, -1, -1)) + list(range(1, n_notes - 1))
            sequence = [notes[pattern[i % len(pattern)]]
                        for i in range(cfg.num_steps)]

        elif direction == PatternDirection.RANDOM:
            sequence = [notes[random.randint(0, n_notes - 1)]
                        for _ in range(cfg.num_steps)]

        elif direction == PatternDirection.RANDOM_WALK:
            current = 0
            sequence.append(notes[current])
            for _ in range(cfg.num_steps - 1):
                step = random.choice([-2, -1, 1, 2])
                current = max(0, min(n_notes - 1, current + step))
                sequence.append(notes[current])

        elif direction == PatternDirection.ORDERED_UP:
            repeats = max(1, cfg.num_steps // n_notes)
            for note in notes:
                sequence.extend([note] * repeats)
            sequence = sequence[:cfg.num_steps]

        elif direction == PatternDirection.CHORD:
            # All notes at once (repeat for each step)
            sequence = notes[:cfg.num_steps]

        return sequence

    def generate_midi_notes(self,
                            config: Optional[ArpeggioConfig] = None,
                            bpm: int = 120) -> list[dict]:
        """Generate data ready for MIDI output.

        Returns list of dicts with: note, velocity, time (seconds), duration (seconds)
        """
        events = self.generate(config)
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
