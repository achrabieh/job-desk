# Builds dist\JobDesk-Setup.exe: a per-user Windows installer (no admin rights needed)
# that bundles its own Python, the app and its libraries.
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1 [-Version 0.7.0] [-StageOnly]
param([string]$Version = "0.0.0-dev", [switch]$StageOnly)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root 'build'
$Stage = Join-Path $Build 'stage'
$PyVer = '3.12.10'

if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }
New-Item -ItemType Directory -Force "$Stage\python", "$Stage\app", (Join-Path $Root 'dist') | Out-Null

# 1. Private Python (official embeddable build)
$zip = Join-Path $Build "python-$PyVer-embed-amd64.zip"
Invoke-WebRequest -UseBasicParsing "https://www.python.org/ftp/python/$PyVer/python-$PyVer-embed-amd64.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath "$Stage\python"
# Allow site-packages and the app folders on the import path
$pth = Get-ChildItem "$Stage\python" -Filter 'python3*._pth' | Select-Object -First 1
$lines = (Get-Content $pth.FullName) -replace '^#\s*import site', 'import site'
$lines += 'Lib\site-packages', '..\app\jobdesk', '..\app\jobdesk\cv'
Set-Content -Encoding ascii $pth.FullName $lines

# 2. Libraries, as prebuilt Windows wheels for that Python
$py = (Get-Command python).Source
& $py -m pip install --quiet --disable-pip-version-check --target "$Stage\python\Lib\site-packages" `
    --platform win_amd64 --python-version 3.12 --implementation cp --only-binary=:all: `
    -r (Join-Path $Root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip failed' }

# 3. The app (code, prompts, examples, feed directory) - never any personal data
Copy-Item -Recurse (Join-Path $Root 'jobdesk') "$Stage\app\jobdesk"
Copy-Item -Recurse (Join-Path $Root 'prompts') "$Stage\app\prompts"
Copy-Item -Recurse (Join-Path $Root 'profile.example') "$Stage\app\profile.example"
New-Item -ItemType Directory -Force "$Stage\app\docs" | Out-Null
Copy-Item (Join-Path $Root 'docs\feeds.json') "$Stage\app\docs\feeds.json"
Copy-Item (Join-Path $Root 'LICENSE'), (Join-Path $Root 'README.md') "$Stage\app"
Copy-Item (Join-Path $PSScriptRoot 'jobdesk.ico') "$Stage\jobdesk.ico"
Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Set-Content -Encoding ascii "$Stage\app\VERSION" $Version

# 4. Smoke test: the bundled Python can import everything the app needs
& "$Stage\python\python.exe" -c "import docx, pymupdf, openpyxl, server, setup_wizard, updater, cv_tools, cli, ingest, factcheck, linkcheck, build_cv, build_cover; print('bundle imports ok')"
if ($LASTEXITCODE -ne 0) { throw 'bundle smoke test failed' }
if ($StageOnly) { Write-Host "Staged in $Stage"; exit 0 }

# 5. Installer
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 (ISCC.exe) not found. Install it from https://jrsoftware.org/isdl.php' }
& $iscc "/DAppVersion=$Version" "/DStageDir=$Stage" "/O$(Join-Path $Root 'dist')" (Join-Path $PSScriptRoot 'jobdesk.iss')
if ($LASTEXITCODE -ne 0) { throw 'ISCC failed' }
Write-Host "Built $(Join-Path $Root 'dist\JobDesk-Setup.exe')"
