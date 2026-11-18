param(
    [string]$Configuration = "Release",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = Join-Path $root "ColophonWin.csproj"
if (-not (Test-Path -LiteralPath $project)) { throw "ColophonWin.csproj not found beside this script." }

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $root "publish"
}

if (Test-Path -LiteralPath $Output) {
    Get-ChildItem -LiteralPath $Output | Remove-Item -Recurse -Force
}

& dotnet publish $project -c $Configuration -r win-x64 --self-contained true `
    -p:PublishSingleFile=false -o $Output

$size = (Get-ChildItem -LiteralPath $Output -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("Published to {0}" -f $Output)
Write-Host ("Size: {0:N1} MB" -f ($size / 1MB))
