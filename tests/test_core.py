"""Quick sanity tests for the core music theory modules.

Run with: uv run pytest tests/ -q
or just:  uv run python -m tests.test_core
"""

from arpeggiator.core import (
    Scale, Chord, parse_chord, diatonic_chords,
    parse_roman_progression, parse_chord_progression, normalize_octaves,
    ArpeggioEngine, ArpeggioConfig, PatternDirection,
    Treatment, ToneSelector, OctaveMode, OrnamentConfig,
    note_name_to_midi, midi_to_note_name,
)


def test_midi_conversion():
    assert note_name_to_midi("C", 4) == 60
    assert note_name_to_midi("A", 4) == 69
    assert note_name_to_midi("C#", 5) == 73
    assert note_name_to_midi("Eb", 2) == 39
    assert midi_to_note_name(60) == "C4"
    assert midi_to_note_name(69) == "A4"


def test_chord_construction():
    c = Chord("C", "major")
    assert c.midi_notes() == [60, 64, 67]

    dm7 = Chord("D", "min7")
    assert dm7.midi_notes() == [62, 65, 69, 72]

    # Inversion: C/E should start on E
    c_inv = Chord("C", "major", inversion=1)
    notes = c_inv.midi_notes()
    assert notes[0] == 64, f"First inversion should start on E, got {notes}"


def test_chord_parsing():
    assert parse_chord("C").quality == "major"
    assert parse_chord("Dm7").quality == "min7"
    assert parse_chord("G7").quality == "dom7"
    assert parse_chord("F#m9").quality == "min9"
    assert parse_chord("Bbdim7").quality == "dim7"


def test_diatonic():
    triads = diatonic_chords(Scale("C", "Major", 3))
    labels = [c.label for c in triads]
    assert labels[0] == "C"
    assert labels[1] == "Dminor"
    assert labels[4] == "G"
    assert labels[6] == "Bdim"


def test_roman_progression():
    scale = Scale("C", "Major", 3)
    prog = parse_roman_progression("ii V I", scale)
    labels = [s.chord.label for s in prog]
    assert labels == ["Dminor", "G", "C"], f"got {labels}"


def test_seventh_progression():
    scale = Scale("C", "Major", 3)
    prog = parse_roman_progression("ii7 V7 I7", scale, seventh=True)
    labels = [s.chord.label for s in prog]
    assert labels == ["Dm7", "G7", "Cmaj7"], f"got {labels}"


def test_explicit_chords():
    prog = parse_chord_progression("Cmaj7 Am7 Dm7 G7")
    labels = [s.chord.label for s in prog]
    assert labels == ["Cmaj7", "Am7", "Dm7", "G7"]


def test_normalize_octaves():
    scale = Scale("A", "Natural Minor", 3)
    prog = parse_roman_progression("i VII VI VII", scale)
    raw_roots = [s.chord.midi_notes()[0] for s in prog]
    # Without normalization the roots spread across octaves (A3 57 → G4 67)
    raw_spread = max(raw_roots) - min(raw_roots)
    assert raw_spread >= 10, f"Expected spread roots, got {raw_roots}"

    norm = normalize_octaves(prog, 48, 72)
    norm_roots = [s.chord.midi_notes()[0] for s in norm]
    assert all(48 <= r <= 72 for r in norm_roots), f"Roots outside window: {norm_roots}"
    # Normalized roots should sit tighter than the raw spread
    norm_spread = max(norm_roots) - min(norm_roots)
    assert norm_spread <= 12, f"Normalized spread too wide: {norm_roots}"


def test_engine_scale_path():
    engine = ArpeggioEngine()
    cfg = ArpeggioConfig(direction=PatternDirection.UP, num_steps=8, octave_range=1)
    events = engine.generate(cfg)
    assert len(events) == 8
    # Should be ascending within the octave
    midis = [e.note.midi for e in events]
    assert midis == sorted(midis)


def test_engine_progression_path():
    scale = Scale("C", "Major", 3)
    prog = normalize_octaves(parse_roman_progression("I V vi IV", scale))
    engine = ArpeggioEngine()
    cfg = ArpeggioConfig(direction=PatternDirection.UP, rate_divider=4, octave_range=1)
    events = engine.generate_progression(prog, cfg, Treatment())

    assert len(events) > 0
    # Each chord should have contributed events tagged with its index
    chord_indices = {e.chord_index for e in events}
    assert chord_indices == {0, 1, 2, 3}

    # Chord 0 (C major) events should all be from {C, E, G}
    c_major_pcs = {0, 4, 7}
    for e in events:
        if e.chord_index == 0 and not e.is_grace:
            assert e.note.midi % 12 in c_major_pcs


def test_tone_selector_shell():
    scale = Scale("C", "Major", 3)
    prog = normalize_octaves(parse_roman_progression("ii7 V7 I7", scale, seventh=True))
    engine = ArpeggioEngine()
    cfg = ArpeggioConfig(direction=PatternDirection.UP, rate_divider=2, octave_range=1)
    tr = Treatment(tone_selector=ToneSelector.SHELL)
    events = engine.generate_progression(prog, cfg, tr)

    # Shell = root, 3rd, 7th. Dm7 shell = D, F, C (no A)
    dm7_notes = {e.note.midi % 12 for e in events if e.chord_index == 0}
    assert 9 not in dm7_notes, f"Dm7 shell should not include the 5th (A), got {dm7_notes}"


def test_rhythm_rests():
    from arpeggiator.core.treatments import parse_rhythm
    steps = parse_rhythm("x-.-x-.-")
    actives = [s.active for s in steps]
    assert actives == [True, True, False, True, True, True, False, True]


def test_ornaments_approach():
    scale = Scale("C", "Major", 3)
    prog = normalize_octaves(parse_roman_progression("I V", scale))
    engine = ArpeggioEngine()
    cfg = ArpeggioConfig(direction=PatternDirection.UP, rate_divider=4, octave_range=1)
    tr = Treatment(ornament=OrnamentConfig(approach_notes=True))
    events = engine.generate_progression(prog, cfg, tr)

    grace = [e for e in events if e.is_grace]
    assert len(grace) == 2, f"Expected 2 approach notes (one per chord), got {len(grace)}"
    # Each grace note should be 1 semitone below a real note at the same chord
    for g in grace:
        matching = [
            e for e in events
            if e.chord_index == g.chord_index and not e.is_grace
            and e.note.midi == g.note.midi + 1
        ]
        assert matching, f"Grace {g.note.midi} has no target a semitone above"


def run_all():
    """Run every test_* function."""
    import traceback
    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception:
            print(f"  ERROR {name}:")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
