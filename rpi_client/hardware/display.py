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

import socket
import textwrap
import time
from PIL import Image, ImageDraw, ImageFont

try:
    import ST7789
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False

def get_local_ip() -> str:
    """Detect local IP address of the device."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

def is_emoji_character(char: str) -> bool:
    """Determine if a character is an emoji or special pictograph/symbol."""
    code = ord(char)
    return (
        0x1F000 <= code <= 0x1FAFF or  # Miscellaneous Symbols & Pictographs, Emoticons, Transport, etc.
        0x1F1E6 <= code <= 0x1F1FF or  # Flags (Regional Indicator Symbols)
        0x2600 <= code <= 0x27BF or    # Miscellaneous Symbols & Dingbats (⚡, ☕, ⌛, 🦖, etc.)
        0x2300 <= code <= 0x23FF or    # Miscellaneous Technical
        0x2B50 <= code <= 0x2B55 or    # Stars & special shapes
        0xFE00 <= code <= 0xFE0F or    # Variation Selectors
        code == 0x200D                 # Zero Width Joiner (ZWJ)
    )

def split_text_emoji_chunks(text: str):
    """Split text into contiguous segments of (substring, is_emoji)."""
    if not text:
        return []
    chunks = []
    current_chunk = []
    current_is_emoji = None

    for char in text:
        emoji_flag = is_emoji_character(char)
        if current_is_emoji is None:
            current_is_emoji = emoji_flag
            current_chunk.append(char)
        elif emoji_flag == current_is_emoji:
            current_chunk.append(char)
        else:
            chunks.append(("".join(current_chunk), current_is_emoji))
            current_chunk = [char]
            current_is_emoji = emoji_flag

    if current_chunk:
        chunks.append(("".join(current_chunk), current_is_emoji))
    return chunks

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE_LANCZOS = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", Image.BICUBIC))

_emoji_cache = {}

def get_rendered_emoji(emoji_str: str, emoji_font, target_size: int, fill=(255, 255, 255)):
    """Render emoji string at native strike size (e.g. 109px NotoColorEmoji) and resize to match target_size."""
    if not emoji_font or not emoji_str:
        return None
    cache_key = (emoji_str, target_size, fill)
    if cache_key in _emoji_cache:
        return _emoji_cache[cache_key]

    try:
        buf_w = max(160, len(emoji_str) * 130)
        buf_h = 160
        temp_img = Image.new("RGBA", (buf_w, buf_h), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)

        try:
            temp_draw.text((10, 10), emoji_str, font=emoji_font, fill=fill, embedded_color=True)
        except (TypeError, ValueError):
            temp_draw.text((10, 10), emoji_str, font=emoji_font, fill=fill)

        bbox = temp_img.getbbox()
        if not bbox:
            return None

        x0 = max(0, bbox[0] - 1)
        y0 = max(0, bbox[1] - 1)
        x1 = min(buf_w, bbox[2] + 1)
        y1 = min(buf_h, bbox[3] + 1)
        cropped = temp_img.crop((x0, y0, x1, y1))

        orig_w, orig_h = cropped.size
        if orig_h == 0 or orig_w == 0:
            return None

        scale = target_size / float(orig_h)
        new_w = max(1, int(round(orig_w * scale)))
        new_h = max(1, int(round(orig_h * scale)))

        resized = cropped.resize((new_w, new_h), RESAMPLE_LANCZOS)
        _emoji_cache[cache_key] = resized
        return resized
    except Exception:
        return None

def measure_multilingual_text(draw: ImageDraw.ImageDraw, text: str, font_cjk, font_emoji, target_size: int = 16):
    """Calculate the total width and height for text with mixed CJK/Latin and emoji matching target_size."""
    chunks = split_text_emoji_chunks(text)
    total_w = 0
    max_h = target_size
    for chunk_text, is_emoji in chunks:
        if is_emoji and font_emoji:
            emoji_img = get_rendered_emoji(chunk_text, font_emoji, target_size)
            if emoji_img:
                total_w += emoji_img.width + 2
                if emoji_img.height > max_h:
                    max_h = emoji_img.height
                continue

        try:
            bbox = draw.textbbox((0, 0), chunk_text, font=font_cjk)
            chunk_w = bbox[2] - bbox[0]
            chunk_h = bbox[3] - bbox[1]
        except Exception:
            try:
                chunk_w = int(font_cjk.getlength(chunk_text))
                chunk_h = getattr(font_cjk, "size", target_size)
            except Exception:
                chunk_w = len(chunk_text) * target_size
                chunk_h = target_size
        total_w += chunk_w
        if chunk_h > max_h:
            max_h = chunk_h
    return total_w, max_h

def draw_multilingual_text(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple,
    text: str,
    font_cjk,
    font_emoji,
    target_size: int = 16,
    fill=(255, 255, 255),
):
    """Draw text segment by segment choosing CJK font or properly-scaled Emoji font."""
    chunks = split_text_emoji_chunks(text)
    cur_x, y = xy
    for chunk_text, is_emoji in chunks:
        if is_emoji and font_emoji:
            emoji_img = get_rendered_emoji(chunk_text, font_emoji, target_size, fill=fill)
            if emoji_img:
                emoji_y = y + max(0, (target_size - emoji_img.height) // 2)
                img.paste(emoji_img, (cur_x, emoji_y), mask=emoji_img)
                cur_x += emoji_img.width + 2
                continue

        draw.text((cur_x, y), chunk_text, fill=fill, font=font_cjk)
        try:
            bbox = draw.textbbox((cur_x, y), chunk_text, font=font_cjk)
            chunk_w = bbox[2] - bbox[0]
        except Exception:
            try:
                chunk_w = int(font_cjk.getlength(chunk_text))
            except Exception:
                chunk_w = len(chunk_text) * target_size
        cur_x += chunk_w

def _get_font(size: int, is_emoji: bool = False):
    """Attempt to load a TrueType font with the specified size, prioritizing CJK or Emoji fonts."""
    if is_emoji:
        emoji_candidates = [
            # Linux / Raspberry Pi OS Emoji fonts
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
            "/usr/share/fonts/opentype/noto/NotoColorEmoji.ttf",
            "/usr/share/fonts/truetype/ancient-scripts/Symbola.ttf",
            "/usr/share/fonts/truetype/symbola/Symbola.ttf",
            "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            # Windows Emoji fonts
            "seguiemj.ttf",
            "C:/Windows/Fonts/seguiemj.ttf",
            "Symbola.ttf",
            # macOS Emoji fonts
            "/System/Library/Fonts/Apple Color Emoji.ttc",
            "/Library/Fonts/Symbola.ttf",
        ]
        for font_name in emoji_candidates:
            # Try with embedded_color=True first for color emojis
            try:
                return ImageFont.truetype(font_name, size, embedded_color=True)
            except (TypeError, ValueError, OSError):
                try:
                    return ImageFont.truetype(font_name, size)
                except Exception:
                    continue
            except Exception:
                continue
        return None

    font_candidates = [
        # Linux / Raspberry Pi OS Multilingual & CJK fonts (Debian packages: fonts-noto-cjk, fonts-nanum, fonts-wqy-microhei, fonts-takao-gothic, etc.)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/takao-gothic/TakaoPGothic.ttf",
        "/usr/share/fonts/truetype/takao-gothic/TakaoGothic.ttf",
        "/usr/share/fonts/truetype/vlgothic/VL-PGothic-Regular.ttf",
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
        "/usr/share/fonts/truetype/baekmuk/dotum.ttf",
        # Windows Multilingual / CJK fonts (Korean, Japanese, Chinese, Unicode)
        "malgun.ttf",
        "malgunbd.ttf",
        "msgothic.ttc",
        "meiryo.ttc",
        "YuGothM.ttc",
        "msjh.ttc",
        "msyh.ttc",
        "arialuni.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arialuni.ttf",
        # macOS Multilingual / CJK fonts
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Generic names
        "NotoSansCJK-Regular.ttc",
        "NanumGothic.ttf",
        # Fallback fonts
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "arial.ttf",
        "Arial.ttf",
    ]
    for font_name in font_candidates:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

class DisplayManager:
    def __init__(self):
        self.last_rendered_image = None
        self.last_state = {"expression": "•   •", "subtitle": "", "mode": "LOCAL", "ip": ""}
        self._cached_ip = None
        self._last_ip_check = 0

        if HAS_HARDWARE:
            try:
                self.disp = ST7789.ST7789(
                    port=0, cs=ST7789.BG_SPI_CS_FRONT, dc=9, backlight=13, rst=None,
                    width=240, height=240, rotation=90, spi_speed_hz=80000000
                )
                self.disp.begin()
            except Exception as e:
                print(f"[DisplayManager] Hardware ST7789 init failed ({e}), using virtual display fallback.")
                self.disp = None
        else:
            self.disp = None
            print("[DisplayManager] ST7789 module not found. Running in virtual display mode.")

        self.font_badge = _get_font(14)
        self.font_ip = _get_font(13)
        self.font_large = _get_font(44)
        self.font_text = _get_font(16)
        self.font_emoji = _get_font(109, is_emoji=True)

    def get_ip(self) -> str:
        now = time.time()
        if self._cached_ip is None or (now - self._last_ip_check > 30):
            self._cached_ip = get_local_ip()
            self._last_ip_check = now
        return self._cached_ip

    def render(self, expression: str, subtitle: str = "", mode: str = "LOCAL", ip: str = None):
        current_ip = ip if ip is not None else self.get_ip()
        self.last_state = {"expression": expression, "subtitle": subtitle, "mode": mode, "ip": current_ip}
        img = Image.new("RGB", (240, 240), color=(10, 10, 15))
        draw = ImageDraw.Draw(img)

        # Mode Badge
        mode_color = (0, 255, 128) if mode == "LOCAL" else (255, 200, 0)
        draw.text((10, 8), f"[{mode}]", fill=mode_color, font=self.font_badge)

        # IP Address (placed right next to mode badge)
        try:
            bbox = draw.textbbox((10, 8), f"[{mode}]", font=self.font_badge)
            ip_x = bbox[2] + 6
        except Exception:
            ip_x = 75
        draw.text((ip_x, 9), current_ip, fill=(150, 175, 205), font=self.font_ip)

        # Facial Expression (Centered in upper area)
        try:
            text_w, text_h = measure_multilingual_text(draw, expression, self.font_large, self.font_emoji, target_size=44)
            x = max(0, (240 - text_w) // 2)
            y = max(35, (150 - text_h) // 2)
            draw_multilingual_text(
                img,
                draw,
                (x, y),
                expression,
                self.font_large,
                self.font_emoji,
                target_size=44,
                fill=(255, 255, 255)
            )
        except Exception:
            draw.text((60, 60), expression, fill=(255, 255, 255), font=self.font_large)

        # Subtitle Text (Bottom)
        if subtitle:
            draw.rectangle([(8, 155), (232, 232)], fill=(20, 20, 30), outline=(50, 50, 70))
            wrapped = textwrap.fill(subtitle[-80:], width=24)
            line_y = 160
            for line in wrapped.split("\n"):
                draw_multilingual_text(
                    img,
                    draw,
                    (14, line_y),
                    line,
                    self.font_text,
                    self.font_emoji,
                    target_size=16,
                    fill=(200, 220, 255),
                )
                line_y += 18

        self.last_rendered_image = img

        if self.disp is not None:
            self.disp.display(img)

