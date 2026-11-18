#! python3
"""ベール製造計画 初回セットアップ（ダブルクリックで実行）。

スマート アプリ コントロールが有効な PC では、メールやダウンロードで受け取った .bat が
「インターネットから来た危険な拡張子」としてブロックされるため、セットアップは Python で行う。

  1. Python のバージョンと tkinter を確認
  2. このフォルダに仮想環境（.venv）を作成
  3. wheels フォルダから追加パッケージを導入（インターネット不要）
  4. 動作確認
  5. デスクトップにショートカットを作成
"""
import base64
import os
import shutil
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv")
PY = os.path.join(VENV, "Scripts", "python.exe")
PYW = os.path.join(VENV, "Scripts", "pythonw.exe")
ICON = os.path.join(HERE, "bale_planner", "assets", "app.ico")
SHORTCUTS = [("ベール製造計画", ""), ("ベール製造計画（全画面）", "--fullscreen")]


def step(n, text):
    print(f"[{n}/5] {text}", flush=True)


def run(args):
    r = subprocess.run(args, cwd=HERE, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"コマンドが失敗しました: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def make_shortcut(name: str, args: str) -> str:
    """デスクトップにショートカット（.lnk）を作る。pythonw を直接起動するので .bat を使わない。"""
    q = lambda s: s.replace("'", "''")
    ps = (
        "$s = New-Object -ComObject WScript.Shell;"
        "$d = [Environment]::GetFolderPath('Desktop');"
        f"$p = Join-Path $d '{q(name)}.lnk';"
        "$l = $s.CreateShortcut($p);"
        f"$l.TargetPath = '{q(PYW)}';"
        f"$l.Arguments = '-m bale_planner.app {q(args)}'.Trim();"
        f"$l.WorkingDirectory = '{q(HERE)}';"
        f"$l.IconLocation = '{q(ICON)}';"
        "$l.Save(); Write-Output $p"
    )
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    return run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc]).strip()


def main(no_shortcut: bool) -> None:
    step(1, "Python を確認しています...")
    print(f"      Python {sys.version.split()[0]}  ({sys.executable})")
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 以降が必要です。同梱の python-3.12.10-amd64.exe をインストールしてください。")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        raise RuntimeError("この Python には画面表示の部品（tcl/tk）がありません。\n"
                           "Python のインストーラを再実行 →「Modify」→「tcl/tk and IDLE」にチェックしてください。")

    step(2, "仮想環境（.venv）を作成しています...")
    if os.path.exists(VENV):
        shutil.rmtree(VENV)
    run([sys.executable, "-m", "venv", VENV])

    step(3, "追加パッケージを導入しています（インターネット不要）...")
    run([PY, "-m", "pip", "install", "--no-index", "--find-links", "wheels", "-r", "requirements.txt",
         "-q", "--disable-pip-version-check"])

    step(4, "動作確認をしています...")
    check = os.path.join(HERE, "setup_check.txt")
    r = subprocess.run([PY, "-m", "bale_planner.app", "--check", check], cwd=HERE)
    with open(check, encoding="utf-8") as fh:
        print("      " + fh.read().replace("\n", "\n      "))
    if r.returncode != 0:
        raise RuntimeError("動作確認に失敗しました。setup_check.txt を開発担当に送ってください。")

    step(5, "デスクトップにショートカットを作成しています...")
    if no_shortcut:
        print("      （スキップ）")
    else:
        for name, args in SHORTCUTS:
            try:
                print("      作成: " + make_shortcut(name, args))
            except Exception as e:
                print(f"      作成できませんでした（{name}）: 手順書の「ショートカットを手動で作る」を参照してください")
                print("      " + str(e).splitlines()[0])

    print()
    print("=" * 70)
    print(" セットアップが完了しました。")
    print(" デスクトップの「ベール製造計画」または「ベール製造計画（全画面）」から起動してください。")
    print("=" * 70)


if __name__ == "__main__":
    ok = True
    try:
        main(no_shortcut="--no-shortcut" in sys.argv)
    except Exception as e:
        ok = False
        print()
        print("!" * 70)
        print(" エラー: " + str(e))
        print("!" * 70)
        if not isinstance(e, RuntimeError):
            traceback.print_exc()
        print(" この画面の写真を撮って、開発担当に送ってください。")
    if "--no-pause" not in sys.argv:
        input("\nEnter キーを押すと閉じます...")
    sys.exit(0 if ok else 1)
