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

import pytest
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from app import app, check_time, take_note, set_reminder, TOOLS, TOOL_REGISTRY

def test_check_time_function():
    """Test that check_time returns a non-empty human-readable time string with year."""
    time_str = check_time()
    assert isinstance(time_str, str)
    assert len(time_str) > 0
    # Should contain current year
    assert str(datetime.now().year) in time_str

def test_take_note_function():
    """Test that take_note returns confirmation with the content."""
    res = take_note("buy milk and eggs")
    assert "buy milk and eggs" in res
    assert "Note recorded" in res

    empty_res = take_note("")
    assert "Empty note" in empty_res

def test_set_reminder_function():
    """Test that set_reminder returns confirmation with content and delay."""
    res = set_reminder("drink water", 30)
    assert "drink water" in res
    assert "30 seconds" in res

    empty_res = set_reminder("")
    assert "Reminder" in empty_res
    assert "60 seconds" in empty_res

def test_tools_schema():
    """Test that check_time, take_note, and set_reminder tool schemas are properly registered."""
    tool_names = [t["function"]["name"] for t in TOOLS if t["type"] == "function"]
    assert "check_time" in tool_names
    assert "check_time" in TOOL_REGISTRY
    assert TOOL_REGISTRY["check_time"] == check_time

    assert "take_note" in tool_names
    assert "take_note" in TOOL_REGISTRY
    assert TOOL_REGISTRY["take_note"] == take_note

    assert "set_reminder" in tool_names
    assert "set_reminder" in TOOL_REGISTRY
    assert TOOL_REGISTRY["set_reminder"] == set_reminder

@pytest.mark.asyncio
async def test_chat_stream_local():
    """Test the streaming chat endpoint with local mode."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/chat/stream",
            json={"prompt": "Hello dino!", "mode": "local"}
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

@pytest.mark.asyncio
async def test_chat_stream_cloud():
    """Test the streaming chat endpoint with cloud mode."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/chat/stream",
            json={"prompt": "Hello Gemini!", "mode": "cloud"}
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

@pytest.mark.asyncio
async def test_chat_stream_default_mode():
    """Test that the endpoint defaults to local mode if mode is omitted."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/chat/stream",
            json={"prompt": "What time is it?"}
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

from unittest.mock import patch

@pytest.mark.asyncio
async def test_chat_stream_with_audio_local():
    """Test streaming chat endpoint with attached base64 audio payload in local mode using Whisper."""
    with patch("app.transcribe_audio_whisper", return_value="What time is it?"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/v1/chat/stream",
                json={
                    "prompt": "",
                    "audio_base64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
                    "audio_format": "wav",
                    "mode": "local"
                }
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

@pytest.mark.asyncio
async def test_chat_stream_with_audio_cloud():
    """Test streaming chat endpoint with attached base64 audio payload in cloud mode."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/chat/stream",
            json={
                "prompt": "Listen carefully",
                "audio_base64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
                "audio_format": "wav",
                "mode": "cloud"
            }
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

