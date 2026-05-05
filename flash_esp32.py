#!/usr/bin/env python3
"""
Flash the ESP32 with the Arpeggiator LED firmware.

Prerequisites:
    pip install esptool adafruit-ampy

Usage:
    python flash_esp32.py               # Auto-detect and flash
    python flash_esp32.py --port /dev/ttyUSB0  # Specify port
    python flash_esp32.py --monitor     # Flash + open serial monitor
"""

import subprocess
import sys
import os
import time
import argparse


FIRMWARE_DIR = os.path.join(os.path.dirname(__file__), "esp32_firmware")
BOOT_PY = os.path.join(FIRMWARE_DIR, "boot.py")
MAIN_PY = os.path.join(FIRMWARE_DIR, "main.py")


def find_esptool():
    """Find esptool.py in path or common locations."""
    try:
        subprocess.run(["esptool.py", "--version"],
                       capture_output=True, check=True)
        return "esptool.py"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        subprocess.run(["esptool", "--version"],
                       capture_output=True, check=True)
        return "esptool"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def find_ampy():
    """Find ampy tool."""
    try:
        subprocess.run(["ampy", "--help"],
                       capture_output=True, check=True)
        return "ampy"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def detect_port():
    """Detect ESP32 port using esptool."""
    esptool = find_esptool()
    if not esptool:
        return None

    try:
        result = subprocess.run(
            [esptool, "--port", "list"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split("\n"):
            if any(x in line.lower() for x in
                   ["cp210", "ch340", "ftdi", "silicon labs",
                    "usb serial", "uart"]):
                return line.strip().split()[0]
    except Exception:
        pass

    # Try common ports
    for port in ["/dev/ttyUSB0", "/dev/ttyUSB1",
                 "/dev/ttyACM0", "/dev/ttyACM1",
                 "COM3", "COM4", "COM5"]:
        if os.path.exists(port):
            return port

    return None


def flash_esp32(port: str, baud: int = 115200):
    """Flash MicroPython firmware to ESP32."""
    print(f"🚀 Flashing ESP32 on {port}...")

    esptool = find_esptool()
    if not esptool:
        print("❌ esptool not found. Install with: pip install esptool")
        return False

    # Erase flash
    cmd = [esptool, "--port", port, "--baud", str(baud), "erase_flash"]
    print(f"   {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # Flash MicroPython
    # You'll need to download the firmware first
    firmware_url = "https://micropython.org/download/ESP32_GENERIC/"
    firmware_file = "ESP32_GENERIC-20231005-v1.21.0.bin"
    firmware_path = os.path.join(FIRMWARE_DIR, firmware_file)

    if not os.path.exists(firmware_path):
        print(f"\n⚠️  MicroPython firmware not found at {firmware_path}")
        print(f"   Download from: {firmware_url}")
        print(f"   Save as: {firmware_path}")
        print(f"   Then run: {sys.argv[0]} --port {port}")
        return False

    cmd = [
        esptool, "--port", port, "--baud", str(baud),
        "write_flash", "-z", "0x1000", firmware_path,
    ]
    print(f"   {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    return True


def upload_files(port: str):
    """Upload firmware files to ESP32."""
    print(f"📤 Uploading firmware to {port}...")

    ampy = find_ampy()
    if not ampy:
        print("❌ ampy not found. Install with: pip install adafruit-ampy")
        print("   Trying mpremote instead...")
        return upload_files_mpremote(port)

    for file_path, target in [(BOOT_PY, "boot.py"), (MAIN_PY, "main.py")]:
        if not os.path.exists(file_path):
            print(f"   ⚠️  {file_path} not found, skipping")
            continue
        cmd = [ampy, "--port", port, "put", file_path, target]
        print(f"   {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

    print("✅ Firmware uploaded!")
    return True


def upload_files_mpremote(port: str):
    """Upload firmware using mpremote (alternative to ampy)."""
    try:
        import mpremote
        # mpremote has a different API, let's use raw serial
        for file_path, target in [(BOOT_PY, "boot.py"), (MAIN_PY, "main.py")]:
            if not os.path.exists(file_path):
                continue
            cmd = [
                sys.executable, "-m", "mpremote",
                "connect", port,
                "fs", "cp", file_path, f":{target}",
            ]
            print(f"   {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
        return True
    except ImportError:
        print("❌ mpremote not available either.")
        print("   Try: pip install mpremote")
        print("   Then manually copy:")
        print(f"     mpremote connect {port} fs cp {BOOT_PY} :boot.py")
        print(f"     mpremote connect {port} fs cp {MAIN_PY} :main.py")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Flash Arpeggiator firmware to ESP32"
    )
    parser.add_argument("--port", "-p", default=None,
                        help="Serial port (auto-detect if not given)")
    parser.add_argument("--baud", "-b", type=int, default=115200,
                        help="Baud rate")
    parser.add_argument("--monitor", "-m", action="store_true",
                        help="Open serial monitor after flashing")
    parser.add_argument("--skip-flash", action="store_true",
                        help="Skip flashing firmware, just upload files")
    args = parser.parse_args()

    port = args.port or detect_port()
    if not port:
        print("❌ Could not detect ESP32 port.")
        print("   Specify with: --port /dev/ttyUSB0")
        sys.exit(1)

    print(f"🎯 Using port: {port}")

    if not args.skip_flash:
        if not flash_esp32(port, args.baud):
            print("   (continuing with file upload anyway...)")
        time.sleep(2)  # Wait for ESP32 to boot

    upload_files(port)
    time.sleep(1)

    # Reset ESP32
    print("🔄 Resetting ESP32...")
    try:
        import serial
        with serial.Serial(port, args.baud, timeout=1) as ser:
            ser.setDTR(False)
            time.sleep(0.1)
            ser.setDTR(True)
            time.sleep(0.1)
    except Exception:
        pass

    print("\n✅ Done! Your ESP32 should now be running the Arpeggiator firmware.")
    print(f"   Connect to it from the GUI (ESP32 tab) or CLI.")

    if args.monitor:
        print(f"\n📟 Opening serial monitor on {port}...")
        subprocess.run(["python3", "-m", "serial.tools.miniterm", port, str(args.baud)])


if __name__ == "__main__":
    main()
