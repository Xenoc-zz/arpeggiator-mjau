"""
Progressions: ordered sequences of chords with timing.

A Progression is a list of (Chord, duration_beats) plus metadata.
Presets cover common progressions; custom ones parse from symbols.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .chords import Chord, parse_chord, diatonic_chords


@dataclass(frozen=True)
class ProgressionStep:
    """One chord in a progression."""
    chord: Chord
    duration: float = 4.0   # In beats (4 = one bar in 4/4)

    @property
    def label(self) -> str:
        return self.chord.label


@dataclass
class Progression:
    """An ordered sequence of chords."""
    steps: list[ProgressionStep] = field(default_factory=list)
    name: str = "Custom"

    def __post_init__(self):
        if self.steps is None:
            self.steps = []

    @property
    def total_duration(self) -> float:
        """Total length in beats."""
        return sum(s.duration for s in self.steps)

    @property
    def chords(self) -> list[Chord]:
        return [s.chord for s in self.steps]

    def __len__(self):
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)

    def __repr__(self):
        labels = " - ".join(s.chord.label for s in self.steps)
        return f"<Progression '{self.name}': {labels}>"


# ---------------------------------------------------------------------------
# Parse "ii V I" style progressions relative to a key
# ---------------------------------------------------------------------------

# Roman numeral → scale degree (0-indexed)
ROMAN_TO_DEGREE: dict[str, int] = {
    "I": 0, "II": 1, "III": 2, "IV": 3,
    "V": 4, "VI": 5, "VII": 6,
    "i": 0, "ii": 1, "iii": 2, "iv": 3,
    "v": 4, "vi": 5, "vii": 6,
}


def _is_minor_roman(token: str) -> bool:
    """Lowercase = minor quality."""
    base = token.rstrip("°o")
    return base.islower()


def _is_diminished_roman(token: str) -> bool:
    return token.endswith("°") or token.endswith("o")


def parse_roman_progression(spec: str, scale, seventh: bool = False) -> Progression:
    """Parse a roman-numeral progression against a scale.

    Example: parse_roman_progression("I V vi IV", Scale("C", "Major"))
    → C - G - Am - F

    Supports:
      - Uppercase = major, lowercase = minor
      - '°' or 'o' suffix = diminished
      - 7 suffix = add seventh (e.g. "V7")
    """
    diatonic = diatonic_chords(scale, seventh=seventh)

    if not diatonic:
        raise ValueError("Scale has no diatonic chords")

    n_degrees = len(diatonic)
    steps: list[ProgressionStep] = []

    for raw_token in spec.split():
        token = raw_token.strip()
        if not token:
            continue

        # Handle a trailing "7" to upgrade to seventh chord
        wants_7th = False
        if token.endswith("7") and not token.endswith("°7"):
            token = token[:-1]
            wants_7th = True

        degree = ROMAN_TO_DEGREE.get(token)
        if degree is None:
            raise ValueError(
                f"Unknown roman numeral '{raw_token}'. "
                f"Use I-VII (uppercase major, lowercase minor)."
            )

        if degree >= n_degrees:
            raise ValueError(
                f"Degree {degree + 1} exceeds scale length {n_degrees}"
            )

        base_chord = diatonic[degree % n_degrees]

        # Determine quality from casing + seventh flag.
        # NOTE: `base_chord.quality` may already be a 7th quality (e.g. 'min7')
        # when called with seventh=True, so reduce it back to its triad family
        # before deciding the final quality.
        base_is_minor = base_chord.quality in ("minor", "min7", "min9", "m6")
        base_is_dim = base_chord.quality in (
            "diminished", "dim7", "m7b5", "m9b5"
        )

        if _is_diminished_roman(raw_token):
            quality = "dim7" if wants_7th else "diminished"
        elif _is_minor_roman(raw_token):
            quality = "min7" if wants_7th else "minor"
        elif base_is_dim:
            # Uppercase but dim degree (e.g. VII in minor) — keep diminished
            quality = "m7b5" if wants_7th else "diminished"
        elif wants_7th:
            # Uppercase major degree: I → maj7, V → dom7 (dominant!)
            if degree == 4:  # V in a major context = dominant 7th
                quality = "dom7"
            else:
                quality = "maj7"
        else:
            quality = "minor" if base_is_minor else "major"

        chord = Chord(base_chord.root, quality, octave=base_chord.octave)
        steps.append(ProgressionStep(chord, 4.0))

    return Progression(steps, name=spec)


def parse_chord_progression(spec: str, octave: int = 4) -> Progression:
    """Parse an explicit chord progression like 'Cmaj7 Am7 Dm7 G7'."""
    steps: list[ProgressionStep] = []
    for token in spec.split():
        token = token.strip()
        if not token:
            continue
        chord = parse_chord(token, octave=octave)
        steps.append(ProgressionStep(chord, 4.0))
    return Progression(steps, name=spec)


# ---------------------------------------------------------------------------
# Preset progressions (diatonic, relative to key)
# ---------------------------------------------------------------------------

PROGRESSION_PRESETS: dict[str, str] = {
    # Pop / rock classics
    "I-V-vi-IV (Pop)":        "I V vi IV",
    "vi-IV-I-V (Pop alt)":    "vi IV I V",
    "I-IV-V (Blues/Rock)":    "I IV V",
    "ii-V-I (Jazz)":          "ii V I",
    "I-vi-IV-V (50s)":        "I vi IV V",
    "I-V-vi-iii-IV (Canon)":  "I V vi iii IV",
    "vi-ii-V-I (Circle)":     "vi ii V I",
    "I-vi-ii-V (Turnaround)": "I vi ii V",
    "i-VII-VI-VII (Andalusian)": "i VII VI VII",
    "i-iv-v (Minor rock)":    "i iv v",
}

# A few 7th-chord presets
PROGRESSION_PRESETS_7TH: dict[str, str] = {
    "ii7-V7-I7 (Jazz)":       "ii7 V7 I7",
    "I7-vi7-ii7-V7":          "I7 vi7 ii7 V7",
    "iii7-vi7-ii7-V7":        "iii7 vi7 ii7 V7",
}


def get_preset(name: str, scale) -> Optional[Progression]:
    """Look up a preset by name and build it against a scale."""
    if name in PROGRESSION_PRESETS:
        return parse_roman_progression(PROGRESSION_PRESETS[name], scale)
    if name in PROGRESSION_PRESETS_7TH:
        return parse_roman_progression(
            PROGRESSION_PRESETS_7TH[name], scale, seventh=True
        )
    return None


def list_presets() -> dict[str, str]:
    """All preset names with their roman-numeral specs."""
    merged = dict(PROGRESSION_PRESETS)
    merged.update(PROGRESSION_PRESETS_7TH)
    return merged


# ---------------------------------------------------------------------------
# Voice-leading helper: keep chords in a common register
# ---------------------------------------------------------------------------

def normalize_octaves(progression: Progression,
                      target_low: int = 48,
                      target_high: int = 72) -> Progression:
    """Slide each chord's octave so its root sits inside a register window.

    Without this, chords derived from a scale climb octaves as the scale
    ascends (A3, B3, C4, D4, E4, F4, G4). That's fine for a scale, but a
    progression reads better when every chord lives in the same range.

    Args:
        progression: the progression to normalize
        target_low:  lowest acceptable MIDI root (default C3)
        target_high: highest acceptable MIDI root (default C5)
    """
    new_steps: list[ProgressionStep] = []
    for step in progression.steps:
        chord = step.chord
        root_midi = chord.midi_notes()[0] if chord.midi_notes() else 60

        # Slide by whole octaves until the root lands in the window
        while root_midi < target_low:
            root_midi += 12
            chord = _shift_chord_octave(chord, +1)
        while root_midi > target_high:
            root_midi -= 12
            chord = _shift_chord_octave(chord, -1)

        new_steps.append(ProgressionStep(chord, step.duration))

    return Progression(new_steps, name=progression.name)


def _shift_chord_octave(chord: Chord, octaves: int) -> Chord:
    """Return a copy of the chord moved by whole octaves."""
    return Chord(
        chord.root, chord.quality,
        inversion=chord.inversion,
        octave=chord.octave + octaves,
        extensions=chord.extensions,
    )
