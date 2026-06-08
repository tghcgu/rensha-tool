from __future__ import annotations

import ctypes
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk


APP_NAME = "右+左 連射ツール"

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


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


class WindowsMouse:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("このツールはWindows専用です。")

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self._user32.GetAsyncKeyState.restype = ctypes.c_short
        self._user32.SendInput.argtypes = [
            ctypes.c_uint,
            ctypes.POINTER(Input),
            ctypes.c_int,
        ]
        self._user32.SendInput.restype = ctypes.c_uint

    def is_pressed(self, virtual_key: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(virtual_key) & 0x8000)

    def _send_mouse_event(self, flags: int) -> None:
        event = Input(
            type=INPUT_MOUSE,
            union=InputUnion(mi=MouseInput(0, 0, 0, flags, 0, 0)),
        )
        sent = self._user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def left_click_pulse(self) -> None:
        # The user is physically holding left click. Releasing then pressing
        # creates repeated click pulses without needing a keyboard hotkey.
        self._send_mouse_event(MOUSEEVENTF_LEFTUP)
        time.sleep(0.006)
        self._send_mouse_event(MOUSEEVENTF_LEFTDOWN)


@dataclass(frozen=True)
class ClickerSettings:
    enabled: bool
    clicks_per_second: float


class RapidClicker:
    def __init__(self, mouse: WindowsMouse, on_active_change) -> None:
        self._mouse = mouse
        self._on_active_change = on_active_change
        self._lock = threading.Lock()
        self._settings = ClickerSettings(enabled=True, clicks_per_second=12.0)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._active = False
        self._last_error: str | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)

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
        clicks_per_second = max(1.0, min(60.0, clicks_per_second))
        with self._lock:
            self._settings = ClickerSettings(
                enabled=self._settings.enabled,
                clicks_per_second=clicks_per_second,
            )

    def last_error(self) -> str | None:
        return self._last_error

    def _set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._on_active_change(active)

    def _trigger_is_down(self) -> bool:
        return self._mouse.is_pressed(VK_RBUTTON) and self._mouse.is_pressed(VK_LBUTTON)

    def _run(self) -> None:
        next_pulse_at = 0.0

        while not self._stop_event.is_set():
            settings = self.settings()
            trigger_down = settings.enabled and self._trigger_is_down()

            if not trigger_down:
                self._set_active(False)
                next_pulse_at = 0.0
                time.sleep(0.012)
                continue

            self._set_active(True)
            now = time.perf_counter()
            if now < next_pulse_at:
                time.sleep(min(0.004, next_pulse_at - now))
                continue

            try:
                self._mouse.left_click_pulse()
            except OSError as exc:
                self._last_error = str(exc)
                self._set_active(False)
                time.sleep(0.2)
                continue

            interval = 1.0 / settings.clicks_per_second
            next_pulse_at = time.perf_counter() + interval


class RenshaApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("430x420")
        self.minsize(390, 380)
        self.configure(bg="#f5f7fb")

        self.mouse = WindowsMouse()
        self.clicker = RapidClicker(self.mouse, self._thread_active_changed)

        self.enabled_var = tk.BooleanVar(value=True)
        self.cps_var = tk.DoubleVar(value=12.0)
        self.status_var = tk.StringVar(value="待機中")
        self.hint_var = tk.StringVar(value="右クリックを押したまま、左クリックしている間だけ連射")
        self.right_state_var = tk.StringVar(value="右: OFF")
        self.left_state_var = tk.StringVar(value="左: OFF")

        self._build_style()
        self._build_ui()
        self._bind_events()

        self.clicker.start()
        self.after(50, self._refresh_button_states)

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

        self.hint_label = ttk.Label(card, textvariable=self.hint_var, style="Hint.TLabel", anchor="center")
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
            command=self._enabled_changed,
        ).pack(anchor="w", pady=(0, 16))

        speed_row = ttk.Frame(card, style="Card.TFrame")
        speed_row.pack(fill="x", pady=(0, 6))
        ttk.Label(speed_row, text="連射速度", style="Card.TLabel").pack(side="left")
        self.speed_value_label = ttk.Label(speed_row, text="12 回/秒", style="Card.TLabel")
        self.speed_value_label.pack(side="right")

        speed_controls = ttk.Frame(card, style="Card.TFrame")
        speed_controls.pack(fill="x")
        self.speed_scale = ttk.Scale(
            speed_controls,
            from_=1,
            to=60,
            variable=self.cps_var,
            command=self._speed_changed,
        )
        self.speed_scale.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.speed_spin = ttk.Spinbox(
            speed_controls,
            from_=1,
            to=60,
            width=5,
            textvariable=self.cps_var,
            command=self._speed_changed,
        )
        self.speed_spin.pack(side="right")

        ttk.Label(
            card,
            text="使い方: 対象画面で右クリックを押したまま左クリック。左か右を離すと止まります。",
            style="Hint.TLabel",
            wraplength=350,
            justify="left",
        ).pack(anchor="w", pady=(18, 16))

        ttk.Button(card, text="終了", command=self._close).pack(fill="x")

    def _bind_events(self) -> None:
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.cps_var.trace_add("write", lambda *_: self._speed_changed())
        self.enabled_var.trace_add("write", lambda *_: self._enabled_changed())

    def _enabled_changed(self, *_args) -> None:
        enabled = bool(self.enabled_var.get())
        self.clicker.set_enabled(enabled)
        if not enabled:
            self.status_var.set("無効")
            self.hint_var.set("チェックを入れると右+左で連射できます")
            self._paint_status(active=False, disabled=True)
        else:
            self.status_var.set("待機中")
            self.hint_var.set("右クリックを押したまま、左クリックしている間だけ連射")
            self._paint_status(active=False, disabled=False)

    def _speed_changed(self, *_args) -> None:
        try:
            cps = float(self.cps_var.get())
        except (TypeError, tk.TclError, ValueError):
            return
        cps = max(1.0, min(60.0, cps))
        self.clicker.set_clicks_per_second(cps)
        self.speed_value_label.configure(text=f"{cps:.0f} 回/秒")

    def _thread_active_changed(self, active: bool) -> None:
        self.after(0, lambda: self._set_active(active))

    def _set_active(self, active: bool) -> None:
        if not self.enabled_var.get():
            return

        if active:
            self.status_var.set("連射中")
            self.hint_var.set("左か右を離すと止まります")
            self._paint_status(active=True, disabled=False)
        else:
            self.status_var.set("待機中")
            self.hint_var.set("右クリックを押したまま、左クリックしている間だけ連射")
            self._paint_status(active=False, disabled=False)

        error = self.clicker.last_error()
        if error:
            self.hint_var.set(f"入力送信でエラー: {error}")

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

    def _refresh_button_states(self) -> None:
        right_down = self.mouse.is_pressed(VK_RBUTTON)
        left_down = self.mouse.is_pressed(VK_LBUTTON)

        self.right_state_var.set("右: ON" if right_down else "右: OFF")
        self.left_state_var.set("左: ON" if left_down else "左: OFF")
        self.right_badge.configure(bg="#dbeafe" if right_down else "#e7ecf3")
        self.left_badge.configure(bg="#dbeafe" if left_down else "#e7ecf3")

        self.after(50, self._refresh_button_states)

    def _close(self) -> None:
        self.clicker.stop()
        self.destroy()


def main() -> int:
    if "--self-test" in sys.argv:
        if sys.platform != "win32":
            print("Windows only")
            return 1
        WindowsMouse()
        print("OK")
        return 0

    try:
        app = RenshaApp()
    except Exception as exc:
        messagebox.showerror(APP_NAME, str(exc))
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
