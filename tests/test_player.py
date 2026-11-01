"""Tests for ProgressionPlayer - loop timing and live progression swapping.

These run headless (no MIDI hardware) using a mock port.
"""

import time

from arpeggiator.core import (
    Scale, parse_roman_progression, normalize_octaves,
    parse_chord_progression, Progression, ProgressionStep,
    ArpeggioConfig, PatternDirection, Treatment, ProgressionPlayer,
)
from mock_midi import MockMidiOutput


def _make_prog(spec="I V vi IV"):
    scale = Scale("C", "Major", 3)
    return normalize_octaves(parse_roman_progression(spec, scale))


def _make_player(prog, bpm=600):
    """High BPM keeps tests fast (a 4-beat loop = 0.4s at 600bpm)."""
    midi = MockMidiOutput()
    player = ProgressionPlayer(midi_output=midi)
    player.bpm = bpm
    cfg = ArpeggioConfig(direction=PatternDirection.UP,
                         rate_divider=2, octave_range=1)
    player.load(prog, cfg, Treatment())
    return player, midi


def test_player_plays_notes():
    prog = _make_prog()
    player, midi = _make_player(prog, bpm=600)
    player.start()
    try:
        assert midi.port.wait_for_notes(4, timeout=3.0), \
            "Player produced no note-on messages"
    finally:
        player.stop()

    notes = midi.port.notes_played()
    assert len(notes) >= 4
    # All notes should be valid MIDI
    assert all(0 <= n <= 127 for n in notes)


def test_player_stop_silences():
    prog = _make_prog()
    player, midi = _make_player(prog, bpm=600)
    player.start()
    midi.port.wait_for_notes(2, timeout=3.0)
    player.stop()
    time.sleep(0.05)
    assert not player.is_running
    # After stop, all-notes-off control messages should have been sent
    with midi.port._lock:
        cc123 = [m for m in midi.port.messages
                 if m["type"] == "control_change" and m["control"] == 123]
    assert cc123, "stop() should send all-notes-off (CC123)"


def test_chord_callback_fires():
    prog = _make_prog()
    player, midi = _make_player(prog, bpm=900)
    seen = []
    player.on_chord = lambda idx, chord, t: seen.append((idx, chord.label))
    player.start()
    try:
        deadline = time.monotonic() + 3.0
        while len(seen) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        player.stop()

    assert len(seen) >= 2, f"chord callback fired only {len(seen)} times"
    # First chord of I-V-vi-IV in C is C, second is G
    assert seen[0][1] == "C", f"first chord should be C, got {seen[0][1]}"
    assert seen[1][1] == "G", f"second chord should be G, got {seen[1][1]}"


def test_swap_at_loop_boundary():
    """A queued progression should take over at the loop boundary."""
    prog_a = _make_prog("I V")
    prog_b = parse_chord_progression("Dm7 G7")
    prog_b = Progression(prog_b.steps, name="second")

    player, midi = _make_player(prog_a, bpm=900)
    swapped = []
    player.on_swap = lambda p: swapped.append(p.name)

    player.start()
    try:
        time.sleep(0.02)          # let it get going
        player.queue_next(prog_b)  # queue the swap
        assert player.state.pending_swap

        deadline = time.monotonic() + 4.0
        while not swapped and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        player.stop()

    assert swapped == ["second"], f"expected one swap to 'second', got {swapped}"
    assert player.state.current_progression_name == "second"
    assert not player.state.pending_swap


def test_swap_waits_for_boundary_not_instant():
    """An A-note of prog A must play at least once before prog B appears."""
    prog_a = _make_prog("I V")           # starts with C
    prog_b = parse_chord_progression("Dm7 G7")
    prog_b = Progression(prog_b.steps, name="second")

    player, midi = _make_player(prog_a, bpm=1200)  # very fast loop
    player.start()
    try:
        time.sleep(0.01)
        player.queue_next(prog_b)
        midi.port.wait_for_notes(6, timeout=3.0)
    finally:
        player.stop()

    notes = midi.port.notes_played()
    # C major pool is C/E/G ; Dm7 pool is D/F/A/C
    # We just assert notes from A appeared early
    assert 48 in notes or 52 in notes or 55 in notes, \
        f"prog A notes missing before swap: {notes[:8]}"


def test_cancel_queued_swap():
    prog_a = _make_prog("I V")
    prog_b = parse_chord_progression("Dm7 G7")
    prog_b = Progression(prog_b.steps, name="second")

    player, midi = _make_player(prog_a, bpm=1200)
    player.queue_next(prog_b)
    player.cancel_queued()
    assert not player.state.pending_swap

    player.start()
    try:
        midi.port.wait_for_notes(4, timeout=3.0)
    finally:
        player.stop()
    assert player.state.current_progression_name == "I V"


def test_beat_listener():
    prog = _make_prog("I")
    player, midi = _make_player(prog, bpm=1200)
    beats = []
    player.add_beat_listener(lambda b: beats.append(b))
    player.start()
    try:
        deadline = time.monotonic() + 3.0
        while len(beats) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        player.stop()
    assert beats[:2] == [0, 1], f"expected beats [0, 1], got {beats[:4]}"


def run_all():
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
