$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = $null
. (Join-Path $PSScriptRoot "resolve-python.ps1")
$requirementsPath = Join-Path $root "backend\requirements.txt"
$requiredPackages = Read-InterviewArenaPinnedRequirements -Path $requirementsPath
$python = Resolve-InterviewArenaPython -RequiredModules @(
    "docx",
    "fastapi",
    "httpx",
    "multipart",
    "pydantic",
    "pymysql"
) -RequiredPackages $requiredPackages

Invoke-InterviewArenaPython -Command $python -Arguments @("backend/scripts/export_openapi.py")
