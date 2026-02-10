# Zen Sentry

Zen Sentry is a Python-based focus enforcement tool designed to help you maintain productivity by penalizing distractions and rewarding focus. It monitors your active window, tracks your "Focus Capital" (Points), and enforces penalties if you stray into blacklisted applications.

## How It Works

### 1. The Economy
- **Focus Capital (Points)**: You earn points over time by staying in "Green" (Productive) or "Yellow" (Neutral) apps.
- **Bank Balance**: Your total accumulated points across days.
- **Daily Goal**: A target number of points to earn each day (Default: 1400).
- **Rollover**: If you exceed your Daily Goal, the excess points are added to your Bank. If you miss it, the deficit is subtracted from your Bank.

### 2. Monitoring States
- **🟩 GREEN (Productive)**: Whitelisted apps (e.g., VS Code, Obsidian) or titles containing session keywords. Multipliers increase streak (1.0x -> 1.5x).
- **🟨 YELLOW (Neutral)**: Browsers or unknown apps.
- **🟥 RED (Distraction)**: Blacklisted apps (e.g., Discord, Twitter). Triggers penalties.
- **🟦 CYAN (Success)**: Activated when you reach your Daily Goal. **Penalties disabled**, points accumulate at 0.5x rate.

### 3. Penalties & Enforcement
- **Grace Period**: You have 10 seconds (configurable) to close a Red app before consequences.
- **The Wall**: If you stay in a Red app past the grace period:
    - A full-screen overlay blocks your view.
    - **Penalty**: -20 points are deducted immediately.
    - You must type "I will focus" to dismiss the wall.
- **Rapid Switch**: Switching from Red to Green and back to Red within 10s incurs a -10 point penalty.

### 4. Special Modes
- **Trust Mode (Ghost Overlay)**: When entering a Yellow app, a small "Ghost" overlay appears.
    - Click **"Trust (30m)"** to mark the current session as Trusted (Green behavior) for 30 minutes.
- **Idle Check**: If you are idle (no input) for 5 minutes, a check appears.
    - If ignored, you enter "PAUSED" state (no points).
    - **Move mouse or press any key to resume tracking immediately.**

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

---
*Stay Focused.*
