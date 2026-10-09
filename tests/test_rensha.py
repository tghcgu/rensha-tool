"""Checks for rensha_tool.pyw that are safe to run on a working PC.

No real clicks are ever sent. The clicker logic runs against fake mice. The
only real input is a 1px cursor nudge to prove the mouse hook receives
events, and a short cursor move onto a test window to check the "over this
app's own window" detection; the cursor is put back both times.

Run from the project folder:

    py tests\\test_rensha.py

Exit code 0 means every check passed. A window flashes up briefly while the
UI checks run.
"""
import ctypes
import importlib.machinery
import importlib.util
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parent.parent

if sys.stdout is not None:
    sys.stdout.reconfigure(errors="backslashreplace")


def load_tool():
    path = ROOT / "rensha_tool.pyw"
    loader = importlib.machinery.SourceFileLoader("rensha_tool", str(path))
    spec = importlib.util.spec_from_loader("rensha_tool", loader)
    module = importlib.util.module_from_spec(spec)
    # dataclasses look the module up while its classes are being built.
    sys.modules["rensha_tool"] = module
    loader.exec_module(module)
    return module


rt = load_tool()
RealPhysicalButtons = rt.PhysicalButtons
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def wait_until(predicate, timeout=1.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return bool(predicate())


# ----------------------------------------------------------- real mouse hook
class RecordingButtons(rt.PhysicalButtons):
    def __init__(self, mouse):
        self.extras = []
        super().__init__(mouse)

    def _on_event(self, code, message, data):
        if data:
            self.extras.append(data.contents.dwExtraInfo)
        return super()._on_event(code, message, data)


def check_real_hook():
    mouse = rt.WindowsMouse()
    buttons = RecordingButtons(mouse)
    check("hook installs", buttons.start())

    # Zero-distance moves are dropped by Windows, so nudge 1px and back, then
    # put the cursor exactly where it was. No clicks are sent.
    saved = wintypes.POINT()
    mouse.user32.GetCursorPos(ctypes.byref(saved))
    for dx in (1, -1):
        event = rt.Input(
            type=rt.INPUT_MOUSE,
            union=rt.InputUnion(mi=rt.MouseInput(dx, 0, 0, 0x0001, 0, rt.RENSHA_SIGNATURE)),
        )
        mouse.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(rt.Input))
    received = wait_until(lambda: rt.RENSHA_SIGNATURE in buttons.extras)
    mouse.user32.SetCursorPos(saved.x, saved.y)
    check("hook receives events", len(buttons.extras) > 0, f"events={len(buttons.extras)}")
    check("signature reaches the hook", received)

    buttons.stop()
    check("hook thread exits on stop", not buttons._thread.is_alive())
    check("hook reports unavailable after stop", not buttons.available())


def check_hook_filtering():
    tracker = rt.PhysicalButtons(rt.WindowsMouse())  # not started: drive it by hand
    tracker._left = tracker._right = False

    def fire(message, extra):
        info = rt.MouseHookStruct()
        info.dwExtraInfo = extra
        tracker._on_event(rt.HC_ACTION, message, ctypes.pointer(info))

    fire(rt.WM_LBUTTONDOWN, rt.RENSHA_SIGNATURE)
    check("own injected press ignored", not tracker.left_down() and tracker.press_count() == 0)
    fire(rt.WM_LBUTTONDOWN, 0)
    check("physical press tracked and counted", tracker.left_down() and tracker.press_count() == 1)
    fire(rt.WM_LBUTTONUP, rt.RENSHA_SIGNATURE)
    check("own injected release ignored", tracker.left_down())
    fire(rt.WM_LBUTTONUP, 0)
    check("physical release tracked", not tracker.left_down())
    fire(rt.WM_RBUTTONDOWN, 12345)  # another injector, e.g. remote desktop
    check("foreign injected right press counts as the user", tracker.press_count() == 2)
    fire(rt.WM_RBUTTONUP, 0)

    tracker.resync(True, False)
    check("resync counts a press the hook missed", tracker.press_count() == 3 and tracker.left_down())
    tracker.resync(True, False)
    check("resync does not count a press twice", tracker.press_count() == 3)
    tracker.resync(False, False)


def check_cursor_detection():
    mouse = rt.WindowsMouse()
    saved = wintypes.POINT()
    mouse.user32.GetCursorPos(ctypes.byref(saved))
    root = tk.Tk()
    root.geometry("220x140+240+240")
    root.attributes("-topmost", True)
    root.update()
    try:
        mouse.user32.SetCursorPos(
            root.winfo_rootx() + root.winfo_width() // 2,
            root.winfo_rooty() + root.winfo_height() // 2,
        )
        time.sleep(0.05)
        over = mouse.cursor_over_own_window()
        mouse.user32.SetCursorPos(root.winfo_rootx() - 60, root.winfo_rooty() - 60)
        time.sleep(0.05)
        outside = mouse.cursor_over_own_window()
    finally:
        mouse.user32.SetCursorPos(saved.x, saved.y)
        root.destroy()
    check("cursor over this app's window is detected", over is True)
    check("cursor elsewhere is not this app", outside is False)


# ------------------------------------------------------------------- fakes
class FakeMouse:
    """Models the system's async key state, including what the tool injects."""

    def __init__(self):
        self.async_left = False
        self.async_right = False
        self.esc = False
        self.over_self = False
        self.latched = False
        self.pulses = 0
        self.onces = 0
        self.releases = 0

    def is_pressed(self, vk):
        return {
            rt.VK_LBUTTON: self.async_left,
            rt.VK_RBUTTON: self.async_right,
            rt.VK_ESCAPE: self.esc,
        }[vk]

    def cursor_over_own_window(self):
        return self.over_self

    def left_click_pulse(self):
        self.latched = True
        self.async_left = True  # the pair ends pressed
        self.pulses += 1

    def left_click_once(self):
        self.onces += 1  # down and up: the system ends released

    def left_latched_by_us(self):
        return self.latched

    def forget_left_latch(self):
        self.latched = False

    def release_left(self):
        if self.latched:
            self.async_left = False
            self.latched = False
            self.releases += 1


class FakeButtons:
    """Stands in for the hook: tests set .left to play the user's finger."""

    def __init__(self, available=True):
        self._available = available
        self.left = False
        self.right = False
        self.presses = 0

    def available(self):
        return self._available

    def left_down(self):
        return self.left

    def press_count(self):
        return self.presses

    def resync(self, left, right):
        if (left and not self.left) or (right and not self.right):
            self.presses += 1
        self.left, self.right = left, right


def new_clicker(available=True):
    mouse, buttons = FakeMouse(), FakeButtons(available)
    clicker = rt.RapidClicker(mouse, buttons)
    clicker.set_clicks_per_second(60)
    return mouse, buttons, clicker


def stop_thread(clicker):
    clicker._stop_event.set()
    clicker._thread.join(1)


# ------------------------------------------------------------ clicker logic
def check_trigger():
    m, b, c = new_clicker()
    c.start()
    b.left = True
    m.async_left = m.async_right = True
    check("trigger: pulses while both are held", wait_until(lambda: m.pulses > 3), f"pulses={m.pulses}")

    # The stuck-button race: the hook sees the finger leave, but our last
    # pulse landed after the physical release, so the system still holds it.
    b.left = False
    m.async_left = True
    check("race: the missing release is sent", wait_until(lambda: m.releases == 1 and not m.async_left))
    before = m.pulses
    time.sleep(0.1)
    check("race: no pulses after the release", m.pulses == before, f"extra={m.pulses - before}")
    check("race: clicker inactive", not c.is_active())

    m.releases = 0
    b.left = True
    m.async_left = True
    wait_until(lambda: m.pulses > before)
    m.async_right = False  # right released first, left still physically held
    time.sleep(0.1)
    check("right-first release keeps the user's own left press", m.releases == 0 and m.async_left)

    b.left = False
    m.async_left = False  # the user's release landed after our last press
    check("normal release: latch forgotten once the system shows it up", wait_until(lambda: not m.latched))
    check("normal release: no extra release sent", m.releases == 0)

    # If Windows drops the hook, its state freezes (b.left stays False here).
    # Presses then show only in the key state, and resync must pick them up.
    before = m.pulses
    m.async_left = m.async_right = True
    check("dropped hook: trigger still works through resync", wait_until(lambda: m.pulses > before + 2))
    stop_thread(c)

    m, b, c = new_clicker()
    c.start()
    m.over_self = True
    b.left = True
    m.async_left = m.async_right = True
    time.sleep(0.15)
    check("trigger: never clicks into this app's own window", m.pulses == 0)
    m.over_self = False
    check("trigger: works again off the window", wait_until(lambda: m.pulses > 0))
    stop_thread(c)


def check_afk():
    m, b, c = new_clicker()
    c.start()
    b.left = True
    m.async_left = True  # still holding when the countdown ends
    c.start_afk()
    time.sleep(0.1)
    check("AFK: waits while a button is held", m.onces == 0 and c.afk_active() and not c.afk_armed())
    b.left = False
    m.async_left = False
    check("AFK: arms and clicks after release", wait_until(lambda: c.afk_armed() and m.onces > 3), f"onces={m.onces}")
    check("AFK: not cancelled by its own clicks", c.afk_active() and c.afk_cancel_count() == 0)

    m.over_self = True
    wait_until(c.afk_paused)
    before = m.onces
    time.sleep(0.1)
    check("AFK: no clicks over this app's window", m.onces == before and c.afk_paused())
    b.left = True
    m.async_left = True  # a click on our own window, e.g. the stop button
    time.sleep(0.1)
    check("AFK: a click on this app's window does not cancel", c.afk_active() and c.afk_cancel_count() == 0)
    b.left = False
    m.async_left = False
    m.over_self = False
    check("AFK: resumes after leaving the window", wait_until(lambda: m.onces > before + 2 and not c.afk_paused()))

    b.left = True
    m.async_left = True
    check("AFK: a physical click elsewhere cancels", wait_until(lambda: not c.afk_active()) and c.afk_cancel_count() == 1)
    b.left = False
    m.async_left = False

    time.sleep(0.05)
    c.start_afk()
    wait_until(c.afk_armed)
    m.over_self = True
    m.esc = True
    check("AFK: Esc cancels even over this app's window", wait_until(lambda: not c.afk_active()) and c.afk_cancel_count() == 2)
    m.esc = False
    m.over_self = False
    stop_thread(c)


def check_no_hook_and_stop():
    m, b, c = new_clicker(available=False)
    c._last_injection_at = time.perf_counter()
    m.async_left = True
    check("no hook: a stale reading inside the grace is not a press", c._mouse_held(c._snapshot()) is False)
    time.sleep(rt.INJECTION_GRACE + 0.01)
    check("no hook: a real press after the grace counts", c._mouse_held(c._snapshot()) is True)

    m, b, c = new_clicker()
    c.start()
    m.latched = True
    m.async_left = True
    b.left = False
    c.stop()
    check("a latched injected press is released by the time stop() returns", m.releases == 1)


# ----------------------------------------------------------------------- UI
class StubButtons(FakeButtons):
    instances = []
    hook_ready = True

    def __init__(self, _mouse):
        super().__init__(available=True)
        StubButtons.instances.append(self)

    def start(self):
        return self.hook_ready

    def stop(self):
        pass


def quit_button_fits(app):
    app.update()
    buttons = [w for w in app.afk_button.master.winfo_children() if isinstance(w, ttk.Button)]
    quit_button = buttons[-1]
    return quit_button.winfo_ismapped() and (
        quit_button.winfo_rooty() + quit_button.winfo_height()
        <= app.winfo_rooty() + app.winfo_height()
    )


def check_ui():
    rt.PhysicalButtons = StubButtons
    mouse = FakeMouse()
    app = rt.RenshaApp(mouse)
    stub = StubButtons.instances[-1]
    app.update()

    check(
        "layout: quit button fully visible at the starting size",
        quit_button_fits(app),
        f"window={app.winfo_width()}x{app.winfo_height()} needed={app.winfo_reqheight()}",
    )
    app.hint_var.set("\n")
    app.update()
    two_lines = app.hint_label.winfo_reqheight()

    def hint_fits():
        app.update()
        return app.hint_label.winfo_reqheight() <= two_lines and quit_button_fits(app)

    app._afk_button_clicked()
    check("countdown: starts at 3", app._afk_countdown == 3)
    check("countdown: hint fits in two lines", hint_fits(), app.hint_var.get())
    mouse.over_self = True
    stub.presses += 1
    app._skip_countdown_on_click()
    check("countdown: a click on this app's window does not skip", app._afk_countdown == 3 and not app.clicker.afk_active())
    mouse.over_self = False
    stub.presses += 1
    app._skip_countdown_on_click()
    check(
        "countdown: a click elsewhere starts at once",
        app._afk_countdown == 0 and app.clicker.afk_active() and app._afk_after_id is None,
    )

    mouse.over_self = True
    wait_until(app.clicker.afk_paused)
    app._update_status()
    check("paused: shown as paused", app.status_var.get() == "一時停止(放置)", app.status_var.get())
    check("paused: hint fits", hint_fits())
    mouse.over_self = False

    app._afk_button_clicked()
    check("stop button: AFK stops with a notice", not app.clicker.afk_active() and "解除" in app.hint_var.get())
    app._afk_button_clicked()
    app._afk_button_clicked()
    check("countdown cancel: says the start was called off", "中止" in app.hint_var.get(), app.hint_var.get())

    app._scale_moved("23.456790123")
    app.update()
    check("slider drag: spinbox shows an integer", app.speed_spin.get() == "23", repr(app.speed_spin.get()))
    check("slider drag: label matches", app.speed_value_label.cget("text") == "23 回/秒")
    check("slider drag: clicker rate matches", app.clicker.settings().clicks_per_second == 23.0)
    check("slider snapped to an integer", app.cps_var.get() == 23.0)
    app.speed_text_var.set("45")
    app._commit_speed_text()
    check("spinbox commit applies", app.clicker.settings().clicks_per_second == 45.0 and app.cps_var.get() == 45.0)
    check("validate rejects 999", app._validate_speed_text("999") is False)
    check("validate rejects full-width digits", app._validate_speed_text("１２") is False)
    check("validate allows empty while editing", app._validate_speed_text("") is True)
    app.speed_text_var.set("")
    app._commit_speed_text()
    check("empty commit snaps back", app.speed_spin.get() == "45")
    app.speed_text_var.set("0")
    app._commit_speed_text()
    check("0 clamps to 1", app.speed_spin.get() == "1" and app.speed_value_label.cget("text") == "1 回/秒")
    app.speed_text_var.set("99")
    app._commit_speed_text()
    check("99 clamps to 60", app.speed_spin.get() == "60")

    app.clicker._afk_cancels += 1
    # Run one refresh by hand without starting a second polling loop.
    app.after_cancel(app._refresh_after_id)
    app._refresh_ui()
    check("auto-cancel shows a notice", "解除しました" in app.hint_var.get(), app.hint_var.get())

    errors = []
    app.report_callback_exception = lambda *args: errors.append(args)
    app.speed_spin.focus_force()
    app.update()
    app._close()
    check("closing with the spinbox focused raises nothing", not errors, repr(errors))
    check("close is idempotent", app._close() is None)

    StubButtons.hook_ready = False
    app = rt.RenshaApp(FakeMouse())
    app.update()
    check("no hook: the notice fits", app.hint_label.winfo_reqheight() <= two_lines and quit_button_fits(app), app.hint_var.get())
    app._close()
    StubButtons.hook_ready = True

    class ExplodingButtons(StubButtons):
        def start(self):
            raise RuntimeError("boom")

    rt.PhysicalButtons = ExplodingButtons
    try:
        rt.RenshaApp(FakeMouse())
        check("init failure raises", False)
    except RuntimeError:
        check("init failure raises", True)
    check("init failure destroys its window", tk._default_root is None, repr(tk._default_root))
    rt.PhysicalButtons = RealPhysicalButtons


def main():
    check_real_hook()
    check_hook_filtering()
    check_cursor_detection()
    check_trigger()
    check_afk()
    check_no_hook_and_stop()
    check_ui()

    failed = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
