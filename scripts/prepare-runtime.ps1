param(
  [Parameter(Mandatory=$true)][string]$Python,
  [Parameter(Mandatory=$true)][string]$Wheelhouse
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = (Get-Command $Python -ErrorAction Stop).Source
$wheels = (Resolve-Path -LiteralPath $Wheelhouse).Path
if ($wheels.StartsWith('\\')) { throw 'Wheelhouse must be on local storage.' }
$packages = Join-Path $root 'runtime\python'
New-Item -Path $packages -ItemType Directory -Force | Out-Null
& $pythonPath -I -c 'import struct,sys; assert sys.version_info[:2]==(3,12) and struct.calcsize("P")==8, "Use 64-bit Python 3.12"'
if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python runtime.' }
& $pythonPath -m pip --disable-pip-version-check install --no-index --only-binary=:all: --find-links $wheels --target $packages --requirement (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Local wheel installation failed; no network fallback is used.' }
& $pythonPath -I (Join-Path $PSScriptRoot 'prepare_runtime.py')
if ($LASTEXITCODE -ne 0) { throw 'Local runtime preparation failed.' }
