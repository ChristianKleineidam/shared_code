# Run from a Windows x64 PowerShell session, with Dart and clang/gcc in PATH.
param(
  [int] $Frames = 4096,
  [int] $Repeats = 32,
  [int] $Trials = 5
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$dart = Get-Command dart -ErrorAction SilentlyContinue
if (-not $dart) { throw 'Dart SDK not in PATH. Install Dart or Flutter SDK first.' }
$compiler = Get-Command clang -ErrorAction SilentlyContinue
if (-not $compiler) { $compiler = Get-Command gcc -ErrorAction SilentlyContinue }
if (-not $compiler) { throw 'Install LLVM clang or GCC (x86_64) and add it to PATH.' }
& dart compile exe window_bench.dart -o window_bench_dart.exe
if ($LASTEXITCODE -ne 0) { throw 'Dart AOT compilation failed.' }
& $compiler.Source -O3 -march=x86-64-v2 -ffp-contract=off window_bench.c -o window_bench_c_128.exe
if ($LASTEXITCODE -ne 0) { throw 'C 128-bit baseline compilation failed.' }
& $compiler.Source -O3 -march=native -ffp-contract=off window_bench.c -o window_bench_c_native.exe
if ($LASTEXITCODE -ne 0) { throw 'C native compilation failed.' }
$log = Join-Path $PSScriptRoot 'results.csv'
'backend,mode,hop,frames,repeats,trials,median_seconds,ns_per_sample,checksum' | Set-Content $log
foreach ($hop in @(441, 440)) {
  foreach ($mode in @('scalar','packed','aligned')) {
    if ($mode -eq 'aligned' -and ($hop % 4 -ne 0)) { continue }
    $line = & .\window_bench_dart.exe "--mode=$mode" "--hop=$hop" "--frames=$Frames" "--repeats=$Repeats" "--trials=$Trials"
    if ($LASTEXITCODE -ne 0) { throw "Dart benchmark failed: $mode / $hop" }
    Write-Output $line
    Add-Content $log $line
  }
  foreach ($target in @('128','native')) {
    foreach ($mode in @('scalar','sse')) {
      $binary = Join-Path $PSScriptRoot "window_bench_c_$target.exe"
      $line = & $binary "--backend=c-$target" "--mode=$mode" "--hop=$hop" "--frames=$Frames" "--repeats=$Repeats" "--trials=$Trials"
      if ($LASTEXITCODE -ne 0) { throw "C benchmark failed: $target $mode / $hop" }
      Write-Output $line
      Add-Content $log $line
    }
  }
}
Write-Output "Results saved: $log"
