## Pico-Nunchuk — Version 2 (Dual-Profile)

> **This is the current release**, adding a second control profile to the original CAD-focused design.
> For the original single-profile version, see [Version 1](../Version%201/README.md).

Use a Wii Nunchuk as a USB HID input device via a Raspberry Pi Pico 2 W. Version 2 introduces two switchable control profiles — one for CAD work in TinkerCAD, and one for general browser/navigation use.

### Profile Switching

Hold **Button C for 2.5 seconds** to toggle between profiles. The active profile is printed to the serial console on switch.

---

### Profile 2 — Browser / Navigation (Default)

Optimised for browsing and general desktop navigation. Active on boot.

| Input | Action |
|-------|--------|
| Joystick Up/Down | Scroll Up / Down |
| Joystick Left | Alt+Left (Back) |
| Joystick Right | Alt+Right (Forward) |
| Button C (tap, Z not held) | Ctrl+Tab (next browser tab) |
| Button Z (hold) | Hold Alt (opens window switcher) |
| Button C (tap, while Z held) | Tab (cycle to next window in switcher) |
| Button Z (release after hold) | Release Alt (confirms window selection) |
| Button Z (tap) | Nothing |
| Hold C (2.5 s) | Switch to Profile 1 |

---

### Profile 1 — CAD

Optimised for 3D viewport navigation in TinkerCAD (and compatible CAD software).

| Input | Default | Button C Held | Button Z Held |
|-------|---------|---------------|---------------|
| Joystick Up/Down | Zoom In/Out (scroll) | Mouse Move + Left Click (drag) | Orbit Up/Down |
| Joystick Left/Right | Pan Left/Right | Mouse Move + Left Click (drag) | Orbit Left/Right |
| Button C (tap) | Keyboard "F" (Fit to View) | — | — |
| Button Z (tap) | Keyboard "D" (Drop to Workplane) | — | — |
| Hold C (2.5 s) | Switch to Profile 2 | | |

---

### Hardware

- Raspberry Pi Pico 2 W
- Wii Nunchuk
- Nunchuk Adapter (e.g. Keyes W11Chuck)

### Built With

- [CircuitPython](https://circuitpython.org/) — firmware platform
- [Adafruit CircuitPython Nunchuk](https://github.com/adafruit/Adafruit_CircuitPython_Nunchuk) — I2C Nunchuk driver
- [Adafruit CircuitPython HID](https://github.com/adafruit/Adafruit_CircuitPython_HID) — USB HID keyboard/mouse

### Setup

#### 1. Hardware Wiring

Connect the Keyes W11Chuck adapter to the Pico 2 W:

| Adapter Pin | Pico 2 W Pin | Pico 2 W Physical Pin |
|-------------|--------------|----------------------|
| DATA (SDA)  | GP4          | Pin 6                |
| CLOCK (SCL) | GP5          | Pin 7                |
| 3V3         | 3V3 (OUT)    | Pin 36               |
| GND         | GND          | Pin 38               |

No external pull-up resistors are needed — the adapter board includes them.

#### 2. Flash CircuitPython

1. Download the latest CircuitPython UF2 for **Raspberry Pi Pico 2 W** from:
   https://circuitpython.org/board/raspberry_pi_pico2_w/

2. Put the Pico 2 W into bootloader mode:
   - Hold the **BOOTSEL** button
   - Plug in the USB cable
   - Release the button after the drive appears

3. Drag the `.uf2` file onto the `RPI-RP2` drive

4. The board will reboot and a `CIRCUITPY` drive will appear

#### 3. Install Libraries

Download the **Adafruit CircuitPython Bundle** matching your CircuitPython version from:
https://circuitpython.org/libraries

Copy these to `CIRCUITPY/lib/`:
- `adafruit_nunchuk.mpy`
- `adafruit_hid/` (entire folder)
- `adafruit_bus_device/` (entire folder)

#### 4. Install Firmware

Copy from this directory to the `CIRCUITPY` drive:
- `code.py` → `CIRCUITPY/code.py`
- `boot.py` → `CIRCUITPY/boot.py`

The board will auto-reload after copying `code.py`.

#### 5. Verify

Open a serial console to see debug output:

```bash
screen /dev/ttyACM0 115200
```

Or use Mu Editor, Thonny, or any serial terminal. On startup you will see `Active profile: 2 (Browser/Navigation)`. Hold C for 2.5 seconds to switch profiles and confirm the switch message appears.

### Troubleshooting

- **CIRCUITPY drive doesn't appear**: Re-flash CircuitPython (Step 2)
- **ImportError for libraries**: Ensure all three library folders/files are in `lib/`
- **No Nunchuk detected**: Check wiring, ensure adapter is firmly connected to Nunchuk
- **I2C error**: Verify SDA→GP4 and SCL→GP5 connections

### License

This project is open source. See [LICENSE](LICENSE) for details.
