import tkinter as tk
import sys
import zen_config as config

class ZenOverlay:
    def __init__(self, mode="WALL", score=0, title="Unknown", blocked=False):
        self.root = tk.Tk()
        self.mode = mode
        self.score = int(score)
        self.title = title.lower()
        self.is_blacklisted = blocked
        self.exit_code = 0
        self.root.title(f"ZenSentry Overlay - {mode}")
        
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        if self.mode == "WALL":
            self._setup_wall(screen_width, screen_height)
        elif self.mode == "GHOST":
            self._setup_ghost(screen_width, screen_height)
        elif self.mode == "IDLE_CHECK":
            self._setup_idle(screen_width, screen_height)
        
        self.root.lift()
        if self.mode == "WALL":
            self.root.focus_force()
            self.entry.focus_set()

    def _setup_idle(self, w, h):
        self.root.geometry(f"500x200+{w//2-250}+{h//2-100}")
        self.root.configure(bg="#003333") 
        self.root.attributes("-alpha", 0.95)
        self.root.overrideredirect(True)

        tk.Label(self.root, text="MOVE MOUSE TO RESUME", font=("Arial", 20, "bold"), fg="#00FFFF", bg="#003333").pack(pady=40)
        
        tk.Label(self.root, text="Tracking Paused - User Idle", font=("Arial", 10), fg="#00AAAA", bg="#003333").pack(pady=5)

    def _setup_wall(self, w, h):
        self.root.geometry(f"{w}x{h}+0+0")
        self.root.configure(bg="black")
        frame = tk.Frame(self.root, bg="black")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        
        tk.Label(frame, text="FOCUS BREACHED", font=("Courier", 40, "bold"), fg="red", bg="black").pack(pady=20)
        reason = "Blacklisted App" if self.is_blacklisted else "Distraction Limit Exceeded"
        tk.Label(frame, text=f"Reason: {reason}", font=("Arial", 12), fg="#555", bg="black").pack(pady=10)
        tk.Label(frame, text="Type 'I will focus' to unlock.", font=("Arial", 14), fg="white", bg="black").pack(pady=10)
        tk.Label(frame, text=f"You will have {config.UNLOCK_COOLDOWN}s to switch back to work.",
                 font=("Arial", 12), fg="#aaaaaa", bg="black").pack(pady=5)

        self.entry = tk.Entry(frame, font=("Arial", 20), justify="center")
        self.entry.pack(pady=20, ipadx=10, ipady=5)
        self.entry.bind("<Return>", self._check_unlock)
        self.entry.focus_set()

    def _setup_ghost(self, w, h):
        width = 340
        height = 180
        x_pos = w - width - 20
        y_pos = h - height - 60
        
        self.root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")
        self.root.configure(bg="#1a1a1a")
        self.root.attributes("-alpha", 0.95)

        header_text = "⛔ Restricted Area" if self.is_blacklisted else "⚠️ Unknown Context"
        header_col = "#ff4444" if self.is_blacklisted else "#ffaa00"
        
        tk.Label(self.root, text=header_text, font=("Arial", 11, "bold"), fg=header_col, bg="#1a1a1a").pack(pady=(15,2))
        tk.Label(self.root, text=f"App: {self.title[:30]}...", font=("Consolas", 8), fg="#666", bg="#1a1a1a").pack(pady=0)
        tk.Label(self.root, text=f"Focus Capital: {self.score}", font=("Consolas", 10, "bold"), fg="white", bg="#1a1a1a").pack(pady=5)

        btn_frame = tk.Frame(self.root, bg="#1a1a1a")
        btn_frame.pack(pady=15, fill="x")

        # LOGIC: Differentiate Blacklist vs Unknown
        if self.is_blacklisted:
            # No buttons for blacklist
            tk.Label(self.root, text="Cannot Trust Blacklist", font=("Arial", 9), fg="#555", bg="#1a1a1a").pack(pady=5)
        else:
            btn_action = tk.Button(btn_frame, text="Trust (30m)", bg="#2a2a4a", fg="white", command=self._trust_site, width=15)
            btn_action.pack(side="left", padx=15)

        btn_drift = tk.Button(btn_frame, text="I'm Drifting", bg="#4a2a2a", fg="white", command=self.root.destroy, width=12)
        btn_drift.pack(side="right", padx=15)

    def _check_unlock(self, event):
        if self.entry.get().strip().casefold() == "i will focus":
            self.exit_code = 11
            self.root.destroy()
        else:
            self.entry.delete(0, tk.END)
            self.entry.config(bg="#500000")

    def _trust_site(self):
        self.exit_code = 10
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.exit_code

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "WALL"
    score = sys.argv[2] if len(sys.argv) > 2 else "0"
    title = sys.argv[3] if len(sys.argv) > 3 else "Unknown App"
    blocked = len(sys.argv) > 4 and sys.argv[4] == "blocked"
    app = ZenOverlay(mode, score, title, blocked)
    sys.exit(app.run())
