[CmdletBinding()]
param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($Version -and $Version -notmatch '^[0-9A-Za-z][0-9A-Za-z.!+_-]*$') {
    throw "Version contains unsupported characters."
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    $uvInstaller = Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1"
    Invoke-Expression $uvInstaller

    $uvCandidates = @(
        $env:UV_INSTALL_DIR,
        (Join-Path $HOME ".local\bin"),
        (Join-Path $HOME ".cargo\bin")
    ) | Where-Object { $_ }
    $env:Path = ($uvCandidates + $env:Path) -join [IO.Path]::PathSeparator
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was installed but could not be found on PATH."
}

$packageRequirement = "maid-runner"
if ($Version) {
    $packageRequirement = "maid-runner==$Version"
}

Write-Host "Installing $packageRequirement..."
& uv tool install --python 3.12 $packageRequirement
if ($LASTEXITCODE -ne 0) {
    throw "uv failed to install MAID Runner."
}

& uv tool update-shell
if ($LASTEXITCODE -ne 0) {
    throw "uv could not persist its tool directory on PATH."
}

$toolBin = (& uv tool dir --bin | Select-Object -Last 1)
if ($LASTEXITCODE -ne 0) {
    throw "uv could not report its tool executable directory."
}
if ([string]::IsNullOrWhiteSpace($toolBin)) {
    throw "uv returned an empty tool executable directory."
}
$env:Path = "$toolBin$([IO.Path]::PathSeparator)$env:Path"

if (-not (Get-Command maid -ErrorAction SilentlyContinue)) {
    throw "MAID Runner was installed but maid could not be found on PATH."
}

& maid --version
if ($LASTEXITCODE -ne 0) {
    throw "MAID Runner installation verification failed."
}

Write-Host "MAID Runner is ready."
Write-Host "Run: maid init"
