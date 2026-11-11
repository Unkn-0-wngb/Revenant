# Sets up Python for Revenant. Revenant.bat runs this the first time, or run it yourself:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
# Everything game related (Trackmania, TMLoader, the plugin, maps, models, the profile) is done from the dashboard's Setup tab.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
function Check($step) { if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE)" } }

Write-Host 'Revenant setup: Python and the AI libraries. The first run downloads about 3 GB.'

$py = $null
foreach ($candidate in @("$env:LOCALAPPDATA\Programs\Python\Python311\python.exe", "C:\Program Files\Python311\python.exe")) {
    if (Test-Path $candidate) { $py = $candidate; break }
}
if (-not $py -and (Get-Command py -ErrorAction SilentlyContinue)) {
    $found = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $found) { $py = $found.Trim() }
}
if (-not $py) {
    Write-Host 'Installing Python 3.11...'
    winget install --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    Check 'Python install'
    $py = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
}
Write-Host "Python: $py"

$v = "$root\venv\Scripts\python.exe"
Set-Location $root
if (-not (Test-Path $v)) { & $py -m venv venv; Check 'venv' }
& $v -m pip install --upgrade pip --quiet; Check 'pip upgrade'
& $v -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121; Check 'torch'
& $v -m pip install -c "$root\constraints.txt" torchrl==0.6.0 tensordict==0.6.1 tensorboard; Check 'torchrl'
Set-Location "$root\linesight"
& $v -m pip install -c "$root\constraints.txt" -e .; Check 'linesight'
Set-Location $root
& $v -m pip install psutil matplotlib python-lzo==1.15 pygbx==0.3 scipy opencv-python pillow joblib; Check 'extras'

& $v -c "import torch; print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none that CUDA can use')"
Write-Host 'Python is ready. Revenant.bat opens the dashboard, its Setup tab does the rest.'
