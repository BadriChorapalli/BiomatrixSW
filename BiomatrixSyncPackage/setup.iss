; BiomatrixSync — Inno Setup Script
; Builds a single-file installer wizard for Windows

#define AppName      "BiomatrixSync"
#define AppVersion   "1.0.0"
#define AppPublisher "BellWeather School Insights"
#define AppURL       "https://schoolinsights.in"
#define InstallDir   "{autopf}\BiomatrixSync"

[Setup]
AppId={{A3F7C2D1-4B8E-4F9A-B2C3-D4E5F6A7B8C9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={#InstallDir}
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename=BiomatrixSync_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableProgramGroupPage=yes
UninstallDisplayName=BiomatrixSync
UninstallDisplayIcon={app}\BiomatrixSync.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; GUI application
Source: "dist\BiomatrixSync.exe";        DestDir: "{app}"; Flags: ignoreversion
; Windows service executable
Source: "dist\BiomatrixSyncService.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcut for the GUI app
Name: "{group}\BiomatrixSync";         Filename: "{app}\BiomatrixSync.exe"
Name: "{group}\Uninstall BiomatrixSync"; Filename: "{uninstallexe}"
; Desktop shortcut
Name: "{autodesktop}\BiomatrixSync";   Filename: "{app}\BiomatrixSync.exe"

[Run]
; Install and start the Windows service after files are copied
Filename: "{app}\BiomatrixSyncService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing background service..."
Filename: "sc.exe"; Parameters: "config BiomatrixSync start= auto"; Flags: runhidden waituntilterminated; StatusMsg: "Configuring service auto-start..."
Filename: "{app}\BiomatrixSyncService.exe"; Parameters: "start";   Flags: runhidden waituntilterminated; StatusMsg: "Starting background service..."
; Offer to launch the GUI after install
Filename: "{app}\BiomatrixSync.exe"; Description: "Launch BiomatrixSync now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop and remove the service on uninstall
Filename: "{app}\BiomatrixSyncService.exe"; Parameters: "stop";   Flags: runhidden waituntilterminated; RunOnceId: "StopService"
Filename: "{app}\BiomatrixSyncService.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"

[Code]
// Show a success message at the end of installation
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    MsgBox(
      'BiomatrixSync has been installed successfully.' + #13#10 + #13#10 +
      'The background sync service is now running.' + #13#10 +
      'Use the desktop shortcut to open the application.',
      mbInformation, MB_OK
    );
  end;
end;
