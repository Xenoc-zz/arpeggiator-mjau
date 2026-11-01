"""
Treatments: rhythm patterns, chord-tone selection, inversions, ornaments.

These are the "knobs and levers" that transform a plain note sequence
into something with character.
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Rhythm patterns (per-step gate/accent/skip)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RhythmStep:
    """One step of a rhythm pattern.

    active  — whether a note is played on this step
    accent  — velocity multiplier (1.0 = normal, >1 louder, <1 softer)
    gate    — length multiplier (1.0 = normal)
    """
    active: bool = True
    accent: float = 1.0
    gate: float = 1.0


# Named rhythm presets: strings of symbols
#   '.' = rest (skip)
#   '-' = normal step
#   'x' = accent (louder)
#   '_' = ghost (softer)
#   '=' = legato (longer gate)
RHYTHM_PRESETS: dict[str, str] = {
    "Straight 16ths":          "----------------",
    "Straight 16ths accented": "x-x-x-x-x-x-x-x-",
    "Offbeat":                 "-.-.-.-.-.-.-.-.",
    "Gallop":                  "--.---.---.---.-",
    "Dotted":                  "-_._-_._-_._-_._",
    "Triplet swing":           "x--x--x--x--x--x",
    "Tresillo":                "x--x--x---x--x--",
    "Clave (3-2)":             "x--x--x-----x---",
    "Clave (2-3)":             "---x--x---x--x--",
    "Chaar (5-stroke)":        "x.x.x.x.x.x.x.x.",
    "Breakbeat":               "x-.x-..-x-.x-..-",
}


def parse_rhythm(spec: str) -> list[RhythmStep]:
    """Parse a rhythm spec string into RhythmStep objects.

    Symbols:
        '-' normal, 'x' accent, '_' ghost, '=' legato, '.' rest
    Spaces/commas are ignored.
    """
    symbols = [c for c in spec if c in "-x_=."]
    if not symbols:
        return [RhythmStep() for _ in range(16)]

    steps: list[RhythmStep] = []
    for sym in symbols:
        if sym == "-":
            steps.append(RhythmStep(active=True))
        elif sym == "x":
            steps.append(RhythmStep(active=True, accent=1.3))
        elif sym == "_":
            steps.append(RhythmStep(active=True, accent=0.6))
        elif sym == "=":
            steps.append(RhythmStep(active=True, gate=1.5))
        elif sym == ".":
            steps.append(RhythmStep(active=False))
    return steps


def rhythm_at(steps: list[RhythmStep], index: int) -> RhythmStep:
    """Get the rhythm step at an index, cycling as needed."""
    if not steps:
        return RhythmStep()
    return steps[index % len(steps)]


# ---------------------------------------------------------------------------
# Chord-tone selection
# ---------------------------------------------------------------------------

class ToneSelector(str, Enum):
    """Which chord tones to include in the arpeggio."""
    ALL = "all"              # every chord tone
    ROOT_ONLY = "root"       # just the root
    NO_FIFTH = "no_fifth"    # root, 3rd, 7th (jazz style)
    ROOT_AND_FIFTH = "root_5"
    SHELL = "shell"          # root, 3rd, 7th (no 5th)
    TOP_TONES = "top_tones"  # 3rd, 5th, 7th


def select_tones(intervals: list[int], selector: ToneSelector) -> list[int]:
    """Filter chord intervals according to a selector.

    Intervals are semitones above the root (0 = root).
    """
    if not intervals:
        return intervals

    if selector == ToneSelector.ALL:
        return list(intervals)

    if selector == ToneSelector.ROOT_ONLY:
        return [0]

    def degree_of(semi: int) -> Optional[int]:
        s = semi % 12
        if s == 0:
            return 1   # root
        if s in (3, 4):
            return 3   # third
        if s in (6, 7, 8):
            return 5   # fifth
        if s in (9, 10, 11):
            return 7   # seventh
        if s in (1, 2):
            return 9   # ninth
        return None

    degrees = [degree_of(i) for i in intervals]

    if selector == ToneSelector.NO_FIFTH:
        return [i for i, d in zip(intervals, degrees) if d != 5]

    if selector == ToneSelector.ROOT_AND_FIFTH:
        return [i for i, d in zip(intervals, degrees) if d in (1, 5)]

    if selector == ToneSelector.SHELL:
        return [i for i, d in zip(intervals, degrees) if d in (1, 3, 7)]

    if selector == ToneSelector.TOP_TONES:
        return [i for i, d in zip(intervals, degrees) if d in (3, 5, 7)]

    return list(intervals)


# ---------------------------------------------------------------------------
# Octave spread modes
# ---------------------------------------------------------------------------

class OctaveMode(str, Enum):
    """How notes are spread across the octave range."""
    LINEAR = "linear"           # natural chord/scale order
    OCTAVE_UP = "octave_up"     # every 4th step jumps an octave
    ROOT_BASS = "root_bass"     # alternate low root and high chord
    EXPANDING = "expanding"     # first half low, second half up an octave
    CONVERGING = "converging"   # first half up, second half low


def apply_octave_mode(notes: list[int], mode: OctaveMode,
                      num_octaves: int = 2) -> list[int]:
    """Transform a note list according to an octave-spread mode."""
    if not notes:
        return notes

    if mode == OctaveMode.LINEAR:
        return notes

    if mode == OctaveMode.OCTAVE_UP:
        result = []
        for i, n in enumerate(notes):
            octave_jump = (i // 4) % num_octaves
            result.append(n + octave_jump * 12)
        return result

    if mode == OctaveMode.ROOT_BASS:
        result = []
        root = notes[0]
        for i, n in enumerate(notes):
            result.append(root - 12 if i % 2 == 0 else n)
        return result

    if mode == OctaveMode.EXPANDING:
        half = len(notes) // 2
        return notes[:half] + [n + 12 for n in notes[half:]]

    if mode == OctaveMode.CONVERGING:
        half = len(notes) // 2
        return [n + 12 for n in notes[:half]] + notes[half:]

    return notes


# ---------------------------------------------------------------------------
# Ornaments (grace notes, approach notes)
# ---------------------------------------------------------------------------

@dataclass
class OrnamentConfig:
    """Configuration for ornaments applied to arpeggios."""
    grace_notes: bool = False
    grace_count: int = 1            # notes in each grace cluster
    grace_duration: float = 0.01    # in beats
    approach_notes: bool = False    # chromatic lead-in to next chord
    approach_distance: int = 1      # semitones
    turnaround: bool = False        # add a little lick at phrase end


def apply_grace_notes(note: int, count: int = 1,
                      direction: int = -1) -> list[int]:
    """Generate grace notes leading into a note.

    Returns a list of grace MIDI numbers (not including the main note).
    """
    if count <= 0:
        return []
    return [note + direction * (count - i) for i in range(count)]


def chromatic_approach(target: int, distance: int = 1) -> int:
    """The chromatic note leading into a target."""
    return target - distance


# ---------------------------------------------------------------------------
# Accent shaping (dynamics)
# ---------------------------------------------------------------------------

def shape_velocity(base: int, accent: float,
                   position: int, total: int) -> int:
    """Compute an accent-adjusted velocity with a subtle dynamic arch."""
    if total <= 1:
        arch = 1.0
    else:
        t = position / (total - 1)
        arch = 0.85 + 0.15 * (1 - abs(2 * t - 1))

    v = int(base * accent * arch)
    return max(1, min(127, v))


# ---------------------------------------------------------------------------
# Full treatment bundle
# ---------------------------------------------------------------------------

@dataclass
class Treatment:
    """A complete bundle of arpeggio treatments."""
    rhythm_spec: str = "----------------"
    tone_selector: ToneSelector = ToneSelector.ALL
    octave_mode: OctaveMode = OctaveMode.LINEAR
    ornament: OrnamentConfig = field(default_factory=OrnamentConfig)
    humanize_velocity: float = 0.0   # 0-1, random velocity jitter

    @property
    def rhythm_steps(self) -> list[RhythmStep]:
        return parse_rhythm(self.rhythm_spec)

    def rhythm_len(self) -> int:
        return len(self.rhythm_steps)
