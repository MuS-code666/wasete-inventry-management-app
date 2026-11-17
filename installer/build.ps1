# ベール製造計画アプリのインストーラを作成する。
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1
# 出力: dist\BalePlanner-Setup-<version>.exe
#
# 必要なもの（開発PCのみ。インストール先のPCには不要）
#   - .venv（requirements.txt と requirements-build.txt をインストール済み）
#   - Inno Setup 6（winget install JRSoftware.InnoSetup --scope user）

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw ".venv がありません。README の手順で作成してください。" }

$version = (& $py -c "import bale_planner; print(bale_planner.__version__)").Trim()
Write-Host "== バージョン $version"

Write-Host "== テスト"
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "テストが失敗しました。インストーラは作成しません。" }

Write-Host "== アイコン生成"
& $py installer\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "アイコン生成に失敗しました。" }

Write-Host "== exe 作成（PyInstaller）"
& $py -m PyInstaller --noconfirm --clean --windowed `
    --name BalePlanner `
    --icon "$root\bale_planner\assets\app.ico" `
    --add-data "$root\bale_planner\assets;bale_planner\assets" `
    --collect-submodules jpholiday `
    --exclude-module pytest --exclude-module PIL `
    --distpath "$root\build\dist" --workpath "$root\build\work" --specpath "$root\build" `
    "$root\installer\launcher.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller が失敗しました。" }

Write-Host "== exe の動作確認"
$check = Join-Path $root "build\selfcheck.txt"
Remove-Item $check -ErrorAction SilentlyContinue
try {
    $proc = Start-Process "$root\build\dist\BalePlanner\BalePlanner.exe" -ArgumentList "--check", "`"$check`"" -Wait -PassThru
    Get-Content $check -Encoding UTF8
    if ($proc.ExitCode -ne 0) { throw "exe の動作確認に失敗しました。" }
} catch [System.InvalidOperationException] {
    # Windows 11 のスマートアプリコントロール等で、署名のない exe の実行が禁止されている PC
    Write-Warning "この PC のアプリ制御ポリシーにより exe を実行できないため、動作確認をスキップします。"
    Write-Warning "署名のない exe は、スマートアプリコントロールが有効な PC では起動できません（README 参照）。"
}

Write-Host "== インストーラ作成（Inno Setup）"
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 が見つかりません。winget install JRSoftware.InnoSetup --scope user" }
& $iscc "/DAppVersion=$version" "$root\installer\BalePlanner.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup が失敗しました。" }

Write-Host "== 完了: $root\dist\BalePlanner-Setup-$version.exe"
