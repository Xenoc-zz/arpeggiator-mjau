"""
Arpeggiator GUI — built with tkinter (no extra deps).

Standalone app with:
  - Scale / root note / octave selector
  - Direction pattern selector
  - Octave range
  - BPM / swing / gate controls
  - MIDI output port selector
  - Play / Stop / Save MIDI
  - Save / Load presets (JSON)
"""

from __future__ import annotations
import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from ..core.music_theory import (
    SCALE_PATTERNS, SCALE_DESCRIPTIONS, CHROMATIC_NOTES, NOTE_TO_SEMITONE,
)
from ..core.arpeggio_engine import (
    ArpeggioEngine, ArpeggioConfig, ArpeggioEvent,
    PatternDirection, PATTERN_DIRECTION_NAMES,
)
from ..core.midi_out import MidiOutput


PRESET_DIR = os.path.expanduser("~/.arpeggiator_presets")


class ArpeggiatorGUI:
    """Main GUI application."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🎹 Arpeggiator Mjau")
        self.root.geometry("780x640")
        self.root.minsize(640, 520)

        # State
        self.engine = ArpeggioEngine()
        self.midi_out = MidiOutput()
        self.current_events: list[ArpeggioEvent] = []
        self.is_playing = False
        self.preset_dir = PRESET_DIR
        os.makedirs(self.preset_dir, exist_ok=True)

        # Build UI
        self._build_ui()
        self._refresh_midi_ports()
        self._update_preview()

        # Key bindings
        self.root.bind("<space>", lambda e: self._toggle_play())
        self.root.bind("<Control-s>", lambda e: self._save_preset())
        self.root.bind("<Control-o>", lambda e: self._load_preset())

    def run(self):
        self.root.mainloop()

    # ------------------------------------------------------------------
    # UI BUILD
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Main container with padding
        main = ttk.Frame(self.root, padding="12")
        main.pack(fill=tk.BOTH, expand=True)

        # -- Top: Title --
        title = ttk.Label(main, text="🎹 Arpeggiator Mjau 🐶",
                          font=("Helvetica", 18, "bold"))
        title.pack(pady=(0, 12))

        # -- Notebook for tabs --
        nb = ttk.Notebook(main)
        nb.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Controls
        controls_frame = ttk.Frame(nb, padding="10")
        nb.add(controls_frame, text="🎛 Controls")
        self._build_controls_tab(controls_frame)

        # Tab 2: Presets
        presets_frame = ttk.Frame(nb, padding="10")
        nb.add(presets_frame, text="💾 Presets")
        self._build_presets_tab(presets_frame)

        # -- Bottom: Preview + Transport --
        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X, pady=(8, 0))

        # Preview
        preview_frame = ttk.LabelFrame(bottom, text="Preview", padding="6")
        preview_frame.pack(fill=tk.X, pady=(0, 6))

        self.preview_text = tk.Text(preview_frame, height=4,
                                     font=("Courier", 10),
                                     wrap=tk.WORD, state=tk.DISABLED)
        self.preview_text.pack(fill=tk.X)

        # Transport
        transport = ttk.Frame(bottom)
        transport.pack(fill=tk.X)

        self.play_btn = ttk.Button(transport, text="▶ Play",
                                    command=self._toggle_play, width=12)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = ttk.Button(transport, text="⏹ Stop",
                                    command=self._stop, width=12)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(transport, text="💾 Save MIDI",
                   command=self._save_midi, width=12).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(transport, text="▶ Send to MIDI Out",
                   command=self._play_midi, width=16).pack(side=tk.LEFT, padx=(0, 6))

        self.status_var = tk.StringVar(value="Ready 🐶")
        status = ttk.Label(transport, textvariable=self.status_var,
                           font=("Helvetica", 9))
        status.pack(side=tk.RIGHT, padx=(6, 0))

    def _build_controls_tab(self, parent):
        """Build the controls tab with scale, pattern, rate settings."""
        # Use grid for layout
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        # ---- Row 0: Scale & Root ----
        ttk.Label(parent, text="Scale:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.scale_var = tk.StringVar(value="Major")
        scale_names = sorted(SCALE_PATTERNS.keys(),
                             key=lambda x: (x not in ("Major", "Natural Minor"), x))
        self.scale_combo = ttk.Combobox(parent, textvariable=self.scale_var,
                                         values=scale_names, state="readonly",
                                         width=20)
        self.scale_combo.grid(row=0, column=1, sticky=tk.EW, pady=3, padx=(0, 12))
        self.scale_combo.bind("<<ComboboxSelected>>", self._on_change)

        ttk.Label(parent, text="Root Note:").grid(row=0, column=2, sticky=tk.W, pady=3)
        self.root_var = tk.StringVar(value="C")
        self.root_combo = ttk.Combobox(parent, textvariable=self.root_var,
                                        values=CHROMATIC_NOTES, state="readonly",
                                        width=6)
        self.root_combo.grid(row=0, column=3, sticky=tk.W, pady=3)
        self.root_combo.bind("<<ComboboxSelected>>", self._on_change)

        # Scale description
        self.scale_desc_var = tk.StringVar(value=SCALE_DESCRIPTIONS.get("Major", ""))
        ttk.Label(parent, textvariable=self.scale_desc_var,
                  font=("Helvetica", 9, "italic")).grid(row=0, column=4, sticky=tk.W,
                                                        padx=(12, 0))

        # ---- Row 1: Octave & Range ----
        ttk.Label(parent, text="Octave:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.octave_var = tk.IntVar(value=3)
        ttk.Spinbox(parent, from_=1, to=7, textvariable=self.octave_var,
                    width=5, command=self._on_change).grid(row=1, column=1, sticky=tk.W, pady=3)

        ttk.Label(parent, text="Octave Range:").grid(row=1, column=2, sticky=tk.W, pady=3)
        self.range_var = tk.IntVar(value=2)
        ttk.Spinbox(parent, from_=1, to=4, textvariable=self.range_var,
                    width=5, command=self._on_change).grid(row=1, column=3, sticky=tk.W, pady=3)

        # ---- Row 2: Direction ----
        ttk.Label(parent, text="Direction:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.dir_var = tk.StringVar(value="Up & Down")
        dir_names = list(PATTERN_DIRECTION_NAMES.keys())
        self.dir_combo = ttk.Combobox(parent, textvariable=self.dir_var,
                                       values=dir_names, state="readonly",
                                       width=16)
        self.dir_combo.grid(row=2, column=1, sticky=tk.W, pady=3)
        self.dir_combo.bind("<<ComboboxSelected>>", self._on_change)

        # ---- Row 3: BPM ----
        ttk.Label(parent, text="BPM:").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.bpm_var = tk.IntVar(value=120)
        ttk.Spinbox(parent, from_=30, to=300, textvariable=self.bpm_var,
                    width=6, command=self._on_change).grid(row=3, column=1, sticky=tk.W, pady=3)

        ttk.Label(parent, text="Rate:").grid(row=3, column=2, sticky=tk.W, pady=3)
        self.rate_var = tk.StringVar(value="1/16")
        rate_names = ["1/4", "1/8", "1/8T", "1/16", "1/32"]
        ttk.Combobox(parent, textvariable=self.rate_var,
                     values=rate_names, state="readonly",
                     width=8).grid(row=3, column=3, sticky=tk.W, pady=3)
        # ... wait, rate_divider maps differently, let's bind

        # ---- Row 4: Swing & Gate ----
        ttk.Label(parent, text="Swing:").grid(row=4, column=0, sticky=tk.W, pady=3)
        self.swing_var = tk.DoubleVar(value=0.0)
        swing_scale = ttk.Scale(parent, from_=0.0, to=1.0,
                                 variable=self.swing_var, orient=tk.HORIZONTAL,
                                 command=self._on_change)
        swing_scale.grid(row=4, column=1, sticky=tk.EW, pady=3, padx=(0, 12))
        self.swing_label = ttk.Label(parent, text="0%")
        self.swing_label.grid(row=4, column=1, sticky=tk.E, pady=3)

        ttk.Label(parent, text="Gate:").grid(row=4, column=2, sticky=tk.W, pady=3)
        self.gate_var = tk.DoubleVar(value=0.8)
        gate_scale = ttk.Scale(parent, from_=0.1, to=1.0,
                                variable=self.gate_var, orient=tk.HORIZONTAL,
                                command=self._on_change)
        gate_scale.grid(row=4, column=3, sticky=tk.EW, pady=3)
        self.gate_label = ttk.Label(parent, text="80%")
        self.gate_label.grid(row=4, column=3, sticky=tk.E, pady=3)

        # ---- Row 5: Steps & Humanize ----
        ttk.Label(parent, text="Steps:").grid(row=5, column=0, sticky=tk.W, pady=3)
        self.steps_var = tk.IntVar(value=16)
        ttk.Spinbox(parent, from_=1, to=64, textvariable=self.steps_var,
                    width=6, command=self._on_change).grid(row=5, column=1, sticky=tk.W, pady=3)

        ttk.Label(parent, text="Humanize:").grid(row=5, column=2, sticky=tk.W, pady=3)
        self.humanize_var = tk.DoubleVar(value=0.0)
        ttk.Scale(parent, from_=0.0, to=0.1,
                  variable=self.humanize_var, orient=tk.HORIZONTAL,
                  command=self._on_change).grid(row=5, column=3, sticky=tk.EW, pady=3)

        # ---- Row 6: Velocity range ----
        ttk.Label(parent, text="Velocity:").grid(row=6, column=0, sticky=tk.W, pady=3)
        vel_frame = ttk.Frame(parent)
        vel_frame.grid(row=6, column=1, columnspan=3, sticky=tk.EW, pady=3)
        self.vel_min_var = tk.IntVar(value=60)
        self.vel_max_var = tk.IntVar(value=100)
        ttk.Scale(vel_frame, from_=1, to=127, variable=self.vel_min_var,
                  orient=tk.HORIZONTAL, command=self._on_change,
                  length=100).pack(side=tk.LEFT)
        self.vel_min_label = ttk.Label(vel_frame, text="60")
        self.vel_min_label.pack(side=tk.LEFT, padx=2)
        ttk.Label(vel_frame, text="→").pack(side=tk.LEFT, padx=4)
        ttk.Scale(vel_frame, from_=1, to=127, variable=self.vel_max_var,
                  orient=tk.HORIZONTAL, command=self._on_change,
                  length=100).pack(side=tk.LEFT)
        self.vel_max_label = ttk.Label(vel_frame, text="100")
        self.vel_max_label.pack(side=tk.LEFT, padx=2)

        # ---- Row 7: MIDI Port ----
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=7, column=0,
                                                          columnspan=5, sticky=tk.EW,
                                                          pady=8)

        ttk.Label(parent, text="MIDI Out:").grid(row=8, column=0, sticky=tk.W, pady=3)
        self.midi_port_var = tk.StringVar(value="")
        self.midi_port_combo = ttk.Combobox(parent, textvariable=self.midi_port_var,
                                             state="readonly", width=30)
        self.midi_port_combo.grid(row=8, column=1, columnspan=3, sticky=tk.EW, pady=3)
        ttk.Button(parent, text="🔄 Refresh", command=self._refresh_midi_ports,
                   width=10).grid(row=8, column=4, padx=(6, 0))

    def _build_presets_tab(self, parent):
        """Build the presets tab."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        # Preset list
        self.preset_listbox = tk.Listbox(parent, font=("Courier", 11))
        self.preset_listbox.grid(row=0, column=0, sticky=tk.NSEW, pady=(0, 6))
        self.preset_listbox.bind("<Double-Button-1>", lambda e: self._load_selected_preset())
        self.preset_listbox.bind("<<ListboxSelect>>", self._on_preset_select)

        # Buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, sticky=tk.EW)

        ttk.Button(btn_frame, text="💾 Save Current",
                   command=self._save_preset).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="📂 Load Selected",
                   command=self._load_selected_preset).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="🗑 Delete",
                   command=self._delete_preset).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="🔄 Refresh",
                   command=self._refresh_presets).pack(side=tk.LEFT)

        self.preset_desc_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.preset_desc_var,
                  font=("Helvetica", 9, "italic")).grid(row=2, column=0, sticky=tk.W)

        self._refresh_presets()

    # ------------------------------------------------------------------
    # EVENTS
    # ------------------------------------------------------------------

    def _on_change(self, *args):
        """Called when any control changes."""
        self._update_labels()
        self._update_preview()

    def _update_labels(self):
        """Update value labels for sliders."""
        self.swing_label.config(text=f"{int(self.swing_var.get() * 100)}%")
        self.gate_label.config(text=f"{int(self.gate_var.get() * 100)}%")
        self.vel_min_label.config(text=str(self.vel_min_var.get()))
        self.vel_max_label.config(text=str(self.vel_max_var.get()))

        # Scale description
        scale_name = self.scale_var.get()
        self.scale_desc_var.set(SCALE_DESCRIPTIONS.get(scale_name, ""))

    def _get_config(self) -> ArpeggioConfig:
        """Build config from current UI state."""
        dir_name = self.dir_var.get()
        direction = PATTERN_DIRECTION_NAMES.get(dir_name, PatternDirection.UP_DOWN)

        # Rate mapping
        rate_map = {"1/4": 1, "1/8": 2, "1/8T": 3, "1/16": 4, "1/32": 8}

        return ArpeggioConfig(
            scale_name=self.scale_var.get(),
            root_note=self.root_var.get(),
            octave=self.octave_var.get(),
            direction=direction,
            octave_range=self.range_var.get(),
            rate_divider=rate_map.get(self.rate_var.get(), 4),
            gate=round(self.gate_var.get(), 2),
            swing=round(self.swing_var.get(), 2),
            num_steps=self.steps_var.get(),
            humanize=round(self.humanize_var.get(), 3),
            velocity_min=self.vel_min_var.get(),
            velocity_max=self.vel_max_var.get(),
        )

    def _update_preview(self):
        """Update the preview text with generated notes."""
        cfg = self._get_config()
        self.current_events = self.engine.generate(cfg)

        # Show first 3 lines of notes
        lines = []
        notes_per_line = 8
        for i in range(0, len(self.current_events), notes_per_line):
            chunk = self.current_events[i:i + notes_per_line]
            line = "  ".join(
                f"{e.note.name}{e.note.octave}".ljust(5)
                for e in chunk
            )
            lines.append(line)
            if len(lines) >= 3:
                break

        remaining = max(0, len(self.current_events) - 3 * notes_per_line)
        if remaining > 0:
            lines.append(f"  ... and {remaining} more notes")

        preview = "\n".join(lines) if lines else "(no notes)"

        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete(1.0, tk.END)
        self.preview_text.insert(1.0, preview)
        self.preview_text.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # TRANSPORT
    # ------------------------------------------------------------------

    def _toggle_play(self):
        if self.is_playing:
            self._stop()
        else:
            self._play_audio()

    def _play_audio(self):
        """Play via MIDI out."""
        if not self.midi_out.is_connected:
            port_name = self.midi_port_var.get()
            if port_name:
                self.midi_out = MidiOutput(port_name)
            else:
                messagebox.showwarning("No MIDI",
                    "No MIDI output connected.\nSave to MIDI file instead.")
                return

        events = self.current_events
        if not events:
            return

        bpm = self.bpm_var.get()
        self.midi_out.play(events, bpm)
        self.is_playing = True
        self.play_btn.config(text="⏸ Pause")
        self.status_var.set(f"▶ Playing {len(events)} notes @ {bpm} BPM")

    def _stop(self):
        self.midi_out.stop()
        self.is_playing = False
        self.play_btn.config(text="▶ Play")
        self.status_var.set("⏹ Stopped")

    def _play_midi(self):
        """Send to MIDI out (same as play)."""
        self._play_audio()

    def _save_midi(self):
        """Save to MIDI file."""
        if not self.current_events:
            messagebox.showinfo("Nothing to save", "Generate some notes first!")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".mid",
            filetypes=[("MIDI files", "*.mid"), ("All files", "*.*")],
            initialfile="arpeggio.mid",
        )
        if not filename:
            return

        try:
            bpm = self.bpm_var.get()
            self.midi_out.save_midi(self.current_events, filename, bpm)
            self.status_var.set(f"💾 Saved to {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # ------------------------------------------------------------------
    # MIDI PORTS
    # ------------------------------------------------------------------

    def _refresh_midi_ports(self):
        ports = MidiOutput.list_ports()
        self.midi_port_combo["values"] = ports
        if ports and not self.midi_port_var.get():
            self.midi_port_var.set(ports[0])

        # Update status
        if ports:
            self.status_var.set(f"🔌 MIDI ports: {len(ports)} available")
        else:
            self.status_var.set("🔇 No MIDI ports — save to file instead")

    # ------------------------------------------------------------------
    # PRESETS
    # ------------------------------------------------------------------

    def _get_presets(self) -> list[dict]:
        """List all presets as dicts."""
        presets = []
        if not os.path.isdir(self.preset_dir):
            return presets
        for fname in sorted(os.listdir(self.preset_dir)):
            if fname.endswith(".json"):
                path = os.path.join(self.preset_dir, fname)
                try:
                    with open(path) as f:
                        data = json.load(f)
                    data["_file"] = fname
                    data["_name"] = fname[:-5]
                    presets.append(data)
                except (json.JSONDecodeError, OSError):
                    pass
        return presets

    def _refresh_presets(self):
        self.preset_listbox.delete(0, tk.END)
        for p in self._get_presets():
            name = p.get("_name", "?")
            scale = p.get("scale_name", "?")
            root = p.get("root_note", "?")
            direction = p.get("direction", "?")
            self.preset_listbox.insert(tk.END,
                                       f"{name:20s}  {root} {scale:15s}  {direction}")

    def _save_preset(self, *args):
        """Save current config as a preset."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Save Preset")
        dialog.geometry("360x120")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Preset name:", padding=(12, 12, 0, 0)).pack(anchor=tk.W)
        name_var = tk.StringVar(value=self.scale_var.get().lower().replace(" ", "_"))
        entry = ttk.Entry(dialog, textvariable=name_var, width=40)
        entry.pack(padx=12, pady=(4, 8), fill=tk.X)
        entry.select_range(0, tk.END)
        entry.focus()

        def do_save():
            name = name_var.get().strip()
            if not name:
                return
            cfg = self._get_config()
            data = {
                "scale_name": cfg.scale_name,
                "root_note": cfg.root_note,
                "octave": cfg.octave,
                "direction": cfg.direction.value,
                "octave_range": cfg.octave_range,
                "rate_divider": cfg.rate_divider,
                "gate": cfg.gate,
                "swing": cfg.swing,
                "num_steps": cfg.num_steps,
                "humanize": cfg.humanize,
                "velocity_min": cfg.velocity_min,
                "velocity_max": cfg.velocity_max,
            }
            path = os.path.join(self.preset_dir, f"{name}.json")
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            self._refresh_presets()
            self.status_var.set(f"💾 Saved preset: {name}")
            dialog.destroy()

        ttk.Button(dialog, text="Save", command=do_save).pack(pady=(0, 12))
        dialog.bind("<Return>", lambda e: do_save())

    def _load_preset(self, *args):
        """Load preset from file via file dialog."""
        path = filedialog.askopenfilename(
            initialdir=self.preset_dir,
            filetypes=[("Preset files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self._apply_preset(data)
            self.status_var.set(f"📂 Loaded: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    def _load_selected_preset(self):
        selection = self.preset_listbox.curselection()
        if not selection:
            return
        presets = self._get_presets()
        idx = selection[0]
        if idx >= len(presets):
            return
        data = presets[idx]
        try:
            with open(os.path.join(self.preset_dir, data["_file"])) as f:
                self._apply_preset(json.load(f))
            self.status_var.set(f"📂 Loaded: {data['_name']}")
        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    def _on_preset_select(self, *args):
        selection = self.preset_listbox.curselection()
        if not selection:
            return
        presets = self._get_presets()
        idx = selection[0]
        if idx < len(presets):
            p = presets[idx]
            desc = f"{p.get('root_note', '?')} {p.get('scale_name', '?')} — {p.get('direction', '?')} — {p.get('num_steps', '?')} steps"
            self.preset_desc_var.set(desc)

    def _delete_preset(self):
        selection = self.preset_listbox.curselection()
        if not selection:
            return
        presets = self._get_presets()
        idx = selection[0]
        if idx >= len(presets):
            return
        data = presets[idx]
        name = data["_name"]
        if messagebox.askyesno("Delete", f"Delete preset '{name}'?"):
            path = os.path.join(self.preset_dir, data["_file"])
            try:
                os.remove(path)
                self._refresh_presets()
                self.status_var.set(f"🗑 Deleted: {name}")
            except OSError as e:
                messagebox.showerror("Error", str(e))

    def _apply_preset(self, data: dict):
        """Apply preset data to UI controls."""
        dir_reverse = {v.value: k for k, v in PATTERN_DIRECTION_NAMES.items()}
        rate_reverse = {1: "1/4", 2: "1/8", 3: "1/8T", 4: "1/16", 8: "1/32"}

        if "scale_name" in data:
            self.scale_var.set(data["scale_name"])
        if "root_note" in data:
            self.root_var.set(data["root_note"])
        if "octave" in data:
            self.octave_var.set(data["octave"])
        if "direction" in data:
            self.dir_var.set(dir_reverse.get(data["direction"], "Up & Down"))
        if "octave_range" in data:
            self.range_var.set(data["octave_range"])
        if "rate_divider" in data:
            self.rate_var.set(rate_reverse.get(data["rate_divider"], "1/16"))
        if "gate" in data:
            self.gate_var.set(data["gate"])
        if "swing" in data:
            self.swing_var.set(data["swing"])
        if "num_steps" in data:
            self.steps_var.set(data["num_steps"])
        if "humanize" in data:
            self.humanize_var.set(data["humanize"])
        if "velocity_min" in data:
            self.vel_min_var.set(data["velocity_min"])
        if "velocity_max" in data:
            self.vel_max_var.set(data["velocity_max"])

        self._on_change()


def main():
    app = ArpeggiatorGUI()
    app.run()


if __name__ == "__main__":
    main()
