param(
    [switch]$Full,
    [switch]$E2E
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

. (Join-Path $PSScriptRoot "resolve-python.ps1")

function Invoke-GitLines {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & git @Arguments 2>$null
        if ($LASTEXITCODE -ne 0) {
            return @()
        }
        @($output)
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Get-ChangedBackendPythonFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $paths = @()
    $paths += Invoke-GitLines -Arguments @(
        "diff",
        "--name-only",
        "--diff-filter=ACMRTUXB",
        "HEAD",
        "--",
        "backend"
    )
    $paths += Invoke-GitLines -Arguments @(
        "diff",
        "--cached",
        "--name-only",
        "--diff-filter=ACMRTUXB",
        "HEAD",
        "--",
        "backend"
    )
    $paths += Invoke-GitLines -Arguments @(
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "backend"
    )

    $seen = @{}
    foreach ($path in $paths) {
        $normalized = $path.Trim().Replace("\", "/")
        if (-not $normalized.EndsWith(".py")) {
            continue
        }

        $fullPath = Join-Path $Root $normalized
        if (-not (Test-Path -LiteralPath $fullPath)) {
            continue
        }

        if (-not $seen.ContainsKey($normalized)) {
            $seen[$normalized] = $true
            $normalized
        }
    }
}

function Invoke-Npm {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & npm @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "npm $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

$requirementsPath = Join-Path $root "backend\requirements-dev.txt"
$requiredPackages = Read-InterviewArenaPinnedRequirements -Path $requirementsPath

$python = Resolve-InterviewArenaPython -RequiredModules @(
    "docx",
    "fastapi",
    "httpx",
    "multipart",
    "mypy",
    "pydantic",
    "pymysql",
    "pytest",
    "ruff"
) -RequiredPackages $requiredPackages

if ($Full) {
    Invoke-InterviewArenaPython -Command $python -Arguments @("-m", "ruff", "check", "backend")
    Invoke-InterviewArenaPython -Command $python -Arguments @("-m", "mypy")
    Invoke-InterviewArenaPython -Command $python -Arguments @("-m", "pytest", "backend/tests")
}
else {
    Invoke-InterviewArenaPython -Command $python -Arguments @("backend/scripts/export_openapi.py")
    $changedPython = @(Get-ChangedBackendPythonFiles -Root $root)
    if ($changedPython.Count -gt 0) {
        Write-Host "Running ruff on $($changedPython.Count) changed backend Python file(s)."
        Invoke-InterviewArenaPython -Command $python -Arguments (@("-m", "ruff", "check") + $changedPython)
    }
    else {
        Write-Host "No changed backend Python files detected; skipping quick ruff."
    }
    Invoke-InterviewArenaPython -Command $python -Arguments @(
        "-m",
        "pytest",
        "backend/tests/test_auth.py",
        "backend/tests/test_resume.py",
        "backend/tests/test_history.py",
        "backend/tests/test_history_repository.py",
        "backend/tests/test_memory_database_contracts.py"
    )
}

Push-Location frontend
try {
    Invoke-Npm -Arguments @("run", "lint")
    Invoke-Npm -Arguments @("run", "format:check")
    Invoke-Npm -Arguments @("run", "typecheck")
    Invoke-Npm -Arguments @("run", "build")
    if ($E2E) {
        Invoke-Npm -Arguments @("run", "test:e2e")
    }
}
finally {
    Pop-Location
}
