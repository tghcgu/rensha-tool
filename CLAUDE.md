# CLAUDE.md

右+左 連射ツール: Windows 用の連射ツールです。Python の標準ライブラリ(tkinter と ctypes)だけで書かれた1ファイル構成(`rensha_tool.pyw`)です。

作業を始める前に [HANDOFF.md](HANDOFF.md) を読んでください。今の状態、残っている作業、仕組みの要点、これまでの決定が書いてあります。

## コマンド

- テスト: `py tests\test_rensha.py`(実際のクリックは送りません。終了コード 0 で全件成功)
- 起動: `py rensha_tool.pyw`
- exe のビルドと自己チェック: HANDOFF.md の「4. exe のビルド」。PowerShell で exe に `--self-test` を付けて直接実行すると結果が出ないので、`Start-Process -Wait -PassThru` で ExitCode を見ます。

## 守ること

- マウスイベントは必ず `WindowsMouse._send` 経由で送ってください。`RENSHA_SIGNATURE` が付かないと、フックが自分のクリックをユーザーの物理クリックと誤認します。
- 左ボタンを押した状態で終わる注入をしたら、ユーザーの指が離れているときに LEFTUP を送る責任があります(`_release_left_if_free`)。左ボタンを押されたまま残さないでください。
- アプリ自身のウィンドウの上では、クリックを注入しないでください。
- Tk のウィジェットは UI スレッドからだけ触ってください。
- 動作確認で実際のクリックを送らないでください。ユーザーの PC で何をクリックするか分かりません。テストは偽のマウスで書きます。
- 作業の区切りで HANDOFF.md を更新してコミットし、作業ブランチを GitHub に push してください。PC が壊れても引き継げるようにしたい、というユーザーの要望です。
