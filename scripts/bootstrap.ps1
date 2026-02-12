$ErrorActionPreference = "Stop"

Write-Host "[bootstrap] backend"
Push-Location "C:\Dev\llm-workspace\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
Pop-Location

Write-Host "[bootstrap] frontend"
Push-Location "C:\Dev\llm-workspace\frontend"
npm install
Pop-Location

Write-Host "[bootstrap] complete"
