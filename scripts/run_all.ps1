# ============================================================
# Notion Journal Loops - Run Full Pipeline (PowerShell)
# ============================================================
param(
    [int]$FromStep = 1,
    [int]$ToStep = 7,
    [int]$MaxPages = 0,
    [string]$ClusterMethod = "",
    [string]$Provider = "",
    [string]$WritebackMode = "",
    [float]$DedupeThreshold = 0,
    [switch]$Force
)

Write-Host "[Notion Journal Loops] Starting pipeline (steps $FromStep to $ToStep)..." -ForegroundColor Cyan

# Activate virtual environment if it exists
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .venv\Scripts\Activate.ps1
    Write-Host "[INFO] Virtual environment activated." -ForegroundColor Green
}

# Build argument list
$args_list = @("--from-step", $FromStep, "--to-step", $ToStep)

if ($MaxPages -gt 0) { $args_list += @("--max-pages", $MaxPages) }
if ($ClusterMethod) { $args_list += @("--cluster-method", $ClusterMethod) }
if ($Provider) { $args_list += @("--provider", $Provider) }
if ($WritebackMode) { $args_list += @("--writeback-mode", $WritebackMode) }
if ($DedupeThreshold -gt 0) { $args_list += @("--dedupe-threshold", $DedupeThreshold) }
if ($Force) { $args_list += "--force" }

# Run pipeline
python -m src.pipeline.run_pipeline @args_list

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Pipeline failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "[SUCCESS] Pipeline complete! Check data\outputs\ for results." -ForegroundColor Green
