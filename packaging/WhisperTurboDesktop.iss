; Whisper Turbo Desktop bootstrap installer

#ifndef MyAppVersion
  #define MyAppVersion "0.2.6"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\release\bootstrap"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "..\release\installer"
#endif

#define MyAppName "Whisper Turbo Desktop"
#define MyAppPublisher "mc_leafwave"
#define MyAppURL "https://github.com/Orion-Quest/whisper-turbo-desktop"
#define MyBootstrapExe "WhisperTurboDesktop.exe"
#define MyManifestName "release-manifest.json"
#define MyAppId "{{D8D2A5A8-6E0B-4D78-A9A7-5D44F4E4E9A1}}"
#define MyIconFile "..\assets\app.ico"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\WhisperTurboDesktop
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#MyOutputDir}
OutputBaseFilename=WhisperTurboDesktop-Bootstrap-Setup-{#MyAppVersion}
SetupIconFile={#MyIconFile}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyBootstrapExe}
ChangesAssociations=no
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousLanguage=yes
UsePreviousTasks=yes
MinVersion=10.0
ExtraDiskSpaceRequired=104857600

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{userappdata}\WhisperTurboDesktop"; Permissions: users-modify

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyBootstrapExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyBootstrapExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyBootstrapExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
