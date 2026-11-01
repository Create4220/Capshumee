$ErrorActionPreference = 'Stop'
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if (Get-ItemProperty -LiteralPath $key -Name '卡输咪' -ErrorAction SilentlyContinue) {
  Remove-ItemProperty -LiteralPath $key -Name '卡输咪'
}
Write-Output 'Capshumee login startup disabled. Exit the running app from its tray menu.'
