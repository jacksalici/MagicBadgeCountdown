# /// script
# requires-python = ">=3.10"
# dependencies = ["hidapi"]
# ///
"""Countdown timer for the BadgeMagic / LS32 LED badge (11x44, USB 0416:5020).

Shows the remaining time as -HHhMMm and re-uploads once a minute (every upload
rewrites the badge's flash, so there are no seconds).

Protocol taken from https://github.com/fossasia/led-name-badge-ls32 (lednamebadge.py).

Examples:
    uv run badge_countdown.py --target "2026-09-25 24:00" --tz AoE
    uv run badge_countdown.py --target "2026-10-01 09:30" --tz Europe/Rome
    uv run badge_countdown.py            # asks interactively
"""

import argparse
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import hid

VENDOR_ID, PRODUCT_ID = 0x0416, 0x5020
WIDTH, HEIGHT = 44, 11

# 5x7 pixel font ('#' = LED on).
FONT = {
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    "3": [" ### ", "#   #", "    #", "  ## ", "    #", "#   #", " ### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": [" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "],
    ":": [" ", "#", " ", " ", " ", "#", " "],
    " ": ["  "] * 7,
    "d": ["    #", "    #", " ####", "#   #", "#   #", "#   #", " ####"],
    "h": ["#    ", "#    ", "#### ", "#   #", "#   #", "#   #", "#   #"],
    "m": ["     ", "     ", "## # ", "# # #", "# # #", "# # #", "# # #"],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "!": ["#", "#", "#", "#", "#", " ", "#"],
    "-": ["   ", "   ", "   ", "###", "   ", "   ", "   "],
}
GLYPH_TOP = 2  # vertical offset of the 7-row glyphs inside the 11-row display


# ---------------------------------------------------------------- rendering

def render(text: str) -> list[list[int]]:
    """Render text into an 11x44 pixel matrix, horizontally centred."""
    columns: list[list[int]] = []
    for i, ch in enumerate(text):
        glyph = FONT[ch]
        if i:
            columns.append([0] * 7)  # 1 px spacing
        for x in range(len(glyph[0])):
            columns.append([1 if row[x] == "#" else 0 for row in glyph])
    if len(columns) > WIDTH:
        raise ValueError(f"'{text}' is {len(columns)} px wide, max {WIDTH}")
    left = (WIDTH - len(columns)) // 2
    pixels = [[0] * WIDTH for _ in range(HEIGHT)]
    for x, col in enumerate(columns):
        for y, on in enumerate(col):
            pixels[GLYPH_TOP + y][left + x] = on
    return pixels


def to_badge_bitmap(pixels: list[list[int]]) -> tuple[bytes, int]:
    """Pack pixels into the badge format: byte-columns of 8 px, 11 bytes each."""
    n_cols = (WIDTH + 7) // 8
    out = bytearray()
    for col in range(n_cols):
        for row in range(HEIGHT):
            byte = 0
            for bit in range(8):
                x = col * 8 + bit
                if x < WIDTH and pixels[row][x]:
                    byte |= 1 << (7 - bit)
            out.append(byte)
    return bytes(out), n_cols


def build_packet(bitmap: bytes, length: int, mode: int = 4, speed: int = 4,
                 blink: bool = False, brightness: int = 100) -> bytes:
    """Protocol header (64 bytes) + bitmap, padded to a multiple of 64 bytes."""
    h = bytearray(64)
    h[0:4] = b"wang"
    h[5] = {25: 0x40, 50: 0x20, 75: 0x10}.get(brightness, 0x00)
    h[6] = 0xFF if blink else 0x00                 # blink flags for all 8 slots
    h[8:16] = bytes([16 * (speed - 1) + mode] * 8)  # speed/mode per slot
    h[16], h[17] = length // 256, length % 256      # length of message slot 1
    now = datetime.now()
    h[38:44] = bytes([now.year % 100, now.month, now.day, now.hour, now.minute, now.second])
    buf = bytes(h) + bitmap
    buf += bytes(-len(buf) % 64)
    return buf


class Badge:
    def __init__(self):
        self.dev = None

    def open(self):
        self.dev = hid.device()
        self.dev.open(VENDOR_ID, PRODUCT_ID)

    def close(self):
        if self.dev:
            try:
                self.dev.close()
            except Exception:
                pass
        self.dev = None

    def show(self, text: str, blink: bool = False, brightness: int = 100, mode: int = 9):
        bitmap, length = to_badge_bitmap(render(text))
        packet = build_packet(bitmap, length, mode=mode, blink=blink, brightness=brightness)
        for attempt in range(2):
            try:
                if self.dev is None:
                    self.open()
                for i in range(0, len(packet), 64):
                    # first byte is the HID report id (0)
                    if self.dev.write(b"\x00" + packet[i:i + 64]) < 0:
                        raise OSError("hid write failed")
                return
            except (OSError, IOError):
                self.close()
                if attempt:
                    raise


# ------------------------------------------------------------ time handling

def parse_tz(name: str):
    n = name.strip()
    if n.lower() in ("aoe", "anywhere on earth"):
        return timezone(timedelta(hours=-12), "AoE")
    if n.lower() in ("local", ""):
        return datetime.now().astimezone().tzinfo
    m = re.fullmatch(r"(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?", n, re.I)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
        return timezone(sign * delta, n)
    if n.upper() in ("UTC", "GMT", "Z"):
        return timezone.utc
    return ZoneInfo(n)


def parse_target(text: str, tz) -> datetime:
    """Accepts 'YYYY-MM-DD HH:MM[:SS]'; '24:00' means midnight at the end of that day."""
    m = re.fullmatch(r"\s*(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?\s*", text)
    if not m:
        raise ValueError(f"Cannot parse '{text}', use 'YYYY-MM-DD HH:MM'")
    day = datetime.strptime(m.group(1), "%Y-%m-%d")
    hh, mm, ss = int(m.group(2)), int(m.group(3)), int(m.group(4) or 0)
    if hh == 24 and mm == 0 and ss == 0:
        return (day + timedelta(days=1)).replace(tzinfo=tz)
    return day.replace(hour=hh, minute=mm, second=ss, tzinfo=tz)


def format_remaining(seconds: int) -> str:
    """-HHhMMm, rounded up to the minute so it reads -00h00m exactly at the deadline.
    With 100+ hours the '-' is dropped to fit the 44 px width."""
    minutes = -(-seconds // 60)
    text = f"{minutes // 60:02d}h{minutes % 60:02d}m"
    return text if minutes >= 100 * 60 else "-" + text


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="LED badge countdown")
    ap.add_argument("--target", "-t", help="deadline, e.g. '2026-09-25 24:00'")
    ap.add_argument("--tz", "-z", default=None,
                    help="AoE, UTC, UTC+2, Europe/Rome, local ... (default: local)")
    ap.add_argument("--brightness", "-B", type=int, default=100, choices=(25, 50, 75, 100))
    ap.add_argument("--mode", "-m", type=int, default=9,
                    help="display mode: 0-8 standard (4 = still-centered), "
                         "9 = smooth, 10 = rotate (default: 9)")
    ap.add_argument("--dry-run", action="store_true", help="print only, don't touch the badge")
    args = ap.parse_args()

    target_str = args.target or input("Deadline (YYYY-MM-DD HH:MM): ")
    tz_str = args.tz if args.tz is not None else (
        input("Timezone [local] (e.g. AoE, UTC+2, Europe/Rome): ") if not args.target else "local")
    target = parse_target(target_str, parse_tz(tz_str))
    print(f"Counting down to {target.isoformat()}  "
          f"(= {target.astimezone().strftime('%a %d %b %H:%M:%S %Z')} local)")

    badge = Badge()
    last_text = None
    try:
        while True:
            now = datetime.now(timezone.utc)
            remaining = int((target - now).total_seconds() + 0.999)  # ceil
            if remaining <= 0:
                text, blink = "DONE!", True
            else:
                text, blink = format_remaining(remaining), False

            if text != last_text:
                print(f"\r{text:>10}", end="", flush=True)
                if not args.dry_run:
                    try:
                        badge.show(text, blink=blink, brightness=args.brightness, mode=args.mode)
                    except (OSError, IOError) as e:
                        print(f"\n[badge not reachable: {e}] retrying...")
                        time.sleep(2)
                        continue
                last_text = text
                if remaining <= 0:
                    print("\nTime's up!")
                    return

            # check every second; the text (and so the upload) only changes once a minute
            time.sleep(1 - (time.time() % 1) + 0.01)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        badge.close()


if __name__ == "__main__":
    sys.exit(main())
