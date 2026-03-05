"""
Pico-Nunchuk: Wii Nunchuk to USB HID (Mouse + Keyboard) for TinkerCAD
Runs on Raspberry Pi Pico 2 W with CircuitPython

Profiles:
  Profile 2 (default) — Browser / Navigation controls
  Profile 1           — CAD controls (TinkerCAD)
  Toggle: Hold C for 2.5 seconds to switch between profiles.
"""

import time
import board
import busio
import digitalio
import usb_hid
import adafruit_nunchuk
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.mouse import Mouse

# --- Configuration ---

# I2C pins (GP4=SDA, GP5=SCL)
I2C_SDA = board.GP4
I2C_SCL = board.GP5

# Joystick settings
JOY_CENTER = 128
JOY_DEADZONE = 25  # Ignore values within center ± deadzone

# Joystick-to-mouse sensitivity (pixels per tick at max deflection)
MOUSE_SENSITIVITY = 15

# Joystick-to-scroll speed: divider for scroll wheel (higher = slower scroll)
SCROLL_DIVIDER = 40       # Profile 1 (CAD)

# Profile 2 scroll: divider and cooldown work together for smooth, slower scrolling
SCROLL_DIVIDER_P2 = 80     # step size divider (higher = smaller steps)
SCROLL_COOLDOWN_P2 = 0.05  # seconds between events (lower = smoother)

# Orbit sensitivity (Z held + joystick)
ORBIT_SENSITIVITY = 12  # Mouse pixels per tick for orbit movement

# Button tap detection
TAP_MAX_DURATION = 0.3  # Max seconds for a press to count as a tap

# Profile switch: hold C this long to toggle between profiles
# Must be greater than TAP_MAX_DURATION or hold_start fires before the switch
PROFILE_SWITCH_DURATION = 2.5  # seconds
assert TAP_MAX_DURATION < PROFILE_SWITCH_DURATION, \
    "TAP_MAX_DURATION must be less than PROFILE_SWITCH_DURATION"

# Main loop timing
LOOP_DELAY = 0.01  # 100Hz update rate

# --- State tracking ---

class ButtonState:
    """Track press/release for tap vs hold detection."""

    def __init__(self):
        self.is_pressed = False
        self.press_time = 0.0
        self.moved_during_press = False
        self.was_held = False

    def update(self, pressed, now, moved):
        """Update button state. Returns 'tap', 'hold_start', 'hold_end', or None."""
        event = None

        if pressed and not self.is_pressed:
            # Button just pressed
            self.is_pressed = True
            self.press_time = now
            self.moved_during_press = False
            self.was_held = False

        elif pressed and self.is_pressed:
            # Button still held
            if moved:
                self.moved_during_press = True
            duration = now - self.press_time
            if duration > TAP_MAX_DURATION and not self.was_held:
                self.was_held = True
                event = "hold_start"

        elif not pressed and self.is_pressed:
            # Button just released
            self.is_pressed = False
            duration = now - self.press_time
            if self.was_held:
                event = "hold_end"
            elif duration <= TAP_MAX_DURATION and not self.moved_during_press:
                event = "tap"

        return event


def scale_axis(value, center, deadzone, sensitivity):
    """Scale an axis value from raw to mouse movement."""
    offset = value - center
    if abs(offset) <= deadzone:
        return 0
    if offset > 0:
        offset -= deadzone
    else:
        offset += deadzone
    max_range = center - deadzone
    if max_range <= 0:
        return 0
    scaled = (offset / max_range) * sensitivity
    return int(max(min(scaled, 127), -127))


def joy_to_mouse(jx, jy, sensitivity):
    """Convert joystick axes to mouse deltas with Y inverted."""
    return (scale_axis(jx, JOY_CENTER, JOY_DEADZONE, sensitivity),
            -scale_axis(jy, JOY_CENTER, JOY_DEADZONE, sensitivity))


def do_scroll(mouse, sy, divider):
    """Send a scroll event if the computed step is non-zero. Returns True if scrolled."""
    scroll = int(sy / divider)
    if scroll != 0:
        mouse.move(0, 0, scroll)
        return True
    return False


def joy_active(jx, jy):
    """Check if joystick is outside deadzone."""
    return abs(jx - JOY_CENTER) > JOY_DEADZONE or abs(jy - JOY_CENTER) > JOY_DEADZONE


# --- Main ---

def check_pullups():
    """Check if SDA/SCL lines have pull-up resistors."""
    for name, pin in [("SDA", I2C_SDA), ("SCL", I2C_SCL)]:
        d = digitalio.DigitalInOut(pin)
        d.direction = digitalio.Direction.INPUT
        # No pull — reads high if external pull-up exists
        d.pull = None
        has_external = d.value
        # Enable internal pull-up for comparison
        d.pull = digitalio.Pull.UP
        with_pull = d.value
        d.deinit()
        print(f"  {name}: external_pullup={'yes' if has_external else 'NO'}, with_internal={'high' if with_pull else 'low'}")
    print()


def release_i2c_bus():
    """Pulse SCL to release a stuck I2C bus.

    Some devices (including Nunchuk) can hold SCL low after power-on or
    incomplete transactions. Toggling SCL manually sends enough clock pulses
    to free the bus.
    """
    print("  Sending clock pulses to release I2C bus...")
    scl = digitalio.DigitalInOut(I2C_SCL)
    sda = digitalio.DigitalInOut(I2C_SDA)
    scl.direction = digitalio.Direction.OUTPUT
    sda.direction = digitalio.Direction.INPUT
    sda.pull = digitalio.Pull.UP

    # Send 9 clock pulses (standard I2C bus recovery)
    for i in range(9):
        scl.value = False
        time.sleep(0.001)
        scl.value = True
        time.sleep(0.001)
        if sda.value:
            print(f"  Bus released after {i + 1} clock pulses")
            break

    # Send STOP condition: SDA low->high while SCL high
    sda.deinit()
    sda = digitalio.DigitalInOut(I2C_SDA)
    sda.direction = digitalio.Direction.OUTPUT
    sda.value = False
    time.sleep(0.001)
    scl.value = True
    time.sleep(0.001)
    sda.value = True
    time.sleep(0.001)

    scl.deinit()
    sda.deinit()
    time.sleep(0.05)


def init_i2c():
    """Initialize I2C with bus recovery if needed."""
    print("Checking I2C pull-ups...")
    check_pullups()

    print("Initializing I2C...")

    # Strategy 1: Try hardware I2C directly
    try:
        i2c = busio.I2C(I2C_SCL, I2C_SDA, frequency=100000)
        print("  Using hardware I2C")
        return i2c
    except RuntimeError as e:
        print(f"  Hardware I2C failed: {e}")

    # Strategy 2: Recover the bus and retry hardware I2C
    release_i2c_bus()
    print("  Retrying hardware I2C after bus recovery...")
    try:
        i2c = busio.I2C(I2C_SCL, I2C_SDA, frequency=100000)
        print("  Using hardware I2C (after recovery)")
        return i2c
    except RuntimeError as e:
        print(f"  Hardware I2C still failed: {e}")

    # Strategy 3: bitbangio as last resort
    print("  Trying bitbangio (software I2C)...")
    import bitbangio
    for freq in [100000, 50000, 10000]:
        try:
            i2c = bitbangio.I2C(I2C_SCL, I2C_SDA, frequency=freq)
            print(f"  Using software I2C at {freq}Hz")
            return i2c
        except (TimeoutError, ValueError, RuntimeError) as e2:
            print(f"  bitbangio at {freq}Hz failed: {e2}")
            try:
                i2c.deinit()
            except Exception:
                pass

    # All failed
    print()
    print("  ERROR: Could not initialize I2C after all attempts.")
    print("  The Nunchuk may be holding SCL low and not releasing.")
    print("  Try: power-cycle the Pico (unplug USB and replug)")
    print()
    print("  Halting. Fix wiring and press CTRL-D to reload.")
    while True:
        time.sleep(1)


def main():
    i2c = init_i2c()

    # Scan for devices
    while not i2c.try_lock():
        pass
    devices = i2c.scan()
    i2c.unlock()
    print(f"  I2C devices found: {[hex(d) for d in devices]}")

    if 0x52 not in devices:
        print("  WARNING: Nunchuk (0x52) not found on I2C bus!")
        print("  Check wiring: SDA->GP4, SCL->GP5, 3V3, GND")
        print("  Retrying in 3 seconds...")
        time.sleep(3)

    nunchuk = adafruit_nunchuk.Nunchuk(i2c)
    print("Nunchuk initialized")

    # Initialize HID devices
    keyboard = Keyboard(usb_hid.devices)
    mouse = Mouse(usb_hid.devices)
    print("USB HID initialized")

    # Button state trackers
    btn_c = ButtonState()
    btn_z = ButtonState()

    # Active profile (1 = CAD/TinkerCAD, 2 = Browser/Navigation)
    profile = 2
    # Prevents a long C-hold from also firing the normal hold_start action
    profile_switched_this_hold = False
    # Cooldown tracker for Profile 2 scroll
    last_scroll_p2 = 0.0

    print("Ready — move joystick or press buttons")
    print("Active profile: 2 (Browser/Navigation)")

    while True:
        now = time.monotonic()

        # Read Nunchuk
        joy = nunchuk.joystick
        buttons = nunchuk.buttons

        jx, jy = joy[0], joy[1]  # 0-255
        c_pressed = buttons.C
        z_pressed = buttons.Z

        # Detect movement for tap detection
        joy_moved = joy_active(jx, jy)

        # --- Profile switch: C held >= PROFILE_SWITCH_DURATION ---
        # Must run before btn_c.update() so we can read press_time accurately.
        if c_pressed and btn_c.is_pressed and not profile_switched_this_hold:
            if (now - btn_c.press_time) >= PROFILE_SWITCH_DURATION:
                # Release any held keys/buttons before switching profiles
                # to prevent them getting stuck in the new profile context.
                if btn_z.is_pressed and btn_z.was_held:
                    keyboard.release(Keycode.ALT)   # Profile 2 Z-hold
                    mouse.release(Mouse.RIGHT_BUTTON)  # Profile 1 Z-hold
                profile = 2 if profile == 1 else 1
                profile_switched_this_hold = True
                label = "CAD" if profile == 1 else "Browser/Navigation"
                print(f"Profile switched to {profile} ({label})")

        if not c_pressed:
            profile_switched_this_hold = False

        # Update button states
        c_event = btn_c.update(c_pressed, now, joy_moved)
        z_event = btn_z.update(z_pressed, now, joy_moved)

        # Suppress C events for the rest of this hold after a profile switch
        if profile_switched_this_hold:
            c_event = None

        # ================================================================
        # PROFILE 1 — CAD / TinkerCAD (original behaviour)
        # ================================================================
        if profile == 1:

            if c_event == "tap":
                keyboard.send(Keycode.F)

            if z_event == "tap":
                keyboard.send(Keycode.D)

            if btn_c.is_pressed and btn_c.was_held and not profile_switched_this_hold:
                # C HELD: Mouse movement + left click (pan)
                if c_event == "hold_start":
                    mouse.press(Mouse.LEFT_BUTTON)
                mx, my = joy_to_mouse(jx, jy, MOUSE_SENSITIVITY)
                if mx != 0 or my != 0:
                    mouse.move(mx, my)

            elif btn_z.is_pressed and btn_z.was_held:
                # Z HELD: Orbit (right mouse button + drag)
                if z_event == "hold_start":
                    mouse.press(Mouse.RIGHT_BUTTON)
                mx, my = joy_to_mouse(jx, jy, ORBIT_SENSITIVITY)
                if mx != 0 or my != 0:
                    mouse.move(mx, my)

            else:
                # NO MODIFIER: zoom and pan
                if joy_moved:
                    sy = jy - JOY_CENTER
                    if abs(sy) > JOY_DEADZONE:
                        do_scroll(mouse, sy, SCROLL_DIVIDER)

                    # TinkerCAD: Shift+right-click drag to pan horizontally
                    sx = scale_axis(jx, JOY_CENTER, JOY_DEADZONE, MOUSE_SENSITIVITY)
                    if sx != 0:
                        keyboard.press(Keycode.SHIFT)
                        mouse.press(Mouse.RIGHT_BUTTON)
                        mouse.move(sx, 0)
                        mouse.release(Mouse.RIGHT_BUTTON)
                        keyboard.release(Keycode.SHIFT)

        # ================================================================
        # PROFILE 2 — Browser / Navigation
        # ================================================================
        elif profile == 2:

            # C tap (standalone, Z not held): Ctrl+Tab (next browser tab)
            if c_event == "tap" and not btn_z.is_pressed:
                keyboard.send(Keycode.CONTROL, Keycode.TAB)

            # Z hold: keep Alt pressed so the switcher stays open
            if z_event == "hold_start":
                keyboard.press(Keycode.ALT)

            # C tap while Z is held: cycle to next window in the switcher
            # Alt is already held via keyboard.press(Keycode.ALT), so just tap Tab
            if c_event == "tap" and btn_z.is_pressed and btn_z.was_held:
                keyboard.press(Keycode.TAB)
                keyboard.release(Keycode.TAB)

            # Z released after hold: release Alt to confirm window selection
            if z_event == "hold_end":
                keyboard.release(Keycode.ALT)

            # Z tap: do nothing

            # Joystick (C/Z hold does nothing in profile 2)
            no_modifier = not (btn_c.is_pressed and btn_c.was_held and not profile_switched_this_hold) \
                          and not (btn_z.is_pressed and btn_z.was_held)

            if no_modifier and joy_moved:
                # Vertical: scroll wheel (up/down) with cooldown
                sy = jy - JOY_CENTER
                if abs(sy) > JOY_DEADZONE and (now - last_scroll_p2) >= SCROLL_COOLDOWN_P2:
                    if do_scroll(mouse, sy, SCROLL_DIVIDER_P2):
                        last_scroll_p2 = now

                # Horizontal: Alt+Left (back) / Alt+Right (forward)
                sx = jx - JOY_CENTER
                if abs(sx) > JOY_DEADZONE:
                    if sx > 0:
                        keyboard.send(Keycode.ALT, Keycode.RIGHT_ARROW)
                    else:
                        keyboard.send(Keycode.ALT, Keycode.LEFT_ARROW)

        # ================================================================
        # Shared: release held mouse buttons when their modifier is released
        # ================================================================
        if c_event == "hold_end":
            mouse.release(Mouse.LEFT_BUTTON)

        if z_event == "hold_end":
            mouse.release(Mouse.RIGHT_BUTTON)

        time.sleep(LOOP_DELAY)


main()
