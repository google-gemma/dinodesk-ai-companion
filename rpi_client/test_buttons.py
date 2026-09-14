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
import pytest
from unittest.mock import MagicMock, patch
from hardware.buttons import InputController

def test_button_a_single_click():
    cancel_mock = MagicMock()
    poweroff_mock = MagicMock()

    inputs = InputController(
        on_nose_press=None,
        on_toggle_mode=None,
        on_cancel=cancel_mock,
        on_poweroff=poweroff_mock
    )

    # Single click
    inputs.trigger_btn_a()

    # Wait for single-click timer (0.42s) to fire
    time.sleep(0.5)

    assert cancel_mock.call_count == 1
    assert poweroff_mock.call_count == 0

def test_button_a_double_click():
    cancel_mock = MagicMock()
    poweroff_mock = MagicMock()

    inputs = InputController(
        on_nose_press=None,
        on_toggle_mode=None,
        on_cancel=cancel_mock,
        on_poweroff=poweroff_mock
    )

    # Double click within 400ms
    inputs.trigger_btn_a()
    time.sleep(0.1)
    inputs.trigger_btn_a()

    # Wait to ensure single-click timer was cancelled and did not fire
    time.sleep(0.5)

    assert poweroff_mock.call_count == 1
    assert cancel_mock.call_count == 0

def test_dinodesk_poweroff_method():
    with patch("os._exit") as mock_exit, \
         patch("subprocess.run") as mock_run, \
         patch("main.REMINDERS_FILE", "temp_rem.json"), \
         patch("main.NOTES_FILE", "temp_notes.json"):
        mock_run.return_value = MagicMock(returncode=0)
        from main import DinoDesk

        app = DinoDesk(enable_web=False)
        app.poweroff()

        # Check that shutdown executed
        assert app._running is False
        assert app._reminder_scheduler_running is False
        assert mock_exit.called
        assert mock_run.called
