param(
    [string]$Rom = '', [string]$Framework = '', [string]$Ui = '',
    [string]$Oracle = '', [string]$Build = 'build',
    [string]$Toolchain = 'C:\msys64\mingw64\bin', [string]$Python = '',
    [int]$Jobs = 4, [switch]$NoUi, [switch]$FastBuild,
    [switch]$Production, [switch]$SkipRegenerate
)
$ErrorActionPreference = 'Stop'
$gameRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (!$Framework) { $Framework = Join-Path $gameRoot 'vbrecomp' }
$arguments = @{} + $PSBoundParameters
$arguments['GameRoot'] = $gameRoot
$arguments['Framework'] = $Framework
& (Join-Path $Framework 'tools/build_game.ps1') @arguments
