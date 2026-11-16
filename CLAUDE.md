# CLAUDE.md

このファイルは、本リポジトリで作業する Claude Code 向けのガイドです。

## プロジェクト概要

- 名称: waste-inventry-management-app（廃棄物在庫管理アプリ）
- 状態: 初期セットアップ段階（ソースコードはまだありません）
- 技術スタック・ビルド/テストコマンドが決まり次第、このファイルに追記してください。

## Git 運用ルール

- リモート: `origin` = https://github.com/MuS-code666/wasete-inventry-management-app.git
- メインブランチ: `main`
- **コードを変更するたびに、変更をコミットして GitHub（`origin`）にプッシュすること。**
  - 変更が一区切りついたら `git add` → `git commit` → `git push` まで必ず行う。
  - 作業を終える前に、未コミット・未プッシュの変更が残っていないか `git status` で確認する。
- コミットは論理的な単位で小さく分け、何を・なぜ変更したかがわかるメッセージを書く。
- 秘密情報（APIキー、パスワード、`.env` など）はコミットしない。`.gitignore` で除外する。
- `--force` プッシュやフックのスキップ（`--no-verify`）は、ユーザーの明示的な指示がない限り行わない。
