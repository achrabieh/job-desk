# Windows convenience wrapper. Same as: python jobdesk\cli.py daily ...
param([string]$JobDeskHome = $env:JOB_DESK_HOME, [switch]$Force)
$a = @("daily", "--home", $JobDeskHome); if ($Force) { $a += "--force" }
python (Join-Path (Split-Path -Parent $PSScriptRoot) "jobdesk\cli.py") @a; exit $LASTEXITCODE
