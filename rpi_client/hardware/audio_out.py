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

import numpy as np

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

class SoundFX:
    def __init__(self, on_sound_event=None):
        self.on_sound_event = on_sound_event
        self.audio_ready = False
        if HAS_PYGAME:
            try:
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
                self.audio_ready = True
            except Exception as e:
                print(f"[SoundFX] Pygame mixer init failed ({e}). Audio will be logged/emitted virtually.")
        else:
            print("[SoundFX] Pygame not available. Audio will be logged/emitted virtually.")

    def _play_tone(self, freq, duration=0.04):
        if self.audio_ready:
            try:
                sample_rate = 22050
                volume = 0.05
                n_samples = int(sample_rate * duration)
                buf = (np.sin(2 * np.pi * np.arange(n_samples) * freq / sample_rate) > 0).astype(np.float32)
                sound = pygame.sndarray.make_sound((buf * 16383 * volume).astype(np.int16))
                sound.play()
            except Exception as e:
                pass

    def typewriter_beep(self):
        if self.on_sound_event:
            self.on_sound_event("typewriter")
        self._play_tone(880, duration=0.03)

    def wake_beep(self):
        if self.on_sound_event:
            self.on_sound_event("wake")
        self._play_tone(523, 0.08)
        self._play_tone(659, 0.08)

    def reminder_beep(self):
        if self.on_sound_event:
            self.on_sound_event("reminder_alert")
        # Cheerful 3-tone chime for reminder alarm (C5 -> E5 -> G5)
        self._play_tone(523, 0.09)
        time_sleep = 0.02
        try:
            import time
            time.sleep(time_sleep)
        except Exception:
            pass
        self._play_tone(659, 0.09)
        try:
            import time
            time.sleep(time_sleep)
        except Exception:
            pass
        self._play_tone(784, 0.14)


