# Zen Sentry

Zen Sentry is a Python-based focus enforcement tool designed to help you maintain productivity by penalizing distractions and rewarding focus. It monitors your active window, tracks your "Focus Capital" (Points), and enforces penalties if you stray into blacklisted applications.

## How It Works

### 1. The Economy
- **Focus Capital (Daily Target)**: Your goal for the day (Default: 1400 points).
- **Bank Balance**: Stores *surplus* points earned above your daily target.
- **Debt Accumulation**: If you miss your Daily Target, the deficit is added to the *Next Day's Target*.
    - *Example*: Target 1400. Score 900. Next Day Target = 1400 + 500 = 1900.
- **Smart Redemption**: Accumulated Bank points automatically reduce your Daily Target, down to a minimum floor.
    - **Floor**: Target never drops below **500** (`MIN_DAILY_TARGET`).
    - **Cap**: Target never exceeds **10,000** (`MAX_DAILY_TARGET`) to prevent perpetual debt.
- **Rollover**: 
    - **Surplus**: Stored in Bank.
    - **Deficit**: Added to Tomorrow's Target.

### 2. Monitoring States
- **🟩 GREEN (Productive)**: Whitelisted app executables (e.g., VS Code, Obsidian) or titles containing whole session keywords. Multipliers increase streak (1.0x -> 1.5x).
- **🟨 YELLOW (Neutral)**: Browsers or unknown apps.
- **🟥 RED (Distraction)**: Blacklisted apps (e.g., Discord, Twitter). Triggers penalties.
- **🟦 CYAN (Success)**: Activated when you reach your Daily Goal. **Penalties disabled**, points accumulate at 0.5x rate.

App rules match the foreground app's executable identity. Browser rules match the
actual address-bar hostname, including subdomains, rather than the page title.
For example, a paper titled "How Facebook uses their datacenters" does not count
as Facebook. A PDF reader can be productive through the whitelist; an unknown
browser page can be approved with Trust.

Address detection supports Chrome, Edge, Firefox and compatible browser address
controls through Windows UI Automation. If accessibility, the browser version,
or localized control labels prevent reading the address, the page remains unknown
and offers Trust; a title alone never proves that a browser is on a blocked site.
Typing a URL into the address bar does not count as visiting it. Domain matching
does not match names in paths, query strings, or lookalike domains.

### 3. Penalties & Enforcement
- **Grace Period**: You have 10 seconds (configurable) to leave a Red app or approve an unknown Yellow context. Changing a distracting window's title does not restart the timer.
- **The Wall**: If you stay in an unapproved Red or Yellow context past the grace period:
    - A full-screen overlay blocks your view.
    - **Penalty**: -20 points are deducted immediately.
    - You must type "I will focus" to dismiss the wall.
    - Only one wall runs at a time. Tracking ticks and incorrect unlock text do not recreate it or repeat the penalty.
    - Unlocking gives you **30 seconds to switch context**, with no warning overlay or switch penalties. If you are still in an unapproved context afterward, a fresh grace period starts.
    - Background launches of a second ZenSentry instance are ignored so they cannot create competing walls.
- **Rapid Switch**: Switching from Red to Green and back to Red within 10s incurs a -10 point penalty.

### 4. Special Modes
- **Trust Mode (Ghost Overlay)**: When entering a Yellow app, a small "Ghost" overlay appears.
    - Click **"Trust (30m)"** to mark the current session as Trusted (Green behavior) for 30 minutes.
- **Idle Check**: If you are idle (no input) for 5 minutes, a check appears.
    - If ignored, you enter "PAUSED" state (no points).
    - **Move mouse or press any key to resume tracking immediately.**
    - Only audible playback keeps tracking awake; having the volume turned up alone does not.

## Installation & Usage

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *(Requires: `pygetwindow`, `pystray`, `Pillow`, `pycaw`, `pyaudio`)*

2. **Configuration**:
   - Edit `zen_config.json` to customize:
     - `WHITELIST_APPS` / `BLACKLIST_APPS`
     - `ECONOMY` values (Daily Goal, Penalty amounts)
     - `TIMING` (Grace period, idle timeout)
     - Optional `TIMING.UNLOCK_COOLDOWN` (seconds; defaults to 30)

3. **Run**:
   ```bash
   python zen_main.py
   ```
   or simply double click the `ZenSentry.vbs` file.
   
   - The app runs in the system tray.
   - Hover over the tray icon to see your Bank and Daily Score/Target.

## Persistence
- Data is saved to `zen_sentry.db` (SQLite).
- If you miss a day, the system detects it on next login and deducts the missed Daily Goal points from your Bank.

Configue through zen_config.json

## Detection regression checks

Run `python -m unittest discover -s tests -p test_focus_regressions.py -v` for
false title matches, real site detection, overlay lifecycle, unlock recovery,
idle handling, audio detection, and unchanged daily-goal behavior.
---
*Stay Focused.*
