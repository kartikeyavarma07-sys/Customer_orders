# PowerShell Launch Script for OrderFlow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Starting OrderFlow Web Application" -ForegroundColor Cyan
Write-Host "  Customer, Item & Order Management (MySQL)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# Seed initial data if first time
if (-not (Test-Path "data\db_store.json")) {
    Write-Host "[INFO] Running initial seed data script..." -ForegroundColor Yellow
    python seed_data.py
    Write-Host ""
}

Write-Host "[INFO] Starting web application on http://localhost:5000" -ForegroundColor Green
Write-Host "[INFO] Press Ctrl+C to terminate the server." -ForegroundColor Gray
python app.py 5000
