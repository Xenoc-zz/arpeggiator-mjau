"""Tests for ChordCaptureSession — live chord capture from a keyboard.

Drives the session directly (no real MIDI hardware) by calling the
note-on/note-off handlers, so timing behaviour is deterministic.
"""

import time

from arpeggiator.core import (
    ChordCaptureSession, CaptureConfig, MidiInput,
)


class FakeMidiInput(MidiInput):
    """MidiInput that never opens a port; we poke it by hand."""

    def __init__(self):
        super().__init__("")
        self.on_note_on = None
        self.on_note_off = None

    def start(self):
        self._running = True
        return True

    def stop(self):
        self._running = False

    def press(self, note, velocity=100):
        if self.on_note_on:
            self.on_note_on(note, velocity)

    def release(self, note):
        if self.on_note_off:
            self.on_note_off(note)


def _make_session(**cfg_kwargs):
    fake = FakeMidiInput()
    defaults = dict(release_gap=0.03, min_notes=2, auto_build_at=0)
    defaults.update(cfg_kwargs)
    session = ChordCaptureSession(fake, CaptureConfig(**defaults))
    return session, fake


def _play(fake, notes, hold=0.01):
    """Press then release a set of notes as one gesture."""
    for n in notes:
        fake.press(n)
    time.sleep(hold)
    for n in notes:
        fake.release(n)


def test_single_chord_captured():
    session, fake = _make_session()
    seen = []
    session.on_chord = lambda chord, idx: seen.append(chord)

    _play(fake, [60, 64, 67])   # C major
    time.sleep(0.15)            # let the debounce flush

    assert len(seen) == 1, f"expected 1 chord, got {len(seen)}"
    assert seen[0].label == "C", f"expected C, got {seen[0].label}"


def test_multiple_chords_accumulate():
    session, fake = _make_session()
    seen = []
    session.on_chord = lambda chord, idx: seen.append(chord)

    _play(fake, [62, 65, 69, 72])   # Dm7
    time.sleep(0.12)
    _play(fake, [67, 71, 74, 77])   # G7
    time.sleep(0.12)

    labels = [c.label for c in seen]
    assert labels == ["Dm7", "G7"], f"got {labels}"


def test_rolled_chord_counts_as_one():
    """Notes pressed slightly apart should still form a single chord."""
    session, fake = _make_session(release_gap=0.06)
    seen = []
    session.on_chord = lambda chord, idx: seen.append(chord)

    # Roll the chord: press low to high with gaps
    for n in (60, 64, 67, 71):
        fake.press(n)
        time.sleep(0.01)
    for n in (60, 64, 67, 71):
        fake.release(n)

    time.sleep(0.2)
    assert len(seen) == 1, f"rolled chord split into {len(seen)}: {[c.label for c in seen]}"
    assert seen[0].label == "Cmaj7", f"got {seen[0].label}"


def test_min_notes_filters_single_notes():
    session, fake = _make_session()
    seen = []
    session.on_chord = lambda chord, idx: seen.append(chord)

    _play(fake, [60])         # a single note should be ignored
    time.sleep(0.12)
    assert not seen, f"single note should be filtered, got {[c.label for c in seen]}"

    _play(fake, [60, 64])     # two notes is fine
    time.sleep(0.12)
    assert len(seen) == 1


def test_inversion_detected():
    """C/E should be recognized as a C chord, not something exotic."""
    session, fake = _make_session()
    seen = []
    session.on_chord = lambda chord, idx: seen.append(chord)

    _play(fake, [64, 67, 72])   # E G C = C major first inversion
    time.sleep(0.15)

    assert len(seen) == 1
    label = seen[0].label
    assert label in ("C",), f"inversion should resolve to C, got {label}"


def test_auto_build_emits_progression():
    session, fake = _make_session(auto_build_at=2)
    progressions = []
    session.on_progression = lambda p: progressions.append(p)

    _play(fake, [60, 64, 67])   # C
    time.sleep(0.12)
    assert not progressions, "should not emit before reaching auto_build_at"

    _play(fake, [67, 71, 74])   # G
    time.sleep(0.12)

    assert len(progressions) == 1, f"expected 1 progression, got {len(progressions)}"
    labels = [s.chord.label for s in progressions[0].steps]
    assert labels == ["C", "G"], f"got {labels}"


def test_build_now():
    session, fake = _make_session()
    _play(fake, [60, 64, 67])
    time.sleep(0.12)
    _play(fake, [65, 69, 72])   # F
    time.sleep(0.12)

    prog = session.build_now()
    assert prog is not None
    labels = [s.chord.label for s in prog.steps]
    assert labels == ["C", "F"], f"got {labels}"

    # Captured list is cleared after build_now
    assert session.build_now() is None


def test_on_held_callback():
    session, fake = _make_session()
    held_snapshots = []
    session.on_held = lambda notes: held_snapshots.append(list(notes))

    fake.press(60)
    fake.press(64)
    fake.press(67)

    assert held_snapshots[0] == [60]
    assert held_snapshots[1] == [60, 64]
    assert held_snapshots[2] == [60, 64, 67]


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
