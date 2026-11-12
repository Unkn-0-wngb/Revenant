# Starts Linesight training on every level in config_files\all_maps.py, from the saved weights.
# Output goes to logs\train_run1.log. The previous log is kept with a timestamp.
# Training force-closes every running game, so this refuses to start while one is open.
$root = $PSScriptRoot
Add-Type -Name Window -Namespace Console -MemberDefinition '
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);'
[void][Console.Window]::ShowWindow([Console.Window]::GetConsoleWindow(), 6)
if (Get-Process TmForever -ErrorAction SilentlyContinue) {
    Write-Host 'Trackmania is running. Close it first: training would force-close it.'
    exit 1
}
$maps = "$([Environment]::GetFolderPath('MyDocuments'))\TrackMania\Tracks\Challenges\Official Maps"
$needed = (Select-String -Path "$root\linesight\config_files\all_maps.py" -Pattern '^\s+\(').Count
$found = (Get-ChildItem $maps -Filter '*.Challenge.Gbx' -ErrorAction SilentlyContinue).Count
if ($found -lt $needed) {
    Write-Host "Only $found of $needed map files found. Run scripts\tools\get_official_maps.py first."
    exit 1
}
Set-Location "$root\linesight"
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$log = "$root\logs\train_run1.log"
if (Test-Path $log) { Copy-Item $log "$root\logs\train_before_$(Get-Date -Format yyyyMMdd_HHmmss).log" }
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONPATH = "$root\linesight"
& "$root\venv\Scripts\python.exe" scripts\train.py *>&1 | Out-File -FilePath $log -Encoding utf8
