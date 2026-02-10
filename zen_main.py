import threading
import time
import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item
import zen_config as config
from zen_database import ZenDB
from zen_tracker import ZenTracker 

class ZenSentryApp:
    def __init__(self):
        self.db = ZenDB()
        self.is_running = True
        self.is_tracking = True
        self.icon = None
        self.tracker = ZenTracker(self.db)
        self.tracker_thread = threading.Thread(target=self._tracker_loop, daemon=True)

    def _create_image(self, color):
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color)
        dc = ImageDraw.Draw(image)
        dc.ellipse((16, 16, 48, 48), fill="white")
        return image

    def _tracker_loop(self):
        print("[SYSTEM] Tracker Thread Started")
        while self.is_running:
            if self.is_tracking and self.icon:
                try:
                    stats = self.tracker.step()
                    
                    # Update Tooltip
                    self.icon.title = f"ZenSentry | Bank: {stats['bank']} | Daily: {stats['score']} / {stats['target']}"

                    # ICON LOGIC
                    if stats["state"] == "PAUSED":
                         self.icon.icon = self._create_image(config.ICON_COLOR_PAUSED)
                    
                    elif stats["state"] == "CYAN":
                         self.icon.icon = self._create_image(config.ICON_COLOR_SUCCESS)

                    elif self.tracker.is_trust_active(): # <--- NEW: Blue for Trust
                        self.icon.icon = self._create_image(config.ICON_COLOR_RESEARCH)
                        
                    elif stats["state"] == "GREEN":
                        self.icon.icon = self._create_image(config.ICON_COLOR_ACTIVE)
                    elif stats["state"] == "YELLOW":
                        self.icon.icon = self._create_image(config.ICON_COLOR_WARN)
                    elif stats["state"] == "RED":
                        self.icon.icon = self._create_image(config.ICON_COLOR_ALERT)
                        
                except Exception as e:
                    print(f"[ERROR] {e}")
            
            time.sleep(config.HEARTBEAT_INTERVAL)

    def on_toggle_log(self, icon, item):
        self.is_tracking = not self.is_tracking
        if self.is_tracking:
            self.db.log_event("SESSION", "Log In")
            icon.icon = self._create_image(config.ICON_COLOR_ACTIVE)
        else:
            self.db.log_event("SESSION", "Log Out")
            icon.icon = self._create_image(config.ICON_COLOR_PAUSED)

    def on_exit(self, icon, item):
        self.is_running = False
        self.db.close()
        icon.stop()

    def run(self):
        self.db.log_event("SYSTEM", "Application Started")
        
        # Removed "Research Mode" from menu
        menu = (
            item('Toggle Login/Logout', self.on_toggle_log),
            item('Exit', self.on_exit)
        )

        self.icon = pystray.Icon("ZenSentry", self._create_image(config.ICON_COLOR_ACTIVE), "ZenSentry", menu)
        self.tracker_thread.start()
        self.icon.run()

if __name__ == "__main__":
    app = ZenSentryApp()
    app.run()