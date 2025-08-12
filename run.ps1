Param(
  [int]$Port = 8503,
  [string]$Address = "0.0.0.0",
  [string]$Page = "streamlit-demos/Home.py"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host "[run.ps1] Ensuring virtual environment..." -ForegroundColor Cyan
if (!(Test-Path .\.venv\Scripts\python.exe)) {
  py -3.12 -m venv .venv
}
$py = Resolve-Path .\.venv\Scripts\python.exe

Write-Host "[run.ps1] Updating pip & installing requirements..." -ForegroundColor Cyan
& $py -m pip install --upgrade pip setuptools wheel
& $py -m pip install -r requirements.txt

Write-Host ("[run.ps1] Launching Streamlit on http://{0}:{1} ..." -f $Address, $Port) -ForegroundColor Green
& $py -m streamlit run $Page --server.address $Address --server.port $Port


