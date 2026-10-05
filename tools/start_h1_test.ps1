param(
    [Parameter(Mandatory=$true)][string]$Qemu,
    [string]$DllDir,
    [string]$EmulatorScript,
    [string]$WorkDir,
    [switch]$GdbWait
)
$ErrorActionPreference = 'Stop'
$h1TaskRoot = Split-Path -Parent $PSScriptRoot
$h1TaskWork = Join-Path $h1TaskRoot 'build/h1-emulator-test'
$h1TaskScript = Join-Path $h1TaskRoot '.tools/h1-emulator/h1/h1_emulator.py'
if ($WorkDir) { $h1TaskWork = (Resolve-Path -LiteralPath $WorkDir).Path }
if ($EmulatorScript) { $h1TaskScript = (Resolve-Path -LiteralPath $EmulatorScript).Path }
$h1TaskQemu = (Resolve-Path -LiteralPath $Qemu).Path
$h1TaskPidFile = Join-Path $h1TaskWork 'frontend.pid'
if (Test-Path -LiteralPath $h1TaskPidFile) {
    $h1TaskOldPid = [int](Get-Content -LiteralPath $h1TaskPidFile)
    $h1TaskOldProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$h1TaskOldPid"
    if ($h1TaskOldProcess -and $h1TaskOldProcess.CommandLine.Contains($h1TaskScript)) {
        Invoke-RestMethod -Method Post -ContentType 'application/json' -Body '{}' http://127.0.0.1:8793/api/stop | Out-Null
        Stop-Process -Id $h1TaskOldPid
    }
}
$h1TaskArgs = @('-u', ('"{0}"' -f $h1TaskScript), '--qemu', ('"{0}"' -f $h1TaskQemu),
    '--kernel', ('"{0}"' -f (Join-Path $h1TaskWork 'project.bin')),
    '--nand', ('"{0}"' -f (Join-Path $h1TaskWork 'h1-system.raw')),
    '--port', '8793', '--gdb-port', '8794', '--no-browser', '--writable')
if ($DllDir) { $h1TaskArgs += @('--dll-dir', ('"{0}"' -f $DllDir)) }
if ($GdbWait) { $h1TaskArgs += '--gdb-wait' }
$h1TaskProcess = Start-Process -FilePath (Get-Command python).Source -ArgumentList $h1TaskArgs -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $h1TaskWork 'frontend.stdout.log') `
    -RedirectStandardError (Join-Path $h1TaskWork 'frontend.stderr.log')
$h1TaskProcess.Id | Set-Content -LiteralPath $h1TaskPidFile
Write-Output "H1 test frontend PID=$($h1TaskProcess.Id) http://127.0.0.1:8793/"
