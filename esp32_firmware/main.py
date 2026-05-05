"""
ESP32 MicroPython Firmware — Arpeggiator LED Visualizer + Sensor Input

Connects to PC via serial (USB UART).
Receives NOTE/BPM/DIRECTION commands and drives WS2812B NeoPixels.
Sends POT/BTN sensor data back to PC.

Wiring:
  - NeoPixel data pin → GPIO 4  (configurable below)
  - Potentiometer (center pin) → GPIO 34 (ADC1_CH6)
  - Button (optional) → GPIO 0 (built-in BOOT button)
"""

# ============================================================
# CONFIGURATION
# ============================================================

NEOPIXEL_PIN = 4          # GPIO for NeoPixel data
NUM_LEDS = 16             # Number of LEDs in your strip/ring
POT_PIN = 34              # ADC pin for potentiometer
BTN_PIN = 0               # Button pin (optional, 0 = BOOT button on most boards)
SEND_INTERVAL_MS = 50     # How often to send sensor data to PC
LED_BRIGHTNESS = 80       # Max brightness (0-255)

# ============================================================
# IMPORTS
# ============================================================

import machine
import neopixel
import time
import math
import sys
import ubinascii

# ============================================================
# SETUP
# ============================================================

np = neopixel.NeoPixel(machine.Pin(NEOPIXEL_PIN), NUM_LEDS)
pot = machine.ADC(machine.Pin(POT_PIN))
pot.atten(machine.ADC.ATTN_11DB)  # 0-3.3V range

btn = machine.Pin(BTN_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# ============================================================
# STATE
# ============================================================

class ArpState:
    """Current arpeggio visualization state."""
    def __init__(self):
        self.notes = []           # List of (midi_note, velocity, time_received)
        self.bpm = 120
        self.direction = "up"
        self.scale = "Major"
        self.last_pot_value = -1
        self.last_btn_state = 1
        self.mode = "notes"       # "notes", "bpm", "direction"

state = ArpState()

# ============================================================
# LED EFFECTS
# ============================================================

def hsv_to_rgb(h, s, v):
    """HSV (0-360, 0-1, 0-1) → RGB (0-255)."""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c

    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)


def midi_to_led_index(midi_note):
    """Map a MIDI note number to an LED index.
    
    Uses the note's pitch class (C=0, C#=1, ... B=11) to
    determine position on the LED ring.
    """
    pitch_class = midi_note % 12
    # Spread 12 pitch classes across NUM_LEDS
    return (pitch_class * NUM_LEDS) // 12


def midi_to_color(midi_note, velocity=100):
    """Map MIDI note + velocity to an RGB color.
    
    Note pitch → hue (C=red, E=green, G#=blue, etc.)
    Velocity → brightness
    """
    pitch_class = midi_note % 12
    hue = (pitch_class / 12) * 360
    saturation = 0.9
    value = velocity / 127 * LED_BRIGHTNESS / 255
    value = max(0.05, min(1.0, value))
    return hsv_to_rgb(hue, saturation, value)


def render_note_mode():
    """Render active notes on the LED strip.
    
    Notes fade out over time. Each note lights up its
    pitch-class position with note color.
    """
    np.fill((0, 0, 0))
    now = time.ticks_ms()
    active_leds = {}

    for midi_note, velocity, received in state.notes:
        age = time.ticks_diff(now, received)
        # Notes fade out over 500ms
        if age > 500:
            continue

        idx = midi_to_led_index(midi_note)
        r, g, b = midi_to_color(midi_note, velocity)
        fade = 1.0 - (age / 500)
        r = int(r * fade)
        g = int(g * fade)
        b = int(b * fade)

        # Combine overlapping notes (take brightest)
        if idx in active_leds:
            old_r, old_g, old_b = active_leds[idx]
            brightness = r + g + b
            old_brightness = old_r + old_g + old_b
            if brightness > old_brightness:
                active_leds[idx] = (r, g, b)
        else:
            active_leds[idx] = (r, g, b)

    for idx, (r, g, b) in active_leds.items():
        np[idx] = (r, g, b)

    np.write()


def render_bpm_mode():
    """Render BPM as a rotating pulse around the LED ring."""
    now = time.ticks_ms()
    beat_ms = 60000 // state.bpm
    progress = (now % beat_ms) / beat_ms

    # One bright LED rotates, with a trail
    for i in range(NUM_LEDS):
        led_progress = i / NUM_LEDS
        dist = abs(progress - led_progress)
        if dist > 0.5:
            dist = 1.0 - dist
        brightness = max(0, 1.0 - dist * 6)  # Trail length
        brightness = brightness * brightness * LED_BRIGHTNESS  # Quadratic fade
        np[i] = (int(brightness), int(brightness * 0.3), int(brightness * 0.1))

    np.write()


def render_direction_mode():
    """Visualize the direction pattern as LED animations."""
    patterns = {
        "up": _render_up,
        "down": _render_down,
        "up_down": _render_up_down,
        "random": _render_random,
    }
    render_fn = patterns.get(state.direction, _render_up)
    render_fn()


def _render_up():
    """Chase from bottom to top."""
    now = time.ticks_ms()
    speed = max(50, 500 - state.bpm)
    pos = (now // speed) % NUM_LEDS
    _render_chase(pos)


def _render_down():
    """Chase from top to bottom."""
    now = time.ticks_ms()
    speed = max(50, 500 - state.bpm)
    pos = NUM_LEDS - 1 - ((now // speed) % NUM_LEDS)
    _render_chase(pos)


def _render_up_down():
    """Ping-pong chase."""
    now = time.ticks_ms()
    speed = max(50, 500 - state.bpm)
    total_steps = NUM_LEDS * 2 - 2
    step = (now // speed) % total_steps
    if step < NUM_LEDS:
        pos = step
    else:
        pos = total_steps - step
    _render_chase(pos)


def _render_random():
    """Random sparkles."""
    now = time.ticks_ms()
    for i in range(NUM_LEDS):
        val = (machine.time_pulse_us(machine.Pin(4), 1, 10) or 0) % 100
        if val < 5:  # ~5% chance of sparkle
            np[i] = (LED_BRIGHTNESS, LED_BRIGHTNESS, LED_BRIGHTNESS)
        else:
            np[i] = (0, 0, 0)
    np.write()


def _render_chase(pos):
    """Render a chase effect at position pos."""
    for i in range(NUM_LEDS):
        d = abs(i - pos)
        if d == 0:
            brightness = LED_BRIGHTNESS
        elif d == 1:
            brightness = LED_BRIGHTNESS // 3
        elif d == 2:
            brightness = LED_BRIGHTNESS // 8
        else:
            brightness = 0
        np[i] = (brightness, 0, 0)
    np.write()


# ============================================================
# SERIAL COMMANDS
# ============================================================

def handle_command(cmd):
    """Parse and handle a command from the PC."""
    cmd = cmd.strip()
    if not cmd:
        return

    if cmd.startswith("NOTE:"):
        # Format: NOTE:<midi>,<velocity>
        try:
            parts = cmd[5:].split(",")
            midi = int(parts[0])
            vel = int(parts[1]) if len(parts) > 1 else 100
            state.notes.append((midi, vel, time.ticks_ms()))
            # Keep only recent notes (last 50)
            if len(state.notes) > 50:
                state.notes = state.notes[-50:]
        except (ValueError, IndexError):
            pass

    elif cmd.startswith("BPM:"):
        try:
            state.bpm = max(20, min(300, int(cmd[4:])))
        except ValueError:
            pass

    elif cmd.startswith("DIRECTION:"):
        state.direction = cmd[10:].strip().lower()

    elif cmd.startswith("SCALE:"):
        state.scale = cmd[6:].strip()

    elif cmd == "RESET":
        state.notes.clear()
        np.fill((0, 0, 0))
        np.write()

    elif cmd == "MODE:NOTES":
        state.mode = "notes"
    elif cmd == "MODE:BPM":
        state.mode = "bpm"
    elif cmd == "MODE:DIRECTION":
        state.mode = "direction"


# ============================================================
# SENSOR READING
# ============================================================

def read_sensors():
    """Read sensors and send data to PC."""
    global state

    # Read potentiometer
    pot_val = pot.read()
    if abs(pot_val - state.last_pot_value) > 5:  # Debounce threshold
        state.last_pot_value = pot_val
        print(f"POT:{pot_val}")

    # Read button
    btn_state = btn.value()
    if btn_state != state.last_btn_state:
        state.last_btn_state = btn_state
        print(f"BTN:{BTN_PIN}:{btn_state}")

        # Single press toggles display mode
        if btn_state == 0:  # Pressed (active low)
            modes = ["notes", "bpm", "direction"]
            idx = (modes.index(state.mode) + 1) % len(modes)
            state.mode = modes[idx]


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    """Main firmware loop."""
    print("ARPEGGIATOR_ESP32_READY")
    sys.stdout.flush()

    last_sensor_time = time.ticks_ms()
    last_render_time = time.ticks_ms()

    while True:
        # --- Handle incoming serial commands ---
        if sys.stdin.buffer.any():
            try:
                line = sys.stdin.readline()
                if line:
                    handle_command(line)
            except Exception:
                pass

        # --- Send sensor data ---
        now = time.ticks_ms()
        if time.ticks_diff(now, last_sensor_time) >= SEND_INTERVAL_MS:
            read_sensors()
            last_sensor_time = now

        # --- Render LEDs ---
        if time.ticks_diff(now, last_render_time) >= 20:  # ~50fps
            if state.mode == "notes":
                render_note_mode()
            elif state.mode == "bpm":
                render_bpm_mode()
            elif state.mode == "direction":
                render_direction_mode()
            last_render_time = now

        # Small yield for background tasks
        time.sleep_ms(5)


if __name__ == "__main__":
    main()
