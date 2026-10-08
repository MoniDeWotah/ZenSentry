import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zen_config as config
from zen_browser import BrowserAddressReader
from zen_detection import is_blocked, matches_app, matches_keywords
from zen_overlay import ZenOverlay
from zen_tracker import ZenTracker, is_audio_playing


class DetectionTests(unittest.TestCase):
    def test_article_mentions_are_not_blocked_apps(self):
        for process in ("chrome.exe", "SumatraPDF.exe", "Code.exe", "notepad.exe", None):
            with self.subTest(process=process):
                self.assertFalse(is_blocked(process, "How Facebook uses their datacenters",
                                            "https://example.org/research/facebook", config.BLACKLIST_APPS))

    def test_actual_app_identity_ignores_document_title(self):
        self.assertTrue(is_blocked("Discord.exe", "general", None, config.BLACKLIST_APPS))
        self.assertFalse(is_blocked("notepad.exe", "Discord", None, config.BLACKLIST_APPS))
        self.assertFalse(is_blocked("discord-helper.exe", "paper", None, config.BLACKLIST_APPS))

    def test_real_domains_and_subdomains_are_blocked(self):
        for address in ("https://facebook.com", "www.facebook.com/research", "https://m.facebook.com/",
                        "https://x.com/home", "https://twitter.com/home", "https://discord.gg/invite"):
            with self.subTest(address=address):
                self.assertTrue(is_blocked("chrome.exe", "documentation", address, config.BLACKLIST_APPS))

    def test_domain_mentions_and_lookalikes_are_not_blocked(self):
        for address in ("https://example.com/facebook.com", "https://facebook.com.example.org/",
                        "https://notfacebook.com", "https://facebook.com@example.org/",
                        "https://example.org/?q=facebook.com", "file:///facebook.com/paper.pdf",
                        None, "how facebook uses datacenters", "http://[invalid"):
            with self.subTest(address=address):
                self.assertFalse(is_blocked("chrome.exe", "Facebook", address, config.BLACKLIST_APPS))

    def test_browser_title_alone_cannot_prove_a_blocked_site(self):
        self.assertFalse(is_blocked("msedge.exe", "Facebook", None, config.BLACKLIST_APPS))

    def test_case_and_single_letter_rules(self):
        self.assertTrue(is_blocked("TWITTER.EXE", "home", None, ["Twitter"]))
        self.assertTrue(is_blocked("chrome.exe", "home", "https://X.COM", ["X"]))
        self.assertFalse(is_blocked(None, "Matrix examples", None, ["X"]))

    def test_whitelist_matches_identity_and_keywords_have_boundaries(self):
        self.assertTrue(matches_app("Code.exe", "Facebook paper", ["code"]))
        self.assertFalse(matches_app("chrome.exe", "barcode terminality", ["code", "terminal"]))
        self.assertTrue(matches_keywords("Python documentation", ["python"]))
        self.assertFalse(matches_keywords("shellfish pythonic", ["shell", "python"]))


class FakeOverlay:
    def __init__(self):
        self.exit_code = None
        self.pid = 12345
        self.kill_count = 0

    def poll(self):
        return self.exit_code

    def kill(self):
        self.kill_count += 1
        self.exit_code = -9

    def wait(self):
        return self.exit_code


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.db = MagicMock()
        self.db.get_bank_balance.return_value = (0, 0, 1400)
        self.db.get_last_login_date.return_value = None
        self.context = ("discord.exe", "general")
        self.address = None
        self.pid = 99
        self.idle = 0
        patches = [
            patch("zen_tracker.time.monotonic", side_effect=lambda: self.now),
            patch("zen_tracker.time.time", side_effect=lambda: self.now),
            patch("zen_tracker.get_idle_duration", side_effect=lambda: self.idle),
            patch("zen_tracker.is_audio_playing", return_value=False),
            patch("zen_tracker.subprocess.Popen", side_effect=lambda *a, **k: FakeOverlay()),
            patch.object(config, "GRACE_PERIOD", 10),
            patch.object(config, "UNLOCK_COOLDOWN", 30),
        ]
        started = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.popen = started[4]
        self.tracker = ZenTracker(self.db)
        self.window_patch = patch.object(self.tracker, "_get_active_window_info", side_effect=self.window)
        self.window_patch.start()
        self.addCleanup(self.window_patch.stop)

    def window(self):
        self.tracker.active_url = self.address
        self.tracker.active_pid = self.pid
        return self.context

    def open_wall(self):
        self.tracker.step()
        self.now += 11
        self.tracker.step()
        self.assertEqual(self.tracker.overlay_mode, "WALL")
        return self.tracker.overlay_process

    def test_wall_stays_alive_and_penalty_is_applied_once(self):
        wall = self.open_wall()
        score = self.tracker.current_score
        for _ in range(20):
            self.now += 2
            self.tracker.step()
        self.assertIs(self.tracker.overlay_process, wall)
        self.assertEqual(wall.kill_count, 0)
        self.assertEqual(self.popen.call_count, 2)  # Ghost, then wall.
        self.assertEqual(self.tracker.current_score, score)
        self.db.update_balance.assert_called_with(0, int(score))

    def test_unlock_has_cooldown_then_a_fresh_grace_period(self):
        wall = self.open_wall()
        score = self.tracker.current_score
        wall.exit_code = 11
        self.tracker.step()
        self.assertIsNone(self.tracker.overlay_process)
        self.now += 29
        self.tracker.step()
        self.assertIsNone(self.tracker.overlay_process)
        self.assertEqual(self.tracker.current_score, score)
        self.now += 1
        self.tracker.step()
        self.assertEqual(self.tracker.overlay_mode, "GHOST")
        self.now += 9
        self.tracker.step()
        self.assertEqual(self.tracker.overlay_mode, "GHOST")
        self.now += 2
        self.tracker.step()
        self.assertEqual(self.tracker.overlay_mode, "WALL")
        self.assertEqual(self.tracker.current_score, score + config.POINTS["PENALTY"])

    def test_slow_switches_during_recovery_do_not_add_penalties(self):
        wall = self.open_wall()
        wall.exit_code = 11
        self.tracker.step()
        self.now += 2
        self.context = ("code.exe", "paper")
        self.tracker.step()
        score = self.tracker.current_score
        self.now += 2
        self.context = ("discord.exe", "general")
        self.tracker.step()
        self.assertEqual(self.tracker.current_score, score)
        self.assertIsNone(self.tracker.overlay_process)

    def test_ghost_is_replaced_once_and_title_changes_do_not_restart_grace(self):
        self.tracker.step()
        ghost = self.tracker.overlay_process
        self.now += 6
        self.context = ("discord.exe", "another channel")
        self.tracker.step()
        self.now += 5
        self.tracker.step()
        self.assertEqual(ghost.kill_count, 1)
        self.assertEqual(self.tracker.overlay_mode, "WALL")

    def test_wall_focus_is_not_counted_as_a_switch(self):
        wall = self.open_wall()
        switches = self.db.log_event.call_count
        self.context = ("python.exe", "zensentry overlay - wall")
        self.pid = wall.pid
        self.now += 20
        self.tracker.step()
        self.assertEqual(self.db.log_event.call_count, switches)
        self.assertEqual(self.tracker.last_window_title, "general")

    def test_productive_context_closes_ghost(self):
        self.tracker.step()
        ghost = self.tracker.overlay_process
        self.context = ("SumatraPDF.exe", "How Facebook uses their datacenters")
        stats = self.tracker.step()
        self.assertEqual(stats["state"], "GREEN")
        self.assertEqual(ghost.kill_count, 1)
        self.assertIsNone(self.tracker.violation_start_time)

    def test_switching_from_blocked_to_unknown_restores_trust_button(self):
        self.tracker.step()
        blocked_ghost = self.tracker.overlay_process
        self.context = ("chrome.exe", "How Facebook uses their datacenters")
        self.tracker.step()
        self.assertEqual(blocked_ghost.kill_count, 1)
        self.assertEqual(self.popen.call_args.args[0][-1], "unknown")

    def test_confirmed_blocked_address_betrays_trust_even_without_title_change(self):
        self.context = ("chrome.exe", "same title")
        self.tracker.trust_start_time = self.now
        self.tracker.trust_mode_expiry = self.now + 60
        self.tracker.step()
        score = self.tracker.current_score
        self.address = "https://facebook.com"
        self.tracker.step()
        self.assertEqual(self.tracker.state, "RED")
        self.assertEqual(self.tracker.current_score, score + config.POINTS["BETRAYAL"])
        self.assertFalse(self.tracker.is_trust_active())

    def test_false_mention_does_not_betray_trust(self):
        self.tracker.trust_mode_expiry = self.now + 60
        self.tracker.trust_start_time = self.now
        self.context = ("chrome.exe", "How Facebook uses their datacenters")
        self.address = "https://example.org/paper"
        stats = self.tracker.step()
        self.assertEqual(stats["state"], "GREEN")
        self.assertGreaterEqual(self.tracker.current_score, 0)
        self.assertTrue(self.tracker.is_trust_active())

    def test_system_titles_are_exact_and_stats_are_complete(self):
        self.context = ("explorer.exe", "taskbar")
        stats = self.tracker.step()
        self.assertIn("target", stats)
        self.assertIn("multiplier", stats)
        self.context = ("notepad.exe", "idle research paper")
        self.assertEqual(self.tracker.step()["state"], "GREEN")

    def test_idle_pause_returns_tray_fields_and_wakes_without_old_timer(self):
        self.tracker.step()
        self.idle = 400
        self.now += 400
        stats = self.tracker.step()
        self.assertEqual(stats["state"], "PAUSED")
        self.assertIn("target", stats)
        self.assertIn("multiplier", stats)
        self.idle = 10
        self.tracker.step()
        self.assertFalse(self.tracker.is_paused)
        self.assertEqual(self.tracker.overlay_mode, "GHOST")

    def test_idle_prompt_closes_on_input_even_if_it_has_focus(self):
        self.context = ("code.exe", "work")
        self.idle = 400
        self.tracker.step()
        prompt = self.tracker.overlay_process
        self.assertEqual(self.tracker.overlay_mode, "IDLE_CHECK")
        self.idle = 0
        self.pid = prompt.pid
        self.context = ("python.exe", "zensentry overlay - idle_check")
        self.tracker.step()
        self.assertEqual(prompt.kill_count, 1)
        self.assertFalse(self.tracker.idle_overlay_active)

    def test_success_mode_preserves_economy_behavior(self):
        self.tracker.current_score = self.tracker.daily_target + 100
        stats = self.tracker.step()
        self.assertEqual(stats["state"], "CYAN")
        self.popen.assert_not_called()
        self.assertGreater(self.tracker.current_score, 1500)

    def test_unknown_context_can_still_be_trusted(self):
        self.context = ("chrome.exe", "How Facebook uses their datacenters")
        self.tracker.step()
        self.assertEqual(self.tracker.state, "YELLOW")
        self.assertEqual(self.popen.call_args.args[0][-1], "unknown")
        self.tracker.overlay_process.exit_code = 10
        self.assertEqual(self.tracker.step()["state"], "GREEN")


class OverlayTests(unittest.TestCase):
    def test_ghost_does_not_steal_keyboard_focus(self):
        with patch("zen_overlay.tk.Tk") as tk_root, patch.object(ZenOverlay, "_setup_ghost"):
            ZenOverlay("GHOST")
            tk_root.return_value.focus_force.assert_not_called()

    def test_wrong_phrase_keeps_same_wall_and_valid_phrase_signals_unlock(self):
        overlay = ZenOverlay.__new__(ZenOverlay)
        overlay.entry = MagicMock()
        overlay.root = MagicMock()
        overlay.exit_code = 0
        overlay.entry.get.return_value = "focus"
        overlay._check_unlock(None)
        overlay.root.destroy.assert_not_called()
        overlay.entry.get.return_value = " I will focus "
        overlay._check_unlock(None)
        overlay.root.destroy.assert_called_once()
        self.assertEqual(overlay.exit_code, 11)

    def test_trust_signals_after_cleanly_closing_window(self):
        overlay = ZenOverlay.__new__(ZenOverlay)
        overlay.root = MagicMock()
        overlay._trust_site()
        overlay.root.destroy.assert_called_once()
        self.assertEqual(overlay.exit_code, 10)


class BrowserReaderTests(unittest.TestCase):
    def test_foreground_identity_uses_window_pid_and_browser_address(self):
        tracker = ZenTracker.__new__(ZenTracker)
        tracker.browser_reader = MagicMock()
        tracker.browser_reader.read.return_value = "https://facebook.com"
        window = MagicMock()
        window.title = "Research"
        window._hWnd = 123

        def set_pid(hwnd, pid):
            self.assertEqual(hwnd, 123)
            pid._obj.value = 999

        with patch("zen_tracker.gw.getActiveWindow", return_value=window), \
                patch("zen_tracker.ctypes.windll.user32.GetWindowThreadProcessId", side_effect=set_pid), \
                patch("zen_tracker.psutil.Process") as process:
            process.return_value.name.return_value = "chrome.exe"
            self.assertEqual(tracker._get_active_window_info(), ("chrome.exe", "research"))
            self.assertEqual(tracker.active_pid, 999)
            self.assertEqual(tracker.active_url, "https://facebook.com")

    def test_cache_never_leaks_another_window_or_expired_address(self):
        reader = BrowserAddressReader()
        reader._thread = MagicMock()
        reader._result = ((1, "paper"), "https://facebook.com", 100)
        with patch("zen_browser.time.monotonic", return_value=101):
            self.assertEqual(reader.read(1, "paper"), "https://facebook.com")
            self.assertIsNone(reader.read(2, "paper"))
            self.assertIsNone(reader.read(1, "other title"))
        with patch("zen_browser.time.monotonic", return_value=106):
            self.assertIsNone(reader.read(1, "paper"))

    def test_typed_address_and_webpage_controls_are_not_visited_sites(self):
        automation = MagicMock()
        element = MagicMock()
        element.CurrentAutomationId = "omnibox"
        element.CurrentName = "Address and search bar"
        element.CurrentHasKeyboardFocus = True
        edits = automation.ElementFromHandle.return_value.FindAll.return_value
        edits.Length = 1
        edits.GetElement.return_value = element
        automation.ControlViewWalker.GetParentElement.return_value = None
        self.assertIsNone(BrowserAddressReader._read_address(automation, MagicMock(), 1))
        element.CurrentHasKeyboardFocus = False
        parent = MagicMock()
        parent.CurrentControlType = 50030
        automation.ControlViewWalker.GetParentElement.return_value = parent
        self.assertIsNone(BrowserAddressReader._read_address(automation, MagicMock(), 1))
        element.GetCurrentPattern.assert_not_called()

    def test_address_bar_value_is_read_without_keyboard_actions(self):
        automation = MagicMock()
        element = MagicMock()
        element.CurrentAutomationId = "urlbar-input"
        element.CurrentName = "Address bar"
        element.CurrentHasKeyboardFocus = False
        edits = automation.ElementFromHandle.return_value.FindAll.return_value
        edits.Length = 1
        edits.GetElement.return_value = element
        automation.ControlViewWalker.GetParentElement.return_value = None
        element.GetCurrentPattern.return_value.QueryInterface.return_value.CurrentValue = "https://facebook.com"
        self.assertEqual(BrowserAddressReader._read_address(automation, MagicMock(), 1), "https://facebook.com")


class AudioTests(unittest.TestCase):
    def test_volume_setting_alone_is_not_audio_playback(self):
        session = MagicMock()
        session.Process.name.return_value = "chrome.exe"
        session.SimpleAudioVolume.GetMute.return_value = False
        session.SimpleAudioVolume.GetMasterVolume.return_value = 1
        session.State = 0
        with patch("zen_tracker.AudioUtilities.GetAllSessions", return_value=[session]):
            self.assertFalse(is_audio_playing())
            session.State = 1
            meter = session._ctl.QueryInterface.return_value
            meter.GetPeakValue.return_value = 0
            self.assertFalse(is_audio_playing())
            meter.GetPeakValue.return_value = 0.2
            self.assertTrue(is_audio_playing())
            session.SimpleAudioVolume.GetMute.return_value = True
            self.assertFalse(is_audio_playing())


if __name__ == "__main__":
    unittest.main()
