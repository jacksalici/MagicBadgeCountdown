# MagicBadgeCountdown

Countdown to a deadline on a BadgeMagic / LS32 LED badge (11x44, USB `0416:5020`).
Shows the remaining time as `-HHhMMm`, updates once a minute and blinks `DONE!` at the end.

Based on the protocol from [fossasia/led-name-badge-ls32](https://github.com/fossasia/led-name-badge-ls32).

## Usage

Requires [uv](https://docs.astral.sh/uv/). Connect the badge via USB, then:

```bash
./countdown_aoe.sh                       # 25 Sept 2026, 24:00 Anywhere on Earth
uv run badge_countdown.py -t "2026-10-01 09:30" -z Europe/Rome
uv run badge_countdown.py                # asks for date and timezone
uv run badge_countdown.py -t "2026-10-01 09:30" --dry-run   # no badge, terminal only
```

Options: `-t/--target "YYYY-MM-DD HH:MM"` (`24:00` = end of day), `-z/--tz` (`AoE`, `UTC`, `UTC+2`, `Europe/Rome`, `local`), `-m/--mode` (display mode, default 9), `-B/--brightness` (25/50/75/100).

Or install it as a command with `uv sync` and run `uv run badge-countdown ...`.

## Notes

- On the stock firmware the badge briefly shows `M1-8` after each upload; mode 9 keeps the message visible while on USB.
- On Linux you may need the udev rule from the original project to run without `sudo`.
