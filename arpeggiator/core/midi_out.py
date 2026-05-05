"""
MIDI output: send arpeggios to real MIDI devices or save to files.
"""

from __future__ import annotations
from typing import Optional
import time
import threading

from .arpeggio_engine import ArpeggioEvent


class MidiOutput:
    """Handles MIDI output — both real-time and file-based."""

    def __init__(self, port_name: Optional[str] = None):
        self._port = None
        self._port_name = port_name
        self._playing = False
        self._thread: Optional[threading.Thread] = None
        self._events: list[ArpeggioEvent] = []
        self._bpm = 120
        self._open_port()

    def _open_port(self):
        """Open a MIDI output port."""
        try:
            import mido
            if self._port_name:
                self._port = mido.open_output(self._port_name)
            else:
                # Try to find the first available output
                outputs = mido.get_output_names()
                if outputs:
                    self._port = mido.open_output(outputs[0])
                    self._port_name = outputs[0]
        except (ImportError, OSError):
            self._port = None

    @property
    def is_connected(self) -> bool:
        return self._port is not None

    @property
    def port_name(self) -> Optional[str]:
        return self._port_name

    @staticmethod
    def list_ports() -> list[str]:
        """List available MIDI output ports."""
        try:
            import mido
            return mido.get_output_names()
        except ImportError:
            return []

    def play(self, events: list[ArpeggioEvent], bpm: int = 120):
        """Play arpeggio events in real-time (non-blocking)."""
        self.stop()
        self._events = list(events)
        self._bpm = bpm
        self._playing = True
        self._thread = threading.Thread(target=self._play_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop playback and send all notes off."""
        self._playing = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._all_notes_off()

    def _play_loop(self):
        """Background thread for real-time playback."""
        if not self._port:
            return

        import mido
        beat_duration = 60.0 / self._bpm

        # Sort events by start time
        sorted_events = sorted(self._events, key=lambda e: e.start_time)

        if not sorted_events:
            return

        # Track currently playing notes for note-off
        active_notes: dict[int, float] = {}

        start_time = time.time()
        total_duration = sorted_events[-1].start_time * beat_duration + \
                         sorted_events[-1].duration * beat_duration
        end_time = start_time + total_duration + 0.5

        idx = 0
        while self._playing and time.time() < end_time:
            now = time.time() - start_time

            # Send note-offs for expired notes
            expired = [n for n, off_time in active_notes.items()
                       if off_time <= now]
            for n in expired:
                self._port.send(mido.Message('note_off', note=n, velocity=0))
                del active_notes[n]

            # Send pending note-ons
            while idx < len(sorted_events):
                ev = sorted_events[idx]
                ev_time = ev.start_time * beat_duration
                if ev_time > now + 0.01:  # 10ms lookahead
                    break
                self._port.send(mido.Message(
                    'note_on',
                    note=ev.note.midi,
                    velocity=ev.velocity,
                ))
                active_notes[ev.note.midi] = ev_time + ev.duration * beat_duration
                idx += 1

            time.sleep(0.002)  # 2ms sleep to prevent busy-wait

        # Ensure all notes off
        self._all_notes_off()

    def _all_notes_off(self):
        if not self._port:
            return
        try:
            for ch in range(16):
                self._port.send(mido.Message('control_change',
                                              channel=ch,
                                              control=123,
                                              value=0))
        except Exception:
            pass

    def send_note(self, note: int, velocity: int = 100,
                  duration: float = 0.25, bpm: int = 120):
        """Send a single note (blocking)."""
        if not self._port:
            return
        import mido
        self._port.send(mido.Message('note_on', note=note, velocity=velocity))
        time.sleep(duration * 60.0 / bpm)
        self._port.send(mido.Message('note_off', note=note, velocity=0))

    def save_midi(self, events: list[ArpeggioEvent],
                  filename: str = "arpeggio.mid",
                  bpm: int = 120, track_name: str = "Arpeggiator"):
        """Save events to a standard MIDI file."""
        try:
            from midiutil import MIDIFile
        except ImportError:
            # Fallback: write a simple MIDI file manually
            return self._save_midi_simple(events, filename, bpm)

        midi = MIDIFile(1)
        midi.addTrackName(0, 0, track_name)
        midi.addTempo(0, 0, bpm)

        for ev in events:
            midi.addNote(
                0, 0,
                ev.note.midi,
                ev.start_time,
                ev.duration,
                ev.velocity,
            )

        with open(filename, "wb") as f:
            midi.writeFile(f)

    def _save_midi_simple(self, events: list[ArpeggioEvent],
                          filename: str, bpm: int):
        """Write a minimal MIDI file without midiutil."""
        # MIDI file header + track
        ticks_per_beat = 480
        tempo = 60_000_000 // bpm

        track_events = bytearray()
        # Tempo event
        track_events.extend([
            0x00, 0xFF, 0x51, 0x03,
            (tempo >> 16) & 0xFF,
            (tempo >> 8) & 0xFF,
            tempo & 0xFF,
        ])

        for ev in sorted(events, key=lambda e: e.start_time):
            ticks = int(ev.start_time * ticks_per_beat)
            dur_ticks = max(1, int(ev.duration * ticks_per_beat))

            # Delta time (variable length)
            self._write_var_len(track_events, ticks)
            track_events.extend([0x90, ev.note.midi, ev.velocity])  # note on

            self._write_var_len(track_events, dur_ticks)
            track_events.extend([0x80, ev.note.midi, 0x00])  # note off

        # End of track
        track_events.extend([0x00, 0xFF, 0x2F, 0x00])

        # Build full MIDI file
        data = bytearray([
            0x4D, 0x54, 0x68, 0x64,  # MThd
            0x00, 0x00, 0x00, 0x06,  # header length
            0x00, 0x01,              # format 1
            0x00, 0x01,              # 1 track
            (ticks_per_beat >> 8) & 0xFF,
            ticks_per_beat & 0xFF,
            0x4D, 0x54, 0x72, 0x6B,  # MTrk
        ])
        # Track length
        track_len = len(track_events)
        data.extend([
            (track_len >> 24) & 0xFF,
            (track_len >> 16) & 0xFF,
            (track_len >> 8) & 0xFF,
            track_len & 0xFF,
        ])
        data.extend(track_events)

        with open(filename, "wb") as f:
            f.write(data)

    @staticmethod
    def _write_var_len(buf: bytearray, value: int):
        """Write a variable-length value to buffer."""
        if value < 0:
            value = 0
        v = value & 0x7F
        while value > 0x7F:
            value >>= 7
            v = (v << 8) | ((value & 0x7F) | 0x80)
        # Now write in correct order
        result = []
        while v > 0x7F:
            result.append(v & 0xFF)
            v >>= 8
        result.append(v)
        for b in reversed(result):
            buf.append(b)
