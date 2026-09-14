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

import json
import os
import queue
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

class DinoWebServer:
    def __init__(self, dino_client, host="0.0.0.0", port=5000, static_dir=None):
        self.dino = dino_client
        self.host = host
        self.port = port
        self.static_dir = static_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        self.listeners = set()
        self.lock = threading.Lock()
        self.server = None
        self.thread = None

    def broadcast_event(self, event_type: str, data: dict):
        """Broadcast an event to all connected SSE clients."""
        with self.lock:
            payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
            dead_listeners = set()
            for q in self.listeners:
                try:
                    q.put_nowait(payload)
                except Exception:
                    dead_listeners.add(q)
            self.listeners -= dead_listeners

    def start(self):
        server_instance = self

        class RequestHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=server_instance.static_dir, **kwargs)

            def log_message(self, format, *args):
                # Suppress noisy access logs
                pass

            def do_GET(self):
                parsed = urlparse(self.path)
                
                if parsed.path == "/api/status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    status = {
                        "state": server_instance.dino.state.name,
                        "mode": server_instance.dino.mode,
                        "gateway_url": server_instance.dino.gateway_url,
                        "last_subtitle": getattr(server_instance.dino, "last_subtitle", ""),
                        "expression": getattr(server_instance.dino, "current_expression", "•   •"),
                        "notes_count": len(server_instance.dino.notes) if hasattr(server_instance.dino, "notes") else 0,
                        "reminders_count": len(server_instance.dino.reminders) if hasattr(server_instance.dino, "reminders") else 0,
                        "motors": server_instance.dino.motors.get_state() if getattr(server_instance.dino, "motors", None) else {}
                    }
                    self.wfile.write(json.dumps(status).encode("utf-8"))
                    return

                elif parsed.path == "/api/notes":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    notes = server_instance.dino.get_notes() if hasattr(server_instance.dino, "get_notes") else []
                    self.wfile.write(json.dumps({"notes": notes, "count": len(notes)}).encode("utf-8"))
                    return

                elif parsed.path == "/api/reminders":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    reminders = server_instance.dino.get_reminders() if hasattr(server_instance.dino, "get_reminders") else []
                    self.wfile.write(json.dumps({"reminders": reminders, "count": len(reminders)}).encode("utf-8"))
                    return

                elif parsed.path == "/api/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    client_queue = queue.Queue(maxsize=100)
                    with server_instance.lock:
                        server_instance.listeners.add(client_queue)

                    # Send initial state
                    init_data = {
                        "state": server_instance.dino.state.name,
                        "mode": server_instance.dino.mode,
                        "gateway_url": server_instance.dino.gateway_url,
                        "expression": getattr(server_instance.dino, "current_expression", "•   •"),
                        "subtitle": getattr(server_instance.dino, "last_subtitle", ""),
                        "notes": server_instance.dino.get_notes() if hasattr(server_instance.dino, "get_notes") else [],
                        "reminders": server_instance.dino.get_reminders() if hasattr(server_instance.dino, "get_reminders") else [],
                        "motors": server_instance.dino.motors.get_state() if getattr(server_instance.dino, "motors", None) else {}
                    }
                    self.wfile.write(f"event: state_change\ndata: {json.dumps(init_data)}\n\n".encode("utf-8"))
                    self.wfile.flush()

                    try:
                        while True:
                            try:
                                msg = client_queue.get(timeout=15.0)
                                self.wfile.write(msg.encode("utf-8"))
                                self.wfile.flush()
                            except queue.Empty:
                                # Keep-alive ping comment
                                self.wfile.write(b": ping\n\n")
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        with server_instance.lock:
                            server_instance.listeners.discard(client_queue)
                    return

                elif parsed.path == "/" or parsed.path == "/index.html":
                    return super().do_GET()
                else:
                    return super().do_GET()

            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_POST(self):
                parsed = urlparse(self.path)
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                try:
                    data = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    data = {}

                resp_data = {"status": "ok"}

                if parsed.path == "/api/button/nose":
                    threading.Thread(target=server_instance.dino.handle_nose_press, daemon=True).start()
                    resp_data["message"] = "Nose pressed"

                elif parsed.path == "/api/button/nose_down":
                    server_instance.dino.handle_nose_down()
                    resp_data["message"] = "Nose down - recording voice"
                    resp_data["state"] = server_instance.dino.state.name

                elif parsed.path == "/api/button/nose_up":
                    server_instance.dino.handle_nose_up()
                    resp_data["message"] = "Nose up - processing audio"
                    resp_data["state"] = server_instance.dino.state.name

                elif parsed.path == "/api/button/mode":
                    server_instance.dino.toggle_mode()
                    resp_data["mode"] = server_instance.dino.mode

                elif parsed.path == "/api/button/btn_x_double":
                    server_instance.dino.inputs.trigger_btn_x()
                    time.sleep(0.1)
                    server_instance.dino.inputs.trigger_btn_x()
                    resp_data["mode"] = server_instance.dino.mode

                elif parsed.path == "/api/button/btn_a":
                    server_instance.dino.inputs.trigger_btn_a()
                    resp_data["message"] = "Button A triggered (Single: Cancel)"

                elif parsed.path == "/api/button/btn_a_double":
                    server_instance.dino.inputs.trigger_btn_a_double()
                    resp_data["message"] = "Button A double-click triggered (Power off)"

                elif parsed.path == "/api/poweroff":
                    threading.Thread(target=server_instance.dino.poweroff, daemon=True).start()
                    resp_data["message"] = "Powering off Raspberry Pi"

                elif parsed.path == "/api/button/btn_b":
                    server_instance.dino.recenter()
                    resp_data["message"] = "Recentered"
                    resp_data["motors"] = server_instance.dino.motors.get_state() if getattr(server_instance.dino, "motors", None) else {}

                elif parsed.path == "/api/button/btn_y":
                    server_instance.dino.trigger_tail_knock(times=2)
                    resp_data["message"] = "Tail knock triggered"

                elif parsed.path == "/api/button/sleep":
                    from main import State
                    if server_instance.dino.state == State.SLEEPING:
                        server_instance.dino.state = State.IDLE
                    else:
                        server_instance.dino.state = State.SLEEPING
                    server_instance.dino.update_ui()
                    resp_data["state"] = server_instance.dino.state.name

                elif parsed.path == "/api/servos/move":
                    if getattr(server_instance.dino, "motors", None):
                        neck_tilt = data.get("neck_tilt")
                        neck_pan = data.get("neck_pan")
                        tail_speed = data.get("tail_speed", data.get("tail_angle"))
                        server_instance.dino.motors.move(
                            neck_tilt=neck_tilt,
                            neck_pan=neck_pan,
                            tail_speed=tail_speed
                        )
                        resp_data["motors"] = server_instance.dino.motors.get_state()
                    else:
                        resp_data["error"] = "Motors module not loaded"

                elif parsed.path == "/api/servos/knock":
                    if getattr(server_instance.dino, "motors", None):
                        count = int(data.get("count", 1))
                        delay_ms = int(data.get("delay_ms", 120))
                        server_instance.dino.motors.trigger_tail_knock(times=count, delay_ms=delay_ms)
                        resp_data["message"] = f"Triggered {count} tail knock(s)"
                    else:
                        resp_data["error"] = "Motors module not loaded"

                elif parsed.path == "/api/servos/preset":
                    preset = data.get("preset", "").lower()
                    if getattr(server_instance.dino, "motors", None):
                        if preset == "home" or preset == "recenter":
                            server_instance.dino.motors.recenter()
                        elif preset == "sleep":
                            server_instance.dino.motors.apply_fsm_pose("SLEEPING")
                        elif preset == "listen":
                            server_instance.dino.motors.apply_fsm_pose("LISTENING")
                        elif preset == "thinking" or preset == "thinking_sway":
                            server_instance.dino.motors.apply_fsm_pose("THINKING")
                        elif preset == "speaking" or preset == "tail_knock":
                            server_instance.dino.motors.apply_fsm_pose("SPEAKING")
                        else:
                            resp_data["error"] = f"Unknown preset: {preset}"
                        resp_data["motors"] = server_instance.dino.motors.get_state()
                    else:
                        resp_data["error"] = "Motors module not loaded"

                elif parsed.path == "/api/prompt":
                    prompt = data.get("prompt", "").strip()
                    override_mode = data.get("mode")
                    if override_mode and override_mode.upper() in ["LOCAL", "CLOUD"]:
                        server_instance.dino.mode = override_mode.upper()
                    
                    if not prompt:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Prompt cannot be empty"}).encode("utf-8"))
                        return

                    threading.Thread(target=server_instance.dino.run_inference, args=(prompt,), daemon=True).start()
                    resp_data["message"] = f"Inference started for prompt: {prompt}"

                elif parsed.path == "/api/config":
                    if "gateway_url" in data:
                        server_instance.dino.gateway_url = data["gateway_url"]
                        resp_data["gateway_url"] = server_instance.dino.gateway_url
                        server_instance.broadcast_event("config_change", {"gateway_url": server_instance.dino.gateway_url})

                elif parsed.path == "/api/notes":
                    text = data.get("text", data.get("content", data.get("note", ""))).strip()
                    if not text:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Note text cannot be empty"}).encode("utf-8"))
                        return
                    new_note = server_instance.dino.add_note(text)
                    resp_data["message"] = "Note saved"
                    resp_data["note"] = new_note
                    resp_data["notes"] = server_instance.dino.get_notes()

                elif parsed.path == "/api/notes/delete":
                    note_id = data.get("id")
                    if not note_id:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Note ID is required"}).encode("utf-8"))
                        return
                    deleted = server_instance.dino.delete_note(note_id)
                    resp_data["success"] = deleted
                    resp_data["notes"] = server_instance.dino.get_notes()

                elif parsed.path == "/api/notes/clear":
                    server_instance.dino.clear_notes()
                    resp_data["message"] = "All notes cleared"
                    resp_data["notes"] = []

                elif parsed.path == "/api/reminders":
                    text = data.get("text", data.get("content", data.get("reminder", ""))).strip()
                    delay = data.get("delay_seconds", data.get("delay", 60))
                    try:
                        delay = float(delay)
                    except (ValueError, TypeError):
                        delay = 60.0

                    if not text:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Reminder text cannot be empty"}).encode("utf-8"))
                        return
                    new_reminder = server_instance.dino.add_reminder(text, delay_seconds=delay)
                    resp_data["message"] = "Reminder set"
                    resp_data["reminder"] = new_reminder
                    resp_data["reminders"] = server_instance.dino.get_reminders()

                elif parsed.path == "/api/reminders/delete":
                    rem_id = data.get("id")
                    if not rem_id:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Reminder ID is required"}).encode("utf-8"))
                        return
                    deleted = server_instance.dino.delete_reminder(rem_id)
                    resp_data["success"] = deleted
                    resp_data["reminders"] = server_instance.dino.get_reminders()

                elif parsed.path == "/api/reminders/clear":
                    server_instance.dino.clear_reminders()
                    resp_data["message"] = "All reminders cleared"
                    resp_data["reminders"] = []
                else:
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))
                    return

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(resp_data).encode("utf-8"))

        self.server = ThreadingHTTPServer((self.host, self.port), RequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"[DinoWebServer] Local test server running at http://{self.host}:{self.port}/ (or http://localhost:{self.port}/)")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
