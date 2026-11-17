; ベール製造計画アプリ インストーラ定義（Inno Setup 6）
; installer\build.ps1 から /DAppVersion=x.y.z を渡してコンパイルする

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "ベール製造計画"
#define AppExe "BalePlanner.exe"

[Setup]
; AppId はアップデート時に同じアプリと認識するための固定値（変更しないこと）
AppId={{FA7AA0E6-5B59-488C-AC43-DE597A69A89B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={autopf}\BalePlanner
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 管理者権限なしでインストールできる（工場のタブレット向け）。管理者なら全ユーザー向けも選べる
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=BalePlanner-Setup-{#AppVersion}
SetupIconFile=..\bale_planner\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\dist\BalePlanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName}（全画面）"; Filename: "{app}\{#AppExe}"; Parameters: "--fullscreen"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Messages]
; アンインストールしても入力データ（%LOCALAPPDATA%\BalePlanner）は残す
UninstalledAll=%1 を削除しました。%n%n入力したデータ（在庫・出荷予定・設定）は次の場所に残しています。不要な場合は手動で削除してください。%n%LOCALAPPDATA%\BalePlanner
