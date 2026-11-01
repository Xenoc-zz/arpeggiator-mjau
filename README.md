# 🎹 Arpeggiator Mjau 🐶

A Python MIDI arpeggiator with scales, modes, and patterns.
Works as a **standalone app**, **CLI tool**, or **importable module**.

## Features

### Music theory
- **18+ scales & modes** — Major, Minor, Dorian, Phrygian, Blues, Pentatonic, Whole Tone, Diminished...
- **30+ chord qualities** — triads, 7ths, 9ths, 11ths, 13ths, sus, dim, aug, altered
- **Diatonic harmony** — auto-derive I-ii-iii-IV-V-vi-vii from any scale
- **Roman-numeral progressions** — write `ii7 V7 I7` and it builds Dm7-G7-Cmaj7
- **Explicit chords** — write `Cmaj7 Am7 Dm7 G7` directly
- **12 progression presets** — Pop, Jazz, Andalusian, Canon, Blues, minor rock...

### Arpeggio engine
- **9 direction patterns** — Up, Down, Up & Down, Down & Up, Random, Random Walk,
  Chord, Ordered Up, Block
- **Global pattern across progressions** — the pattern locks, chord tones shift
- **Rhythm patterns** — gallop, tresillo, clave, breakbeat, triplet swing, or custom
  using `-` (normal), `x` (accent), `_` (ghost), `=` (legato), `.` (rest)
- **Chord-tone selection** — all, root only, no 5th, shell voicings, top tones
- **Octave modes** — linear, octave-up, root-bass, expanding, converging
- **Ornaments** — grace notes, chromatic approach notes
- **Dynamics** — accent shaping, humanize jitter, velocity arch

### I/O
- **Real MIDI output** — any device via `mido` + `python-rtmidi`
- **MIDI input** — read chords live from a controller (e.g. AKAI MPK261)
- **MIDI file save** — standard `.mid`
- **ESP32 bridge** — NeoPixel LED visualizer + sensor input

### Performance
- **ProgressionPlayer** — loops a progression with beat-accurate timing
- **Live swaps** — change progression mid-performance, quantized to the loop
  boundary so it never lands mid-chord
- **Callbacks** — `on_chord`, `on_loop`, `on_swap`, plus beat listeners
  for UI/ESP32 sync

### Interfaces
- **GUI** — tkinter (no extra deps)
- **CLI** — full-featured with preview, save, play
- **Live CLI** — interactive loop mode with hot-swapping
- **Library** — import `arpeggiator.core`, everything is pure data

## Quick Start

```bash
cd arpeggiator

# Run the GUI
uv run arpeggiator-gui

# Plain scale arpeggio (classic mode)
uv run arpeggiator --preview --scale Dorian --root D --direction "Up & Down"

# Chord progression, roman numerals
uv run arpeggiator --progression "ii7 V7 I7" --root C --tones shell --preview

# Chord progression, explicit chords + gallop rhythm
uv run arpeggiator --chords "Cmaj7 Am7 Dm7 G7" --rhythm Gallop --preview

# With ornaments, save to file
uv run arpeggiator --preset "i-VII-VI-VII (Andalusian)" --root A \
    --scale "Natural Minor" --approach-notes --save andalusian.mid

# List everything available
uv run arpeggiator --list-presets
uv run arpeggiator --list-ports
```

## Live Loop Mode

Loop a progression and swap it while it plays — changes are quantized to the
loop boundary, so they never land in the middle of a chord.

```bash
uv run arpeggiator-live --preset "ii7-V7-I7 (Jazz)" --root C --bpm 120 --tones shell
```

While running:

| Type | Effect |
|------|--------|
| `1`..`9` | swap to preset N |
| `g I V vi IV` | swap to a roman-numeral progression |
| `c Dm7 G7 Cmaj7` | swap to explicit chords |
| `b 140` | change tempo |
| `s global` | switch pattern scope live |
| `d up_down` | change direction |
| `q` | quit |

Programmatically:

```python
from arpeggiator.core import ProgressionPlayer

player = ProgressionPlayer(midi_output=midi)
player.bpm = 120
player.load(progression, config, treatment)
player.on_chord = lambda idx, chord, t: print(chord.label)
player.start()
player.queue_next(other_progression)   # swaps at next loop boundary
player.stop()
```

## CLI Reference

### Progressions
| Flag | Meaning |
|------|---------|
| `--progression, -g` | Roman numerals: `"I V vi IV"` |
| `--chords, -c` | Explicit: `"Cmaj7 Am7 Dm7 G7"` |
| `--preset, -k` | Named preset (see `--list-presets`) |
| `--no-normalize` | Keep original chord octaves |

### Treatments
| Flag | Meaning |
|------|---------|
| `--rhythm` | Rhythm preset name |
| `--rhythm-spec` | Custom: `"x-.-x---x-.-x---"` |
| `--tones` | `all`, `shell`, `no_fifth`, `root`, `root_5`, `top_tones` |
| `--octave-mode` | `linear`, `octave_up`, `root_bass`, `expanding`, `converging` |
| `--grace-notes` | Grace notes on accented steps |
| `--approach-notes` | Chromatic lead-in into each chord |
| `--scope` | `per_chord` (default) or `global` |

### Pattern scope: which one do I want?

| | `per_chord` (default) | `global` |
|---|---|---|
| Every chord starts on its root | yes | no |
| Harmonic changes audible | clearly | camouflaged |
| Continuity / hypnotic groove | resets per chord | continuous |
| Good for | jazz, pop, most music | trance, minimalism, ostinato |

Example (`ii7 V7 I7`, up & down, one note per chord):

```
per_chord:  D3  G3  C3     <- each chord announces itself
 global:    D3  B3  G3     <- pattern continues across changes
```

Any chord can also override the global settings individually:

```python
from arpeggiator.core import ProgressionStep, ChordOverride

ProgressionStep(chord, 4.0, ChordOverride(
    direction="down", tone_selector="shell", velocity_boost=20,
))
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
