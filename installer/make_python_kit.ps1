# Python版キット（インストーラを使わない配布用）を作成する。
#   powershell -ExecutionPolicy Bypass -File installer\make_python_kit.ps1
#   powershell -ExecutionPolicy Bypass -File installer\make_python_kit.ps1 -PythonInstaller C:\path\python-3.12.10-amd64.exe
# 出力: dist\BalePlanner-PythonKit-<version>\ と同名の .zip
#
# キットには、アプリのソース・起動用バッチ・オフラインで入れるためのパッケージ（wheels）を入れる。
# -PythonInstaller を指定すると Python のインストーラも同梱する（顧客PCがオフラインの場合）。

param([string]$PythonInstaller = "")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw ".venv がありません。" }

$version = (& $py -c "import bale_planner; print(bale_planner.__version__)").Trim()
$name = "BalePlanner-PythonKit-$version"
$kit = Join-Path $root "dist\$name"
Write-Host "== キット作成: $kit"

Write-Host "== テスト"
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "テストが失敗しました。キットは作成しません。" }

if (Test-Path $kit) { Remove-Item $kit -Recurse -Force }
New-Item -ItemType Directory -Path $kit | Out-Null

# アプリ本体（キャッシュは除く）
Copy-Item "$root\bale_planner" "$kit\bale_planner" -Recurse
Get-ChildItem $kit -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
# .bat は入れない：メール等で受け取ったPCではスマートアプリコントロールにブロックされるため、
# セットアップ・起動は .py / .pyw とショートカット（pythonw を直接起動）で行う
Copy-Item "$root\requirements.txt" $kit
Copy-Item "$root\installer\kit\*" $kit -Exclude "__pycache__"
Copy-Item "$root\docs\install_python.md" $kit

Write-Host "== オフライン用パッケージ（wheels）を取得"
& $py -m pip download -r "$root\requirements.txt" -d "$kit\wheels" --only-binary=:all: --disable-pip-version-check -q
if ($LASTEXITCODE -ne 0) { throw "パッケージの取得に失敗しました（インターネット接続を確認）。" }

if ($PythonInstaller) {
    if (-not (Test-Path $PythonInstaller)) { throw "Python インストーラが見つかりません: $PythonInstaller" }
    Write-Host "== Python インストーラを同梱: $(Split-Path $PythonInstaller -Leaf)"
    Copy-Item $PythonInstaller $kit
}

$zip = "$kit.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $kit -DestinationPath $zip
Write-Host "== 完了"
Get-ChildItem $kit | Select-Object Name | Format-Table -HideTableHeaders
Write-Host "ZIP: $zip"
