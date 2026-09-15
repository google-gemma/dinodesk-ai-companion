# DinoDesk AI Companion

A smart desk AI companion robot using Gemma 4 and Raspberry Pi.

[![Watch the video](https://img.youtube.com/vi/pXOTjxcNzdQ/0.jpg)](https://www.youtube.com/watch?v=pXOTjxcNzdQ)

## Project Layout

```
pc_gateway/
├── app.py                  # FastAPI Dynamic Model Gateway (Local Gemma 4 ↔ Gemini Flash)
└── requirements.txt
```

```
rpi_client/
├── main.py                 # Core Loop, Finite State Machine (FSM) & Web Testbench
├── web_server.py           # Embedded HTTP & SSE Server for PC Simulator
├── web/
│   └── index.html          # Interactive Testbench (LCD Screen, Buttons, Prompts, Audio)
├── hardware/               # ST7789 display, GPIO buttons, and sound effects
└── requirements.txt
```

```
scripts/
└── init.sh                 # Update the codes and launch DinoDesk app
```

## Running RPi Client Locally on PC

You can run `rpi_client` directly on your PC to simulate and test hardware interactions, buttons, expressions, and prompt streaming:

```bash
cd dinodesk-ai/rpi_client
python main.py
```

Then open **`http://localhost:5000`** in your browser to:
- 🦖 View real-time 240x240 LCD display output & facial expressions.
- 🔴 Simulate pressing the Nose Button, Mode Switch, and Double-Click actions.
- 🚀 Test custom prompts and preset questions with token-by-token typewriter streaming.
- 🔊 Hear browser audio sound effects (wake chord & typewriter beeps).
- ⚙️ Configure and test connectivity to the `pc_gateway`.

## Disclaimer

This is not an officially supported Google product. This project is not
eligible for the [Google Open Source Software Vulnerability Rewards
Program](https://bughunters.google.com/open-source-security).

This app is not an officially supported Google Product.
