# 🦖 DinoDesk AI - Product Requirements Document

## 1. Project Overview

* **Product Name:** DinoDesk AI (LEGO Pixel Dino AI Companion Robot)
* **Objective:** Build a smart desk AI companion robot featuring **Dual LLM Switching (Cloud ↔ Local)**, low-power RPi Zero 2 W control, Pirate Audio audiovisual effects, a **large LEGO nose button**, and an **optional sensor module system**.
* **Core Value:** Complete visual privacy (no camera), ultra-fast response times, and the flexibility to toggle between zero-cost private local inference and higher capable cloud model.

## 2. Hybrid LLM Switching Architecture (Cloud ↔ Local)

The robot connects to a unified **LLM Gateway (Router)** hosted on the local PC. RPi Zero sends identical API requests regardless of which model is currently active.

```
                               ┌─────────────────────────────────────────────────┐
                               │           [ Main PC / Local Gateway ]           │
                               │                                                 │
                               │   ┌─────────────────────────────────────────┐   │
                               │   │      Dynamic Model Router / Switch      │   │
                               │   └────────────────────┬────────────────────┘   │
                               │                        │                        │
                               │     ┌──────────────────┴──────────────────┐     │
                               │     ▼                                     ▼     │
                               │  [ LOCAL ENGINE ]              [ CLOUD ENGINE ] │
                               │  LM Studio / Gemma 4           Gemini Flash /   │
                               │  (Zero Latency, Private)       Gemini Live      │
                               └────────────────────────┬────────────────────────┘
                                                        │
                                                        │ Wi-Fi (Unified OpenAI-Compatible SSE Stream)
                                                        ▼
                               ┌─────────────────────────────────────────────────┐
                               │           [ DinoDesk AI (RPi Zero 2 W) ]        │
                               │  - Pirate Audio LCD & I2S Beep Speaker          │
                               │  - LEGO Nose Button & Optional Sensors          │
                               └─────────────────────────────────────────────────┘

```

### 2.1. Model Switching Modes & Triggers

| Mode | Active Model | Strengths / Primary Use Case | Switch Method |
| --- | --- | --- | --- |
| **Local Mode** *(Default)* | Gemma 4 (via LM Studio) | **Zero-cost, offline, 100% private.** Ideal for daily casual chats, desk timers, status checks, and fast responses. | - Double-press **Pirate Audio Button X**<br>- Or Option C Touch Sensor long-press (3s)<br>- Or Voice Command ("Switch to Cloud Mode") |
| **Cloud Mode** | Gemini Flash / Gemini Live | **High reasoning & complex task solving.** Ideal for coding help, complex math, deep explanations, or foreign language tutoring. | Same as above |
| **Auto-Hybrid Mode** *(Advanced)* | Automatic Routing | Uses **Gemma 4 locally by default**. If Gemma 4 detects a complex intent or explicit request for deep reasoning, it hands off the prompt to the Cloud Model. | Automatic System Routing |

## 3. Finite State Machine (FSM) & Interaction Definitions

```
                   ┌──────────────┐
                   │   Sleeping   │ (Idle / Nighttime / Inactive)
                   └──────┬───────┘
                          │ (Nose button click OR sensor trigger)
                          ▼
┌───────────┐      ┌──────────────┐
│   Idle    │ ───► │  Listening   │ (Capturing Audio / Listening to User)
└───────────┘      └──────┬───────┘
                          │ (Audio Input Complete)
                          ▼
                   ┌──────────────┐
                   │   Thinking   │ (Router selecting Cloud or Local -> Inferring)
                   └──────┬───────┘
                          │ (Token Streaming Response Starts)
                          ▼
                   ┌──────────────┐
                   │   Speaking   │ (Typewriter Text + Beep Audio Output)
                   └──────────────┘

```

| State | Entry Condition | Pirate Audio LCD Expression | 8-bit Beep Sound | LEGO Motor Motion (Neck/Tail) |
| --- | --- | --- | --- | --- |
| **1. Sleeping** | Inactive for 3 mins OR Lights off | Closed eyes (`- _ -`) | Silent | Head tilted slightly downward |
| **2. Idle** | Default standby | Eyes move autonomously (`•  •`) | Occasional eye-blink sounds | Neck moves slowly and autonomously |
| **3. Listening** | **Nose button click OR Sensor trigger** | **Eyes widen bright (`O  O`)** | **"Beep-Boop!" (Rising tone)** | **Head tilts 15° toward the user** |
| **4. Thinking** | Audio complete; Router selecting engine | Eyes spin continuously (`º  º`)<br>*(Cloud: Gold icon / Local: Green icon)* | Irregular processing tones (`tick-teek-poh`) | Neck sways slowly side-to-side |
| **5. Speaking** | Receiving SSE streaming tokens | Blinking eyes + Subtitle rendered | Typewriter beep per character | Tail knocks in sync with text length |

## 4. Hardware Architecture & Base BOM

### Core BOM (Required)

1. **Robot Main Controller:** Raspberry Pi Zero 2 W + 32GB MicroSD
2. **Host / Gateway PC:** Main PC running Local Router + LM Studio (Gemma 4) & Cloud API Keys
3. **Display/Audio Shield:** **Pimoroni Pirate Audio Speaker** (1.3" ST7789 LCD + I2S 1W Speaker)
4. **Base Trigger Switch:** Micro Limit Switch — inside the large LEGO nose button
5. **Audio Input:** USB Mini Microphone
6. **Motor Controller & Motors:** Compact PWM Motor Driver (DRV8833/PCA9685) + LEGO Technic Medium Angular Motors x 2
7. **Exterior Frame:** Basic LEGO Bricks & Technic Spring/Lever Mechanism Set

## 5. Pirate Audio Physical Button Mapping (Updated)

* **Button A (GPIO 5):** Cancel voice recognition immediately / Mute Microphone
* **Button B (GPIO 6):** Reset robot modules to home/center position
* **Button X (GPIO 16):** **Single-click:** Cycle expressions manually / **Double-click: Toggle Local ↔ Cloud Mode**
* **Button Y (GPIO 24):** Tail-knock test & Volume adjustment

## 📌 [Appendix] Expansion Sensor Module Options

| Option Code | Sensor Name | Protocol | Interaction Features & Scenarios | Recommendation |
| --- | --- | --- | --- | --- |
| **Option A** | **ToF Laser Distance Sensor**<br>(VL53L0X / VL53L1X) | I2C | **Hand Sweep & Contactless Proximity Trigger:**<br>Swipe a hand (10–15cm) to enter **`Listening`** state. | ⭐⭐⭐⭐⭐<br>(Top Contactless Pick) |
| **Option B** | **Ambient Light Sensor**<br>(BH1750 / TSL2561) | I2C | **Auto Day/Night Cycle:**<br>Enters **`Sleeping`** state when room lights turn off; wakes up to **`Idle`** when lights turn on. | ⭐⭐⭐⭐<br>(Great for Desk Companion) |
| **Option C** | **Capacitive Touch Sensor**<br>(TTP223 Module) | GPIO (Digital) | **Hidden Petting Detection & Mode Switch:**<br>Single tap to enter **`Listening`**; long-press (3s) to toggle **Local ↔ Cloud Mode**. | ⭐⭐⭐⭐⭐<br>(Dual Utility) |
| **Option D** | **Vibration/Knock Sensor**<br>(SW-420 / Piezo) | GPIO (Digital) | **Knock-to-Talk Trigger:**<br>Detects a double-knock ("knock-knock") on the desk surface to trigger **`Listening`**. | ⭐⭐⭐<br>(Desk Utility) |
| **Option E** | **NeoPixel RGB LEDs**<br>(WS2812B x 2~3) | GPIO (PWM) | **Engine Indicator & Status Lamp:**<br>Green glow for Local Mode (Gemma 4); Gold/Purple glow for Cloud Mode. | ⭐⭐⭐⭐<br>(Visual Mode Indicator) |

