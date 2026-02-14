; Inno Setup script for Claude Tracker
; Compile with: iscc installer.iss

#define MyAppName "Claude Tracker"
#define MyAppExeName "ClaudeTracker.exe"
#define MyAppPublisher "Claude Tracker"
#define MyAppURL "https://github.com/niceperson4210/claude-tracker"

; Version is passed via /DMyAppVersion=x.y.z from CI; default for local builds
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

[Setup]
; Stable AppId — never change this, it ties all versions together for upgrades
AppId={{B3F7E2A1-9C4D-4E8B-A1F6-3D5C7E9B2A4F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\ClaudeTracker
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=ClaudeTracker-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Allow reinstall / upgrade over existing installation
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startup"; Description: "Start with &Windows"; GroupDescription: "Startup:"

[Files]
Source: "dist\ClaudeTracker.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; "Run on startup" — created only when user checks the task, removed on uninstall
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ClaudeTracker"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Kill the app before uninstalling so the exe isn't locked
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: files; Name: "{app}\*"
Type: dirifempty; Name: "{app}"

[Code]
// Always remove the startup registry entry on uninstall, even if it was toggled via app settings
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'ClaudeTracker');
  end;
end;
