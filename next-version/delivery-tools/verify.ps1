# Verify available full .xz/.img files in this script's directory.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$checked = 0
$lists = @(Get-ChildItem -LiteralPath . -File | Where-Object { $_.Name -like '*.img.sha256' -or $_.Name -like '*.img.xz.sha256' })
foreach ($list in $lists) {
    $file = $list.Name -replace '\.sha256$', ''
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
    $lines = @(Get-Content -LiteralPath $list.FullName)
    if ($lines.Count -ne 1 -or $lines[0] -notmatch '^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$') { throw 'Invalid SHA256 record.' }
    $hash = $Matches[1]
    if ($Matches[2] -cne $file) { throw 'SHA256 filename mismatch.' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant() -cne $hash) { throw "SHA256 mismatch: $file. Do not flash." }
    Write-Host "SHA256 verified: $file"
    $checked += 1
}
if ($checked -eq 0) { throw 'No full .img.xz or .img available. Merge the parts first.' }
Write-Host 'After decompressing, rerun this script to verify the raw .img too.'
