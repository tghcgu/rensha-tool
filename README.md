# 右+左 連射ツール

[English](README.en.md)

右クリックを押しながら左クリックしている間だけ、左クリックを連射するWindows用ツールです。

余計な起動ショートカットは使わず、配布用のexeを直接開く構成にしています。

## 特徴

- 右クリック + 左クリックを押している間だけ連射
- どちらかを離すと即停止
- 連射速度を画面から調整可能
- Pythonなしで動く配布用exe付き
- 外部サービスや常駐インストール不要

## 必要環境

- Windows
- 配布用exeを使う場合、Pythonは不要
- ソースから実行する場合のみ Python 3 が必要

## 起動

通常はこのファイルを開きます。

```text
配布用\右+左 連射ツール.exe
```

エクスプローラーで `配布用` フォルダを開き、`右+左 連射ツール.exe` をダブルクリックしてください。

## 使い方

1. `配布用\右+左 連射ツール.exe` を開きます。
2. 必要なら「連射速度」を調整します。
3. 対象画面に移動します。
4. 右クリックを押したまま左クリックします。
5. 左クリックか右クリックを離すと連射が止まります。

## 配布

配布するファイルは基本的にこれ1つです。

```text
配布用\右+左 連射ツール.exe
```

相手のPCにPythonは必要ありません。

## フォルダ構成

```text
rensha-tool
├─ README.md
├─ README.en.md
├─ rensha_tool.py
├─ .gitignore
└─ 配布用
   └─ 右+左 連射ツール.exe
```

## ソースから実行

開発中にPythonで直接起動する場合は、プロジェクトフォルダで次を実行します。

```powershell
py rensha_tool.py
```

## exeを作り直す

PyInstallerを使ってexeを作り直します。

```powershell
py -m pip install --user pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "右+左 連射ツール" --distpath ".\配布用" --workpath ".\build" --specpath ".\build" .\rensha_tool.py
```

作成後、`配布用\右+左 連射ツール.exe` が更新されます。

## 動作確認

ソースコードの構文チェック:

```powershell
py -m py_compile .\rensha_tool.py
```

exeの自己チェック:

```powershell
.\配布用\右+左 連射ツール.exe --self-test
```

## 注意

- Windows専用です。
- 右クリック自体も対象アプリに届きます。
- 管理者権限で動いているアプリに対して入力が届かない場合は、ツール側も管理者として起動する必要があることがあります。
- 使用先のルールや規約に従ってください。
- ゲームやサービスの規約回避、アンチチート回避を目的とした使い方は想定していません。
