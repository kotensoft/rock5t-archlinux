# Run in PowerShell; no administrator privileges or disk writes are needed.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$lists = @(Get-ChildItem -LiteralPath . -File | Where-Object { $_.Name -like '*.img.xz.parts.sha256' })
if ($lists.Count -ne 1) { throw 'Need exactly one matching parts checksum list in this folder.' }
$output = $lists[0].Name -replace '\.parts\.sha256$', ''
$partial = "$output.partial"
if ((Test-Path -LiteralPath $output) -or (Test-Path -LiteralPath $partial)) { throw 'Output or partial file exists; nothing overwritten.' }
$parts = @()
$n = 1
foreach ($line in (Get-Content -LiteralPath $lists[0].FullName)) {
    if ($line -notmatch '^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$') { throw 'Invalid part checksum record.' }
    $hash = $Matches[1]; $part = $Matches[2]
    if ($part -cne ('{0}.part{1:D3}' -f $output, $n)) { throw "Unexpected part order: $part" }
    if (-not (Test-Path -LiteralPath $part -PathType Leaf)) { throw "Missing part: $part" }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $part).Hash.ToLowerInvariant() -cne $hash) { throw "Part SHA256 mismatch: $part" }
    Write-Host "Verified $part"
    $parts += $part; $n += 1
}
if ($parts.Count -eq 0) { throw 'Empty parts list.' }
$fullRecord = @(Get-Content -LiteralPath "$output.sha256")
if ($fullRecord.Count -ne 1 -or $fullRecord[0] -notmatch '^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$') { throw 'Invalid full-file SHA256 record.' }
$fullHash = $Matches[1]
if ($Matches[2] -cne $output) { throw 'Full-file checksum filename mismatch.' }
$created = $false
try {
    $destination = [System.IO.File]::Open((Join-Path $PSScriptRoot $partial), [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $created = $true
    try {
        foreach ($part in $parts) {
            $source = [System.IO.File]::OpenRead((Join-Path $PSScriptRoot $part))
            try { $source.CopyTo($destination) } finally { $source.Dispose() }
        }
        $destination.Flush($true)
    } finally { $destination.Dispose() }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash.ToLowerInvariant() -cne $fullHash) { throw 'Merged SHA256 mismatch. Do not flash.' }
    # File.Move refuses to replace an existing file.
    [System.IO.File]::Move((Join-Path $PSScriptRoot $partial), (Join-Path $PSScriptRoot $output))
    $created = $false
} finally {
    if ($created -and (Test-Path -LiteralPath $partial)) { Remove-Item -LiteralPath $partial }
}
Write-Host "Merged and SHA256 verified: $output"
Write-Host 'Keep every part until the image has been safely written and verified.'
