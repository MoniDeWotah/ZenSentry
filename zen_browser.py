"""Read the foreground browser's address without stealing focus or blocking ticks."""

import queue
import threading
import time


class BrowserAddressReader:
    def __init__(self):
        self._requests = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._result = None
        self._thread = None

    def read(self, hwnd, title):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        key = (hwnd, title)
        try:
            self._requests.put_nowait(key)
        except queue.Full:
            pass
        with self._lock:
            result = self._result
        if result and result[0] == key and time.monotonic() - result[2] < 5:
            return result[1]
        return None

    def _run(self):
        import comtypes
        import comtypes.client

        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        try:
            module = comtypes.client.GetModule("UIAutomationCore.dll")
            automation = comtypes.client.CreateObject(module.CUIAutomation,
                                                       interface=module.IUIAutomation)
            while True:
                key = self._requests.get()
                try:
                    address = self._read_address(automation, module, key[0])
                except Exception:
                    address = None  # Unavailable evidence must not become a blacklist hit.
                with self._lock:
                    self._result = (key, address, time.monotonic())
        except Exception:
            # Browser accessibility may be unavailable on this machine.
            # Keep the reader harmless; the tracker can offer Trust for unknown pages.
            return
        finally:
            comtypes.CoUninitialize()

    @staticmethod
    def _read_address(automation, module, hwnd):
        root = automation.ElementFromHandle(hwnd)
        edits = root.FindAll(4, automation.CreatePropertyCondition(30003, 50004))
        for index in range(edits.Length):
            element = edits.GetElement(index)
            automation_id = element.CurrentAutomationId.casefold()
            name = element.CurrentName.casefold()
            if automation_id not in {"urlbar-input", "addresseditbox", "omnibox"} and name not in {
                "address and search bar", "search or enter web address", "address bar",
                "search with google or enter address", "search or enter address",
            }:
                continue
            # A webpage can contain an identically named edit. Only use browser
            # chrome controls, outside the page's Document subtree.
            parent = automation.ControlViewWalker.GetParentElement(element)
            inside_page = False
            while parent:
                if parent.CurrentControlType == 50030:  # Document
                    inside_page = True
                    break
                parent = automation.ControlViewWalker.GetParentElement(parent)
            if inside_page or element.CurrentHasKeyboardFocus:
                continue  # Typed navigation/search text is not a visited page.
            pattern = element.GetCurrentPattern(10002).QueryInterface(module.IUIAutomationValuePattern)
            return pattern.CurrentValue
        return None
