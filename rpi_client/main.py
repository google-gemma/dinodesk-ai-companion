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
import sys
import time
import json
import base64
import argparse
import threading
import requests
from enum import Enum
from hardware.buttons import InputController
from hardware.display import DisplayManager
from hardware.audio_out import SoundFX
from hardware.audio_in import AudioRecorder
from hardware.motors import MotorController
from web_server import DinoWebServer
from datetime import datetime

DEFAULT_GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000/v1/chat/stream")
NOTES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.json")
REMINDERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reminders.json")

class State(Enum):
    SLEEPING = 1
    IDLE = 2
    LISTENING = 3
    THINKING = 4
    SPEAKING = 5

class DinoDesk:
    def __init__(self, gateway_url: str = DEFAULT_GATEWAY_URL, enable_web: bool = True, web_port: int = 5000):
        self.state = State.IDLE
        self.mode = "LOCAL"  # "LOCAL" or "CLOUD"
        self.gateway_url = gateway_url
        self.last_subtitle = ""
        self.current_expression = "•   •"
        self.notes = self._load_notes()
        self.reminders = self._load_reminders()
        self._reminder_scheduler_running = True
        self._running = True
        
        self.web_server = None
        if enable_web:
            self.web_server = DinoWebServer(self, port=web_port)

        self.display = DisplayManager()
        self.audio_fx = SoundFX(on_sound_event=self._on_sound_event)
        self.audio_in = AudioRecorder()
        self.motors = MotorController(on_motor_event=self._on_motor_event)
        self.inputs = InputController(
            on_nose_press=self.handle_nose_down,
            on_nose_release=self.handle_nose_up,
            on_toggle_mode=self.toggle_mode,
            on_recenter=self.recenter,
            on_tail_knock=self.trigger_tail_knock,
            on_cancel=self.cancel,
            on_poweroff=self.poweroff
        )

        # Start background reminder checker thread
        self._reminder_thread = threading.Thread(target=self._reminder_loop, daemon=True)
        self._reminder_thread.start()

        if self.web_server:
            self.web_server.start()

        self.update_ui()

    def _load_notes(self) -> list:
        """Load persistent notes from local notes.json file."""
        if os.path.exists(NOTES_FILE):
            try:
                with open(NOTES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                print(f"[DinoDesk] Failed to load notes.json: {e}")
        return []

    def _save_notes(self):
        """Save notes list to local notes.json file."""
        try:
            with open(NOTES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DinoDesk] Failed to save notes.json: {e}")

    def get_notes(self) -> list:
        """Return copy of all saved notes."""
        return list(self.notes)

    def add_note(self, text: str) -> dict:
        """Create and store a new note, then broadcast event to web clients."""
        cleaned = text.strip() if text else ""
        if not cleaned:
            return {}
        
        now = datetime.now()
        note = {
            "id": f"note_{int(time.time() * 1000)}",
            "text": cleaned,
            "created_at": now.strftime("%I:%M %p · %b %d, %Y"),
            "timestamp": time.time()
        }
        self.notes.insert(0, note)
        self._save_notes()
        print(f"[DinoDesk] Note added: '{cleaned}' (Total: {len(self.notes)})")

        if self.web_server:
            self.web_server.broadcast_event("note_added", note)
            self.web_server.broadcast_event("notes_update", {"notes": self.notes})
        return note

    def delete_note(self, note_id: str) -> bool:
        """Delete a note by its ID."""
        initial_len = len(self.notes)
        self.notes = [n for n in self.notes if str(n.get("id")) != str(note_id)]
        if len(self.notes) < initial_len:
            self._save_notes()
            if self.web_server:
                self.web_server.broadcast_event("notes_update", {"notes": self.notes})
            return True
        return False

    def clear_notes(self):
        """Clear all stored notes."""
        self.notes = []
        self._save_notes()
        if self.web_server:
            self.web_server.broadcast_event("notes_update", {"notes": self.notes})

    def _load_reminders(self) -> list:
        """Load persistent reminders from local reminders.json file."""
        if os.path.exists(REMINDERS_FILE):
            try:
                with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                print(f"[DinoDesk] Failed to load reminders.json: {e}")
        return []

    def _save_reminders(self):
        """Save reminders list to local reminders.json file."""
        try:
            with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.reminders, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DinoDesk] Failed to save reminders.json: {e}")

    def get_reminders(self) -> list:
        """Return copy of all saved reminders with dynamically computed remaining seconds."""
        now_ts = time.time()
        res = []
        for r in self.reminders:
            item = dict(r)
            due_ts = item.get("due_timestamp", 0)
            item["remaining_seconds"] = max(0, int(due_ts - now_ts)) if not item.get("triggered", False) else 0
            res.append(item)
        return res

    def add_reminder(self, text: str, delay_seconds: float = 60.0, due_timestamp: float = None) -> dict:
        """Create and store a new reminder, then broadcast event to web clients."""
        cleaned = text.strip() if text else "Reminder"
        now = datetime.now()
        now_ts = time.time()
        if due_timestamp is None:
            delay = max(1.0, float(delay_seconds or 60.0))
            target_ts = now_ts + delay
        else:
            target_ts = float(due_timestamp)
            delay = max(1.0, target_ts - now_ts)

        due_dt = datetime.fromtimestamp(target_ts)
        reminder = {
            "id": f"rem_{int(now_ts * 1000)}",
            "text": cleaned,
            "delay_seconds": int(delay),
            "due_timestamp": target_ts,
            "due_time_str": due_dt.strftime("%I:%M %p · %b %d, %Y"),
            "created_at": now.strftime("%I:%M %p · %b %d, %Y"),
            "triggered": False
        }
        self.reminders.insert(0, reminder)
        self._save_reminders()
        print(f"[DinoDesk] Reminder added: '{cleaned}' in {int(delay)}s at {reminder['due_time_str']}")

        if self.web_server:
            self.web_server.broadcast_event("reminder_added", reminder)
            self.web_server.broadcast_event("reminders_update", {"reminders": self.get_reminders()})
        return reminder

    def delete_reminder(self, reminder_id: str) -> bool:
        """Delete a reminder by its ID."""
        initial_len = len(self.reminders)
        self.reminders = [r for r in self.reminders if str(r.get("id")) != str(reminder_id)]
        if len(self.reminders) < initial_len:
            self._save_reminders()
            if self.web_server:
                self.web_server.broadcast_event("reminders_update", {"reminders": self.get_reminders()})
            return True
        return False

    def clear_reminders(self):
        """Clear all stored reminders."""
        self.reminders = []
        self._save_reminders()
        if self.web_server:
            self.web_server.broadcast_event("reminders_update", {"reminders": []})

    def _reminder_loop(self):
        """Background thread checking every 0.5s for due reminders."""
        while self._reminder_scheduler_running:
            try:
                now_ts = time.time()
                for rem in list(self.reminders):
                    if not rem.get("triggered", False) and rem.get("due_timestamp", 0) <= now_ts:
                        rem["triggered"] = True
                        self._save_reminders()
                        threading.Thread(target=self._trigger_reminder_alert, args=(rem,), daemon=True).start()
            except Exception as e:
                print(f"[DinoDesk] Error in reminder loop: {e}")
            time.sleep(0.5)

    def _trigger_reminder_alert(self, reminder: dict):
        """Trigger visual, audio, motor, and web alert when a reminder is due."""
        text = reminder.get("text", "Reminder")
        print(f"[DinoDesk] ⏰ REMINDER DUE: '{text}'")

        # 1. Sound Alert
        self.audio_fx.reminder_beep()

        # 2. Motor Alert (Attention knock)
        self.motors.trigger_tail_knock(times=3, delay_ms=100)

        # 3. Visual Alert on LCD
        prev_subtitle = self.last_subtitle
        alert_subtitle = f"⏰ {text}"
        self.current_expression = "!   !"
        self.last_subtitle = alert_subtitle
        self.display.render(
            expression=self.current_expression,
            subtitle=alert_subtitle,
            mode=self.mode
        )

        # 4. Broadcast SSE
        if self.web_server:
            self.web_server.broadcast_event("reminder_due", reminder)
            self.web_server.broadcast_event("reminders_update", {"reminders": self.get_reminders()})

        # Keep alert displayed on screen for 6 seconds unless superseded
        time.sleep(6)
        if self.last_subtitle == alert_subtitle:
            self.update_ui(text=prev_subtitle if prev_subtitle else "")

    def _on_sound_event(self, sound_name: str):
        if self.web_server:
            self.web_server.broadcast_event("sound", {"sound": sound_name})

    def _on_motor_event(self, motor_data: dict):
        if self.web_server:
            self.web_server.broadcast_event("motor_update", motor_data)

    def toggle_mode(self):
        self.mode = "CLOUD" if self.mode == "LOCAL" else "LOCAL"
        self.update_ui()

    def recenter(self):
        """Button B / Reset handler - recenters servos and sets idle expression."""
        self.motors.recenter()
        if self.state != State.IDLE:
            self.state = State.IDLE
            self.update_ui()

    def trigger_tail_knock(self, times: int = 2):
        """Button Y handler - triggers tail knock test."""
        self.motors.trigger_tail_knock(times=times)

    def cancel(self):
        """Button A single-click handler - cancel current interaction."""
        self.state = State.IDLE
        self.update_ui(text="Cancelled")

    def poweroff(self):
        """Button A double-click handler - exits the program and powers off Raspberry Pi."""
        print("[DinoDesk] Double-click on Button 'A' detected: Exiting program and powering off Raspberry Pi...")
        self.shutdown(poweroff_system=True)

    def shutdown(self, poweroff_system: bool = False):
        """Gracefully shut down FSM, background tasks, display, motors, and optionally trigger OS poweroff."""
        self._running = False
        self._reminder_scheduler_running = False

        # Visual feedback on LCD screen
        try:
            self.state = State.SLEEPING
            self.current_expression = "- _ -"
            self.last_subtitle = "Powering off..." if poweroff_system else "Stopping..."
            self.display.render(
                expression=self.current_expression,
                subtitle=self.last_subtitle,
                mode=self.mode
            )
        except Exception as e:
            print(f"[DinoDesk] Display shutdown error: {e}")

        # Stop web server & notify clients
        if self.web_server:
            try:
                self.web_server.broadcast_event("system_shutdown", {"poweroff": poweroff_system})
            except Exception:
                pass
            try:
                self.web_server.stop()
            except Exception as e:
                print(f"[DinoDesk] Web server stop error: {e}")

        # Park/recenter motors safely
        if self.motors:
            try:
                self.motors.apply_fsm_pose("SLEEPING")
                time.sleep(0.2)
                self.motors.recenter()
            except Exception as e:
                print(f"[DinoDesk] Motor shutdown error: {e}")

        # Execute system poweroff if requested
        if poweroff_system:
            print("[DinoDesk] Initiating system poweroff...")
            self._execute_system_poweroff()

        print("[DinoDesk] Shutdown complete. Exiting...")
        # Terminate program process cleanly
        os._exit(0)

    def _execute_system_poweroff(self):
        """Execute Raspberry Pi system poweroff trying multiple mechanisms (systemctl, logind dbus, sudo -n, direct)."""
        import subprocess

        commands = [
            # 1. systemctl poweroff (often allowed without password by systemd-logind/polkit)
            ["systemctl", "poweroff", "-i"],
            ["systemctl", "poweroff"],
            # 2. logind DBus method (standard desktop/session poweroff)
            ["dbus-send", "--system", "--print-reply", "--dest=org.freedesktop.login1",
             "/org/freedesktop/login1", "org.freedesktop.login1.Manager.PowerOff", "boolean:true"],
            # 3. Non-interactive sudo (avoids "terminal is required to read password" hang)
            ["sudo", "-n", "poweroff"],
            ["sudo", "-n", "shutdown", "-h", "now"],
            # 4. Direct binary paths
            ["/sbin/poweroff"],
            ["/sbin/shutdown", "-h", "now"],
            ["poweroff"],
            ["shutdown", "-h", "now"],
        ]

        for cmd in commands:
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    print(f"[DinoDesk] Poweroff command succeeded: {' '.join(cmd)}")
                    return
                else:
                    err_msg = res.stderr.strip() if res.stderr else res.stdout.strip()
                    print(f"[DinoDesk] '{' '.join(cmd)}' returned {res.returncode}: {err_msg}")
            except Exception as e:
                print(f"[DinoDesk] Failed to execute '{' '.join(cmd)}': {e}")

    def update_ui(self, text=None, sync_motors=True):
        if self.state == State.SLEEPING:
            self.last_subtitle = ""
        elif text is not None:
            self.last_subtitle = text

        expressions = {
            State.SLEEPING: "- _ -",
            State.IDLE: "•   •",
            State.LISTENING: "O   O",
            State.THINKING: "º   º",
            State.SPEAKING: "^   ^",
        }
        self.current_expression = expressions.get(self.state, "• •")

        if sync_motors and self.motors:
            self.motors.apply_fsm_pose(self.state.name)

        self.display.render(
            expression=self.current_expression,
            subtitle=self.last_subtitle,
            mode=self.mode
        )

        if self.web_server:
            self.web_server.broadcast_event("state_change", {
                "state": self.state.name,
                "mode": self.mode,
                "expression": self.current_expression,
                "subtitle": self.last_subtitle,
                "gateway_url": self.gateway_url,
                "motors": self.motors.get_state() if self.motors else {}
            })

    def handle_nose_down(self):
        """Nose button pressed down: wake up and start recording voice from USB mic."""
        if self.state in [State.IDLE, State.SLEEPING]:
            self.state = State.LISTENING
            self.audio_fx.wake_beep()
            self.update_ui(text="Listening... (Hold to talk)")
            self.audio_in.start_recording()

    def handle_nose_up(self):
        """Nose button released: stop recording voice and submit audio for inference."""
        if self.state == State.LISTENING:
            audio_file = self.audio_in.stop_recording()
            self.state = State.THINKING
            self.update_ui(text="Processing voice...")
            threading.Thread(
                target=self.run_inference,
                kwargs={"prompt": "", "audio_file": audio_file},
                daemon=True
            ).start()

    def handle_nose_press(self):
        """Compatibility click / toggle trigger for nose switch."""
        if self.state == State.LISTENING:
            self.handle_nose_up()
        elif self.state in [State.IDLE, State.SLEEPING]:
            self.handle_nose_down()

    def _parse_time_offset(self, time_str: str) -> float:
        """Parse natural language time offset string (e.g. '10 seconds', '5 mins', '1 hour') to seconds."""
        import re
        s = time_str.strip().lower()
        if s in ["a minute", "one minute", "1 min", "1 minute"]:
            return 60.0
        if s in ["half an hour", "30 mins", "30 minutes"]:
            return 1800.0
        if s in ["an hour", "one hour", "1 hour", "1 hr"]:
            return 3600.0

        m = re.match(r"^(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|hr|h)?$", s)
        if m:
            val = float(m.group(1))
            unit = (m.group(2) or "seconds").lower()
            if unit.startswith("h"):
                return val * 3600.0
            elif unit.startswith("m") and not unit.startswith("ms"):
                return val * 60.0
            else:
                return val
        return 60.0

    def _extract_reminder_intent(self, text: str):
        """Extract reminder text and delay (in seconds) if text matches reminder patterns."""
        import re
        cleaned = text.strip()
        if not cleaned:
            return "", 0.0

        # 1. "remind me in 10s to do something" / "set a reminder in 5 minutes to do something"
        p1 = re.search(
            r"^(?:please\s+)?(?:set\s+(?:a\s+)?reminder|remind\s+me)\s+in\s+([\d\w\.\s]+?)\s+(?:to|for|about|that)[:\s]+(.+)$",
            cleaned,
            re.IGNORECASE
        )
        if p1:
            delay = self._parse_time_offset(p1.group(1))
            task = p1.group(2).strip()
            return task, delay

        # 2. "remind me to do something in 10s"
        p2 = re.search(
            r"^(?:please\s+)?remind\s+me\s+to\s+(.+?)\s+in\s+([\d\w\.\s]+)$",
            cleaned,
            re.IGNORECASE
        )
        if p2:
            task = p2.group(1).strip()
            delay = self._parse_time_offset(p2.group(2))
            return task, delay

        # 3. "set a timer for 10s (to boil eggs)?"
        p3 = re.search(
            r"^(?:please\s+)?set\s+(?:a\s+)?timer\s+for\s+([\d\w\.\s]+?)(?:\s+(?:to|for)[:\s]+(.+))?$",
            cleaned,
            re.IGNORECASE
        )
        if p3:
            delay = self._parse_time_offset(p3.group(1))
            task = (p3.group(2) or "Timer finished!").strip()
            return task, delay

        # 4. "set a reminder for 5m (: do something / to do something)"
        p4 = re.search(
            r"^(?:please\s+)?set\s+(?:a\s+)?reminder\s+for\s+([\d\w\.\s]+?)(?:\s+(?:to|for|about)[:\s]+(.+)|:\s*(.+))?$",
            cleaned,
            re.IGNORECASE
        )
        if p4:
            delay = self._parse_time_offset(p4.group(1))
            task = (p4.group(2) or p4.group(3) or "Reminder").strip()
            return task, delay

        # 5. "remind me to do something" / "set a reminder to do something" (default 60s)
        p5 = re.search(
            r"^(?:please\s+)?(?:set\s+(?:a\s+)?reminder\s+to|remind\s+me\s+to)[:\s]+(.+)$",
            cleaned,
            re.IGNORECASE
        )
        if p5:
            task = p5.group(1).strip()
            return task, 60.0

        return "", 0.0

    def _extract_note_intent(self, text: str) -> str:
        """Extract note content from text if it matches note-taking patterns."""
        import re
        patterns = [
            r"^(?:please\s+)?(?:take\s+(?:a\s+)?note|make\s+(?:a\s+)?note|save\s+(?:a\s+)?note|note\s+down|write\s+down|remember\s+that)[:\s]+(.+)$",
            r"^(?:memo|note)[:\s]+(.+)$"
        ]
        for pat in patterns:
            m = re.search(pat, text.strip(), re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    def run_inference(self, prompt: str = "", audio_file: str = None):
        self.state = State.THINKING
        display_text = prompt if prompt else "Listening to audio..."
        self.update_ui(text=display_text)

        payload = {"prompt": prompt, "mode": self.mode.lower()}
        note_recorded = False
        reminder_recorded = False

        if audio_file and os.path.exists(audio_file):
            try:
                with open(audio_file, "rb") as f:
                    audio_bytes = f.read()
                if audio_bytes:
                    payload["audio_base64"] = base64.b64encode(audio_bytes).decode("utf-8")
                    payload["audio_format"] = "wav"
                    payload["audio_filename"] = os.path.basename(audio_file)
                    print(f"[DinoDesk] Attached audio file {audio_file} ({len(audio_bytes)} bytes) to inference")
            except Exception as e:
                print(f"[DinoDesk] Failed to read audio file: {e}")
        
        try:
            with requests.post(self.gateway_url, json=payload, stream=True, timeout=30) as resp:
                self.state = State.SPEAKING
                self.motors.apply_fsm_pose("SPEAKING")
                full_text = ""
                
                for line in resp.iter_lines():
                    if line:
                        line_str = line.decode("utf-8")
                        if line_str.startswith("data: ") and line_str != "data: [DONE]":
                            data = json.loads(line_str[6:])

                            # Check for structured tool actions (e.g. set_reminder, take_note)
                            if data.get("action") == "set_reminder" or "reminder" in data:
                                rem_val = data.get("reminder", "").strip()
                                rem_delay = float(data.get("delay_seconds", 60))
                                if rem_val:
                                    self.add_reminder(rem_val, delay_seconds=rem_delay)
                                    reminder_recorded = True

                            if data.get("action") == "take_note" or "note" in data:
                                note_val = data.get("note", "").strip()
                                if note_val:
                                    self.add_note(note_val)
                                    note_recorded = True

                            token = data.get("token", "")
                            if token:
                                full_text += token
                                
                                # Audio-visual-motor synchronization per token
                                self.audio_fx.typewriter_beep()
                                self.motors.trigger_tail_knock(times=1, delay_ms=50)
                                self.current_expression = "^   ^"
                                self.last_subtitle = full_text
                                self.display.render(
                                    expression=self.current_expression,
                                    subtitle=full_text,
                                    mode=self.mode
                                )
                                if self.web_server:
                                    self.web_server.broadcast_event("token", {
                                        "token": token,
                                        "full_text": full_text,
                                        "state": self.state.name,
                                        "expression": self.current_expression
                                    })
                            
        except Exception as e:
            self.update_ui(text=f"Error: {str(e)}")
            time.sleep(2)
        finally:
            # Fallback reminder intent extraction
            if not reminder_recorded and prompt:
                rem_text, rem_delay = self._extract_reminder_intent(prompt)
                if rem_text:
                    self.add_reminder(rem_text, delay_seconds=rem_delay)
                    reminder_recorded = True

            # Fallback note intent extraction if no reminder/tool event fired
            if not note_recorded and not reminder_recorded and prompt:
                extracted = self._extract_note_intent(prompt)
                if extracted:
                    self.add_note(extracted)

            # Clean up temporary audio file
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except Exception:
                    pass
        
        # Return to IDLE state
        self.state = State.IDLE
        self.update_ui()

    def run(self):
        print(f"[DinoDesk] Core FSM running. Mode: {self.mode}, Gateway: {self.gateway_url}")
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[DinoDesk] Stopping via KeyboardInterrupt...")
            self.shutdown(poweroff_system=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DinoDesk RPi Client")
    parser.add_argument("--gateway", default=DEFAULT_GATEWAY_URL, help="Gateway URL (e.g. http://127.0.0.1:8000/v1/chat/stream)")
    parser.add_argument("--port", type=int, default=int(os.getenv("WEB_PORT", 5000)), help="Local web testbench port")
    parser.add_argument("--no-web", action="store_true", help="Disable embedded local web testbench")
    args = parser.parse_args()

    app = DinoDesk(
        gateway_url=args.gateway,
        enable_web=not args.no_web,
        web_port=args.port
    )
    app.run()

