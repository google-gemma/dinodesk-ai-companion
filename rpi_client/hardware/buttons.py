# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import threading

try:
    from gpiozero import Button
    HAS_GPIO = True
except Exception:
    HAS_GPIO = False

# ==========================================================
# Conflict-Free GPIO Pins (Safe with Pimoroni Pirate Audio)
# ==========================================================
DEFAULT_NOSE_SWITCH_PIN = 27   # Physical Pin 13 (LEGO Nose Limit Switch)
DEFAULT_PIRATE_BTN_A_PIN = 5   # Physical Pin 29 (Pirate Audio Button A: Cancel/Mute)
DEFAULT_PIRATE_BTN_B_PIN = 6   # Physical Pin 31 (Pirate Audio Button B: Recenter/Home)
DEFAULT_PIRATE_BTN_X_PIN = 16  # Physical Pin 36 (Pirate Audio Button X: Cycle / Double-click Toggle)
DEFAULT_PIRATE_BTN_Y_PIN = 24  # Physical Pin 18 (Pirate Audio Button Y: Tail Knock / Vol)


class InputController:
    def __init__(
        self,
        on_nose_press,
        on_toggle_mode,
        on_nose_release=None,
        on_recenter=None,
        on_tail_knock=None,
        on_cancel=None,
        on_cycle_expr=None,
        on_poweroff=None,
        nose_pin=DEFAULT_NOSE_SWITCH_PIN,
        btn_a_pin=DEFAULT_PIRATE_BTN_A_PIN,
        btn_b_pin=DEFAULT_PIRATE_BTN_B_PIN,
        btn_x_pin=DEFAULT_PIRATE_BTN_X_PIN,
        btn_y_pin=DEFAULT_PIRATE_BTN_Y_PIN,
    ):
        self.on_nose_press = on_nose_press
        self.on_nose_release = on_nose_release
        self.on_toggle_mode = on_toggle_mode
        self.on_recenter = on_recenter
        self.on_tail_knock = on_tail_knock
        self.on_cancel = on_cancel
        self.on_cycle_expr = on_cycle_expr
        self.on_poweroff = on_poweroff

        self._last_btn_x_time = 0
        self._single_click_timer_x = None

        self._last_btn_a_time = 0
        self._single_click_timer_a = None

        self.nose_btn = None
        self.btn_a = None
        self.btn_b = None
        self.btn_x = None
        self.btn_y = None

        if HAS_GPIO:
            try:
                self.nose_btn = Button(nose_pin, pull_up=True, bounce_time=0.05)
                self.btn_a = Button(btn_a_pin, pull_up=True, bounce_time=0.05)
                self.btn_b = Button(btn_b_pin, pull_up=True, bounce_time=0.05)
                self.btn_x = Button(btn_x_pin, pull_up=True, bounce_time=0.05)
                self.btn_y = Button(btn_y_pin, pull_up=True, bounce_time=0.05)

                if self.on_nose_press:
                    self.nose_btn.when_pressed = self.on_nose_press
                if self.on_nose_release:
                    self.nose_btn.when_released = self.on_nose_release
                
                self.btn_a.when_pressed = self._handle_btn_a
                
                if self.on_recenter:
                    self.btn_b.when_pressed = self.on_recenter
                
                self.btn_x.when_pressed = self._handle_btn_x
                
                if self.on_tail_knock:
                    self.btn_y.when_pressed = self.on_tail_knock

                print(f"[InputController] Buttons initialized (Nose: GPIO {nose_pin}, HAT: 5, 6, 16, 24).")
            except Exception as e:
                print(f"[InputController] GPIO button init failed ({e}). Running in virtual mode.")
                self._clear_buttons()
        else:
            print("[InputController] gpiozero not available. Running in virtual mode.")
            self._clear_buttons()

    def _clear_buttons(self):
        self.nose_btn = None
        self.btn_a = None
        self.btn_b = None
        self.btn_x = None
        self.btn_y = None

    def trigger_nose_press(self):
        if self.on_nose_press:
            self.on_nose_press()

    def trigger_nose_release(self):
        if self.on_nose_release:
            self.on_nose_release()

    def trigger_btn_a(self):
        self._handle_btn_a()

    def trigger_btn_a_double(self):
        self._handle_btn_a()
        time.sleep(0.05)
        self._handle_btn_a()

    def trigger_btn_b(self):
        if self.on_recenter:
            self.on_recenter()

    def trigger_btn_x(self):
        self._handle_btn_x()

    def trigger_btn_y(self):
        if self.on_tail_knock:
            self.on_tail_knock()

    def _handle_btn_a(self):
        now = time.time()
        # Double-click threshold: within 400ms
        if now - self._last_btn_a_time < 0.4:
            if self._single_click_timer_a and self._single_click_timer_a.is_alive():
                self._single_click_timer_a.cancel()
            self._last_btn_a_time = 0
            if self.on_poweroff:
                self.on_poweroff()
        else:
            self._last_btn_a_time = now
            # If a single-click handler (cancel) is provided, fire after delay window
            if self.on_cancel:
                self._single_click_timer_a = threading.Timer(0.42, self._fire_single_click_a)
                self._single_click_timer_a.daemon = True
                self._single_click_timer_a.start()

    def _fire_single_click_a(self):
        if self._last_btn_a_time != 0 and self.on_cancel:
            self.on_cancel()
            self._last_btn_a_time = 0

    def _handle_btn_x(self):
        now = time.time()
        # Double-click threshold: within 400ms
        if now - self._last_btn_x_time < 0.4:
            if self._single_click_timer_x and self._single_click_timer_x.is_alive():
                self._single_click_timer_x.cancel()
            self._last_btn_x_time = 0
            if self.on_toggle_mode:
                self.on_toggle_mode()
        else:
            self._last_btn_x_time = now
            # If a single-click handler is provided, fire after delay window
            if self.on_cycle_expr:
                self._single_click_timer_x = threading.Timer(0.42, self._fire_single_click_x)
                self._single_click_timer_x.daemon = True
                self._single_click_timer_x.start()

    def _fire_single_click_x(self):
        if self._last_btn_x_time != 0 and self.on_cycle_expr:
            self.on_cycle_expr()
            self._last_btn_x_time = 0
