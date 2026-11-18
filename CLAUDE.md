# CLAUDE.md

このファイルは、本リポジトリで作業する Claude Code 向けのガイドです。

## プロジェクト概要

- 名称: ベール在庫・製造・出荷計画アプリ（waste-inventry-management-app）
- 目的: 実在庫・2週間の出荷予定・製造能力から、日別・午前午後別の製造数と圧縮梱包機の運転時間を提案する
- 状態: 試作版（計画ロジック・SQLite保存・Tkinter画面）
- 仕様・確定済みの計算ルール: [docs/spec.md](docs/spec.md)（仕様変更時はここも更新する）
- 技術: Python 3.12 / Tkinter / SQLite / jpholiday / pytest。Windows タブレット1台・オフラインで動作

## 構成

- `bale_planner/planner.py` — 計画計算の中心（`build_plan`）。UI から独立した純粋ロジックに保つ
- `bale_planner/workcalendar.py` — 製造可能日・出荷可能日の判定
- `bale_planner/models.py` — データ構造（SQLite のテーブルに移せる形）
- `bale_planner/scenarios.py` — ダミーデータとテストシナリオ
- `bale_planner/cli.py` — 確認用のコンソール表示
- `bale_planner/db.py` — SQLite 保存（`Repository`）
- `bale_planner/service.py` — DB から計画を再計算（`compute`）
- `installer/` — 配布用（PyInstaller で exe 化 → Inno Setup でインストーラ化）。手順は [docs/install.md](docs/install.md)
- `bale_planner/app.py` — タッチ操作向け画面。処理は `App` のメソッドに置き、ダイアログはその呼び出しだけにする（テストでダイアログを開かずに検証するため）

## コマンド

```sh
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt   # 実行用は requirements.txt（jpholiday のみ）
.venv/Scripts/python -m pytest -q                         # テスト
.venv/Scripts/python -m bale_planner.cli normal --compare # シナリオを両モードで表示
.venv/Scripts/python -m bale_planner.app --demo           # デモデータで画面を起動（DBは一時）
.venv/Scripts/python -m bale_planner.app                  # 通常起動（%LOCALAPPDATA%/BalePlanner に保存）
build_installer.bat                                       # インストーラ作成 → dist/BalePlanner-Setup-<version>.exe
powershell -ExecutionPolicy Bypass -File installer\make_python_kit.ps1  # Python版キット作成（署名なしでSAC対策）→ docs/install_python.md
```

リリース時は `bale_planner/__init__.py` の `__version__` を上げてからインストーラを作成する。
開発PCはスマートアプリコントロールが有効で、署名のない exe がブロックされることがある（ビルドの動作確認は警告を出してスキップされる）。
ロジックを変更したら必ずテストを実行し、全件成功を確認してからコミットする。
画面を変更したら実際に起動して表示を確認する（高DPIで行の高さや折り返しが崩れやすい。サイズはフォント高さ基準で決める）。

## Git 運用ルール

- リモート: `origin` = https://github.com/MuS-code666/wasete-inventry-management-app.git
- メインブランチ: `main`
- **コードを変更するたびに、変更をコミットして GitHub（`origin`）にプッシュすること。**
  - 変更が一区切りついたら `git add` → `git commit` → `git push` まで必ず行う。
  - 作業を終える前に、未コミット・未プッシュの変更が残っていないか `git status` で確認する。
- コミットは論理的な単位で小さく分け、何を・なぜ変更したかがわかるメッセージを書く。
- 秘密情報（APIキー、パスワード、`.env` など）はコミットしない。`.gitignore` で除外する。
- `--force` プッシュやフックのスキップ（`--no-verify`）は、ユーザーの明示的な指示がない限り行わない。
