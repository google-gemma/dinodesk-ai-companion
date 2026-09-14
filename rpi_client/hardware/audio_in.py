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
import wave
import struct
import shutil
import tempfile
import threading
import subprocess
from typing import Optional

try:
    import sounddevice as sd
    import numpy as np
    HAS_SOUNDDEVICE = True
except Exception:
    HAS_SOUNDDEVICE = False

try:
    import pyaudio
    HAS_PYAUDIO = True
except Exception:
    HAS_PYAUDIO = False


class AudioRecorder:
    """
    USB Microphone Audio Recorder for DinoDesk AI.
    Records audio while the push-to-talk nose button is held down.
    
    Supports:
    1. Linux ALSA `arecord` (Raspberry Pi default with USB mic).
    2. Python `sounddevice` / `pyaudio` if installed.
    3. Simulated / Fallback WAV generation for headless or test environments.
    """
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        output_dir: Optional[str] = None
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.output_dir = output_dir or tempfile.gettempdir()
        self.is_recording = False
        self._current_file = None
        self._record_thread = None
        self._stop_event = threading.Event()
        self._arecord_proc = None
        self._audio_frames = []
        self._start_time = 0.0

        # Check for system ALSA arecord tool (Linux / Raspberry Pi)
        self.has_arecord = shutil.which("arecord") is not None and sys.platform.startswith("linux")

    def start_recording(self) -> str:
        """Start capturing audio from USB microphone."""
        if self.is_recording:
            return self._current_file

        self.is_recording = True
        self._stop_event.clear()
        self._start_time = time.time()
        self._audio_frames = []

        filename = f"dinodesk_voice_{int(self._start_time * 1000)}.wav"
        self._current_file = os.path.join(self.output_dir, filename)

        if self.has_arecord:
            try:
                # Use ALSA arecord on Raspberry Pi for low-latency USB mic capture
                cmd = [
                    "arecord",
                    "-q",
                    "-D", "plughw:1",
                    "-f", "S16_LE",
                    "-r", str(self.sample_rate),
                    "-c", str(self.channels),
                    "-t", "wav",
                    self._current_file
                ]
                self._arecord_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print(f"[AudioRecorder] Started recording via arecord -> {self._current_file}")
                return self._current_file
            except Exception as e:
                print(f"[AudioRecorder] arecord spawn failed ({e}), falling back to Python capture.")
                self._arecord_proc = None

        if HAS_SOUNDDEVICE:
            try:
                self._record_thread = threading.Thread(target=self._record_sounddevice, daemon=True)
                self._record_thread.start()
                print(f"[AudioRecorder] Started recording via sounddevice -> {self._current_file}")
                return self._current_file
            except Exception as e:
                print(f"[AudioRecorder] sounddevice recording failed ({e}).")

        # Fallback thread for virtual / simulated recording
        self._record_thread = threading.Thread(target=self._record_virtual, daemon=True)
        self._record_thread.start()
        print(f"[AudioRecorder] Started simulated recording -> {self._current_file}")
        return self._current_file

    def _record_sounddevice(self):
        """Record audio stream using sounddevice library."""
        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=self.channels, dtype='int16') as stream:
                while not self._stop_event.is_set():
                    data, _ = stream.read(1024)
                    self._audio_frames.append(data.tobytes())
        except Exception as e:
            print(f"[AudioRecorder] Stream read error: {e}")

    def _record_virtual(self):
        """Simulated recording when no physical mic driver is available."""
        while not self._stop_event.is_set():
            time.sleep(0.05)

    def stop_recording(self) -> str:
        """Stop capturing audio and finalize the WAV file."""
        if not self.is_recording:
            return self._current_file or self._create_empty_wav()

        self.is_recording = False
        self._stop_event.set()
        record_duration = time.time() - self._start_time

        # If arecord subprocess is running, terminate it
        if self._arecord_proc:
            try:
                self._arecord_proc.terminate()
                self._arecord_proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._arecord_proc.kill()
                except Exception:
                    pass
            self._arecord_proc = None

        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=1.0)

        # Write WAV frames if collected via Python stream
        if self._audio_frames:
            try:
                with wave.open(self._current_file, "wb") as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(b"".join(self._audio_frames))
            except Exception as e:
                print(f"[AudioRecorder] Error saving WAV frames: {e}")

        # Ensure file exists and contains valid WAV data
        if not os.path.exists(self._current_file) or os.path.getsize(self._current_file) < 44:
            self._generate_fallback_wav(self._current_file, duration=max(0.5, record_duration))

        print(f"[AudioRecorder] Recording complete ({record_duration:.2f}s) -> {self._current_file}")
        return self._current_file

    def _generate_fallback_wav(self, file_path: str, duration: float = 1.0):
        """Generate a valid WAV audio file with soft ambient tone for simulation."""
        try:
            n_samples = int(self.sample_rate * duration)
            with wave.open(file_path, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                # Generate gentle sine wave / silence
                frames = bytearray()
                for i in range(n_samples):
                    val = int(500 * (1.0 if (i // 100) % 2 == 0 else -1.0))
                    frames.extend(struct.pack("<h", val))
                wf.writeframes(frames)
        except Exception as e:
            print(f"[AudioRecorder] Fallback WAV creation error: {e}")

    def _create_empty_wav(self) -> str:
        """Create and return a default empty WAV file path."""
        fallback_path = os.path.join(self.output_dir, f"dinodesk_default_{int(time.time())}.wav")
        self._generate_fallback_wav(fallback_path, duration=0.5)
        return fallback_path
