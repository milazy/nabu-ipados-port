# Read-only project recovery check for a freshly installed Windows/KernelOS PC.
# Run AFTER reconnecting the external backup drive. This script NEVER flashes a device.
param(
    [string]$ExternalDrive = 'F:'
)
$ErrorActionPreference = 'Stop'
$root = Join-Path ($ExternalDrive.TrimEnd('\') + '\') 'NABU_IPADOS_COMPLETE_BACKUP_20261107'
$backup = Join-Path $root 'NABU_IPADOS_LAB'
$reportPath = Join-Path $root 'VERIFICATION_REPORT.json'
$markerPath = Join-Path $root 'BACKUP_COMPLETE_AND_VERIFIED.txt'
$restorePath = Join-Path $root 'RESTORE_NABU_PROJECT.ps1'
$source = Join-Path $env:USERPROFILE 'Desktop\NABU_IPADOS_LAB'

$assessment = [ordered]@{
    assessed_utc = [DateTime]::UtcNow.ToString('o')
    restore_drive = $ExternalDrive
    external_root_found = (Test-Path -LiteralPath $root -PathType Container)
    backup_folder_found = (Test-Path -LiteralPath $backup -PathType Container)
    verification_report_found = (Test-Path -LiteralPath $reportPath -PathType Leaf)
    confirmation_marker_found = (Test-Path -LiteralPath $markerPath -PathType Leaf)
    restoration_script_found = (Test-Path -LiteralPath $restorePath -PathType Leaf)
    desktop_workspace_found = (Test-Path -LiteralPath $source -PathType Container)
    github_kernel_image_flashed = $false
    ipad_os_installed = $false
    source_backup_verified = $false
    approved_to_flash = $false
    issues = @()
}
if ($assessment.verification_report_found) {
    try {
        $manifest = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
        $assessment.backup_files = [int64]$manifest.files
        $assessment.backup_bytes = [int64]$manifest.bytes
        $assessment.verification_result = [string]$manifest.result
        if ($manifest.result -eq 'PASS' -and [int64]$manifest.files -eq 32390 -and
            [int64]$manifest.bytes -eq 40374431865 -and
            $assessment.confirmation_marker_found) {
            $assessment.source_backup_verified = $true
        } else {
            $assessment.issues += 'External copy has not passed confirmed full SHA-256 verification.'
        }
    } catch {
        $assessment.issues += 'Could not parse external backup verification report.'
    }
} else {
    $assessment.issues += 'Missing file-by-file SHA-256 verification report.'
}
if (-not $assessment.backup_folder_found) {
    $assessment.issues += 'Project folder missing from external drive.'
}
if (-not $assessment.restoration_script_found) {
    $assessment.issues += 'Restoration helper missing from external backup.'
}
if (-not (Test-Path -LiteralPath (Join-Path ($ExternalDrive.TrimEnd('\') + '\') 'NABU_IPADOS_RECOVERY_20261106') -PathType Container)) {
    $assessment.issues += 'Separate preexisting tablet recovery folder not found on this drive.'
}
$assessment.python_available = [bool](Get-Command python -ErrorAction SilentlyContinue)
$assessment.git_available = [bool](Get-Command git -ErrorAction SilentlyContinue)
$assessment.flash_readiness = 'NOT_READY: XNU build, real Apple OS/SystemOS root images, owner GPT, physical boot and consent still required.'
Write-Host '=== XIAOMI PAD 5 iPadOS RECOVERY PREFLIGHT (READ-ONLY) ==='
$assessment | ConvertTo-Json -Depth 5
if ($assessment.source_backup_verified) {
    Write-Host 'Source workspace backup: VERIFIED. Recovery copies were not modified.'
} else {
    Write-Warning 'Backup NOT YET VERIFIED; do not erase or flash any partitions.'
}
Write-Host 'No ADB, Fastboot, disk partition, or firmware write commands were run.'
