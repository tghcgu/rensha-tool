# Right + Left Rapid Clicker

[日本語](README.md)

A small Windows tool that repeatedly sends left-click pulses only while you are holding right click and left click at the same time.

The project avoids extra launcher shortcuts. The distributable executable is the main entry point.

## Features

- Rapid-clicks only while right click + left click are both held
- Stops immediately when either button is released
- Adjustable clicks-per-second setting in the app window
- Includes a standalone Windows executable
- No installer or background service required

## Requirements

- Windows
- No Python required when using the packaged executable
- Python 3 is required only when running from source

## Run

Open this file:

```text
配布用\右+左 連射ツール.exe
```

In File Explorer, open the `配布用` folder and double-click `右+左 連射ツール.exe`.

## Usage

1. Open `配布用\右+左 連射ツール.exe`.
2. Adjust the rapid-click speed if needed.
3. Switch to the target window.
4. Hold right click, then hold left click.
5. Release either mouse button to stop.

## Distribution

For normal distribution, share this single file:

```text
配布用\右+左 連射ツール.exe
```

The recipient does not need Python installed.

## Project Layout

```text
rensha-tool
├─ README.md
├─ README.en.md
├─ rensha_tool.py
├─ .gitignore
└─ 配布用
   └─ 右+左 連射ツール.exe
```

## Run From Source

From the project folder:

```powershell
py rensha_tool.py
```

## Rebuild the Executable

The executable is built with PyInstaller.

```powershell
py -m pip install --user pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "右+左 連射ツール" --distpath ".\配布用" --workpath ".\build" --specpath ".\build" .\rensha_tool.py
```

After the build finishes, `配布用\右+左 連射ツール.exe` will be updated.

## Checks

Python syntax check:

```powershell
py -m py_compile .\rensha_tool.py
```

Executable self-test:

```powershell
.\配布用\右+左 連射ツール.exe --self-test
```

## Notes

- Windows only.
- The physical right-click input is still passed through to the target app.
- If the target app is running as administrator and does not receive input, the clicker may also need to be run as administrator.
- Follow the rules and terms of the app or service where you use it.
- This tool is not intended for bypassing game rules, service terms, or anti-cheat systems.
