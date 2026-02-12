import sqlite3
import datetime
import threading
import math
from zen_config import DB_PATH, ECONOMY

class ZenDB:
    def __init__(self, db_path=None):
        self.db_path = db_path if db_path else DB_PATH
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.lock = threading.Lock()
        self.init_db()

    def init_db(self):
        with self.lock:
            # Events
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT,
                    details TEXT
                )
            ''')
            # Daily Stats
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    total_focus_minutes INTEGER DEFAULT 0,
                    distraction_count INTEGER DEFAULT 0,
                    focus_score INTEGER DEFAULT 0,
                    bank_balance INTEGER DEFAULT 0,
                    daily_score INTEGER DEFAULT 0,
                    daily_target INTEGER DEFAULT 1400
                )
            ''')
            # Meta (System State)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Migration check
            try:
                self.cursor.execute("SELECT bank_balance FROM daily_stats LIMIT 1")
                self.cursor.execute("SELECT daily_score FROM daily_stats LIMIT 1")
                self.cursor.execute("SELECT daily_target FROM daily_stats LIMIT 1")
            except sqlite3.OperationalError:
                try:
                    self.cursor.execute("ALTER TABLE daily_stats ADD COLUMN bank_balance INTEGER DEFAULT 0")
                except sqlite3.OperationalError: pass
                
                try:
                    self.cursor.execute("ALTER TABLE daily_stats ADD COLUMN daily_score INTEGER DEFAULT 0")
                except sqlite3.OperationalError: pass

                try:
                    self.cursor.execute("ALTER TABLE daily_stats ADD COLUMN daily_target INTEGER DEFAULT 1400")
                except sqlite3.OperationalError: pass
 
            self.conn.commit()

    def log_event(self, event_type, details=""):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            try:
                self.cursor.execute("INSERT INTO events (timestamp, event_type, details) VALUES (?, ?, ?)", (now, event_type, details))
                self.conn.commit()
            except sqlite3.Error as e:
                print(f"[DB ERROR] {e}")

    def get_bank_balance(self):
        """
        Returns (bank_balance, daily_score, daily_target) for TODAY.
        Implements User's Cumulative Debt & Bank Floor Logic:
        1. Debt Accumulates: Missed target adds to next day's target.
        2. Bank Surplus: Only surplus points go to bank.
        3. Target Floor: Target never drops below MIN_DAILY_TARGET (500).
        """
        today = datetime.date.today().strftime("%Y-%m-%d")
        base_goal = ECONOMY.get("DAILY_GOAL", 1400)
        min_target = ECONOMY.get("MIN_DAILY_TARGET", 500)
        
        with self.lock:
            # 1. Check if Today exists
            self.cursor.execute("SELECT bank_balance, daily_score, daily_target FROM daily_stats WHERE date = ?", (today,))
            row = self.cursor.fetchone()
            if row: return int(row[0]), int(row[1]), int(math.ceil(row[2]))
            
            # 2. Find Last Active Day
            self.cursor.execute("SELECT date, bank_balance, daily_score, daily_target FROM daily_stats ORDER BY date DESC LIMIT 1")
            last_row = self.cursor.fetchone()
            
            start_bank = 0
            final_target = base_goal
            
            if last_row:
                _, last_bank, last_score, last_target = last_row
                
                # --- Step A: Calculate Yesterday's Surplus/Deficit ---
                # Surplus = Score - Target. (Negative means missed target)
                # Ensure we are working with standard float/int first, but surplus should be int potentially?
                # Let's cast inputs to float first to be safe, then convert result to int.
                last_bank_f = float(last_bank)
                last_score_f = float(last_score)
                last_target_f = float(last_target)
                
                surplus = int(last_score_f - last_target_f)
                
                # --- Step B: Update Bank with Surplus ---
                # Bank holds the "extra" work done.
                # If surplus is negative, it subtracts from bank (using up saved work).
                raw_bank = int(last_bank_f + surplus)
                
                # --- Step C: Handle Debt (Negative Bank) ---
                debt = 0
                available_bank = 0
                
                if raw_bank < 0:
                    debt = abs(raw_bank) # This amount must be added to tomorrow's target
                    available_bank = 0   # Bank is empty
                else:
                    debt = 0
                    available_bank = raw_bank
                
                # --- Step D: Calculate New Target ---
                # Base Goal + Accumulating Debt
                # We want to ceil the debt if it was somehow float, but here it is int.
                # But base_goal might be float in config? Let's assume int.
                next_target_raw = base_goal + debt
                
                # --- Step E: Redeem Bank to reduce Target ---
                # We want to reduce Next Target using Available Bank, but respecting the FLOOR.
                # Max reduction allowed = Next_Target_Raw - MIN_TARGET
                
                max_redeemable = max(0, int(next_target_raw - min_target))
                bank_used = int(min(available_bank, max_redeemable))
                
                # Apply Bank Reduction
                target_after_bank = next_target_raw - bank_used
                start_bank = available_bank - bank_used
                
                # --- Step F: Enforce MAX Cap ---
                # "The person would go in perpetual debt otherwise"
                max_target = ECONOMY.get("MAX_DAILY_TARGET", 10000)
                
                # FINAL CEIL (just in case any float slipped in, though with int casts above it shouldn't)
                # If target_after_bank is float like 2841.99, we want 2842.
                # But we did int math above.
                # Use math.ceil if we were doing float math.
                # The user specifically mentioned: "current daily goal is 2841.99999999 for some reason make it a int(target+1) ceil it basically"
                # So to be absolutely sure, let's treat target_after_bank as potentially float from previous iterations/logic if we missed something.
                # But here we cast everything to int.
                # The issue likely comes from `zen_tracker` sending floats to `update_balance` which writes to DB.
                # So when we read `last_target` it might be float.
                # We cast `last_target_f` earlier.
                
                final_target = min(max_target, int(math.ceil(target_after_bank)))

                print(f"[SYSTEM] Rollover: Last(Bk:{last_bank} Sc:{last_score} Tg:{last_target}) -> Surplus:{surplus}")
                print(f"[SYSTEM] RawBank:{raw_bank} -> Debt:{debt} Avail:{available_bank}")
                print(f"[SYSTEM] TargetCalc: Base:{base_goal} + Debt:{debt} - UsedBank:{bank_used} = {target_after_bank} (Floor:{min_target})")
                print(f"[SYSTEM] FinalTarget (Capped at {max_target}): {final_target}")
                print(f"[SYSTEM] NewBank: {start_bank}")

            # 3. Create Today
            self.cursor.execute("INSERT OR IGNORE INTO daily_stats (date, bank_balance, daily_score, daily_target) VALUES (?, ?, ?, ?)", (today, start_bank, 0, final_target))
            self.conn.commit()
            
            return start_bank, 0, final_target

    def update_balance(self, bank_change, daily_score_val, date_str=None):
        if not date_str:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
            
        with self.lock:
            self.cursor.execute("UPDATE daily_stats SET bank_balance = bank_balance + ?, daily_score = ? WHERE date = ?", (int(bank_change), int(daily_score_val), date_str))
            self.conn.commit()

    def get_last_login_date(self):
        with self.lock:
            self.cursor.execute("SELECT value FROM meta WHERE key = 'last_login'")
            row = self.cursor.fetchone()
            return row[0] if row else None

    def set_last_login_today(self):
        today = datetime.date.today().strftime("%Y-%m-%d")
        with self.lock:
            self.cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_login', ?)", (today,))
            self.conn.commit()

    def close(self):
        with self.lock:
            self.conn.close()