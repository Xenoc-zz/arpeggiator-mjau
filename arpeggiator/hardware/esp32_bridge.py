"""
ESP32 bridge: sends/receives serial data to/from ESP32.
"""

from __future__ import annotations
import serial
import serial.tools.list_ports
import threading
import time
from typing import Optional, Callable


class ESP32Bridge:
    """Communicate with ESP32 over serial (USB/UART).

    Protocol (text-based, human-readable):
      PC → ESP32:
        NOTE:<midi_note>,<velocity>
        BPM:<bpm>
        DIRECTION:<up|down|up_down|...>
        SCALE:<name>
        RESET

      ESP32 → PC:
        POT:<value>        (0-4095)
        BTN:<pin>:<state>  (0 or 1)
        READY
    """

    def __init__(self, port: str = "", baud: int = 115200):
        self._port_name = port
        self._baud = baud
        self._ser: Optional[serial.Serial] = None
        self._connected = False
        self._read_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_pot = None
        self._on_button = None
        self._on_message = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ser is not None

    def connect(self) -> bool:
        """Connect to ESP32. Auto-detects port if none given."""
        port = self._port_name
        if not port:
            port = self._find_esp32_port()
        if not port:
            return False

        try:
            self._ser = serial.Serial(port, self._baud, timeout=0.1)
            self._connected = True
            self._running = True
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()
            # Wait for ready signal
            time.sleep(0.5)
            return True
        except (serial.SerialException, OSError) as e:
            print(f"⚠️  Could not connect to ESP32 on {port}: {e}")
            return False

    def disconnect(self):
        self._running = False
        self._connected = False
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def send_note(self, midi_note: int, velocity: int = 100):
        """Send a note to the ESP32 for LED display."""
        if self.is_connected:
            self._send(f"NOTE:{midi_note},{velocity}")

    def send_bpm(self, bpm: int):
        """Send current BPM."""
        if self.is_connected:
            self._send(f"BPM:{bpm}")

    def send_direction(self, direction: str):
        """Send current direction pattern."""
        if self.is_connected:
            self._send(f"DIRECTION:{direction}")

    def send_scale(self, scale: str):
        """Send current scale name."""
        if self.is_connected:
            self._send(f"SCALE:{scale}")

    def send_reset(self):
        """Reset the ESP32 LED display."""
        if self.is_connected:
            self._send("RESET")

    def on_pot(self, callback: Callable[[int], None]):
        """Register callback for potentiometer changes."""
        self._on_pot = callback

    def on_button(self, callback: Callable[[int, int], None]):
        """Register callback for button presses (pin, state)."""
        self._on_button = callback

    def on_message(self, callback: Callable[[str], None]):
        """Register callback for any raw message."""
        self._on_message = callback

    def _send(self, msg: str):
        try:
            self._ser.write(f"{msg}\n".encode())
        except Exception:
            self._connected = False

    def _read_loop(self):
        """Background thread reading from serial."""
        buf = ""
        while self._running and self._ser:
            try:
                data = self._ser.read(128)
                if data:
                    buf += data.decode(errors="replace")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line:
                            self._handle_message(line)
            except serial.SerialTimeoutException:
                pass
            except Exception:
                self._connected = False
                break
            time.sleep(0.005)

    def _handle_message(self, msg: str):
        if self._on_message:
            self._on_message(msg)

        if msg.startswith("POT:"):
            try:
                value = int(msg[4:])
                if self._on_pot:
                    self._on_pot(value)
            except ValueError:
                pass

        elif msg.startswith("BTN:"):
            try:
                parts = msg[4:].split(",")
                pin, state = int(parts[0]), int(parts[1])
                if self._on_button:
                    self._on_button(pin, state)
            except (ValueError, IndexError):
                pass

    @staticmethod
    def _find_esp32_port() -> Optional[str]:
        """Auto-detect ESP32 by USB vendor ID or description."""
        for port in serial.tools.list_ports.comports():
            desc = (port.description or "").lower()
            vid = port.vid or 0
            # Common ESP32 USB-serial chips: CP2102 (0x10C4), CH340 (0x1A86), FTDI (0x0403)
            if vid in (0x10C4, 0x1A86, 0x0403) or "cp210" in desc or "ch340" in desc or "ftdi" in desc:
                return port.device
            # Silabs / generic
            if "silicon labs" in desc or "usb serial" in desc:
                return port.device
        return None

    @staticmethod
    def list_ports() -> list[str]:
        return [p.device for p in serial.tools.list_ports.comports()]
