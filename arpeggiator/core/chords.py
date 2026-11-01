"""
Chords: chord qualities, diatonic harmony, and chord construction.

A Chord is a root note + a quality + optional extensions/inversion.
Chords are immutable value objects.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .music_theory import Note, note_name_to_midi, midi_to_note_name


# ---------------------------------------------------------------------------
# Chord qualities (intervals in semitones from root)
# ---------------------------------------------------------------------------

CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    # Triads
    "major":      (0, 4, 7),
    "minor":      (0, 3, 7),
    "diminished": (0, 3, 6),
    "augmented":  (0, 4, 8),
    "sus2":       (0, 2, 7),
    "sus4":       (0, 5, 7),
    "power":      (0, 7),

    # Seventh chords
    "maj7":       (0, 4, 7, 11),
    "min7":       (0, 3, 7, 10),
    "dom7":       (0, 4, 7, 10),
    "m7b5":       (0, 3, 6, 10),   # half-diminished
    "dim7":       (0, 3, 6, 9),
    "minMaj7":    (0, 3, 7, 11),
    "aug7":       (0, 4, 8, 10),

    # Sixth chords
    "6":          (0, 4, 7, 9),
    "m6":         (0, 3, 7, 9),

    # Ninth chords
    "add9":       (0, 4, 7, 14),
    "maj9":       (0, 4, 7, 11, 14),
    "min9":       (0, 3, 7, 10, 14),
    "dom9":       (0, 4, 7, 10, 14),
    "m9b5":       (0, 3, 6, 10, 14),

    # Extended
    "maj11":      (0, 4, 7, 11, 14, 17),
    "min11":      (0, 3, 7, 10, 14, 17),
    "dom11":      (0, 4, 7, 10, 14, 17),
    "maj13":      (0, 4, 7, 11, 14, 17, 21),
    "min13":      (0, 3, 7, 10, 14, 17, 21),
    "dom13":      (0, 4, 7, 10, 14, 17, 21),

    # Altered
    "7b5":        (0, 4, 6, 10),
    "7#5":        (0, 4, 8, 10),
    "7b9":        (0, 4, 7, 10, 13),
    "7#9":        (0, 4, 7, 10, 15),
}

# Human-readable labels for the GUI/CLI
CHORD_LABELS: dict[str, str] = {
    "major": "Major", "minor": "minor", "diminished": "dim",
    "augmented": "aug", "sus2": "sus2", "sus4": "sus4", "power": "5",
    "maj7": "maj7", "min7": "m7", "dom7": "7", "m7b5": "m7b5",
    "dim7": "dim7", "minMaj7": "mMaj7", "aug7": "aug7",
    "6": "6", "m6": "m6",
    "add9": "add9", "maj9": "maj9", "min9": "m9", "dom9": "9",
    "m9b5": "m9b5",
    "maj11": "maj11", "min11": "m11", "dom11": "11",
    "maj13": "maj13", "min13": "m13", "dom13": "13",
    "7b5": "7b5", "7#5": "7#5", "7b9": "7b9", "7#9": "7#9",
}


class ChordQuality(str, Enum):
    """Named chord quality (value = key into CHORD_INTERVALS)."""
    MAJOR = "major"
    MINOR = "minor"
    DIMINISHED = "diminished"
    AUGMENTED = "augmented"
    SUS2 = "sus2"
    SUS4 = "sus4"
    POWER = "power"
    MAJ7 = "maj7"
    MIN7 = "min7"
    DOM7 = "dom7"
    M7B5 = "m7b5"
    DIM7 = "dim7"
    MINMAJ7 = "minMaj7"
    AUG7 = "aug7"
    SIX = "6"
    M6 = "m6"
    ADD9 = "add9"
    MAJ9 = "maj9"
    MIN9 = "min9"
    DOM9 = "dom9"
    M9B5 = "m9b5"
    MAJ11 = "maj11"
    MIN11 = "min11"
    DOM11 = "dom11"
    MAJ13 = "maj13"
    MIN13 = "min13"
    DOM13 = "dom13"
    SEVEN_B5 = "7b5"
    SEVEN_S5 = "7#5"
    SEVEN_B9 = "7b9"
    SEVEN_S9 = "7#9"
    # Special: the scale default triad inferred from mode degree
    AUTO = "auto"


# ---------------------------------------------------------------------------
# Chord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Chord:
    """A chord: root note + quality + optional inversion/bass.

    Examples:
        Chord("C", "major")      → C major triad
        Chord("D", "min7")       → D minor 7
        Chord("G", "dom7", 1)    → G7 in first inversion
    """
    root: str                       # "C", "F#", "Bb"
    quality: str = "major"          # key into CHORD_INTERVALS
    inversion: int = 0              # 0 = root position
    octave: int = 4                 # Root octave
    extensions: tuple[int, ...] = ()  # Extra notes (semitones above root)

    def __post_init__(self):
        if self.quality not in CHORD_INTERVALS:
            raise ValueError(
                f"Unknown chord quality '{self.quality}'. "
                f"Try: {', '.join(sorted(CHORD_INTERVALS))}"
            )
        if self.inversion < 0:
            raise ValueError("Inversion must be >= 0")

    @property
    def intervals(self) -> tuple[int, ...]:
        """Semitone intervals from root."""
        base = CHORD_INTERVALS[self.quality] + self.extensions
        return tuple(sorted(set(base)))

    def midi_notes(self, octave: Optional[int] = None) -> list[int]:
        """Get MIDI note numbers, applying inversion."""
        root_midi = note_name_to_midi(self.root, octave or self.octave)
        intervals = list(self.intervals)

        # Apply inversion: move lowest N notes up an octave
        inv = self.inversion % len(intervals) if intervals else 0
        notes = [root_midi + i for i in intervals]

        for _ in range(inv):
            if notes:
                notes.append(notes.pop(0) + 12)

        return sorted(notes)

    def notes(self, octave: Optional[int] = None) -> list[Note]:
        """Get chord tones as Note objects."""
        return [self._midi_to_note(m) for m in self.midi_notes(octave)]

    @staticmethod
    def _midi_to_note(midi: int) -> Note:
        s = midi_to_note_name(midi)
        # Parse e.g. "C#4" → name="C#", octave=4
        for i in range(len(s) - 1, -1, -1):
            if s[i] in "0123456789":
                continue
            return Note(s[:i + 1], int(s[i + 1:]))
        return Note(s, 4)

    @property
    def label(self) -> str:
        """Human label, e.g. 'Cmaj7' or 'G7'."""
        q = CHORD_LABELS.get(self.quality, self.quality)
        # Major triad is just the root
        if self.quality == "major":
            return f"{self.root}"
        return f"{self.root}{q}"

    def __repr__(self):
        return f"<Chord {self.label}>"


# ---------------------------------------------------------------------------
# Diatonic harmony: derive chords from a scale
# ---------------------------------------------------------------------------

# Which triad quality belongs to each degree of the major scale
MAJOR_DEGREE_QUALITIES = [
    "major",      # I
    "minor",      # ii
    "minor",      # iii
    "major",      # IV
    "major",      # V
    "minor",      # vi
    "diminished", # vii°
]

MAJOR_DEGREE_7THS = [
    "maj7",  # I
    "min7",  # ii
    "min7",  # iii
    "maj7",  # IV
    "dom7",  # V
    "min7",  # vi
    "m7b5",  # vii
]


# Roman numerals for major-scale degrees
ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII"]


def diatonic_chords(scale, seventh: bool = False) -> list[Chord]:
    """Build the diatonic chords of a scale.

    For a major scale this gives: I ii iii IV V vi vii°
    (correct qualities per degree).

    For non-major scales we fall back to stacking scale thirds
    and naming each chord by its resulting interval structure.
    """
    from .music_theory import Scale, SCALE_PATTERNS

    root_midi = scale.notes[0].midi
    intervals = list(scale.intervals)[:-1]  # drop the octave duplicate
    n = len(intervals)

    # For standard 7-note major, use the canonical quality table —
    # but the ROOT of each chord is the scale note at that degree.
    if scale.pattern_name == "Major" and n == 7:
        qualities = MAJOR_DEGREE_7THS if seventh else MAJOR_DEGREE_QUALITIES
        result = []
        for i in range(7):
            note_midi = root_midi + intervals[i]
            note_name = midi_to_note_name(note_midi)
            name, octv = note_name[:-1], int(note_name[-1])
            result.append(Chord(name, qualities[i], octave=octv))
        return result

    # Generic: stack scale thirds modulo octaves
    result = []
    for degree in range(n):
        # Root of this chord
        root_semi = intervals[degree]
        # Find the third and fifth by stepping through scale degrees
        scale_semis = [intervals[(degree + k) % n] +
                       (12 if (degree + k) >= n else 0)
                       for k in (2, 4, 6)]
        # Normalize thirds relative to chord root
        chord_intervals = [(s - root_semi) % 12 for s in scale_semis]
        if seventh:
            quality = _name_7th_chord(chord_intervals)
        else:
            quality = _name_triad(chord_intervals)
        root_name = midi_to_note_name(root_midi + root_semi)
        # Split name/octave
        name, octv = root_name[:-1], int(root_name[-1])
        result.append(Chord(name, quality, octave=octv))
    return result


def _name_triad(intervals: list[int]) -> str:
    """Identify a triad quality from its semitone intervals."""
    s = set(intervals[:3])
    if s == {0, 4, 7}:
        return "major"
    if s == {0, 3, 7}:
        return "minor"
    if s == {0, 3, 6}:
        return "diminished"
    if s == {0, 4, 8}:
        return "augmented"
    if s == {0, 5, 7}:
        return "sus4"
    if s == {0, 2, 7}:
        return "sus2"
    return "major"  # safe fallback


def _name_7th_chord(intervals: list[int]) -> str:
    """Identify a 7th chord quality from its semitone intervals."""
    s = set(intervals)
    if s == {0, 4, 7, 11}:
        return "maj7"
    if s == {0, 3, 7, 10}:
        return "min7"
    if s == {0, 4, 7, 10}:
        return "dom7"
    if s == {0, 3, 6, 10}:
        return "m7b5"
    if s == {0, 3, 6, 9}:
        return "dim7"
    if s == {0, 3, 7, 11}:
        return "minMaj7"
    if s == {0, 4, 8, 10}:
        return "aug7"
    # Fall back to triad + note
    return _name_7th_fallback(s)


def _name_7th_fallback(s: set[int]) -> str:
    # Not a standard 7th; return closest matching triad
    return _name_triad(sorted(s))


# ---------------------------------------------------------------------------
# Chord symbol parsing: "Cmaj7", "Dm9", "G7#5", "Bb", "F#dim7"
# ---------------------------------------------------------------------------

# Suffix → quality mapping (longest match first)
_SUFFIX_QUALITIES: list[tuple[str, str]] = [
    ("mMaj7", "minMaj7"), ("maj13", "maj13"), ("min13", "min13"),
    ("dom13", "dom13"), ("maj11", "maj11"), ("min11", "min11"),
    ("dom11", "dom11"), ("maj9", "maj9"), ("min9", "min9"),
    ("dom9", "dom9"), ("add9", "add9"), ("m9b5", "m9b5"),
    ("7#5", "7#5"), ("7b5", "7b5"), ("7#9", "7#9"), ("7b9", "7b9"),
    ("maj7", "maj7"), ("min7", "min7"), ("dim7", "dim7"),
    ("aug7", "aug7"), ("m7b5", "m7b5"),
    ("m7", "min7"), ("m9", "min9"), ("m6", "m6"),
    ("sus2", "sus2"), ("sus4", "sus4"),
    ("dim", "diminished"), ("aug", "augmented"),
    ("m", "minor"),
    ("6", "6"), ("7", "dom7"), ("9", "dom9"), ("13", "dom13"),
    ("", "major"),  # just the root = major
]


def parse_chord(symbol: str, octave: int = 4) -> Chord:
    """Parse a chord symbol like 'Cmaj7' or 'F#m9' into a Chord.

    Handles enharmonics: 'Db' and 'C#' both work.
    """
    from .music_theory import NOTE_TO_SEMITONE

    symbol = symbol.strip()
    if not symbol:
        raise ValueError("Empty chord symbol")

    # Parse root: letter + optional accidental
    root_letter = symbol[0].upper()
    idx = 1
    accidental = ""
    while idx < len(symbol) and symbol[idx] in "#b":
        accidental += symbol[idx]
        idx += 1

    root = root_letter + accidental
    if root not in NOTE_TO_SEMITONE:
        raise ValueError(f"Invalid root note in chord '{symbol}'")

    suffix = symbol[idx:]

    # Try to match a known suffix
    for sfx, quality in _SUFFIX_QUALITIES:
        if suffix == sfx:
            return Chord(root, quality, octave=octave)

    raise ValueError(
        f"Unknown chord suffix '{suffix}' in '{symbol}'. "
        f"Known suffixes: maj7, m7, 7, dim, aug, sus4, m9, ..."
    )
