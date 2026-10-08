# Start both self-hosted runners in the background (the Linux one inside the Ubuntu WSL distribution, the Windows
# one on the host). Safe to run again: a runner that is already listening is left alone.
# Register it as a logon task once so CI is available whenever this PC is signed in:
#   schtasks /create /tn "MDARIX CI runners" /sc onlogon /rl limited /tr "powershell -NoProfile -WindowStyle Hidden -File C:\Users\user\Srinivas\MDARIX-R1\infrastructure\ci\self-hosted\start-runners.ps1"
$ErrorActionPreference = 'Stop'

$linuxListening = (wsl -d Ubuntu -u runner -- pgrep -f Runner.Listener 2>$null)
if (-not $linuxListening) {
  Start-Process -WindowStyle Hidden -FilePath wsl.exe -ArgumentList '-d', 'Ubuntu', '-u', 'runner', '--', 'bash', '-lc', 'cd ~/actions-runner && ./run.sh'
  Write-Host 'Linux runner started'
} else {
  Write-Host 'Linux runner already running'
}

$windowsListening = Get-Process Runner.Listener -ErrorAction SilentlyContinue
if (-not $windowsListening) {
  Start-Process -WindowStyle Hidden -FilePath 'C:\actions-runner\run.cmd' -WorkingDirectory 'C:\actions-runner'
  Write-Host 'Windows runner started'
} else {
  Write-Host 'Windows runner already running'
}
