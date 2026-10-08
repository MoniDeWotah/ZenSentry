import time
import datetime
import pygetwindow as gw
import zen_config as config
import subprocess
import sys
import ctypes
import os
import psutil
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
from zen_browser import BrowserAddressReader
from zen_detection import BROWSER_PROCESSES, is_blocked, matches_app, matches_keywords, process_name

# --- IDLE & AUDIO HELPERS ---
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]

def get_idle_duration():
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0

def is_audio_playing():
    try:
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            try:
                if session.Process and process_name(session.Process.name()) in BROWSER_PROCESSES | {"spotify", "vlc"}:
                    volume = session.SimpleAudioVolume
                    if session.State == 1 and not volume.GetMute() and volume.GetMasterVolume() > 0:
                        meter = session._ctl.QueryInterface(IAudioMeterInformation)
                        if meter.GetPeakValue() > 0.001:
                            return True
            except Exception:
                continue
        return False
    except: return False

class ZenTracker:
    def __init__(self, db_instance):
        self.db = db_instance
        
        # 1. Economy Setup 
        # Returns: (Start_Bank, Today_Score, Today_Target)
        self.bank_start_balance, self.current_score, self.daily_target = self.db.get_bank_balance()
        
        # 2. RUN STARTUP AUDIT (Ghost Debt Fix)
        # Audit logic might impact balance, so we reload.
        self._perform_startup_audit()

        # Reload after audit
        self.bank_start_balance, self.current_score, self.daily_target = self.db.get_bank_balance()
        
        self.multiplier = 1.0
        self.shadow_multiplier = 1.0 # Preserves streak during Trust
        
        self.state = "GREEN"
        self.last_window_title = ""
        self.last_date = datetime.date.today()
        
        # Timers
        self.streak_start_time = time.time()
        self.violation_start_time = None
        self.overlay_process = None
        self.overlay_mode = None
        self.overlay_blocked = False
        self.recovery_until = 0
        self.active_url = None
        self.active_pid = None
        self.browser_reader = BrowserAddressReader()
        
        # Modes
        self.trust_mode_expiry = 0     
        self.trust_start_time = 0
        self.trust_active_session = False
        
        self.is_paused = False
        self.goal_reached = False
        
        self.red_exit_time = 0 # Track when we left Red state
        
        self.idle_start_time = None
        self.idle_overlay_active = False
        self.idle_timeout_override = config.IDLE_TIMEOUT 
        
        self.penalty_applied = False

    def is_trust_active(self):
        return time.time() < self.trust_mode_expiry

    def _perform_startup_audit(self):
        """Checks if days were skipped and deducts penalties."""
        last_date_str = self.db.get_last_login_date()
        if not last_date_str: 
            self.db.set_last_login_today()
            return

        last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        today = datetime.date.today()
        delta = (today - last_date).days

        if delta > 1:
            missed_days = delta - 1
            # Penalty logic: X pts per missed day 
            # NOTE: With new debt logic, do we still need generic penalty? 
            # User didn't specify removal, but Debt handles "missed work". 
            # Let's keep strict "Absentee Penalty" separate from Performance Debt for now.
            penalty = missed_days * config.ECONOMY.get("DAILY_GOAL", 1400)
            print(f"[AUDIT] Missed {missed_days} days. Deducting {penalty} pts.")
            self.db.update_balance(-int(penalty), 0) # Updates Today's row
            self.db.log_event("AUDIT", f"Absentee Penalty: -{penalty}")
        
        self.db.set_last_login_today()

    def _get_active_window_info(self):
        self.active_pid = None
        self.active_url = None
        try:
            window = gw.getActiveWindow()
            if not window: return None, None
            title = window.title.casefold()
            process = None
            try:
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(window._hWnd, ctypes.byref(pid))
                self.active_pid = pid.value
                process = psutil.Process(pid.value).name()
            except (OSError, AttributeError, TypeError, psutil.Error):
                pass
            if process_name(process) in BROWSER_PROCESSES:
                self.active_url = self.browser_reader.read(window._hWnd, title)
            return process, title
        except: return None, None

    def _handle_midnight(self):
        today = datetime.date.today()
        if today != self.last_date:
            try:
                print("[SYSTEM] Midnight Reset.")
                # 1. Finalize Yesterday
                self.db.update_balance(0, int(self.current_score), date_str=self.last_date.strftime("%Y-%m-%d"))
                
                # 2. Trigger New Day Rollover
                self.bank_start_balance, _, self.daily_target = self.db.get_bank_balance()
                
                # 3. Reset Stats
                self.current_score = 0
                self.goal_reached = False
                
                self.db.set_last_login_today()
                self.db.log_event("SYSTEM", f"New Day. Target: {self.daily_target}")
                
                # 4. Update Date ONLY after success
                self.last_date = today
                
            except Exception as e:
                print(f"[ERROR] Midnight Rollover Failed: {e}")

    def _determine_state(self, title, process=None, address=None):
        if not title: return "YELLOW"
        
        # 0. Success Mode (Cyan) overrides everything if goal reached
        if self.current_score >= self.daily_target:
             self.goal_reached = True
             return "CYAN"

        self.goal_reached = False

        # 1. Blacklist
        if is_blocked(process, title, address, config.BLACKLIST_APPS): return "RED"
        
        # 2. Whitelist
        if matches_app(process, title, config.WHITELIST_APPS): return "GREEN"
        
        # 3. Trust Mode
        if time.time() < self.trust_mode_expiry: return "TRUSTED_YELLOW" 
        
        # 4. Keywords
        if matches_keywords(title, config.SESSION_KEYWORDS): return "GREEN"
        
        return "YELLOW"

    def _handle_overlay_ipc(self):
        if self.overlay_process:
            ret_code = self.overlay_process.poll()
            if ret_code is None:
                return False
            mode = self.overlay_mode
            self.overlay_process = None
            self.overlay_mode = None
            self.idle_overlay_active = False
            if mode == "WALL":
                # The old violation must not survive an acknowledgement. Also
                # protect against an unexpected wall exit becoming a respawn loop.
                self.recovery_until = time.monotonic() + config.UNLOCK_COOLDOWN
                self.violation_start_time = None
                self.penalty_applied = False
                self.red_exit_time = 0
            if ret_code == 10:  # TRUST ME SIGNAL
                self.trust_mode_expiry = time.time() + config.TRUST_DURATION
                self.trust_start_time = time.time()
                self.db.log_event("TRUST", "Activated Trust Mode")
                return True
        return False

    def _stats(self, notification=None, title=None):
        surplus = max(0, int(self.current_score) - self.daily_target)
        return {"state": "PAUSED" if self.is_paused else self.state,
                "score": int(self.current_score), "multiplier": self.multiplier,
                "bank": self.bank_start_balance + surplus, "target": self.daily_target,
                "title": title or self.last_window_title, "notify": notification}

    def _close_overlay(self):
        if self.overlay_process and self.overlay_process.poll() is None:
            self.overlay_process.kill()
            self.overlay_process.wait()
        self.overlay_process = None
        self.overlay_mode = None
        self.idle_overlay_active = False

    def step(self):
        self._handle_midnight()
        
        notification = None
        if self.goal_reached:
            notification = "DAILY GOAL REACHED! Penalties Disabled."

        process, title = self._get_active_window_info()
        if not title: title = "idle"

        if self._handle_overlay_ipc():
            # Trust Activated
            if self.state != "CYAN": self.state = "GREEN" # Keep Cyan if active
            self.violation_start_time = None
            self.trust_active_session = True
            self.shadow_multiplier = self.multiplier
            self.multiplier = 1.0

        # Our own wall/ghost is not a new user context. While the wall is open,
        # freeze enforcement even if an underlying window temporarily has focus.
        if self.overlay_process and (
                self.overlay_mode == "WALL" or
                (self.overlay_mode == "GHOST" and self.active_pid is not None and
                 self.active_pid == self.overlay_process.pid)):
            return self._stats(notification, title)

        # --- IDLE LOGIC ---
        idle_top = get_idle_duration()
        is_audio = is_audio_playing()
        
        # Green Idle Check
        if self.state in ["GREEN", "CYAN"] and idle_top > 300 and not is_audio and not self.idle_overlay_active:
             # Trigger "Are you there?" overlay
             self._trigger_overlay("IDLE_CHECK")
             self.idle_overlay_active = True
             
        # Dismiss Idle Overlay on Input/Audio
        if self.idle_overlay_active:
            if idle_top < 1 or is_audio:
                self._close_overlay()
        
        # Standard Idle Pause
        if idle_top > self.idle_timeout_override and not is_audio:
            if not self.is_paused: self.is_paused = True
            self.violation_start_time = None
            
            return self._stats(notification, title)
        
        if self.is_paused:
            self.is_paused = False
            self.violation_start_time = None
            # Reset override on wake up? Or keep it for session? Keeping for session as per user implication.

        # ------------------

        if title.strip().casefold() in {name.casefold() for name in config.SYSTEM_TITLES}:
             self.violation_start_time = None
             return self._stats(notification, title)

        raw_state = self._determine_state(title, process, self.active_url)
        recovering = time.monotonic() < self.recovery_until

        # Switch Logic
        if title != self.last_window_title:
            if not self.goal_reached and not recovering:
                self.current_score += config.POINTS["SWITCH_TAX"]
                
            
            # Shadow Restore Check
            if self.trust_active_session:
                current_state = raw_state
                if current_state == "GREEN":
                    self.multiplier = self.shadow_multiplier
                    self.trust_active_session = False
            
            self.db.log_event("SWITCH", f"To: {title[:30]}")
            self.last_window_title = title
            
            # Persist on switch
            self.db.update_balance(0, int(self.current_score)) # Just update score

        # An address can become available after the title has already been seen.
        # Check confirmed transitions, rather than charging for title mentions.
        if (raw_state == "RED" and self.state != "RED" and not recovering and
                self.is_trust_active() and self.trust_start_time > 0 and
                time.time() < self.trust_start_time + 120):
            self.current_score += config.POINTS["BETRAYAL"]
            self.trust_mode_expiry = 0
            self.db.log_event("PENALTY", "Trust betrayed: blocked app/site")
            self.db.update_balance(0, int(self.current_score))

        # RAPID SWITCH PENALTY (Red -> Green -> Red within 10s)
        # Check transition from previous state
        if self.state == "RED" and raw_state == "GREEN" and not recovering:
            self.red_exit_time = time.monotonic()
        
        if self.state in ["GREEN", "YELLOW"] and raw_state == "RED":
             if not recovering and self.red_exit_time and time.monotonic() - self.red_exit_time < config.RAPID_SWITCH_LIMIT:
                 if not self.goal_reached:
                     print("[PENALTY] Rapid Switch Detected!")
                     self.current_score += config.POINTS["RAPID_SWITCH"]
                     self.db.log_event("PENALTY", "Rapid Switch -10")

        # Map Trusted Yellow to Green behavior
        if raw_state == "TRUSTED_YELLOW": 
            self.state = "GREEN"
        else: 
            self.state = raw_state

        # Violation Logic
        if self.state in ["RED", "YELLOW"] and not self.goal_reached and not recovering:
            if self.violation_start_time is None: self.violation_start_time = time.monotonic()
            elapsed = time.monotonic() - self.violation_start_time
            
            if elapsed > config.GRACE_PERIOD:
                self._trigger_overlay("WALL")
                
                # Apply Penalty Once
                if not self.penalty_applied:
                    print(f"[PENALTY] Wall Hit! {config.POINTS['PENALTY']} pts")
                    self.current_score += config.POINTS["PENALTY"]
                    self.db.log_event("PENALTY", "Focus Breach Detected")
                    self.penalty_applied = True
                    self.db.update_balance(0, int(self.current_score))
            else:
                self._trigger_overlay("GHOST")
        else:
            self.violation_start_time = None
            self.penalty_applied = False # Reset flag
            if self.overlay_process and not self.idle_overlay_active: # Don't kill Idle Check
                self._close_overlay()

        # Economy
        if self.goal_reached: # Cyan Mode
             # 0.9x points, freeze on idle (already handled by idle check returning early?)
             # Actually, if idle but not paused (audio playing?), we still gain points?
             # User said: "Idle: Freezes points". 
             # If idle_sec > small_threshold? Or just relies on Pause?
             # Let's assume standard PAUSED logic handles the "Freeze", but we can be stricter.
             if idle_top > 60: # Strict idle freeze for Cyan
                 pass 
             else:
                 points = (config.POINTS["BASE_INCOME"] * self.multiplier * 0.5) / (60 / config.HEARTBEAT_INTERVAL)
                 self.current_score += points
                 
        elif self.state == "GREEN":
            # Only grow multiplier if strictly green (not just trusted yellow)
            if raw_state == "GREEN":
                self._update_multiplier()
            
            points = (config.POINTS["BASE_INCOME"] * self.multiplier) / (60 / config.HEARTBEAT_INTERVAL)
            self.current_score += points
        
        # Periodic Save
        if int(time.time()) % 60 == 0:
             self.db.update_balance(0, int(self.current_score))
             
        return self._stats(notification, title)

    def _update_multiplier(self):
        now = time.time()
        streak = (now - self.streak_start_time) / 60
        if streak > 30: self.multiplier = 1.5
        elif streak > 15: self.multiplier = 1.25
        else: self.multiplier = 1.0

    def _trigger_overlay(self, mode):
        blocked = self.state == "RED"
        if self.overlay_process and self.overlay_process.poll() is None:
            if self.overlay_mode == "WALL":
                return
            if self.overlay_mode == mode and (mode != "GHOST" or self.overlay_blocked == blocked):
                return
            self._close_overlay()
        
        cmd = [sys.executable, os.path.join(config.BASE_DIR, "zen_overlay.py"), mode,
               str(int(self.current_score)), self.last_window_title or "Unknown",
               "blocked" if blocked else "unknown"]
        self.overlay_process = subprocess.Popen(cmd)
        self.overlay_mode = mode
        self.overlay_blocked = blocked
