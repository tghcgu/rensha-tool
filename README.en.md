# Right + Left Rapid Clicker

[日本語](README.md)

A small Windows tool that repeatedly sends left-click pulses only while you are holding right click and left click at the same time.

The project avoids extra launcher shortcuts. The distributable executable is the main entry point.

## Features

- Rapid-clicks only while right click + left click are both held
- Stops immediately when either button is released
- AFK mode that keeps clicking hands-free (any click or Esc cancels it instantly)
- Adjustable clicks-per-second setting in the app window
- Standalone Windows executable distributed via GitHub Releases
- No installer or background service required

## Requirements

- Windows
- No Python required when using the packaged executable
- Python 3 is required only when running from source

## Run

Get the executable from GitHub Releases.

1. Open [Releases](https://github.com/tghcgu/rensha-tool/releases).
2. Download `右+左 連射ツール.exe` from the latest release.
3. Double-click the downloaded executable.

On first launch Windows may show "Windows protected your PC" (SmartScreen). Choose "More info" and then "Run anyway".

If you built it yourself, it is at `配布用\右+左 連射ツール.exe` (see "Rebuild the Executable").

## Usage

1. Open `右+左 連射ツール.exe`.
2. Adjust the rapid-click speed if needed.
3. Switch to the target window.
4. Hold right click, then hold left click.
5. Release either mouse button to stop.

## AFK Mode

Use this when you want the clicking to continue hands-free.

1. Press the "放置連射を開始" (start AFK clicking) button.
2. During the 3-second countdown, move the cursor to the target. Clicking the target starts right away instead of waiting out the countdown.
3. After the countdown, clicking continues at the configured speed with no buttons held.

If a mouse button or Esc is still held when the countdown ends, or right after the click that cut it short, the app shows "放置連射 準備" (getting ready) and starts as soon as you let go. Clicking this app's own window during the countdown does not cut it short, so the cancel button stays usable.

While the cursor is over this app's own window, nothing is clicked and the app shows "一時停止(放置)" (paused). You can change settings or press the stop button without the clicking getting in the way. Clicking resumes once the cursor leaves the window.

Any of these cancels it instantly:

- Click either mouse button outside this app's window
- Press the Esc key
- Press the "放置連射を解除" (stop) button in the app
- Close the app

## Distribution

Only the executable is distributed. It is not kept in the repository; attach it to a GitHub Release instead.

1. Build `配布用\右+左 連射ツール.exe` as described in "Rebuild the Executable".
2. Create a new release on GitHub and attach that executable.

The recipient does not need Python installed.

## Project Layout

```text
rensha-tool
├─ README.md
├─ README.en.md
├─ rensha_tool.pyw
├─ tests
│  └─ test_rensha.py      automated tests
├─ .gitignore
├─ .gitattributes
└─ 配布用                  created by the build (not tracked by Git)
   └─ 右+左 連射ツール.exe
```

## Run From Source

From the project folder:

```powershell
py rensha_tool.pyw
```

Double-clicking `rensha_tool.pyw` in File Explorer also works. The `.pyw` extension runs without a console, so no black command window appears.

## Rebuild the Executable

The executable is built with PyInstaller.

```powershell
py -m pip install --user pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "右+左 連射ツール" --distpath ".\配布用" --workpath ".\build" --specpath ".\build" .\rensha_tool.pyw
```

After the build finishes, the executable is at `配布用\右+左 連射ツール.exe`. Both `配布用` and `build` are ignored by Git.

## Checks

Python syntax check:

```powershell
py -m py_compile .\rensha_tool.pyw
```

Automated tests (no real clicks are sent; the cursor is nudged and put back, and a test window flashes up briefly):

```powershell
py tests\test_rensha.py
```

It ends with a line such as `61/61 passed` and exit code `0` when everything passes.

Executable self-test:

```powershell
$p = Start-Process ".\配布用\右+左 連射ツール.exe" -ArgumentList "--self-test" -Wait -PassThru
$p.ExitCode
```

`0` means OK and `1` means a failure. The executable is a windowed app, so running `.\配布用\右+左 連射ツール.exe --self-test` directly makes PowerShell return without waiting and shows nothing. From Command Prompt or Git Bash it prints `OK`.

## Notes

- Windows only.
- The physical right-click input is still passed through to the target app.
- Nothing is clicked into this app's own window, in either right + left mode or AFK mode.
- While running, the tool uses a low-level mouse hook to tell your real clicks from the ones it sends. Nothing is installed and nothing keeps running after exit. Security software or anti-cheat systems may flag it.
- If the target app is running as administrator and does not receive input, the clicker may also need to be run as administrator.
- Follow the rules and terms of the app or service where you use it.
- This tool is not intended for bypassing game rules, service terms, or anti-cheat systems.
