# Launch the SpikeInterface menu via uv (PowerShell).
#   .\run.ps1            # interactive menu
#   .\run.ps1 report     # run one action directly
$env:PYTHONUTF8 = "1"
Set-Location -Path $PSScriptRoot
uv run python (Join-Path $PSScriptRoot "SpikeInterface_Menu.py") @args
