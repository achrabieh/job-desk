; Job Desk per-user installer. Built by installer\build.ps1 (needs Inno Setup 6).
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#ifndef StageDir
  #define StageDir "..\build\stage"
#endif

[Setup]
AppId={{9D621FCA-65B8-4075-811F-74FD87D0FFB4}
AppName=Job Desk
AppVersion={#AppVersion}
AppPublisher=Job Desk contributors
AppPublisherURL=https://github.com/achrabieh/job-desk
DefaultDirName={localappdata}\Programs\Job Desk
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=JobDesk-Setup
SetupIconFile=jobdesk.ico
UninstallDisplayIcon={app}\jobdesk.ico
UninstallDisplayName=Job Desk
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Put a Job Desk icon on my desktop"; Flags: checkedonce

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; replace the old program files on update (your CV and data live in Documents\Job Desk and are never touched)
Type: filesandordirs; Name: "{app}\app"

[Icons]
Name: "{autodesktop}\Job Desk"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\jobdesk\app.py"""; WorkingDir: "{app}"; IconFilename: "{app}\jobdesk.ico"; Tasks: desktopicon
Name: "{autoprograms}\Job Desk"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\jobdesk\app.py"""; WorkingDir: "{app}"; IconFilename: "{app}\jobdesk.ico"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\jobdesk\app.py"""; WorkingDir: "{app}"; Description: "Open Job Desk now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""Job Desk - morning search"" /F"; Flags: runhidden; RunOnceId: "RemoveSchedule"

[Messages]
FinishedLabel=Job Desk is installed. It will open in your web browser and walk you through setup. Your CV and everything you create are kept in the "Job Desk" folder in your Documents.
