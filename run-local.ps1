param([switch]$Dictation)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot)
if ($root.StartsWith('\\')) { throw 'Use a local disk directory.' }
$hostPath = Join-Path $root 'runtime\host\asr-python.exe'
foreach ($relative in @('runtime\host\asr-python.exe','models\sensevoice\model.int8.onnx','models\sensevoice\tokens.txt')) {
  if (-not (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) { throw "Required local file missing: $relative" }
}
& (Join-Path $root 'scripts\lock-network.ps1') -VerifyOnly | Out-Null
$argument = '-I -B "' + (Join-Path $root 'app\dictation_app.py') + '"'
Start-Process -FilePath $hostPath -ArgumentList $argument -WorkingDirectory $root -WindowStyle Hidden | Out-Null
