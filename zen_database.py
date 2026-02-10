import sqlite3
import datetime
import threading
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
                    daily_score INTEGER DEFAULT 0
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
            except sqlite3.OperationalError:
                try:
                    self.cursor.execute("ALTER TABLE daily_stats ADD COLUMN bank_balance INTEGER DEFAULT 0")
                except sqlite3.OperationalError: pass
                
                try:
                    self.cursor.execute("ALTER TABLE daily_stats ADD COLUMN daily_score INTEGER DEFAULT 0")
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
        Returns (bank_balance, daily_score) for TODAY.
        If today doesn't exist, it rolls over from the LAST ACTIVE DAY:
        New_Bank = Last_Bank + (Last_Score - Daily_Quota)
        """
        today = datetime.date.today().strftime("%Y-%m-%d")
        daily_goal = ECONOMY.get("DAILY_GOAL", 1200)
        
        with self.lock:
            # 1. Check if Today exists
            self.cursor.execute("SELECT bank_balance, daily_score FROM daily_stats WHERE date = ?", (today,))
            row = self.cursor.fetchone()
            if row: return row[0], row[1]
            
            # 2. Find Last Active Day
            self.cursor.execute("SELECT date, bank_balance, daily_score FROM daily_stats ORDER BY date DESC LIMIT 1")
            last_row = self.cursor.fetchone()
            
            start_balance = 0
            
            if last_row:
                # Calculate Rollover
                _, last_bank, last_score = last_row
                performance = last_score - daily_goal
                start_balance = last_bank + performance
                print(f"[SYSTEM] Rollover: Bank {last_bank} + (Score {last_score} - Goal {daily_goal}) = {start_balance}")
            
            # 3. Create Today
            self.cursor.execute("INSERT OR IGNORE INTO daily_stats (date, bank_balance, daily_score) VALUES (?, ?, ?)", (today, start_balance, 0))
            self.conn.commit()
            
            return start_balance, 0

    def update_balance(self, bank_change, daily_score_val, date_str=None):
        if not date_str:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
            
        with self.lock:
            self.cursor.execute("UPDATE daily_stats SET bank_balance = bank_balance + ?, daily_score = ? WHERE date = ?", (bank_change, daily_score_val, date_str))
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