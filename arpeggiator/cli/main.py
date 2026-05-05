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
from ..core.music_theory import SCALE_PATTERNS, CHROMATIC_NOTES


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

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # List ports?
    if args.list_ports:
        ports = MidiOutput.list_ports()
        if ports:
            print("Available MIDI ports:")
            for p in ports:
                print(f"  • {p}")
        else:
            print("No MIDI ports found.")
        return

    # Build config
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

    # Generate
    engine = ArpeggioEngine()
    events = engine.generate(config)

    if not events:
        print("No notes generated!")
        return

    # Preview
    print(f"\n🎹 {args.root} {args.scale} — {args.direction} — {args.bpm} BPM")
    print(f"   {len(events)} notes, {args.octave}O + {args.range} octaves, {args.rate} rate\n")

    notes_line = "  ".join(f"{e.note.name}{e.note.octave}" for e in events[:16])
    print(f"   {notes_line}")
    if len(events) > 16:
        print(f"   ... and {len(events) - 16} more")

    # Save to file?
    if args.save:
        midi = MidiOutput()
        midi.save_midi(events, args.save, args.bpm)
        print(f"\n💾 Saved to {args.save}")
        return

    # Preview only?
    if args.preview:
        return

    # Play via MIDI
    port_name = args.midi_port
    if not port_name:
        ports = MidiOutput.list_ports()
        if ports:
            port_name = ports[0]
            print(f"\n🔌 Using MIDI port: {port_name}")

    if port_name:
        midi = MidiOutput(port_name)
        if midi.is_connected:
            print(f"\n▶ Playing... Press Ctrl+C to stop")
            try:
                midi.play(events, args.bpm)
                # Wait for playback to finish
                total_time = (events[-1].start_time * 60.0 / args.bpm +
                              events[-1].duration * 60.0 / args.bpm)
                time.sleep(total_time + 0.5)
            except KeyboardInterrupt:
                midi.stop()
                print("\n⏹ Stopped")
            return

    print("\n❌ No MIDI output available. Use --save to write a file or --preview to see notes.")


if __name__ == "__main__":
    main()
