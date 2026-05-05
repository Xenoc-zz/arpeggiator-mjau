# 🎹 Arpeggiator Mjau 🐶

A Python MIDI arpeggiator with scales, modes, and patterns.
Works as a **standalone app**, **CLI tool**, or **importable module**.

## Features

- **18+ scales & modes** — Major, Minor, Dorian, Phrygian, Blues, Pentatonic, Whole Tone, Diminished...
- **8 direction patterns** — Up, Down, Up & Down, Random, Random Walk, Chord, Ordered Up
- **Real MIDI output** — Send to any connected MIDI device via `mido` + `python-rtmidi`
- **Save/load presets** — JSON-based preset system
- **Save to MIDI file** — Standard `.mid` files
- **Swing, Gate, Humanize** controls
- **GUI** — tkinter-based (no extra deps!)
- **CLI** — Full featured command line interface

## Quick Start

```bash
cd arpeggiator

# Run the GUI
uv run arpeggiator-gui

# Preview notes from CLI
uv run arpeggiator --preview --scale "Dorian" --root D --direction "Up & Down" --range 2

# Save to MIDI file
uv run arpeggiator --scale "Blues" --root A --direction "Random Walk" --save blues_arpeggio.mid

# List MIDI ports
uv run arpeggiator --list-ports

# Play via MIDI
uv run arpeggiator --scale "Harmonic Minor" --root A --bpm 140
```

## Project Structure

```
arpeggiator/
├── arpeggiator/
│   ├── core/
│   │   ├── music_theory.py    # Notes, scales, modes
│   │   ├── arpeggio_engine.py # Pattern generation
│   │   └── midi_out.py        # MIDI + file output
│   ├── gui/
│   │   └── app.py             # tkinter GUI
│   └── cli/
│       └── main.py            # CLI interface
├── pyproject.toml
└── README.md
```

## Presets

Presets are saved to `~/.arpeggiator_presets/` as JSON files.
Use the GUI's Presets tab or save/load from CLI.
