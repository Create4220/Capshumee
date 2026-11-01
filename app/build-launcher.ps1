param([string]$Compiler='g++',[string]$ResourceCompiler='windres')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cc = (Get-Command $Compiler -ErrorAction Stop).Source
$rc = (Get-Command $ResourceCompiler -ErrorAction Stop).Source
$obj = Join-Path $root 'app\capshumee-res.o'
& $rc -c 65001 -I (Join-Path $root 'assets') -i (Join-Path $root 'app\Capshumee.rc') -o $obj
if ($LASTEXITCODE -ne 0) { throw 'Icon resource build failed.' }
& $cc (Join-Path $root 'app\launcher.cpp') $obj -o (Join-Path $root '卡输咪.exe') -Os -s -municode -mwindows -static -static-libgcc -static-libstdc++ -luser32
if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }
