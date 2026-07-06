$ErrorActionPreference = "Stop"

function New-InterviewArenaPythonCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,

        [string[]]$PrefixArguments = @(),

        [Parameter(Mandatory = $true)]
        [string]$Source
    )

    [pscustomobject]@{
        Executable = $Executable
        PrefixArguments = $PrefixArguments
        Source = $Source
    }
}

function Get-InterviewArenaPythonCandidates {
    $candidates = @()

    if ($env:INTERVIEW_ARENA_PYTHON) {
        $candidates += New-InterviewArenaPythonCandidate `
            -Executable $env:INTERVIEW_ARENA_PYTHON `
            -Source "INTERVIEW_ARENA_PYTHON"
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $candidates += New-InterviewArenaPythonCandidate `
            -Executable $pyLauncher.Source `
            -PrefixArguments @("-3.11") `
            -Source "py -3.11"
    }

    foreach ($commandName in @("python3.11", "python")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += New-InterviewArenaPythonCandidate `
                -Executable $command.Source `
                -Source $commandName
        }
    }

    $condaEnvRoots = @()
    if ($env:CONDA_PREFIX) {
        $activePython = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path -LiteralPath $activePython) {
            $candidates += New-InterviewArenaPythonCandidate `
                -Executable $activePython `
                -Source "CONDA_PREFIX"
        }

        if (Test-Path -LiteralPath (Join-Path $env:CONDA_PREFIX "envs")) {
            $condaEnvRoots += Join-Path $env:CONDA_PREFIX "envs"
        }
        else {
            $condaEnvRoots += Split-Path -Parent $env:CONDA_PREFIX
        }
    }

    if ($env:CONDA_EXE) {
        $condaRoot = Split-Path -Parent (Split-Path -Parent $env:CONDA_EXE)
        $condaEnvRoots += Join-Path $condaRoot "envs"
    }

    $condaEnvRoots += @(
        "D:\anaconda\envs",
        "$HOME\anaconda3\envs",
        "$HOME\miniconda3\envs",
        "C:\ProgramData\anaconda3\envs"
    )

    foreach ($root in ($condaEnvRoots | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }

        foreach ($envDir in (Get-ChildItem -LiteralPath $root -Directory | Sort-Object Name)) {
            $pythonPath = Join-Path $envDir.FullName "python.exe"
            if (Test-Path -LiteralPath $pythonPath) {
                $candidates += New-InterviewArenaPythonCandidate `
                    -Executable $pythonPath `
                    -Source "conda env $($envDir.Name)"
            }
        }
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        $key = "$($candidate.Executable)|$($candidate.PrefixArguments -join ' ')"
        if (-not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            $candidate
        }
    }
}

function Read-InterviewArenaPinnedRequirements {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [hashtable]$SeenPaths = $null
    )

    if ($null -eq $SeenPaths) {
        $SeenPaths = @{}
    }

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    if ($SeenPaths.ContainsKey($resolvedPath)) {
        return @{}
    }
    $SeenPaths[$resolvedPath] = $true

    $packages = @{}
    $baseDir = Split-Path -Parent $resolvedPath
    foreach ($line in Get-Content -LiteralPath $resolvedPath -Encoding utf8) {
        $requirement = (($line -split "#", 2)[0] -split ";", 2)[0].Trim()
        if (-not $requirement) {
            continue
        }

        if ($requirement -match "^(?:-r|--requirement)\s+(.+)$") {
            $includePathText = $Matches[1].Trim().Trim("'").Trim('"')
            $includePath = $includePathText
            if (-not [System.IO.Path]::IsPathRooted($includePath)) {
                $includePath = Join-Path $baseDir $includePath
            }

            $includedPackages = Read-InterviewArenaPinnedRequirements `
                -Path $includePath `
                -SeenPaths $SeenPaths
            foreach ($name in $includedPackages.Keys) {
                if ($packages.ContainsKey($name) -and $packages[$name] -ne $includedPackages[$name]) {
                    throw "Conflicting pin for $name in $resolvedPath."
                }
                $packages[$name] = $includedPackages[$name]
            }
            continue
        }

        if ($requirement -notmatch "^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s=]+)$") {
            throw "Unsupported requirement format '$requirement' in $resolvedPath. Use exact pins like package==1.2.3."
        }

        $name = $Matches[1]
        $version = $Matches[2]
        if ($packages.ContainsKey($name) -and $packages[$name] -ne $version) {
            throw "Conflicting pin for $name in $resolvedPath."
        }
        $packages[$name] = $version
    }

    $packages
}

function Test-InterviewArenaPythonCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Candidate,

        [Parameter(Mandatory = $true)]
        [version]$MinimumVersion,

        [string[]]$RequiredModules = @(),

        [hashtable]$RequiredPackages = @{}
    )

    $versionScript = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    $versionArguments = @($Candidate.PrefixArguments) + @("-c", $versionScript)

    try {
        $versionText = (& $Candidate.Executable @versionArguments 2>$null | Select-Object -First 1)
    }
    catch {
        return [pscustomobject]@{
            Ok = $false
            Reason = "cannot execute"
            Version = $null
        }
    }

    if (-not $versionText) {
        return [pscustomobject]@{
            Ok = $false
            Reason = "cannot read version"
            Version = $null
        }
    }

    try {
        $version = [version]$versionText.Trim()
    }
    catch {
        return [pscustomobject]@{
            Ok = $false
            Reason = "invalid version '$versionText'"
            Version = $null
        }
    }

    if ($version -lt $MinimumVersion) {
        return [pscustomobject]@{
            Ok = $false
            Reason = "Python $version is below $MinimumVersion"
            Version = $version
        }
    }

    if ($RequiredModules.Count -gt 0) {
        $moduleScript = "import importlib.util, sys; missing=[name for name in sys.argv[1:] if importlib.util.find_spec(name) is None]; print(','.join(missing)); raise SystemExit(1 if missing else 0)"
        $moduleArguments = @($Candidate.PrefixArguments) + @("-c", $moduleScript) + $RequiredModules
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $missingModules = (& $Candidate.Executable @moduleArguments 2>&1)
            $moduleExitCode = $LASTEXITCODE
        }
        catch {
            return [pscustomobject]@{
                Ok = $false
                Reason = "module check failed"
                Version = $version
            }
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        if ($moduleExitCode -ne 0) {
            $missingText = ($missingModules -join ",").Trim()
            if (-not $missingText) {
                $missingText = "unknown"
            }
            return [pscustomobject]@{
                Ok = $false
                Reason = "missing modules: $missingText"
                Version = $version
            }
        }
    }

    if ($RequiredPackages.Count -gt 0) {
        $packageScript = @'
import importlib.metadata as metadata
import sys

problems = []
separator = chr(61) + chr(61)
for spec in sys.argv[1:]:
    name, expected = spec.split(separator, 1)
    try:
        actual = metadata.version(name)
    except metadata.PackageNotFoundError:
        problems.append(name + separator + str(None) + chr(32) + expected)
        continue
    if actual != expected:
        problems.append(name + separator + actual + chr(32) + expected)

print((chr(59) + chr(32)).join(problems))
raise SystemExit(1 if problems else 0)
'@
        $packageSpecs = foreach ($name in ($RequiredPackages.Keys | Sort-Object)) {
            "$name==$($RequiredPackages[$name])"
        }
        $packageArguments = @($Candidate.PrefixArguments) + @("-c", $packageScript) + $packageSpecs
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $packageProblems = (& $Candidate.Executable @packageArguments 2>&1)
            $packageExitCode = $LASTEXITCODE
        }
        catch {
            return [pscustomobject]@{
                Ok = $false
                Reason = "package version check failed"
                Version = $version
            }
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        if ($packageExitCode -ne 0) {
            $problemText = ($packageProblems -join " ").Trim()
            if (-not $problemText) {
                $problemText = "unknown"
            }
            return [pscustomobject]@{
                Ok = $false
                Reason = "package version mismatch: $problemText"
                Version = $version
            }
        }
    }

    [pscustomobject]@{
        Ok = $true
        Reason = ""
        Version = $version
    }
}

function Resolve-InterviewArenaPython {
    param(
        [version]$MinimumVersion = [version]"3.11",
        [string[]]$RequiredModules = @(),
        [hashtable]$RequiredPackages = @{}
    )

    $attempts = @()
    foreach ($candidate in Get-InterviewArenaPythonCandidates) {
        $result = Test-InterviewArenaPythonCandidate `
            -Candidate $candidate `
            -MinimumVersion $MinimumVersion `
            -RequiredModules $RequiredModules `
            -RequiredPackages $RequiredPackages

        $display = "$($candidate.Executable) $($candidate.PrefixArguments -join ' ')".Trim()
        if ($result.Ok) {
            Write-Host "Using Python $($result.Version) from $($candidate.Source): $display"
            return [pscustomobject]@{
                Executable = $candidate.Executable
                PrefixArguments = $candidate.PrefixArguments
                Source = $candidate.Source
                Version = $result.Version
            }
        }

        $attempts += "  - $($candidate.Source): $display ($($result.Reason))"
    }

    $requirements = "Python $MinimumVersion+"
    if ($RequiredModules.Count -gt 0) {
        $requirements += " with modules: $($RequiredModules -join ', ')"
    }
    if ($RequiredPackages.Count -gt 0) {
        $packageRequirements = foreach ($name in ($RequiredPackages.Keys | Sort-Object)) {
            "$name==$($RequiredPackages[$name])"
        }
        $requirements += " with packages: $($packageRequirements -join ', ')"
    }
    $attemptText = if ($attempts.Count -gt 0) { $attempts -join [Environment]::NewLine } else { "  - no candidates found" }
    throw "Could not find $requirements. Set INTERVIEW_ARENA_PYTHON to a compatible python.exe.`nTried:`n$attemptText"
}

function Invoke-InterviewArenaPython {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Command,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $allArguments = @($Command.PrefixArguments) + @($Arguments)
    & $Command.Executable @allArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}
