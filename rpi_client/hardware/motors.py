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

import os
import time
import threading
import math

# Use pigpio to avoid audio DMA jitter and eliminate servo twitching
#os.environ["GPIOZERO_PIN_FACTORY"] = "pigpio"

try:
    from gpiozero import AngularServo, Servo
    #from gpiozero.pins.pigpio import PiGPIOFactory
    HAS_GPIO = True
except Exception:
    HAS_GPIO = False

# ==========================================================
# Conflict-Free GPIO Pins (Safe with Pimoroni Pirate Audio)
# ==========================================================
DEFAULT_NECK_TILT_PIN = 12  # Physical Pin 32 (Safe PWM)
DEFAULT_NECK_PAN_PIN = 23   # Physical Pin 16 (Safe; GPIO 13 was LCD Backlight)
DEFAULT_TAIL_PIN = 26       # Physical Pin 37 (Safe; GPIO 18 was I2S Audio Clock)

# Servo / Motor Bounds
NECK_TILT_MIN = -20.0
NECK_TILT_MAX = 30.0
NECK_PAN_MIN = -30.0
NECK_PAN_MAX = 30.0
TAIL_SPEED_MIN = -1.0
TAIL_SPEED_MAX = 1.0

# Geekservo / Hobby Servo Pulse Bounds (0.5ms to 2.5ms @ 50Hz)
SERVO_MIN_PULSE = 0.0005
SERVO_MAX_PULSE = 0.0025


class MotorController:
    """
    Controls LEGO Technic / PWM Servos for DinoDesk:
    - Neck Tilt (Pitch): -20° to +30° (Sleep: -15°, Listen: +15°, Home: 0°) [AngularServo]
    - Neck Pan (Yaw/Sway): -30° to +30° (Thinking sway: -20° to +20°, Home: 0°) [AngularServo]
    - Tail Knock (Actuator): 360° continuous rotation servo (-1.0 to +1.0 speed) [Servo] (Speaking typewriter knock & Button Y test)
    """

    def __init__(
        self,
        neck_tilt_pin=DEFAULT_NECK_TILT_PIN,
        neck_pan_pin=DEFAULT_NECK_PAN_PIN,
        tail_pin=DEFAULT_TAIL_PIN,
        on_motor_event=None
    ):
        self.on_motor_event = on_motor_event
        self.lock = threading.Lock()
        
        self.neck_tilt = 0.0
        self.neck_pan = 0.0
        self.tail_speed = 0.0
        self.tail_angle = 0.0
        self.is_knocking = False
        self.hardware_active = False

        self._sway_thread = None
        self._sway_stop_event = threading.Event()

        # Hardware initialization
        self.servo_tilt = None
        self.servo_pan = None
        self.servo_tail = None

        if HAS_GPIO:
            try:
                # Try initializing pigpio factory for jitter-free hardware timing
                pin_factory = None
                #try:
                #    pin_factory = PiGPIOFactory()
                #except Exception:
                #    pin_factory = None

                # Configure standard 50Hz Geekservos (-90 to +90 mapping for Tilt/Pan)
                self.servo_tilt = AngularServo(
                    neck_tilt_pin,
                    min_angle=-90,
                    max_angle=90,
                    min_pulse_width=SERVO_MIN_PULSE,
                    max_pulse_width=SERVO_MAX_PULSE,
                    pin_factory=pin_factory
                )
                self.servo_pan = AngularServo(
                    neck_pan_pin,
                    min_angle=-90,
                    max_angle=90,
                    min_pulse_width=SERVO_MIN_PULSE,
                    max_pulse_width=SERVO_MAX_PULSE,
                    pin_factory=pin_factory
                )
                # Tail motor is a 360° continuous rotation servo (Servo with -1.0 to 1.0 control)
                self.servo_tail = Servo(
                    tail_pin,
                    min_pulse_width=SERVO_MIN_PULSE,
                    max_pulse_width=SERVO_MAX_PULSE,
                    pin_factory=pin_factory
                )
                self.hardware_active = True
                print(f"[MotorController] Hardware PWM Servos initialized on GPIO {neck_tilt_pin}, {neck_pan_pin}, {tail_pin}.")
            except Exception as e:
                print(f"[MotorController] Hardware servo init failed ({e}). Running in virtual simulation mode.")
                self.servo_tilt = None
                self.servo_pan = None
                self.servo_tail = None
                self.hardware_active = False
        else:
            print("[MotorController] gpiozero not available. Running in virtual servo mode.")

        self.recenter()

    def _notify(self):
        if self.on_motor_event:
            try:
                self.on_motor_event(self.get_state())
            except Exception:
                pass

    def get_state(self) -> dict:
        with self.lock:
            return {
                "neck_tilt": round(self.neck_tilt, 1),
                "neck_pan": round(self.neck_pan, 1),
                "tail_speed": round(self.tail_speed, 2),
                "tail_angle": round(self.tail_speed, 2),
                "is_knocking": self.is_knocking,
                "hardware_active": self.hardware_active,
            }

    def set_neck_tilt(self, angle: float):
        angle = max(NECK_TILT_MIN, min(NECK_TILT_MAX, float(angle)))
        with self.lock:
            self.neck_tilt = angle
        if self.hardware_active and self.servo_tilt:
            try:
                self.servo_tilt.angle = angle
            except Exception:
                pass
        self._notify()

    def set_neck_pan(self, angle: float):
        angle = max(NECK_PAN_MIN, min(NECK_PAN_MAX, float(angle)))
        with self.lock:
            self.neck_pan = angle
        if self.hardware_active and self.servo_pan:
            try:
                self.servo_pan.angle = angle
            except Exception:
                pass
        self._notify()

    def set_tail_speed(self, speed: float):
        speed = max(TAIL_SPEED_MIN, min(TAIL_SPEED_MAX, float(speed)))
        with self.lock:
            self.tail_speed = speed
            self.tail_angle = speed
        if self.hardware_active and self.servo_tail:
            try:
                if abs(speed) < 0.01:
                    self.servo_tail.value = 0.0
                    self.servo_tail.detach()
                else:
                    self.servo_tail.value = speed
            except Exception:
                pass
        self._notify()

    def set_tail_angle(self, angle: float):
        """Compatibility wrapper: converts angle or speed input to tail speed."""
        if abs(angle) > 1.0:
            speed = max(-1.0, min(1.0, float(angle) / 45.0))
        else:
            speed = float(angle)
        self.set_tail_speed(speed)

    def move(self, neck_tilt=None, neck_pan=None, tail_speed=None, tail_angle=None):
        """Move multiple servos in a single operation."""
        self.stop_thinking_sway()
        if neck_tilt is not None:
            self.set_neck_tilt(neck_tilt)
        if neck_pan is not None:
            self.set_neck_pan(neck_pan)
        if tail_speed is not None:
            self.set_tail_speed(tail_speed)
        elif tail_angle is not None:
            self.set_tail_angle(tail_angle)

    def recenter(self):
        """Reset all motors to home/center position (0°, 0°, speed 0.0)."""
        self.stop_thinking_sway()
        self.set_neck_tilt(0.0)
        self.set_neck_pan(0.0)
        self.set_tail_speed(0.0)
        if self.hardware_active and self.servo_tail:
            try:
                self.servo_tail.value = 0.0
                self.servo_tail.detach()
            except Exception:
                pass

    def trigger_tail_knock(self, times: int = 1, delay_ms: int = 120):
        """Trigger one or more tail knock pulses on 360° continuous rotation servo."""
        def _knock_worker():
            with self.lock:
                self.is_knocking = True
            self._notify()

            for _ in range(times):
                if self.hardware_active and self.servo_tail:
                    try:
                        # Forward pulse (knock down/tap)
                        self.set_tail_speed(0.8)
                        time.sleep(delay_ms / 1000.0)
                        # Reverse pulse to recoil/re-arm
                        self.set_tail_speed(-0.6)
                        time.sleep((delay_ms * 0.75) / 1000.0)
                        # Stop and detach
                        self.set_tail_speed(0.0)
                        time.sleep(delay_ms / 1000.0)
                    except Exception:
                        self.set_tail_speed(0.0)
                else:
                    self.set_tail_speed(0.8)
                    time.sleep(delay_ms / 1000.0)
                    self.set_tail_speed(-0.6)
                    time.sleep((delay_ms * 0.75) / 1000.0)
                    self.set_tail_speed(0.0)
                    time.sleep(delay_ms / 1000.0)

            with self.lock:
                self.is_knocking = False
            self._notify()

        thread = threading.Thread(target=_knock_worker, daemon=True)
        thread.start()

    def start_thinking_sway(self, tilt_angle: float = 15.0):
        """Start gentle neck swaying side-to-side while maintaining head in tilt status during Thinking state."""
        self.stop_thinking_sway()
        self._sway_stop_event.clear()
        self.set_neck_tilt(tilt_angle)

        def _sway_worker():
            t = 0.0
            while not self._sway_stop_event.is_set():
                sway_angle = 18.0 * math.sin(t)
                self.set_neck_pan(sway_angle)
                t += 0.35
                time.sleep(0.08)
            # Re-center pan when sway ends
            self.set_neck_pan(0.0)

        self._sway_thread = threading.Thread(target=_sway_worker, daemon=True)
        self._sway_thread.start()

    def stop_thinking_sway(self):
        """Stop thinking sway if running."""
        if self._sway_thread and self._sway_thread.is_alive():
            self._sway_stop_event.set()
            self._sway_thread.join(timeout=0.4)
            self._sway_thread = None

    def apply_fsm_pose(self, state_name: str):
        """Apply motor posture corresponding to DinoDesk FSM State."""
        state = state_name.upper()
        if state == "SLEEPING":
            self.stop_thinking_sway()
            self.set_neck_tilt(-15.0)
            self.set_neck_pan(0.0)
            self.set_tail_speed(0.0)
        elif state == "IDLE":
            self.stop_thinking_sway()
            self.set_neck_tilt(0.0)
            self.set_neck_pan(0.0)
            self.set_tail_speed(0.0)
        elif state == "LISTENING":
            self.stop_thinking_sway()
            self.set_neck_tilt(15.0)  # Tilt head up 15° toward user
            self.set_neck_pan(0.0)
            self.set_tail_speed(0.0)
        elif state == "THINKING":
            self.set_neck_tilt(15.0)  # Head is in tilt status (15°) while thinking & swaying
            self.set_tail_speed(0.0)
            self.start_thinking_sway(tilt_angle=15.0)
        elif state == "SPEAKING":
            self.stop_thinking_sway()
            self.set_neck_tilt(0.0)
            # Tail knocking is triggered rhythmically per token/stream
            self.trigger_tail_knock(times=1, delay_ms=80)
