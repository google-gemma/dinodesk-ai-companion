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
import pytest
from unittest.mock import MagicMock, patch

# Set dummy environment variables to prevent hardware / real server startup during test
os.environ["GATEWAY_URL"] = "http://127.0.0.1:8000/v1/chat/stream"

from main import DinoDesk, REMINDERS_FILE

@pytest.fixture
def dino_instance(tmp_path):
    # Use temporary test reminders file
    test_reminders = str(tmp_path / "test_reminders.json")
    test_notes = str(tmp_path / "test_notes.json")
    with patch("main.REMINDERS_FILE", test_reminders), patch("main.NOTES_FILE", test_notes):
        dino = DinoDesk(enable_web=False)
        yield dino
        dino._reminder_scheduler_running = False

def test_extract_reminder_intent_various_patterns(dino_instance):
    dino = dino_instance

    # Pattern 1: "remind me in 10 seconds to drink water"
    task, delay = dino._extract_reminder_intent("remind me in 10 seconds to drink water")
    assert task == "drink water"
    assert delay == 10.0

    # Pattern 1b: "please set a reminder in 5 minutes to stretch"
    task, delay = dino._extract_reminder_intent("please set a reminder in 5 minutes to stretch")
    assert task == "stretch"
    assert delay == 300.0

    # Pattern 2: "remind me to check the oven in 15 mins"
    task, delay = dino._extract_reminder_intent("remind me to check the oven in 15 mins")
    assert task == "check the oven"
    assert delay == 900.0

    # Pattern 3: "set a timer for 30s"
    task, delay = dino._extract_reminder_intent("set a timer for 30s")
    assert delay == 30.0

    # Pattern 3b: "set a timer for 2 minutes to boil eggs"
    task, delay = dino._extract_reminder_intent("set a timer for 2 minutes to boil eggs")
    assert task == "boil eggs"
    assert delay == 120.0

    # Pattern 4: "set a reminder for 1 hour: weekly sync"
    task, delay = dino._extract_reminder_intent("set a reminder for 1 hour: weekly sync")
    assert "weekly sync" in task
    assert delay == 3600.0

    # Pattern 5: "remind me to call mom" (default 60s)
    task, delay = dino._extract_reminder_intent("remind me to call mom")
    assert task == "call mom"
    assert delay == 60.0

def test_reminder_crud_operations(dino_instance):
    dino = dino_instance
    dino.clear_reminders()
    assert len(dino.get_reminders()) == 0

    # Add reminder
    rem = dino.add_reminder("take medicine", delay_seconds=120)
    assert rem["text"] == "take medicine"
    assert rem["delay_seconds"] == 120
    assert not rem["triggered"]
    assert len(dino.get_reminders()) == 1

    # Remaining seconds calculation
    reminders = dino.get_reminders()
    assert reminders[0]["remaining_seconds"] > 0

    # Add another reminder
    rem2 = dino.add_reminder("drink tea", delay_seconds=30)
    assert len(dino.get_reminders()) == 2

    # Delete reminder
    deleted = dino.delete_reminder(rem["id"])
    assert deleted is True
    assert len(dino.get_reminders()) == 1
    assert dino.get_reminders()[0]["id"] == rem2["id"]

    # Clear reminders
    dino.clear_reminders()
    assert len(dino.get_reminders()) == 0

def test_reminder_trigger_alert(dino_instance):
    dino = dino_instance
    dino.clear_reminders()

    # Add a reminder with 0.1s delay
    rem = dino.add_reminder("quick ping", delay_seconds=0.1)
    assert not rem["triggered"]

    # Wait for background scheduler to trigger
    time.sleep(0.8)

    # Check that reminder has been marked as triggered
    reminders = dino.get_reminders()
    assert len(reminders) == 1
    assert reminders[0]["triggered"] is True
