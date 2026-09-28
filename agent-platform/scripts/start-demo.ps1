param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$pythonPath = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync --locked first.' }
$statePath = Join-Path $taskRoot '.state'
New-Item -ItemType Directory -Force -Path $statePath | Out-Null
$keyPath = Join-Path $statePath 'demo-key.json'
if (Test-Path -LiteralPath $keyPath) {
    $demoKey = (Get-Content -Raw -LiteralPath $keyPath | ConvertFrom-Json).api_key
} else {
    $buffer = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    $demoKey = 'demo_' + ([BitConverter]::ToString($buffer).Replace('-','').ToLowerInvariant())
    $payload = @{api_key=$demoKey} | ConvertTo-Json
    [IO.File]::WriteAllText($keyPath,$payload,[Text.UTF8Encoding]::new($false))
}
$env:AGENT_PLATFORM_DEMO = '1'
$env:PLATFORM_API_KEYS = $demoKey + ':demo'
$env:PLATFORM_KEY_DB = Join-Path $statePath 'keys.sqlite3'
$env:PYTHONIOENCODING = 'utf-8'
Write-Host "OmniRoute Studio: http://127.0.0.1:$Port/"
Write-Host "API docs: http://127.0.0.1:$Port/docs"
Write-Host 'A local demo key is stored in .state/demo-key.json; it is not printed.'
& $pythonPath -m uvicorn platform_api.api:app --host 127.0.0.1 --port $Port
