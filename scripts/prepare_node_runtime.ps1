param(
    [string]$NodeVersion = $(if ($env:NODE_VERSION) { $env:NODE_VERSION } else { "v24.18.0" })
)

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeDir = Join-Path $RootDir "runtimes"
$TmpDir = Join-Path $RuntimeDir ".tmp"
$Arch = "x64"
$Target = Join-Path $RuntimeDir "node-win-$Arch"
$ZipFile = "node-$NodeVersion-win-$Arch.zip"
$Url = "https://nodejs.org/dist/$NodeVersion/$ZipFile"
$ZipPath = Join-Path $TmpDir $ZipFile
$Extracted = Join-Path $TmpDir "node-$NodeVersion-win-$Arch"

New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
Write-Host "[node] downloading $Url"
Invoke-WebRequest -Uri $Url -OutFile $ZipPath

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Target, $Extracted
Expand-Archive -Path $ZipPath -DestinationPath $TmpDir -Force
Move-Item -Path $Extracted -Destination $Target

& (Join-Path $Target "node.exe") -v
& (Join-Path $Target "npm.cmd") -v
Write-Host "[node] ready: $Target"
Write-Host "Build Windows x64 with: pyinstaller HikingTrackAnalyzer.spec"
