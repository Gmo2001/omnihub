$env:GOOGLE_CLOUD_PROJECT = "jnu-rise-edu-147"
$env:FIRESTORE_DATABASE = "(default)"
$env:VERTEX_LOCATION = "us-central1"
$env:ME_ENDPOINT_NAME = "omnihub_endpoint_v1"
$env:ME_DEPLOYED_INDEX_ID = "dep_1769150452"
$env:GEMINI_MODEL = "gemini-2.0-flash-lite-001"


# Set working directory to the script's location (backend folder)
Set-Location $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot

Write-Host "Starting OmniHub Backend..." -ForegroundColor Green
uvicorn app.main:app --reload --port 8000
