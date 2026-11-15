param([ValidateRange(5,3600)][int]$PollSeconds = 15)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Project = Join-Path $Root 'Wishless.uproject'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git for Windows required' }
git lfs version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Git LFS required: https://git-lfs.com/' }
$BundledPython = Join-Path ${env:ProgramFiles} 'Epic Games\UE_5.8\Engine\Binaries\ThirdParty\Python3\Win64\python.exe'
$Python = Get-Command py -ErrorAction SilentlyContinue
if (Test-Path $BundledPython) { $PyExe=$BundledPython; $Prefix=@() }
elseif ($Python) { $PyExe=$Python.Source; $Prefix=@('-3') }
else {
  $Python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $Python) { throw 'Python 3.11+ is required' }
  $PyExe=$Python.Source; $Prefix=@()
}
$Sync = Join-Path $Root 'tools/wishless_sync.py'
Write-Host 'Wishless: synchronizing GitHub before starting UE5...'
& $PyExe @Prefix $Sync once --root $Root
if ($LASTEXITCODE -ne 0) { throw 'Sync blocked or failed. Unreal was not opened.' }
Start-Process -FilePath $Project
Write-Host 'Wishless bridge running. Keep this PowerShell window open.'
& $PyExe @Prefix $Sync watch --root $Root --interval $PollSeconds

