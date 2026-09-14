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
import json
import base64
import tempfile
import asyncio
from datetime import datetime
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from typing import Optional

app = FastAPI(title="DinoDesk Model Router")

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1/chat/completions")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SYSTEM_PROMPT = "You are DinoDesk, a witty pixel dino desk companion. Keep answers concise (under 2 sentences)."
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "base")
_whisper_model = None

def get_whisper_model():
    """Lazily load and cache the local Whisper model."""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(WHISPER_MODEL_NAME)
    return _whisper_model

def transcribe_audio_whisper(audio_base64: str, audio_format: str = "wav") -> str:
    """Decode base64 audio, write to temporary file, and transcribe via Whisper."""
    audio_bytes = base64.b64decode(audio_base64)
    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = get_whisper_model()
        result = model.transcribe(tmp_path, fp16=False)
        return result.get("text", "").strip()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def check_time() -> str:
    """Tool that returns the current local date and time."""
    now = datetime.now()
    return now.strftime("%I:%M %p on %A, %B %d, %Y")

def take_note(content: str = "") -> str:
    """Tool that records a note or memo for the user."""
    cleaned = content.strip() if content else ""
    return f"Note recorded: '{cleaned}'" if cleaned else "Empty note recorded."

def set_reminder(content: str = "", delay_seconds: int = 60) -> str:
    """Tool that schedules a timed reminder or alarm for the user."""
    cleaned = content.strip() if content else "Reminder"
    return f"Reminder set for '{cleaned}' in {int(delay_seconds)} seconds."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_time",
            "description": "Check the current local time and date. Use this tool whenever the user asks for the current time, date, day of the week, or what time it is.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_note",
            "description": "Take, record, or save a quick note, memo, or note for the user. Call this tool whenever the user asks to take a note, write something down, remember something, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The exact note content or memo text to save."
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set or schedule a timed reminder or timer/alarm for the user. Call this tool whenever the user asks to be reminded of something after a certain time, or to set a reminder/timer (e.g. 'remind me in 5 minutes to...', 'set a reminder for 10 seconds to...', 'set a timer for 1 minute').",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The message, task, or description of the reminder."
                    },
                    "delay_seconds": {
                        "type": "integer",
                        "description": "The delay in seconds from now when the reminder should trigger (e.g. 10 for 10 seconds, 60 for 1 minute, 300 for 5 minutes, 3600 for 1 hour). Defaults to 60."
                    }
                },
                "required": ["content"]
            }
        }
    }
]

TOOL_REGISTRY = {
    "check_time": check_time,
    "take_note": take_note,
    "set_reminder": set_reminder
}

class ChatRequest(BaseModel):
    prompt: Optional[str] = ""
    audio_base64: Optional[str] = None
    audio_format: Optional[str] = "wav"
    audio_filename: Optional[str] = None
    mode: str = "local"  # "local" or "cloud"

async def stream_openai_chat(
    url: str,
    headers: dict,
    model: str,
    prompt: str = "",
    audio_base64: Optional[str] = None,
    audio_format: str = "wav"
):
    if audio_base64:
        user_content = []
        text_val = prompt.strip() if prompt else "Please listen to the attached audio message and respond concisely (under 2 sentences)."
        user_content.append({"type": "text", "text": text_val})
        user_content.append({
            "type": "input_audio",
            "input_audio": {
                "data": audio_base64,
                "format": audio_format or "wav"
            }
        })
        user_msg = {"role": "user", "content": user_content}
    else:
        user_msg = {"role": "user", "content": prompt}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        user_msg
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "model": model,
            "messages": messages,
            "tools": TOOLS,
            "reasoning_effort": "low",
            "stream": True
        }

        tool_calls_dict = {}
        has_tool_call = False

        try:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                async for chunk in response.aiter_lines():
                    if chunk.startswith("data: ") and chunk != "data: [DONE]":
                        try:
                            data = json.loads(chunk[6:])
                        except json.JSONDecodeError:
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # 1. Text token streaming
                        token = delta.get("content", "")
                        if token:
                            yield f"data: {json.dumps({'token': token})}\n\n"

                        # 2. Tool call delta streaming
                        if "tool_calls" in delta and delta["tool_calls"]:
                            has_tool_call = True
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_dict:
                                    tool_calls_dict[idx] = {
                                        "id": tc.get("id", f"call_check_time_{idx}"),
                                        "type": "function",
                                        "function": {
                                            "name": tc.get("function", {}).get("name", ""),
                                            "arguments": tc.get("function", {}).get("arguments", "")
                                        }
                                    }
                                else:
                                    if "id" in tc and tc["id"]:
                                        tool_calls_dict[idx]["id"] = tc["id"]
                                    if "function" in tc:
                                        func_delta = tc["function"]
                                        if "name" in func_delta and func_delta["name"]:
                                            tool_calls_dict[idx]["function"]["name"] += func_delta["name"]
                                        if "arguments" in func_delta and func_delta["arguments"]:
                                            tool_calls_dict[idx]["function"]["arguments"] += func_delta["arguments"]

            # If tool calls were made, execute them and stream final answer
            if has_tool_call and tool_calls_dict:
                assistant_tool_calls = list(tool_calls_dict.values())
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": assistant_tool_calls
                })

                for tc in assistant_tool_calls:
                    func_name = tc["function"]["name"] or "check_time"
                    tool_id = tc["id"] or f"call_{func_name}"
                    args_raw = tc["function"].get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) and args_raw else {}
                    except Exception:
                        args = {}

                    if func_name in TOOL_REGISTRY:
                        try:
                            if isinstance(args, dict) and args:
                                tool_result = TOOL_REGISTRY[func_name](**args)
                            else:
                                tool_result = TOOL_REGISTRY[func_name]()
                        except TypeError:
                            tool_result = TOOL_REGISTRY[func_name]()
                        except Exception as e:
                            tool_result = f"Error executing {func_name}: {str(e)}"
                    else:
                        tool_result = f"Unknown tool: {func_name}"

                    if func_name == "take_note":
                        note_content = args.get("content", "") if isinstance(args, dict) else ""
                        if note_content:
                            yield f"data: {json.dumps({'action': 'take_note', 'note': note_content})}\n\n"

                    if func_name == "set_reminder":
                        rem_content = args.get("content", "") if isinstance(args, dict) else ""
                        rem_delay = args.get("delay_seconds", 60) if isinstance(args, dict) else 60
                        if rem_content:
                            yield f"data: {json.dumps({'action': 'set_reminder', 'reminder': rem_content, 'delay_seconds': rem_delay})}\n\n"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": func_name,
                        "content": str(tool_result)
                    })

                followup_payload = {
                    "model": model,
                    "messages": messages,
                    "stream": True
                }

                async with client.stream("POST", url, headers=headers, json=followup_payload) as followup_response:
                    async for chunk in followup_response.aiter_lines():
                        if chunk.startswith("data: ") and chunk != "data: [DONE]":
                            try:
                                data = json.loads(chunk[6:])
                            except json.JSONDecodeError:
                                continue
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    yield f"data: {json.dumps({'token': token})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error: {str(e)}'})}\n\n"

        yield "data: [DONE]\n\n"

async def stream_local_llm(prompt: str = "", audio_base64: Optional[str] = None, audio_format: str = "wav"):
    headers = {}
    user_prompt = prompt
    if audio_base64:
        try:
            transcribed_text = await asyncio.to_thread(transcribe_audio_whisper, audio_base64, audio_format)
            if transcribed_text:
                user_prompt = f"{prompt} {transcribed_text}".strip() if prompt else transcribed_text
            elif not user_prompt:
                user_prompt = "User sent an audio message, but no speech was detected."
        except Exception as e:
            yield f"data: {json.dumps({'token': f'Whisper transcription error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

    effective_prompt = user_prompt if user_prompt else "User sent a voice message. Respond politely as DinoDesk."
    async for item in stream_openai_chat(LM_STUDIO_URL, headers, "google/gemma-4-e2b-qat", effective_prompt):
        yield item

async def stream_gemini_cloud(prompt: str = "", audio_base64: Optional[str] = None, audio_format: str = "wav"):
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
    async for item in stream_openai_chat(url, headers, "gemini-2.5-flash", prompt, audio_base64, audio_format):
        yield item

@app.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest):
    if req.mode == "cloud":
        return StreamingResponse(
            stream_gemini_cloud(req.prompt, req.audio_base64, req.audio_format),
            media_type="text/event-stream"
        )
    return StreamingResponse(
        stream_local_llm(req.prompt, req.audio_base64, req.audio_format),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

