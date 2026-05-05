"""
Music theory: notes, scales, modes, intervals.
No MIDI here — just pure musical knowledge.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

CHROMATIC_NOTES = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
]

# Enharmonic equivalents for flat-based keys
FLAT_NOTES = [
    "C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B",
]

NOTE_TO_SEMITONE = {name: i for i, name in enumerate(CHROMATIC_NOTES)}
NOTE_TO_SEMITONE.update({name: i for i, name in enumerate(FLAT_NOTES)})

# MIDI note numbers: C0 = 12, C1 = 24, ..., C8 = 108
MIDI_BASE_C0 = 12


def note_name_to_midi(note_name: str, octave: int = 4) -> int:
    """Convert note name + octave to MIDI note number.

    MIDI standard: C0 = 12, C4 = 60, A4 = 69, C#5 = 73, Eb2 = 39
    """
    name = note_name.strip()
    # Parse accidentals
    base = name[0].upper()
    accidental = ""
    for ch in name[1:]:
        if ch in "#b":
            accidental += ch
        else:
            octave = int(ch)
            break
    semitone = NOTE_TO_SEMITONE.get(base + accidental, 0)
    return 12 + octave * 12 + semitone


def midi_to_note_name(midi: int) -> str:
    """Convert MIDI note number back to note name + octave."""
    octave = midi // 12 - 1
    semitone = midi % 12
    return f"{CHROMATIC_NOTES[semitone]}{octave}"


@dataclass(frozen=True)
class Note:
    """A musical note with name, octave, and MIDI number."""
    name: str      # e.g. "C", "F#", "Bb"
    octave: int    # e.g. 4

    @property
    def midi(self) -> int:
        return note_name_to_midi(self.name, self.octave)

    def transpose(self, semitones: int) -> Note:
        new_midi = self.midi + semitones
        if new_midi < 0 or new_midi > 127:
            raise ValueError(f"Note out of MIDI range: {new_midi}")
        new_name = midi_to_note_name(new_midi)
        return Note(new_name[:-1], int(new_name[-1]))

    def __repr__(self):
        return f"<Note {self.name}{self.octave} (MIDI {self.midi})>"


# ---------------------------------------------------------------------------
# Intervals & Scales
# ---------------------------------------------------------------------------

class Interval(str, Enum):
    """Standard interval names mapped to semitone steps."""
    ROOT = "1"
    MINOR_SECOND = "b2"
    MAJOR_SECOND = "2"
    MINOR_THIRD = "b3"
    MAJOR_THIRD = "3"
    PERFECT_FOURTH = "4"
    TRITONE = "b5"
    PERFECT_FIFTH = "5"
    MINOR_SIXTH = "b6"
    MAJOR_SIXTH = "6"
    MINOR_SEVENTH = "b7"
    MAJOR_SEVENTH = "7"
    OCTAVE = "8"


# Scale patterns: semitone intervals from root
SCALE_PATTERNS: dict[str, tuple[int, ...]] = {
    # Major modes
    "Major":          (0, 2, 4, 5, 7, 9, 11, 12),
    "Natural Minor":  (0, 2, 3, 5, 7, 8, 10, 12),
    "Harmonic Minor": (0, 2, 3, 5, 7, 8, 11, 12),
    "Melodic Minor":  (0, 2, 3, 5, 7, 9, 11, 12),

    # Modes of Major
    "Ionian":     (0, 2, 4, 5, 7, 9, 11, 12),   # same as Major
    "Dorian":     (0, 2, 3, 5, 7, 9, 10, 12),
    "Phrygian":   (0, 1, 3, 5, 7, 8, 10, 12),
    "Lydian":     (0, 2, 4, 6, 7, 9, 11, 12),
    "Mixolydian": (0, 2, 4, 5, 7, 9, 10, 12),
    "Aeolian":    (0, 2, 3, 5, 7, 8, 10, 12),   # same as Natural Minor
    "Locrian":    (0, 1, 3, 5, 6, 8, 10, 12),

    # Pentatonics
    "Major Pentatonic":   (0, 2, 4, 7, 9, 12),
    "Minor Pentatonic":   (0, 3, 5, 7, 10, 12),
    "Blues":              (0, 3, 5, 6, 7, 10, 12),

    # Exotic
    "Whole Tone":    (0, 2, 4, 6, 8, 10, 12),
    "Diminished":    (0, 2, 3, 5, 6, 8, 9, 11, 12),
    "Chromatic":     tuple(range(13)),
}

# Human-readable descriptions for the UI
SCALE_DESCRIPTIONS: dict[str, str] = {
    "Major": "Happy, bright, stable",
    "Natural Minor": "Sad, dark, emotional",
    "Harmonic Minor": "Middle Eastern, dramatic",
    "Melodic Minor": "Jazz, ascending exotic",
    "Ionian": "Same as Major",
    "Dorian": "Jazzy, minor with raised 6th",
    "Phrygian": "Spanish, flamenco feel",
    "Lydian": "Dreamy, raised 4th",
    "Mixolydian": "Bluesy, dominant feel",
    "Aeolian": "Same as Natural Minor",
    "Locrian": "Unstable, diminished feel",
    "Major Pentatonic": "Folk, rock, simple bright",
    "Minor Pentatonic": "Blues, rock, simple dark",
    "Blues": "Blues with the blue note",
    "Whole Tone": "Dreamy, ambiguous, augmented",
    "Diminished": "Tense, symmetrical",
    "Chromatic": "All 12 semitones",
}


@dataclass
class Scale:
    """A scale defined by a root note and a pattern name."""
    root: str          # e.g. "C", "F#", "Bb"
    pattern_name: str  # e.g. "Major", "Dorian", "Blues"
    octave: int = 3    # Starting octave

    def __post_init__(self):
        if self.pattern_name not in SCALE_PATTERNS:
            raise ValueError(
                f"Unknown scale pattern: {self.pattern_name}. "
                f"Choose from: {', '.join(sorted(SCALE_PATTERNS))}"
            )

    @property
    def intervals(self) -> tuple[int, ...]:
        return SCALE_PATTERNS[self.pattern_name]

    @property
    def notes(self) -> list[Note]:
        """Get all notes in this scale across one octave."""
        root_midi = note_name_to_midi(self.root, self.octave)
        return [Note(midi_to_note_name(root_midi + i)[:-1],
                     int(midi_to_note_name(root_midi + i)[-1]))
                for i in self.intervals]

    def note_at(self, degree: int) -> Note:
        """Get the note at a given scale degree (1-indexed)."""
        midi = note_name_to_midi(self.root, self.octave)
        pattern = self.intervals
        # Wrap around octaves if needed
        octave_offset = (degree - 1) // len(pattern)
        idx = (degree - 1) % len(pattern)
        octave_jumps = pattern[-1] * octave_offset  # 12 per octave for most
        target_midi = midi + pattern[idx] + octave_jumps
        name = midi_to_note_name(target_midi)
        return Note(name[:-1], int(name[-1]))

    def notes_in_range(self, low: int, high: int) -> list[Note]:
        """Get all scale notes between low and high MIDI notes.
        Returns unique notes, sorted by MIDI number."""
        result = []
        root_midi = note_name_to_midi(self.root, self.octave)
        pattern = self.intervals
        octave_size = pattern[-1]  # typically 12

        seen: set[int] = set()
        midi = root_midi
        while midi <= high + octave_size:
            for interval in pattern:
                note_midi = midi + interval
                if note_midi not in seen and low <= note_midi <= high:
                    seen.add(note_midi)
                    name = midi_to_note_name(note_midi)
                    result.append(Note(name[:-1], int(name[-1])))
            midi += octave_size
        return result

    def __repr__(self):
        return f"<Scale {self.root} {self.pattern_name}>"


# Shorthand: modes are just scales
Mode = Scale
