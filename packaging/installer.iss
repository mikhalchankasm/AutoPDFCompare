; Inno Setup script for PDFCompare Local.
;
; Per-user install (no admin / UAC prompt): files go to
; {localappdata}\Programs\PDFCompareLocal, which lets the app self-update by
; downloading this installer and running it with /SILENT.
;
; Build (version comes from pdfcompare_core/constants.py in CI):
;   ISCC.exe /DAppVersion=0.1.13 packaging\installer.iss
; Output: dist_installer\PDFCompareLocal-setup.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "PDFCompare Local"
#define AppExeName "PDFCompareLocal.exe"
#define AppPublisher "mikhalchankasm"
#define AppURL "https://github.com/mikhalchankasm/AutoPDFCompare"

[Setup]
; Stable AppId keeps upgrades installing over the previous version.
AppId={{7B0E9E45-2A0C-4E64-B9F3-5C8D2B1A9F0D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\PDFCompareLocal
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist_installer
OutputBaseFilename=PDFCompareLocal-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Ask a running instance to close before replacing files (silent updates rely on
; the app exiting first; this covers a manually started copy).
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The one-DIR build: the Python runtime sits next to the exe instead of being
; unpacked into %TEMP% on every start. The one-file build raced with this
; installer's own silent relaunch (it deletes its _MEI<pid> temp dir on exit,
; and Windows reuses pids immediately), producing a half-extracted runtime and
; "Failed to load Python DLL".
Source: "..\dist\PDFCompareLocal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Interactive install: offer to launch at the finish page.
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; Silent install (in-app auto-update): relaunch the app automatically.
Filename: "{app}\{#AppExeName}"; Flags: nowait skipifnotsilent
