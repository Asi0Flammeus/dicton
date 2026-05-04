#define AppName "Dicton"
#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

[Setup]
AppId={{1D6E8B7C-1BB7-4A58-8E1F-7F4E8D4F0A21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=asi0 flammeus
AppPublisherURL=https://github.com/Asi0Flammeus/dicton
AppSupportURL=https://github.com/Asi0Flammeus/dicton/issues
AppUpdatesURL=https://github.com/Asi0Flammeus/dicton/releases/latest
DefaultDirName={localappdata}\Programs\Dicton
DefaultGroupName=Dicton
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=DictonSetup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Dicton
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start Dicton automatically when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
Source: "..\..\dist\dicton\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Dicton"; Filename: "{app}\dicton.exe"
Name: "{group}\Dicton Setup"; Filename: "{app}\dicton.exe"; Parameters: "--config"
Name: "{group}\Uninstall Dicton"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Dicton"; Filename: "{app}\dicton.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Dicton"; ValueData: """{app}\dicton.exe"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\dicton.exe"; Parameters: "--config"; Description: "Open Dicton setup"; Flags: nowait postinstall skipifsilent
