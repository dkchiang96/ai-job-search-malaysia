<#
.SYNOPSIS
    Converts a .docx file to PDF using Microsoft Word COM automation.

.DESCRIPTION
    Track B (job-application-assistant/10-docx-editing.md) needs a reliable
    DOCX -> PDF conversion to run the page-count / page-2-integrity /
    widow-line / page-fill verification loop. This script wraps Word COM
    automation, which requires Microsoft Word to be installed and licensed
    on the machine running Claude Code. It is the Windows-native equivalent
    of `soffice --headless --convert-to pdf`, which is not verified in this
    repo (no LibreOffice installed in the environment this was built in).

.PARAMETER InputPath
    Path to the source .docx file.

.PARAMETER OutputPath
    Path to write the converted .pdf file. Parent directory must exist.

.EXAMPLE
    powershell -File tools/docx_to_pdf.ps1 "cv/main_acme_ops_lead.docx" "cv/main_acme_ops_lead.pdf"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$InputPath = (Resolve-Path -LiteralPath $InputPath).Path
$OutputDir = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $OutputDir)) {
    throw "Output directory does not exist: $OutputDir"
}
# Word's SaveAs wants an absolute path even for a file that doesn't exist yet.
$OutputPath = Join-Path (Resolve-Path -LiteralPath $OutputDir).Path (Split-Path -Leaf $OutputPath)

# wdFormatPDF = 17
$wdFormatPDF = 17

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0  # wdAlertsNone

    $doc = $word.Documents.Open($InputPath, $false, $true)  # ReadOnly, no repair prompt
    $doc.SaveAs([ref]$OutputPath, [ref]$wdFormatPDF)
}
finally {
    if ($doc) {
        $doc.Close([ref]$false)
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($doc) | Out-Null
    }
    if ($word) {
        $word.Quit()
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

if (-not (Test-Path -LiteralPath $OutputPath)) {
    throw "Conversion did not produce an output file: $OutputPath"
}

Write-Output "Converted: $OutputPath"
