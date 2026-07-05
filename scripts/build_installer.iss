; Inno Setup script -- builds a real Windows installer around the PyInstaller
; onefile exe: Start Menu shortcut, optional Desktop shortcut, and a proper
; uninstall entry in Windows Settings > Apps.
;
; Prerequisite: build dist\viewYUV.exe first (see README's "Building a
; standalone executable" section).
;
; Build with:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" scripts\build_installer.iss
;
; Output: dist\viewYUV-Setup.exe

#define MyAppName "YUView-lite"
#define MyAppVersion "0.1.0"
#define MyAppExeName "viewYUV.exe"

[Setup]
AppId={{B6E1E2F0-6E0B-4C9E-9C7E-9B7B7C9A9C10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist
OutputBaseFilename=viewYUV-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\resources\icon.ico
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
