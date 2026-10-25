#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
frames="${1:-4096}"
repeats="${2:-32}"
trials="${3:-5}"
if command -v clang >/dev/null 2>&1; then cc=clang; else cc=gcc; fi
"$cc" -O3 -march=x86-64-v2 -ffp-contract=off window_bench.c -lm -o window_bench_c_128
"$cc" -O3 -march=native -ffp-contract=off window_bench.c -lm -o window_bench_c_native
if command -v dart >/dev/null 2>&1; then
  dart compile exe window_bench.dart -o window_bench_dart
else
  echo 'Note: Dart SDK not installed. Running C baseline only.' >&2
fi
printf 'backend,mode,hop,frames,repeats,trials,median_seconds,ns_per_sample,checksum\n' >results.csv
for hop in 441 440; do
  if [[ -x ./window_bench_dart ]]; then
    for mode in scalar packed aligned; do
      if [[ "$mode" == aligned && $(( hop % 4 )) != 0 ]]; then continue; fi
      ./window_bench_dart "--mode=$mode" "--hop=$hop" "--frames=$frames" "--repeats=$repeats" "--trials=$trials" | tee -a results.csv
    done
  fi
  for target in 128 native; do
    for mode in scalar sse; do
      ./window_bench_c_$target "--backend=c-$target" "--mode=$mode" "--hop=$hop" "--frames=$frames" "--repeats=$repeats" "--trials=$trials" | tee -a results.csv
    done
  done
done
