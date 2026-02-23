"""
boot.py — USB HID device configuration for Pico-Nunchuk
Runs once at boot before code.py
"""

import usb_hid

# Enable keyboard + mouse composite HID device
# CircuitPython provides these by default, but we explicitly set them
# to ensure both are available
usb_hid.enable(
    (usb_hid.Device.KEYBOARD, usb_hid.Device.MOUSE)
)
