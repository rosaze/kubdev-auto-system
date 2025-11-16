# Requires the backend running locally on :8000 (uvicorn backend.app:app --reload)
$headers = @{
  "Authorization" = "Bearer admin-key-123"
  "Content-Type"  = "application/json"
}

$body = @{
  name = "sample"
  template_id = "node-20"
  git_repository = "https://github.com/vercel/next.js"
  ref = "canary"
  start_command = "npm run dev"
  ports = @(3000,5173)
  gitpod_compat = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/me/workspaces" -Headers $headers -Body $body | ConvertTo-Json -Depth 5

