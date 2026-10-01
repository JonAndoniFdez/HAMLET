param(
    [string]$PythonExe = "",
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $PythonExe = $pythonCommand.Source
    } else {
        $pyCommand = Get-Command py -ErrorAction SilentlyContinue
        if (-not $pyCommand) {
            throw "No Python launcher found. Install Python and the packages in requirements.txt first."
        }
        $PythonExe = $pyCommand.Source
    }
}

if ((Split-Path -Leaf $PythonExe).ToLowerInvariant() -eq "py.exe") {
    & $PythonExe -3 -m PyInstaller --noconfirm --clean --distpath "$Root\dist" --workpath "$Root\build" "$Root\HAMLET.spec"
} else {
    & $PythonExe -m PyInstaller --noconfirm --clean --distpath "$Root\dist" --workpath "$Root\build" "$Root\HAMLET.spec"
}

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed (exit code $LASTEXITCODE). The existing dist folder is not a new release."
}

if ((Split-Path -Leaf $PythonExe).ToLowerInvariant() -eq "py.exe") {
    & $PythonExe -3 "$Root\tools\verify_release_preview.py" "$Root\dist\HAMLET\HAMLET.exe"
} else {
    & $PythonExe "$Root\tools\verify_release_preview.py" "$Root\dist\HAMLET\HAMLET.exe"
}
if ($LASTEXITCODE -ne 0) {
    throw "Release preview verification failed. Do not publish this build."
}

if ($Zip) {
    $testDir = Join-Path $Root ("build\release-test-" + [guid]::NewGuid().ToString('N'))
    $runnerArgs = @("$Root\tools\run_release_selftest.py", "$Root\dist\HAMLET\HAMLET.exe", $testDir)
    $finalArgs = @("$Root\tools\finalize_release.py", "--test-results", "$testDir\results.json", "--zip")
    if ((Split-Path -Leaf $PythonExe).ToLowerInvariant() -eq "py.exe") {
        & $PythonExe -3 @runnerArgs
    } else {
        & $PythonExe @runnerArgs
    }
    if ($LASTEXITCODE -ne 0) { throw "Executable integration checks failed; release ZIPs were not regenerated." }
    if ((Split-Path -Leaf $PythonExe).ToLowerInvariant() -eq "py.exe") {
        & $PythonExe -3 @finalArgs
    } else {
        & $PythonExe @finalArgs
    }
    if ($LASTEXITCODE -ne 0) { throw "Release validation failed; inspect the validation output." }
    Write-Host "Validated local candidate archives created. Check RELEASE_VALIDATION.json for publication blockers."
}
