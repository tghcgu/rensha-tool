from __future__ import annotations

import ctypes
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass
from tkinter import messagebox, ttk


APP_NAME = "右+左 連射ツール"

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_ESCAPE = 0x1B

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205

# Stamped into every event this tool injects. The low-level mouse hook uses it
# to skip our own pulses: GetAsyncKeyState cannot, because it reports injected
# clicks exactly like physical ones.
RENSHA_SIGNATURE = 0x52454E53  # "RENS"

# How long the async key state may still carry our own injected click. Used
# only where no hook is available, so a stale reading cannot be mistaken for
# the user pressing a button.
INJECTION_GRACE = 0.03

MIN_CPS = 1
MAX_CPS = 60
DEFAULT_CPS = 12


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [("mi", MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", InputUnion)]


class MouseHookStruct(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    ctypes.c_int,
    ctypes.c_size_t,
    ctypes.POINTER(MouseHookStruct),
)


class WindowsMouse:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("このツールはWindows専用です。")

        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.SendInput.argtypes = [
            ctypes.c_uint,
            ctypes.POINTER(Input),
            ctypes.c_int,
        ]
        self.user32.SendInput.restype = ctypes.c_uint

        # True while an injected left press may still be held by the system.
        self._left_latched_by_us = False

    def is_pressed(self, virtual_key: int) -> bool:
        return bool(self.user32.GetAsyncKeyState(virtual_key) & 0x8000)

    def _send(self, *flags: int) -> None:
        # Events in one SendInput call are inserted into the input stream
        # without other input in between, so a pair is never split apart.
        count = len(flags)
        events = (Input * count)(
            *(
                Input(
                    type=INPUT_MOUSE,
                    union=InputUnion(
                        mi=MouseInput(0, 0, 0, flag, 0, RENSHA_SIGNATURE)
                    ),
                )
                for flag in flags
            )
        )
        sent = self.user32.SendInput(count, events, ctypes.sizeof(Input))
        if sent != count:
            code = ctypes.get_last_error()
            if code:
                raise ctypes.WinError(code)
            raise OSError(f"SendInput が {count} 件中 {sent} 件しか受け付けませんでした。")

    def left_click_pulse(self) -> None:
        # The user is physically holding left click. Releasing then pressing
        # creates repeated click pulses without needing a keyboard hotkey.
        # The pair ends pressed, so the release stays our responsibility until
        # the user's own button goes up: see release_left.
        self._left_latched_by_us = True
        self._send(MOUSEEVENTF_LEFTUP, MOUSEEVENTF_LEFTDOWN)

    def left_click_once(self) -> None:
        # A full click for AFK mode, where nothing is physically held. Set the
        # flag before sending: a partially accepted pair must still leave the
        # safety release armed.
        self._left_latched_by_us = True
        self._send(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
        self._left_latched_by_us = False

    def left_latched_by_us(self) -> bool:
        return self._left_latched_by_us

    def release_left(self) -> None:
        if not self._left_latched_by_us:
            return
        self._send(MOUSEEVENTF_LEFTUP)
        self._left_latched_by_us = False


class PhysicalButtons:
    """Physical left/right button state, tracked by a low-level mouse hook.

    The hook is the only reliable way to separate the user's real clicks from
    the ones this tool injects. Our own events carry RENSHA_SIGNATURE and are
    skipped; anything else counts as the user, so input forwarded by remote
    desktop or mouse software still works.

    If the hook cannot be installed, available() stays False and callers fall
    back to the async key state.
    """

    def __init__(self, mouse: WindowsMouse) -> None:
        self._mouse = mouse
        user32 = mouse.user32
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            HOOKPROC,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK,
            ctypes.c_int,
            ctypes.c_size_t,
            ctypes.POINTER(MouseHookStruct),
        ]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.PostThreadMessageW.argtypes = [
            wintypes.DWORD,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self._user32 = user32

        # Nothing has been injected yet, so the key state is the user's own.
        self._left = mouse.is_pressed(VK_LBUTTON)
        self._right = mouse.is_pressed(VK_RBUTTON)
        self._hook: int | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._callback = HOOKPROC(self._on_event)  # must stay referenced
        self._thread = threading.Thread(target=self._pump, daemon=True)

    def start(self) -> bool:
        self._thread.start()
        self._ready.wait(2.0)
        return self.available()

    def available(self) -> bool:
        return self._hook is not None

    def left_down(self) -> bool:
        return self._left

    def right_down(self) -> bool:
        return self._right

    def resync(self, left: bool, right: bool) -> None:
        # Called only when nothing of ours is outstanding, so these values are
        # the user's real state. Keeps the tracked state from drifting if
        # Windows ever drops the hook for being slow to answer.
        self._left = left
        self._right = right

    def stop(self) -> None:
        if self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=1.0)

    def _pump(self) -> None:
        self._thread_id = self._mouse.kernel32.GetCurrentThreadId()
        hook = self._user32.SetWindowsHookExW(WH_MOUSE_LL, self._callback, None, 0)
        self._hook = hook or None
        self._ready.set()
        if not hook:
            return

        # A low-level hook only fires while its own thread pumps messages.
        message = wintypes.MSG()
        while self._user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            pass

        self._hook = None
        self._user32.UnhookWindowsHookEx(hook)

    def _on_event(self, code, message, data):
        # Runs for every mouse event on the system, movement included: keep it
        # as short as possible.
        if code == HC_ACTION and data:
            info = data.contents
            if info.dwExtraInfo != RENSHA_SIGNATURE:
                if message == WM_LBUTTONDOWN:
                    self._left = True
                elif message == WM_LBUTTONUP:
                    self._left = False
                elif message == WM_RBUTTONDOWN:
                    self._right = True
                elif message == WM_RBUTTONUP:
                    self._right = False
        return self._user32.CallNextHookEx(None, code, message, data)


@dataclass(frozen=True)
class ClickerSettings:
    enabled: bool
    clicks_per_second: float


@dataclass(frozen=True)
class ButtonSnapshot:
    left: bool  # the user's own finger, hook-corrected
    right: bool
    left_latched: bool  # what the system currently thinks of the left button


class RapidClicker:
    def __init__(self, mouse: WindowsMouse, buttons: PhysicalButtons) -> None:
        self._mouse = mouse
        self._buttons = buttons
        self._lock = threading.Lock()
        self._settings = ClickerSettings(
            enabled=True, clicks_per_second=float(DEFAULT_CPS)
        )
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._active = False
        self._afk = False
        self._afk_armed = False
        self._afk_cancels = 0
        self._last_injection_at = 0.0
        self._last_error: str | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        # Never leave an injected press behind when quitting.
        self._release_left_if_free(self._snapshot())

    def settings(self) -> ClickerSettings:
        with self._lock:
            return self._settings

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._settings = ClickerSettings(
                enabled=enabled,
                clicks_per_second=self._settings.clicks_per_second,
            )

    def set_clicks_per_second(self, clicks_per_second: float) -> None:
        clicks_per_second = max(float(MIN_CPS), min(float(MAX_CPS), clicks_per_second))
        with self._lock:
            self._settings = ClickerSettings(
                enabled=self._settings.enabled,
                clicks_per_second=clicks_per_second,
            )

    def last_error(self) -> str | None:
        return self._last_error

    def is_active(self) -> bool:
        return self._active

    def start_afk(self) -> None:
        # Armed only once the user has let go of everything, so a button still
        # held when the countdown ends cannot cancel AFK mode instantly.
        self._afk_armed = False
        self._afk = True

    def cancel_afk(self) -> None:
        self._afk = False

    def afk_active(self) -> bool:
        return self._afk

    def afk_armed(self) -> bool:
        return self._afk_armed

    def afk_cancel_count(self) -> int:
        return self._afk_cancels

    def _snapshot(self) -> ButtonSnapshot:
        latched_left = self._mouse.is_pressed(VK_LBUTTON)
        right = self._mouse.is_pressed(VK_RBUTTON)
        settled = not self._mouse.left_latched_by_us() and (
            time.perf_counter() - self._last_injection_at >= INJECTION_GRACE
        )

        if settled:
            self._buttons.resync(latched_left, right)
            return ButtonSnapshot(latched_left, right, latched_left)

        if self._buttons.available():
            # An injected press is outstanding, so only the hook knows whether
            # the user is still holding the button.
            return ButtonSnapshot(
                self._buttons.left_down() and latched_left,
                self._buttons.right_down() and right,
                latched_left,
            )

        return ButtonSnapshot(latched_left, right, latched_left)

    def _afk_cancel_pressed(self, snapshot: ButtonSnapshot) -> bool:
        if self._mouse.is_pressed(VK_ESCAPE):
            return True
        if not self._buttons.available():
            # Without the hook the key state may still carry our own click;
            # trust it only once that has settled.
            if time.perf_counter() - self._last_injection_at < INJECTION_GRACE:
                return False
        return snapshot.left or snapshot.right

    def _release_left_if_free(self, snapshot: ButtonSnapshot) -> None:
        # A pulse ends pressed. If the user's finger is already off the button
        # while the system still holds it down, the matching release is ours to
        # send, otherwise the click stays latched with nothing to release it.
        if snapshot.left or not snapshot.left_latched:
            return
        if not self._mouse.left_latched_by_us():
            return
        try:
            self._mouse.release_left()
        except OSError as exc:
            self._last_error = str(exc)

    def _run(self) -> None:
        next_pulse_at = 0.0

        while not self._stop_event.is_set():
            settings = self.settings()
            snapshot = self._snapshot()

            afk = self._afk and settings.enabled
            if afk and not self._afk_armed:
                if self._afk_cancel_pressed(snapshot):
                    self._active = False
                    self._release_left_if_free(snapshot)
                    time.sleep(0.02)
                    continue
                self._afk_armed = True
            elif afk and self._afk_cancel_pressed(snapshot):
                self._afk = False
                self._afk_cancels += 1
                afk = False

            if afk:
                pulse = self._mouse.left_click_once
            else:
                pulse = self._mouse.left_click_pulse
                if not (settings.enabled and snapshot.left and snapshot.right):
                    self._active = False
                    next_pulse_at = 0.0
                    self._release_left_if_free(snapshot)
                    time.sleep(0.012)
                    continue

            self._active = True
            now = time.perf_counter()
            if now < next_pulse_at:
                time.sleep(min(0.004, next_pulse_at - now))
                continue

            self._last_injection_at = now
            try:
                pulse()
            except OSError as exc:
                self._last_error = str(exc)
                self._active = False
                self._release_left_if_free(self._snapshot())
                time.sleep(0.2)
                continue

            self._last_error = None
            # Base the next deadline on the pre-pulse timestamp so the
            # actual rate matches the configured clicks per second.
            next_pulse_at = now + 1.0 / settings.clicks_per_second


class RenshaApp(tk.Tk):
    def __init__(self, mouse: WindowsMouse) -> None:
        super().__init__()
        try:
            self._setup(mouse)
        except BaseException:
            # Tk is already on screen here, so tear it down instead of leaving
            # an empty window behind the error dialog.
            self.destroy()
            raise

    def _setup(self, mouse: WindowsMouse) -> None:
        self.title(APP_NAME)
        self.geometry("430x480")
        self.minsize(390, 440)
        self.configure(bg="#f5f7fb")

        self.mouse = mouse
        self.buttons = PhysicalButtons(mouse)
        hook_ready = self.buttons.start()
        self.clicker = RapidClicker(self.mouse, self.buttons)

        self._shown_status: tuple | None = None
        self._afk_countdown = 0
        self._afk_after_id: str | None = None
        self._refresh_after_id: str | None = None
        self._seen_afk_cancels = 0
        self._notice_text = ""
        self._notice_until = 0.0
        self._closing = False
        self._cps = DEFAULT_CPS
        self._syncing_speed = False

        self.enabled_var = tk.BooleanVar(value=True)
        self.cps_var = tk.DoubleVar(value=float(DEFAULT_CPS))
        self.speed_text_var = tk.StringVar(value=str(DEFAULT_CPS))
        self.status_var = tk.StringVar(value="待機中")
        self.hint_var = tk.StringVar(value="右クリックを押したまま、左クリックしている間だけ連射")
        self.right_state_var = tk.StringVar(value="右: OFF")
        self.left_state_var = tk.StringVar(value="左: OFF")

        self._build_style()
        self._build_ui()
        self._bind_events()
        if not hook_ready:
            self._show_notice(
                "入力フックが使えません。放置連射の解除は Esc かボタンをお使いください。",
                seconds=6.0,
            )
        self._update_status()

        self.clicker.start()
        self._refresh_after_id = self.after(50, self._refresh_ui)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f5f7fb")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Title.TLabel", background="#f5f7fb", foreground="#172033", font=("", 22, "bold"))
        style.configure("Sub.TLabel", background="#f5f7fb", foreground="#4b5565", font=("", 10))
        style.configure("Card.TLabel", background="#ffffff", foreground="#172033", font=("", 11))
        style.configure("Big.TLabel", background="#ffffff", foreground="#172033", font=("", 24, "bold"))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#526071", font=("", 10))
        style.configure("TCheckbutton", background="#ffffff", foreground="#172033", font=("", 11))
        style.configure("TButton", font=("", 11))
        style.configure("Horizontal.TScale", background="#ffffff")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="トリガーは右クリック + 左クリック。離したら即停止。",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 14))

        card = ttk.Frame(outer, style="Card.TFrame", padding=18)
        card.pack(fill="both", expand=True)

        self.status_label = ttk.Label(card, textvariable=self.status_var, style="Big.TLabel", anchor="center")
        self.status_label.pack(fill="x", pady=(0, 8))

        self.hint_label = ttk.Label(
            card,
            textvariable=self.hint_var,
            style="Hint.TLabel",
            anchor="center",
            justify="center",
            wraplength=340,
        )
        self.hint_label.pack(fill="x", pady=(0, 18))

        state_row = ttk.Frame(card, style="Card.TFrame")
        state_row.pack(fill="x", pady=(0, 16))
        self.left_badge = tk.Label(
            state_row,
            textvariable=self.left_state_var,
            bg="#e7ecf3",
            fg="#172033",
            padx=16,
            pady=10,
            font=("", 12, "bold"),
        )
        self.left_badge.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.right_badge = tk.Label(
            state_row,
            textvariable=self.right_state_var,
            bg="#e7ecf3",
            fg="#172033",
            padx=16,
            pady=10,
            font=("", 12, "bold"),
        )
        self.right_badge.pack(side="left", fill="x", expand=True, padx=(6, 0))

        ttk.Checkbutton(
            card,
            text="連射を有効にする",
            variable=self.enabled_var,
        ).pack(anchor="w", pady=(0, 16))

        speed_row = ttk.Frame(card, style="Card.TFrame")
        speed_row.pack(fill="x", pady=(0, 6))
        ttk.Label(speed_row, text="連射速度", style="Card.TLabel").pack(side="left")
        self.speed_value_label = ttk.Label(speed_row, text=f"{DEFAULT_CPS} 回/秒", style="Card.TLabel")
        self.speed_value_label.pack(side="right")

        speed_controls = ttk.Frame(card, style="Card.TFrame")
        speed_controls.pack(fill="x")
        self.speed_scale = ttk.Scale(
            speed_controls,
            from_=MIN_CPS,
            to=MAX_CPS,
            variable=self.cps_var,
            command=self._scale_moved,
        )
        self.speed_scale.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.speed_spin = ttk.Spinbox(
            speed_controls,
            from_=MIN_CPS,
            to=MAX_CPS,
            increment=1,
            width=5,
            textvariable=self.speed_text_var,
            command=self._commit_speed_text,
            validate="key",
            validatecommand=(self.register(self._validate_speed_text), "%P"),
        )
        self.speed_spin.pack(side="right")

        ttk.Label(
            card,
            text=(
                "使い方: 対象画面で右クリックを押したまま左クリック。左か右を離すと止まります。"
                "放置連射はどこかをクリックするか Esc キーですぐ解除できます。"
            ),
            style="Hint.TLabel",
            wraplength=350,
            justify="left",
        ).pack(anchor="w", pady=(18, 16))

        self.afk_button = ttk.Button(
            card,
            text="放置連射を開始",
            command=self._afk_button_clicked,
        )
        self.afk_button.pack(fill="x", pady=(0, 8))

        ttk.Button(card, text="終了", command=self._close).pack(fill="x")

    def _bind_events(self) -> None:
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.enabled_var.trace_add("write", lambda *_: self._enabled_changed())
        self.speed_spin.bind("<Return>", lambda _event: self._commit_speed_text())
        self.speed_spin.bind("<FocusOut>", lambda _event: self._commit_speed_text())

    def _enabled_changed(self, *_args) -> None:
        enabled = bool(self.enabled_var.get())
        self.clicker.set_enabled(enabled)
        if not enabled:
            self._stop_afk()
        self._update_status()

    def _afk_button_clicked(self) -> None:
        if self._afk_countdown > 0 or self.clicker.afk_active():
            self._stop_afk()
            self._show_notice("放置連射を解除しました。")
        else:
            self._begin_afk_countdown()
        self._update_status()

    def _begin_afk_countdown(self) -> None:
        self._afk_countdown = 3
        self._afk_after_id = self.after(1000, self._afk_tick)

    def _afk_tick(self) -> None:
        self._afk_after_id = None
        self._afk_countdown -= 1
        if self._afk_countdown <= 0:
            self._afk_countdown = 0
            self.clicker.start_afk()
            self._seen_afk_cancels = self.clicker.afk_cancel_count()
        else:
            self._afk_after_id = self.after(1000, self._afk_tick)
        self._update_status()

    def _stop_afk(self) -> None:
        if self._afk_after_id is not None:
            self.after_cancel(self._afk_after_id)
            self._afk_after_id = None
        self._afk_countdown = 0
        self.clicker.cancel_afk()

    def _validate_speed_text(self, proposed: str) -> bool:
        # Two digits cover 1-60, so an out-of-range value cannot be typed in.
        return proposed == "" or (
            proposed.isascii() and proposed.isdigit() and len(proposed) <= 2
        )

    def _scale_moved(self, raw: str) -> None:
        if self._syncing_speed:
            return
        try:
            value = round(float(raw))
        except (TypeError, ValueError):
            return
        self._apply_speed(value)

    def _commit_speed_text(self, *_args) -> None:
        if self._syncing_speed:
            return
        text = self.speed_text_var.get().strip()
        # Empty or out of range snaps back to the value actually in use.
        self._apply_speed(int(text) if text.isascii() and text.isdigit() else self._cps)

    def _apply_speed(self, value: int) -> None:
        value = max(MIN_CPS, min(MAX_CPS, int(value)))
        self._cps = value
        self.clicker.set_clicks_per_second(float(value))
        self.speed_value_label.configure(text=f"{value} 回/秒")

        # Both widgets share one value, so keep the slider on whole numbers and
        # the spinbox free of the raw float a drag would otherwise leave there.
        self._syncing_speed = True
        try:
            self.cps_var.set(float(value))
            self.speed_text_var.set(str(value))
        finally:
            self._syncing_speed = False

    def _show_notice(self, text: str, seconds: float = 2.5) -> None:
        self._notice_text = text
        self._notice_until = time.perf_counter() + seconds

    def _current_notice(self) -> str:
        if self._notice_text and time.perf_counter() >= self._notice_until:
            self._notice_text = ""
        return self._notice_text

    def _update_status(self) -> None:
        enabled = bool(self.enabled_var.get())
        counting = self._afk_countdown > 0
        afk = enabled and self.clicker.afk_active()
        arming = afk and not self.clicker.afk_armed()
        active = enabled and self.clicker.is_active()
        notice = self._current_notice()
        error = self.clicker.last_error()

        if not enabled:
            status = "無効"
            hint = "チェックを入れると右+左で連射できます"
        elif counting:
            status = f"開始まで {self._afk_countdown}"
            hint = "対象にカーソルを合わせてください(ボタンで中止)"
        elif arming:
            status = "放置連射 準備"
            hint = "マウスボタンと Esc を離すと開始します"
        elif afk:
            status = "連射中(放置)"
            hint = "どこかをクリックするか Esc キーで解除"
        elif active:
            status = "連射中"
            hint = "左か右を離すと止まります"
        else:
            status = "待機中"
            hint = "右クリックを押したまま、左クリックしている間だけ連射"
        if notice:
            hint = notice
        if error:
            hint = f"入力送信でエラー: {error}"

        button_text = "放置連射を解除" if (counting or afk) else "放置連射を開始"
        button_state = "normal" if enabled else "disabled"

        shown = (status, hint, active, enabled, button_text, button_state)
        if shown == self._shown_status:
            return
        self._shown_status = shown

        self.status_var.set(status)
        self.hint_var.set(hint)
        self.afk_button.configure(text=button_text, state=button_state)
        self._paint_status(active=active, disabled=not enabled)

    def _paint_status(self, active: bool, disabled: bool) -> None:
        if disabled:
            bg = "#eef1f5"
            fg = "#6b7280"
        elif active:
            bg = "#dcfce7"
            fg = "#116329"
        else:
            bg = "#ffffff"
            fg = "#172033"

        self.status_label.configure(background=bg, foreground=fg)
        self.hint_label.configure(background=bg)

    def _refresh_ui(self) -> None:
        if self._closing:
            return

        right_down = self.mouse.is_pressed(VK_RBUTTON)
        left_down = self.mouse.is_pressed(VK_LBUTTON)

        self.right_state_var.set("右: ON" if right_down else "右: OFF")
        self.left_state_var.set("左: ON" if left_down else "左: OFF")
        self.right_badge.configure(bg="#dbeafe" if right_down else "#e7ecf3")
        self.left_badge.configure(bg="#dbeafe" if left_down else "#e7ecf3")

        cancels = self.clicker.afk_cancel_count()
        if cancels != self._seen_afk_cancels:
            self._seen_afk_cancels = cancels
            self._show_notice("放置連射を解除しました(クリックまたは Esc)")

        self._update_status()
        self._refresh_after_id = self.after(50, self._refresh_ui)

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._refresh_after_id is not None:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None
        self._stop_afk()
        self.clicker.stop()
        self.buttons.stop()
        self.destroy()


def _report(message: str) -> None:
    # A windowed build (and a double-clicked .pyw) has no console at all, so
    # the exit code is the real contract here. See the README for the
    # PowerShell form that reads it.
    stream = sys.stdout
    if stream is None:
        return
    try:
        print(message)
        stream.flush()
    except (OSError, ValueError):
        pass


def _self_test() -> int:
    if sys.platform != "win32":
        _report("Windows only")
        return 1

    try:
        mouse = WindowsMouse()
        buttons = PhysicalButtons(mouse)
        hook_ready = buttons.start()
        buttons.stop()
    except Exception as exc:  # noqa: BLE001 - reported as the test result
        _report(f"NG: {exc}")
        return 1

    _report("OK" if hook_ready else "OK (入力フックは利用できません)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return _self_test()

    try:
        mouse = WindowsMouse()
    except Exception as exc:  # noqa: BLE001 - shown to the user
        messagebox.showerror(APP_NAME, str(exc))
        return 1

    try:
        app = RenshaApp(mouse)
    except Exception as exc:  # noqa: BLE001 - shown to the user
        messagebox.showerror(APP_NAME, str(exc))
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
