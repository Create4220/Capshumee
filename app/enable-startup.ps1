$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$exe = Join-Path $root '卡输咪.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build 卡输咪.exe first.' }
& (Join-Path $root 'scripts\lock-network.ps1') -VerifyOnly | Out-Null
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
New-Item -Path $key -Force | Out-Null
New-ItemProperty -LiteralPath $key -Name '卡输咪' -Value ('"'+$exe+'"') -PropertyType String -Force | Out-Null
Write-Output 'Login startup enabled for the current user. Recording requires Caps Lock.'
