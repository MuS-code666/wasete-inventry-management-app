#! python3
"""ベール製造計画を起動する（ダブルクリック）。全画面にするには --fullscreen を付けるか start_app_fullscreen.pyw を使う。

通常はセットアップ時にデスクトップへ作られるショートカットから起動する。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(HERE, ".venv", "Scripts", "pythonw.exe")


def launch(extra=()):
    if not os.path.exists(PYW):
        import tkinter.messagebox as mb

        mb.showerror("ベール製造計画", "セットアップが済んでいません。\n先に setup_env.py をダブルクリックしてください。")
        return
    subprocess.Popen([PYW, "-m", "bale_planner.app", *extra, *sys.argv[1:]], cwd=HERE)


if __name__ == "__main__":
    launch()
