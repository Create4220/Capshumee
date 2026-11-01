param(
  [string]$Python='python',
  [string]$Iscc='ISCC',
  [string]$RuntimeSource,
  [string]$ModelSource,
  [switch]$UsePreparedPayload
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$compiler=(Get-Command $Iscc -ErrorAction Stop).Source
if (-not $UsePreparedPayload) {
  $arguments=@('-I',(Join-Path $PSScriptRoot 'prepare_payload.py'))
  if ($RuntimeSource) { $arguments+=@('--runtime-source',$RuntimeSource) }
  if ($ModelSource) { $arguments+=@('--model-source',$ModelSource) }
  & $Python @arguments
  if ($LASTEXITCODE -ne 0) { throw 'Payload preparation failed.' }
}
$license='卡输咪应用使用 MIT 许可。安装包中的 SenseVoice 模型使用独立的 FunASR 模型开源协议；其他组件许可随安装包提供。'+"`r`n`r`n"
$license+=(Get-Content -LiteralPath (Join-Path $root 'LICENSE') -Raw -Encoding UTF8)+"`r`n`r`n"
$license+=(Get-Content -LiteralPath (Join-Path $root 'licenses\FunASR-MODEL-LICENSE.txt') -Raw -Encoding UTF8)
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'license.txt'),$license,[Text.UTF8Encoding]::new($true))
& $compiler /Qp (Join-Path $PSScriptRoot 'Capshumee.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
Write-Output 'Offline installer ready in dist. Verify, scan and hash before publishing.'
