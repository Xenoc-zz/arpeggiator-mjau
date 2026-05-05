"""
ESP32 boot.py — runs on startup to configure pins and WiFi (if needed).
For the arpeggiator visualizer, we just need serial + NeoPixels.
"""

import machine
import esp
import os

# Set CPU frequency to 240MHz for smooth LED animations
machine.freq(240000000)

# Disable debug output on GPIO pins for better performance
esp.osdebug(None)

# Run the main firmware
import main
