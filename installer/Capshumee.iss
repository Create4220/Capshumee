#define AppVersion "1.0.0"
#define Payload "..\.payload"
[Setup]
AppId={{18B62C4A-9C6F-4B3F-B0B1-E6B0CF68B344}
AppName=卡输咪
AppVersion={#AppVersion}
AppVerName=卡输咪 {#AppVersion}
AppPublisher=川宁（Create4220）
AppPublisherURL=https://github.com/Create4220/Capshumee
AppSupportURL=https://github.com/Create4220/Capshumee/issues
DefaultDirName={localappdata}\Programs\卡输咪
DefaultGroupName=卡输咪
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
AllowNetworkDrive=no
AllowUNCPath=no
OutputDir=..\dist
OutputBaseFilename=Capshumee-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\assets\capshumee.ico
UninstallDisplayIcon={app}\卡输咪.exe
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
UsePreviousTasks=no
AppMutex=Local\Capshumee
LicenseFile=license.txt
CloseApplications=yes
RestartApplications=no
SetupLogging=no

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "在桌面创建卡输咪快捷方式"; GroupDescription: "快捷方式："
Name: "startup"; Description: "我同意登录 Windows 后自动启动卡输咪（不会自动录音）"; GroupDescription: "开机启动权限（可选）："; Flags: unchecked

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "app\settings.json"
Source: "{#Payload}\app\settings.json"; DestDir: "{app}\app"; Flags: onlyifdoesntexist

[Icons]
Name: "{autoprograms}\卡输咪"; Filename: "{app}\卡输咪.exe"; IconFilename: "{app}\卡输咪.exe"
Name: "{autodesktop}\卡输咪"; Filename: "{app}\卡输咪.exe"; IconFilename: "{app}\卡输咪.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\卡输咪.exe"; Description: "立即启动卡输咪（按 Caps Lock 才录音）"; Flags: nowait postinstall skipifsilent

[Code]
const
  StartupKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := '卡输咪是一款轻量级本地语音输入工具。安装包已经包含识别模型和运行环境，无需另装 Python。' + #13#10#13#10 +
    '安装过程中将请求一次管理员授权，仅用于设置阻止本程序联网的 Windows 防火墙规则。' + #13#10#13#10 +
    '是否开机自启由您在附加任务页主动选择；程序启动后只待机，不会自动录音。';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Arguments: String;
  StartupValue: String;
begin
  if CurStep = ssPostInstall then begin
    Arguments := '-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\scripts\lock-network.ps1') + '"';
    if not ShellExec('runas', ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Arguments, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      RaiseException('离线保护设置未完成。请允许防火墙管理员授权后重新安装；程序不会绕过检查联网。');
    if ResultCode <> 0 then
      RaiseException('Windows 防火墙保护设置失败。请检查系统防火墙服务后重新安装。');
    if WizardIsTaskSelected('startup') then begin
      if not RegWriteStringValue(HKCU, StartupKey, '卡输咪', '"' + ExpandConstant('{app}\卡输咪.exe') + '"') then
        RaiseException('无法保存开机启动设置。请检查当前用户的启动项权限。');
    end else begin
      if RegQueryStringValue(HKCU, StartupKey, '卡输咪', StartupValue) then
        if StartupValue = '"' + ExpandConstant('{app}\卡输咪.exe') + '"' then
          RegDeleteValue(HKCU, StartupKey, '卡输咪');
    end;

  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  Arguments: String;
  StartupValue: String;
begin
  if CurUninstallStep = usUninstall then begin

    if RegQueryStringValue(HKCU, StartupKey, '卡输咪', StartupValue) then
      if StartupValue = '"' + ExpandConstant('{app}\卡输咪.exe') + '"' then
        RegDeleteValue(HKCU, StartupKey, '卡输咪');
    Exec(ExpandConstant('{app}\卡输咪.exe'), '--quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);
    Arguments := '-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\scripts\lock-network.ps1') + '" -Remove';
    ShellExec('runas', ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Arguments, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
