# Windows convenience wrapper. Same as: python jobdesk\cli.py setup ...
param([Parameter(Mandatory = $true)][string]$JobDeskHome, [Parameter(Mandatory = $true)][string]$Owner, [switch]$NoShortcut, [int]$Port = 8765)
$a = @("setup", "--home", $JobDeskHome, "--owner", $Owner, "--port", $Port); if ($NoShortcut) { $a += "--no-shortcut" }
python (Join-Path (Split-Path -Parent $PSScriptRoot) "jobdesk\cli.py") @a; exit $LASTEXITCODE
