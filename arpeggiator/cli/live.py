"""
Live loop mode: play a progression in a loop, swap on the fly by typing.

Usage:
    arpeggiator-live --preset "ii-V-I (Jazz)" --root C --bpm 120

While running, type:
    1..9        swap to preset N (listed on start)
    g <spec>    swap to a roman-numeral progression, e.g. "g I V vi IV"
    c <chords>  swap to explicit chords, e.g. "c Dm7 G7 Cmaj7"
    b <bpm>     change tempo
    s <scope>   per_chord | global
    d <dir>     direction, e.g. "up_down"
    q           quit
"""

from __future__ import annotations
import sys
import threading

from ..core.music_theory import Scale
from ..core.arpeggio_engine import ArpeggioConfig, PatternDirection, PATTERN_DIRECTION_NAMES
from ..core.progressions import (
    parse_roman_progression, parse_chord_progression, normalize_octaves,
    PROGRESSION_PRESETS, PROGRESSION_PRESETS_7TH, get_preset,
)
from ..core.treatments import Treatment, PatternScope
from ..core.midi_out import MidiOutput
from ..core.midi_in import MidiInput
from ..core.player import ProgressionPlayer
from ..core.capture_session import ChordCaptureSession, CaptureConfig


PRESET_LIST = sorted(list(PROGRESSION_PRESETS) + list(PROGRESSION_PRESETS_7TH))


def build_live_parser():
    import argparse
    p = argparse.ArgumentParser(
        prog="arpeggiator-live",
        description="Loop a chord progression and swap it live",
    )
    p.add_argument("--preset", "-k", default=PRESET_LIST[0],
                   choices=PRESET_LIST, help="Starting progression preset")
    p.add_argument("--progression", "-g", default="",
                   help="Roman-numeral progression instead of preset")
    p.add_argument("--chords", "-c", default="",
                   help="Explicit chords instead of preset")
    p.add_argument("--root", "-r", default="C", help="Root note")
    p.add_argument("--scale", "-s", default="Major", help="Scale")
    p.add_argument("--octave", "-o", type=int, default=3)
    p.add_argument("--bpm", "-b", type=int, default=120)
    p.add_argument("--direction", "-d", default="Up & Down",
                   choices=list(PATTERN_DIRECTION_NAMES.keys()))
    p.add_argument("--rate", default="1/16",
                   choices=["1/4", "1/8", "1/8T", "1/16", "1/32"])
    p.add_argument("--range", "-R", type=int, default=1)
    p.add_argument("--tones", default="all",
                   help="all | shell | no_fifth | root | root_5 | top_tones")
    p.add_argument("--scope", default="per_chord",
                   choices=["per_chord", "global"])
    p.add_argument("--midi-port", "-p", default="")
    p.add_argument("--midi-in", "-i", default="",
                   help="MIDI keyboard input port (e.g. MPK261)")
    p.add_argument("--capture-beats", type=float, default=4.0,
                   help="Beats per captured chord (default 4 = one bar)")
    p.add_argument("--list-ports", action="store_true",
                   help="List MIDI input/output ports and exit")
    return p


def _build_progression(args, spec_override=None):
    scale = Scale(args.root, args.scale, args.octave)
    if spec_override:
        kind, value = spec_override
        if kind == "g":
            seventh = any(t.endswith("7") for t in value.split())
            prog = parse_roman_progression(value, scale, seventh=seventh)
        else:
            prog = parse_chord_progression(value)
        return normalize_octaves(prog, 48, 72)

    if args.progression:
        seventh = any(t.endswith("7") for t in args.progression.split())
        return normalize_octaves(
            parse_roman_progression(args.progression, scale, seventh=seventh)
        )
    if args.chords:
        return normalize_octaves(parse_chord_progression(args.chords))
    return normalize_octaves(get_preset(args.preset, scale))


def _build_config(args, config=None):
    rate_map = {"1/4": 1, "1/8": 2, "1/8T": 3, "1/16": 4, "1/32": 8}
    direction = PATTERN_DIRECTION_NAMES.get(args.direction, PatternDirection.UP_DOWN)
    base = config or ArpeggioConfig()
    return ArpeggioConfig(
        scale_name=args.scale,
        root_note=args.root,
        octave=args.octave,
        direction=direction,
        octave_range=args.range,
        rate_divider=rate_map.get(args.rate, 4),
        gate=0.8,
        swing=0.0,
        num_steps=base.num_steps,
        velocity_min=60,
        velocity_max=100,
    )


def _build_treatment(args, treatment=None):
    from ..core.treatments import ToneSelector
    base = treatment or Treatment()
    return Treatment(
        rhythm_spec=base.rhythm_spec,
        tone_selector=ToneSelector(args.tones),
        octave_mode=base.octave_mode,
        ornament=base.ornament,
        pattern_scope=PatternScope(args.scope),
    )


def _start_capture(args, player, initial_progression):
    """Wire a MIDI keyboard so played chords become the next progression."""
    midi_in = MidiInput(args.midi_in)
    cfg = CaptureConfig(beats_per_chord=args.capture_beats, auto_build_at=3)
    session = ChordCaptureSession(midi_in, cfg)

    state = {"held": []}

    def on_held(notes):
        state["held"] = notes

    def on_chord(chord, idx):
        remaining = cfg.auto_build_at - (idx + 1)
        tag = " -> building progression" if remaining <= 0 else \
              f" ({remaining} more)"
        print(f"\r\n  captured: {chord.label}{tag}")

    def on_progression(prog):
        labels = " - ".join(s.chord.label for s in prog.steps)
        print(f"\r\n  capturing complete -> {labels}")
        player.queue_next(normalize_octaves(prog, 48, 72))

    session.on_held = on_held
    session.on_chord = on_chord
    session.on_progression = on_progression

    if not session.start():
        print(f"  Could not open MIDI input: {args.midi_in}")
        print("  Try: arpeggiator-live --list-ports")
        return None

    print(f"  MIDI input connected: {args.midi_in}")
    return session


def main():
    args = build_live_parser().parse_args()

    # --- List ports and exit ---
    if args.list_ports:
        import mido
        ins = mido.get_input_names()
        outs = mido.get_output_names()
        print("MIDI INPUT ports (keyboards):")
        for p in ins:
            print(f"  - {p}")
        if not ins:
            print("  (none)")
        print()
        print("MIDI OUTPUT ports (synths):")
        for p in outs:
            print(f"  - {p}")
        if not outs:
            print("  (none)")
        return

    # --- MIDI output ---
    port = args.midi_port
    if not port:
        ports = MidiOutput.list_ports()
        if not ports:
            print("No MIDI output ports found.")
            print("Tip: create a virtual port, or use --save in the non-live CLI.")
            sys.exit(1)
        port = ports[0]
        print(f"Using MIDI port: {port}")

    midi = MidiOutput(port)
    if not midi.is_connected:
        print(f"Could not open MIDI port: {port}")
        sys.exit(1)

    player = ProgressionPlayer(midi_output=midi)
    player.bpm = args.bpm

    progression = _build_progression(args)
    if progression is None:
        print("Could not build a progression.")
        sys.exit(1)
    config = _build_config(args)
    treatment = _build_treatment(args)
    player.load(progression, config, treatment)

    # --- Visual feedback ---
    def on_chord(idx, chord, elapsed):
        bar = "=" * 8
        print(f"\r  [{bar}] chord {idx + 1}/{len(progression)}: "
              f"{chord.label:<10s}", end="", flush=True)

    def on_swap(new_prog):
        nonlocal progression
        progression = new_prog
        labels = " - ".join(s.chord.label for s in new_prog.steps)
        print(f"\n  swapped -> {labels}")

    player.on_chord = on_chord
    player.on_swap = on_swap

    # --- Live keyboard capture ---
    session = None
    if args.midi_in:
        session = _start_capture(args, player, progression)

    # --- Show preset menu ---
    print()
    print("  Looping. Presets:")
    for i, name in enumerate(PRESET_LIST[:9], start=1):
        print(f"    {i}. {name}")
    print()
    if session:
        print(f"  LIVE CAPTURE: play {CaptureConfig().auto_build_at} chords and "
              f"it becomes the next progression.")
    print("  Commands: <1-9> preset | g <romans> | c <chords> | "
          "b <bpm> | s <scope> | d <dir> | q  quit")
    print()

    player.start()

    # --- Command loop (input thread) ---
    try:
        while True:
            try:
                line = input().strip()
            except EOFError:
                break
            if not line:
                continue

            cmd, _, rest = line.partition(" ")
            rest = rest.strip()

            if cmd in ("q", "quit", "exit"):
                break

            elif cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(PRESET_LIST[:9]):
                    scale = Scale(args.root, args.scale, args.octave)
                    prog = get_preset(PRESET_LIST[idx], scale)
                    if prog:
                        player.queue_next(normalize_octaves(prog, 48, 72))

            elif cmd == "g" and rest:
                player.queue_next(_build_progression(args, ("g", rest)))

            elif cmd == "c" and rest:
                player.queue_next(_build_progression(args, ("c", rest)))

            elif cmd == "b" and rest.isdigit():
                player.bpm = max(30, min(300, int(rest)))
                print(f"\n  tempo -> {player.bpm} BPM")

            elif cmd == "s" and rest in ("per_chord", "global"):
                args.scope = rest
                player.set_treatment(_build_treatment(args, treatment))

            elif cmd == "d" and rest:
                match = [k for k in PATTERN_DIRECTION_NAMES if k.lower() == rest.lower()]
                if match:
                    args.direction = match[0]
                    player.set_config(_build_config(args, config))
                else:
                    print(f"\n  unknown direction: {rest}")

            else:
                print("\n  ? commands: <1-9> g c b s d q")

    except KeyboardInterrupt:
        pass
    finally:
        if session is not None:
            session.stop()
        player.stop()
        print("\n\n  Stopped. Woof.")


if __name__ == "__main__":
    main()
