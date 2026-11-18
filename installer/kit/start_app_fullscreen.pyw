#! python3
"""ベール製造計画をタブレット向けの全画面で起動する（ダブルクリック）。F11 で切り替え。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from start_app import launch  # noqa: E402

if __name__ == "__main__":
    launch(["--fullscreen"])
