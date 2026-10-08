# Register the Windows runner (the frontend job) with the repository. Run in PowerShell on the host:
#   $env:RUNNER_TOKEN = '<registration token>'; .\infrastructure\ci\self-hosted\register-windows.ps1
# The runner package is expected unpacked in C:\actions-runner (see docs/runbooks/SELF_HOSTED_RUNNER.md).
# The label mdarix-windows is what the CI_WINDOWS_RUNNER repository variable points at.
$ErrorActionPreference = 'Stop'
if (-not $env:RUNNER_TOKEN) { throw 'Set RUNNER_TOKEN to a registration token first' }
$repo = if ($env:REPO_URL) { $env:REPO_URL } else { 'https://github.com/stelikicherla-stack/MDARIX-R1' }
Set-Location C:\actions-runner
.\config.cmd --unattended --url $repo --token $env:RUNNER_TOKEN --name "$env:COMPUTERNAME-windows" --labels mdarix-windows --work _work --replace
Write-Host "REGISTERED $env:COMPUTERNAME-windows"
