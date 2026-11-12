<#
.SYNOPSIS
  B6a G7: the release checks, run locally before every release (no CI minutes; CI keeps its weekly schedule).

.DESCRIPTION
  Runs, in order: targeted pytest, ruff, vitest, tsc, the production build, the Playwright journeys on the production
  bundle (chromium only), the k6 smoke with the SLO thresholds (the two pages included when a session is given), and
  the three load measures. Each step's output goes to artifacts/release-checks/<step>.log; the summary (versions,
  timings, pass/fail) is written to artifacts/release-checks-<version>.json for the release evidence (B6b). The pytest
  step also writes artifacts/release-checks/junit.xml, with each test's requirement markers as properties (B6b B4);
  -Full runs the whole suite instead of the targeted files.

  It never deploys, pushes or sends anything. Run it from the repository root with the test database's POSTGRES_DB
  set in the environment (the app reads the repository's .env by itself).

.EXAMPLE
  $env:POSTGRES_DB = "mdarix_r1_test"; .\scripts\release_checks.ps1
  .\scripts\release_checks.ps1 -Skip playwright,k6,load     # the quick set
  .\scripts\release_checks.ps1 -DryRun                      # list the steps and write the JSON, run nothing
  .\scripts\release_checks.ps1 -Full -Only pytest            # the whole pytest suite (the release-pack regression run)
  $env:K6_BASE_URL = "http://127.0.0.1:8007"; $env:K6_SESSION = "<a test session cookie>"; .\scripts\release_checks.ps1 -Only k6
#>
param(
    [string[]]$Skip = @(),
    [string[]]$Only = @(),
    [string[]]$PytestFiles = @(
        "tests/test_b6a_scoped_watch.py",
        "tests/test_b6a_boundaries.py",
        "tests/test_complaint_page.py",
        "tests/test_oversight_provisional.py",
        "tests/test_b6a_deadline_list.py"
    ),
    [switch]$DryRun,
    [switch]$Full
)

$ErrorActionPreference = "Continue"
# "-Skip a,b" arrives as one string under "powershell -File": split it.
$Skip = @($Skip | ForEach-Object { $_ -split "," } | Where-Object { $_ })
$Only = @($Only | ForEach-Object { $_ -split "," } | Where-Object { $_ })
$root = Split-Path -Parent $PSScriptRoot
$python = if (Test-Path "$root\.venv\Scripts\python.exe") { "$root\.venv\Scripts\python.exe" } else {
    Join-Path $root "..\..\..\.venv\Scripts\python.exe"  # a worktree under .claude\worktrees
}
$version = (Get-Content "$root\VERSION" -Raw).Trim()
$logs = Join-Path $root "artifacts\release-checks"
New-Item -ItemType Directory -Force $logs | Out-Null

function Invoke-Measures {
    $env:MDARIX_TRIAL_LOAD_MEASURE = "1"
    $env:MDARIX_TRIAL_LOAD_REPORT = Join-Path $logs "load-trial.json"
    & $python -m pytest tests/test_trial_load_measure.py tests/test_case_load_measure.py `
        tests/test_product_supplier_load_measure.py tests/test_b6a_scoped_watch.py -q -s -p no:cacheprovider
    $code = $LASTEXITCODE
    Remove-Item Env:MDARIX_TRIAL_LOAD_MEASURE, Env:MDARIX_TRIAL_LOAD_REPORT -ErrorAction SilentlyContinue
    $global:LASTEXITCODE = $code
}

function Invoke-K6 {
    if (-not (Get-Command k6 -ErrorAction SilentlyContinue)) { return "skipped: k6 is not installed" }
    if (-not $env:K6_BASE_URL) { return "skipped: set K6_BASE_URL to an approved non-production server" }
    k6 run -e "BASE_URL=$env:K6_BASE_URL" -e "SESSION=$env:K6_SESSION" scripts/k6/mdarix-smoke.js
}

$steps = [ordered]@{
    "pytest"     = {
        $files = if ($Full) { @() } else { $PytestFiles }
        & $python -m pytest @files -q -p no:cacheprovider "--junitxml=$(Join-Path $logs 'junit.xml')"
    }
    "ruff"       = { & $python -m ruff check . }
    "vitest"     = { Push-Location frontend; npx vitest run; $c = $LASTEXITCODE; Pop-Location; $global:LASTEXITCODE = $c }
    "tsc"        = { Push-Location frontend; npx tsc --noEmit -p .; $c = $LASTEXITCODE; Pop-Location; $global:LASTEXITCODE = $c }
    "build"      = { Push-Location frontend; npm run build; $c = $LASTEXITCODE; Pop-Location; $global:LASTEXITCODE = $c }
    "playwright" = {
        Push-Location frontend; $env:E2E_SERVER = "preview"
        npx playwright test --project=chromium; $c = $LASTEXITCODE
        Remove-Item Env:E2E_SERVER; Pop-Location; $global:LASTEXITCODE = $c
    }
    "k6"         = { Invoke-K6 }
    "load"       = { Invoke-Measures }
}

$results = @()
$started = Get-Date
Push-Location $root
try {
    foreach ($name in $steps.Keys) {
        $wanted = ($Only.Count -eq 0 -or $Only -contains $name) -and -not ($Skip -contains $name)
        $log = Join-Path $logs "$name.log"
        if (-not $wanted -or $DryRun) {
            $results += [ordered]@{ step = $name; result = $(if ($DryRun -and $wanted) { "planned" } else { "skipped" }); seconds = 0; log = $null }
            continue
        }
        Write-Host "== $name"
        $clock = [Diagnostics.Stopwatch]::StartNew()
        # No exit code at all (a tool not found) is a failure, never a pass.
        $global:LASTEXITCODE = $null
        $said = & $steps[$name] *>&1 | Tee-Object -FilePath $log
        $clock.Stop()
        $note = if ($name -eq "k6") { @($said | Where-Object { "$_" -clike "skipped:*" }) | Select-Object -First 1 }
        $result = if ($note) { "skipped" } elseif ($LASTEXITCODE -eq 0) { "pass" } else { "fail" }
        $results += [ordered]@{
            step = $name; result = $result; seconds = [math]::Round($clock.Elapsed.TotalSeconds, 1)
            exit_code = $LASTEXITCODE; note = $(if ($note) { "$note" } else { $null }); log = "artifacts/release-checks/$name.log"
        }
        Write-Host "   $result in $([math]::Round($clock.Elapsed.TotalSeconds, 1)) s"
    }
} finally {
    Pop-Location
}

function Get-VersionOf([scriptblock]$read) { try { ("" + (& $read 2>$null | Select-Object -First 1)).Trim() } catch { $null } }
$summary = [ordered]@{
    release        = $version
    commit         = Get-VersionOf { git -C $root rev-parse --short HEAD }
    branch         = Get-VersionOf { git -C $root rev-parse --abbrev-ref HEAD }
    dry_run        = [bool]$DryRun
    full_suite     = [bool]$Full
    junit          = $(if (Test-Path (Join-Path $logs "junit.xml")) { "artifacts/release-checks/junit.xml" } else { $null })
    started_at     = $started.ToUniversalTime().ToString("o")
    finished_at    = (Get-Date).ToUniversalTime().ToString("o")
    machine        = "local (not CI); numbers are local, in-process, not production"
    tools          = [ordered]@{
        python = Get-VersionOf { & $python --version }
        node   = Get-VersionOf { node --version }
        k6     = Get-VersionOf { k6 version }
    }
    steps          = $results
    passed         = -not ($results | Where-Object { $_.result -eq "fail" })
}
$out = Join-Path $root "artifacts\release-checks-$version.json"
[IO.File]::WriteAllText($out, ($summary | ConvertTo-Json -Depth 5))  # UTF-8 without a byte-order mark
Write-Host "Written $out"
if (-not $summary.passed) { exit 1 }
