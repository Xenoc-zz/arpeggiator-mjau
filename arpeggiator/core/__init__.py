"""Arpeggiator Core - Music theory engine for scales, modes, chords, and patterns."""

from .music_theory import (
    Scale, Mode, Note, CHROMATIC_NOTES, FLAT_NOTES,
    SCALE_PATTERNS, SCALE_DESCRIPTIONS,
    note_name_to_midi, midi_to_note_name,
)
from .chords import (
    Chord, ChordQuality, CHORD_INTERVALS, CHORD_LABELS,
    diatonic_chords, parse_chord, ROMAN_NUMERALS,
)
from .progressions import (
    Progression, ProgressionStep, ChordOverride,
    parse_roman_progression, parse_chord_progression,
    PROGRESSION_PRESETS, PROGRESSION_PRESETS_7TH,
    get_preset, list_presets, normalize_octaves,
)
from .treatments import (
    Treatment, ToneSelector, OctaveMode, PatternScope, RhythmStep,
    RHYTHM_PRESETS, parse_rhythm, rhythm_at,
    select_tones, apply_octave_mode, OrnamentConfig,
)
from .arpeggio_engine import (
    ArpeggioEngine, ArpeggioConfig, ArpeggioEvent,
    PatternDirection, PATTERN_DIRECTION_NAMES,
)
from .midi_out import MidiOutput
from .midi_in import MidiInput, ChordCapture, CapturedChord

__all__ = [
    # music theory
    "Scale", "Mode", "Note", "CHROMATIC_NOTES", "FLAT_NOTES",
    "SCALE_PATTERNS", "SCALE_DESCRIPTIONS",
    "note_name_to_midi", "midi_to_note_name",
    # chords
    "Chord", "ChordQuality", "CHORD_INTERVALS", "CHORD_LABELS",
    "diatonic_chords", "parse_chord", "ROMAN_NUMERALS",
    # progressions
    "Progression", "ProgressionStep", "ChordOverride",
    "parse_roman_progression", "parse_chord_progression",
    "PROGRESSION_PRESETS", "PROGRESSION_PRESETS_7TH",
    "get_preset", "list_presets", "normalize_octaves",
    # treatments
    "Treatment", "ToneSelector", "OctaveMode", "PatternScope", "RhythmStep",
    "RHYTHM_PRESETS", "parse_rhythm", "rhythm_at",
    "select_tones", "apply_octave_mode", "OrnamentConfig",
    # engine
    "ArpeggioEngine", "ArpeggioConfig", "ArpeggioEvent",
    "PatternDirection", "PATTERN_DIRECTION_NAMES",
    # io
    "MidiOutput", "MidiInput", "ChordCapture", "CapturedChord",
]
