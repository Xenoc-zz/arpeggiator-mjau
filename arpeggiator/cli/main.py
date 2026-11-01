"""
CLI interface for the arpeggiator.
Generate and play arpeggios from the command line.
"""

from __future__ import annotations
import argparse
import sys
import time

from ..core.arpeggio_engine import (
    ArpeggioEngine, ArpeggioConfig, PatternDirection, PATTERN_DIRECTION_NAMES,
)
from ..core.midi_out import MidiOutput
from ..core.music_theory import SCALE_PATTERNS, CHROMATIC_NOTES, Scale
from ..core.progressions import (
    parse_roman_progression, parse_chord_progression, normalize_octaves,
    PROGRESSION_PRESETS, PROGRESSION_PRESETS_7TH, get_preset,
)
from ..core.treatments import (
    Treatment, ToneSelector, OctaveMode, OrnamentConfig, RHYTHM_PRESETS,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arpeggiator",
        description="🎹 Arpeggiator Mjau — generate and play MIDI arpeggios",
    )

    parser.add_argument("--scale", "-s", default="Major",
                        choices=sorted(SCALE_PATTERNS.keys()),
                        help="Scale or mode to use")
    parser.add_argument("--root", "-r", default="C",
                        choices=CHROMATIC_NOTES,
                        help="Root note")
    parser.add_argument("--octave", "-o", type=int, default=3,
                        help="Starting octave (1-7)")
    parser.add_argument("--range", "-R", type=int, default=2,
                        help="Octave range to span")

    dir_names = list(PATTERN_DIRECTION_NAMES.keys())
    parser.add_argument("--direction", "-d", default="Up & Down",
                        choices=dir_names,
                        help="Arpeggio direction pattern")

    parser.add_argument("--bpm", "-b", type=int, default=120,
                        help="Tempo in BPM")
    parser.add_argument("--rate", choices=["1/4", "1/8", "1/8T", "1/16", "1/32"],
                        default="1/16", help="Note rate")
    parser.add_argument("--steps", "-n", type=int, default=16,
                        help="Number of steps")
    parser.add_argument("--gate", type=float, default=0.8,
                        help="Gate (0.1-1.0)")
    parser.add_argument("--swing", type=float, default=0.0,
                        help="Swing amount (0.0-1.0)")

    parser.add_argument("--midi-port", "-p", default="",
                        help="MIDI output port name")
    parser.add_argument("--list-ports", "-l", action="store_true",
                        help="List available MIDI ports and exit")
    parser.add_argument("--save", "-S", default="",
                        help="Save to MIDI file instead of playing")
    parser.add_argument("--preview", "-P", action="store_true",
                        help="Print notes and exit (no MIDI)")

    parser.add_argument("--velocity-min", type=int, default=60)
    parser.add_argument("--velocity-max", type=int, default=100)

    # ---- Progression options ----
    prog = parser.add_argument_group("progressions")
    prog.add_argument("--progression", "-g", default="",
                      help="Roman-numeral progression, e.g. 'I V vi IV' or 'ii7 V7 I7'")
    prog.add_argument("--chords", "-c", default="",
                      help="Explicit chord progression, e.g. 'Cmaj7 Am7 Dm7 G7'")
    prog.add_argument("--preset", "-k", default="",
                      choices=sorted(list(PROGRESSION_PRESETS) +
                                     list(PROGRESSION_PRESETS_7TH)),
                      help="Named progression preset")
    prog.add_argument("--list-presets", action="store_true",
                      help="List progression presets")
    prog.add_argument("--no-normalize", action="store_true",
                      help="Don't normalize chord octaves to a common register")

    # ---- Treatment options ----
    trt = parser.add_argument_group("treatments")
    trt.add_argument("--rhythm", default="",
                     choices=sorted(RHYTHM_PRESETS),
                     help="Rhythm pattern preset")
    trt.add_argument("--rhythm-spec", default="",
                     help="Custom rhythm: '-' normal, 'x' accent, '_' ghost, '=' legato, '.' rest")
    trt.add_argument("--tones", default="all",
                     choices=[t.value for t in ToneSelector],
                     help="Which chord tones to arpeggiate")
    trt.add_argument("--octave-mode", default="linear",
                     choices=[m.value for m in OctaveMode],
                     help="Octave spread behavior")
    trt.add_argument("--grace-notes", action="store_true",
                     help="Add grace notes on accented steps")
    trt.add_argument("--approach-notes", action="store_true",
                     help="Add chromatic approach into each chord")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # ---- Info-only commands ----
    if args.list_ports:
        _print_list("Available MIDI ports", MidiOutput.list_ports())
        return
    if args.list_presets:
        _print_list("Progression presets", sorted(
            list(PROGRESSION_PRESETS) + list(PROGRESSION_PRESETS_7TH)
        ))
        return

    rate_map = {"1/4": 1, "1/8": 2, "1/8T": 3, "1/16": 4, "1/32": 8}
    direction = PATTERN_DIRECTION_NAMES.get(args.direction, PatternDirection.UP_DOWN)

    config = ArpeggioConfig(
        scale_name=args.scale,
        root_note=args.root,
        octave=args.octave,
        direction=direction,
        octave_range=args.range,
        rate_divider=rate_map.get(args.rate, 4),
        gate=args.gate,
        swing=args.swing,
        num_steps=args.steps,
        velocity_min=args.velocity_min,
        velocity_max=args.velocity_max,
    )

    treatment = Treatment(
        rhythm_spec=_resolve_rhythm(args),
        tone_selector=ToneSelector(args.tones),
        octave_mode=OctaveMode(args.octave_mode),
        ornament=OrnamentConfig(
            grace_notes=args.grace_notes,
            approach_notes=args.approach_notes,
        ),
    )

    engine = ArpeggioEngine()

    # ---- Decide: progression or plain scale ----
    progression = _build_progression(args)

    if progression is not None:
        events = engine.generate_progression(progression, config, treatment)
        header = f" {progression.name} — {args.direction} — {args.bpm} BPM"
        detail = f"{len(progression)} chords → {len(events)} notes"
    else:
        events = engine.generate(config)
        header = f" {args.root} {args.scale} — {args.direction} — {args.bpm} BPM"
        detail = f"{len(events)} notes, {args.octave}O + {args.range} octaves"

    if not events:
        print("No notes generated!")
        return

    # ---- Preview ----
    print(f"\n{header}")
    print(f"   {detail}, {args.rate} rate")
    if progression is not None:
        print(f"   {' - '.join(s.chord.label for s in progression)}\n")
    else:
        print()

    notes_line = "  ".join(f"{e.note.name}{e.note.octave}" for e in events[:16])
    print(f"   {notes_line}")
    if len(events) > 16:
        print(f"   ... and {len(events) - 16} more")

    # ---- Output ----
    if args.save:
        MidiOutput().save_midi(events, args.save, args.bpm)
        print(f"\n Saved to {args.save}")
        return

    if args.preview:
        return

    _play(events, args)


def _print_list(title: str, items: list[str]):
    if items:
        print(f"{title}:")
        for item in items:
            print(f"  • {item}")
    else:
        print(f"No {title.lower()} found.")


def _resolve_rhythm(args) -> str:
    """Pick a rhythm spec from --rhythm preset or --rhythm-spec."""
    if args.rhythm_spec:
        return args.rhythm_spec
    if args.rhythm:
        return RHYTHM_PRESETS[args.rhythm]
    return "----------------"


def _build_progression(args):
    """Build a Progression from CLI args, if any were given."""
    if args.preset:
        scale = Scale(args.root, args.scale, args.octave)
        prog = get_preset(args.preset, scale)
        if prog is None:
            raise SystemExit(f"Unknown preset: {args.preset}")
    elif args.progression:
        scale = Scale(args.root, args.scale, args.octave)
        seventh = any(tok.endswith("7") for tok in args.progression.split())
        prog = parse_roman_progression(args.progression, scale, seventh=seventh)
    elif args.chords:
        prog = parse_chord_progression(args.chords)
    else:
        return None

    if not args.no_normalize:
        prog = normalize_octaves(prog, target_low=48, target_high=72)
    return prog


def _play(events, args):
    """Play events through MIDI output."""
    port_name = args.midi_port
    if not port_name:
        ports = MidiOutput.list_ports()
        if ports:
            port_name = ports[0]
            print(f"\n Using MIDI port: {port_name}")

    if not port_name:
        print("\n No MIDI output. Use --save or --preview.")
        return

    midi = MidiOutput(port_name)
    if not midi.is_connected:
        print(f"\n Could not open {port_name}")
        return

    print("\n▶ Playing... Press Ctrl+C to stop")
    try:
        midi.play(events, args.bpm)
        total = (events[-1].start_time * 60.0 / args.bpm +
                 events[-1].duration * 60.0 / args.bpm)
        time.sleep(total + 0.5)
    except KeyboardInterrupt:
        midi.stop()
        print("\n⏹ Stopped")


if __name__ == "__main__":
    main()
