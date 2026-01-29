$Token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZHVfMTUwQGljZXUua3IiLCJlbWFpbCI6ImVkdV8xNTBAaWNldS5rciIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc2OTcyNDYxOH0.ucazasPsOA55lUc_Hu6kqDwMMpqeksAe5xXzlmsgTpE"
$BaseUrl = "https://omnihub-backend-707724932002.asia-northeast3.run.app"
$Headers = @{Authorization=("Bearer " + $Token)}

Write-Host "1. Fetching Valid File List from Virtual Tree..."
$TreeUrl = "$BaseUrl/files/virtual-tree"

# Helper function to extract file IDs recursively
function Get-FileIds($Node) {
    echo $Node.id
    if ($Node.children) {
        foreach ($child in $Node.children) {
            Get-FileIds -Node $child
        }
    }
}

try {
    $TreeResponse = Invoke-RestMethod -Uri $TreeUrl -Method Get -Headers $Headers
    # Extract IDs recursively
    $FileIds = @()
    if ($TreeResponse -is [System.Collections.IDictionary]) {
         # Single root node logic if needed, or if children logic
         # Adjust based on 'files/virtual-tree' response structure: Root node with children
         $FileIds += Get-FileIds -Node $TreeResponse
    }
    
    # Filter out empty/null IDs
    $FileIds = $FileIds | Where-Object { $_ -ne $null -and $_ -ne "" }
    
    Write-Host "   Found $($FileIds.Count) files."
    if ($FileIds.Count -eq 0) { throw "No files found to test with." }
} catch {
    Write-Host "   Error fetching file list: $($_.Exception.Message)"
    Write-Host "   Using dummy/hardcoded IDs if available, else exiting."
    # Use the one valid ID user pasted earlier just in case
    $FileIds = @("fil_1LZ2cm0mlFAACC-ewg1gsTHkUMsK6hmdp") 
}

Write-Host "2. Starting Traffic Generator (100 Calls)..."
$Actions = @("VIEW", "DOWNLOAD", "VIEW", "VIEW") # More views than downloads

For ($i=1; $i -le 100; $i++) {
    $Action = $Actions | Get-Random
    $TargetId = $FileIds | Get-Random
    
    try {
        if ($Action -eq "VIEW") {
            # GET /files/{id}
            $Response = Invoke-RestMethod -Uri "$BaseUrl/files/$TargetId" -Method Get -Headers $Headers
            Write-Host "[$i/100] ✅ VIEW ($TargetId): Success"
        }
        elseif ($Action -eq "DOWNLOAD") {
            # POST /files/{id}/download
            $Response = Invoke-RestMethod -Uri "$BaseUrl/files/$TargetId/download" -Method Post -Headers $Headers
            Write-Host "[$i/100] ⬇️ DOWNLOAD ($TargetId): Success"
        }
    } catch {
        # 404 is also a valid test for "Audit Log Success=False"
        Write-Host "[$i/100] ⚠️ $Action ($TargetId): Failed/Expected ($_.Exception.Message)"
    }
    
    # Random sleep 0.1s ~ 0.5s
    $Sleep = Get-Random -Minimum 100 -Maximum 500
    Start-Sleep -Milliseconds $Sleep
}
Write-Host "🎉 Traffic Generation Complete!"
