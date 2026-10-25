# Windows Dart/C SIMD results, 2026-10-24

The hop-441 pure-Dart unaligned-load prototype is **6.31x faster than packed
Dart with the same unchecked bounds and four-way unrolling controls**. Its
0.27906 ns/sample median remains **3.03x slower than the fastest C row** in the
same run. A checked unaligned load alone is 3.28x faster than checked packed
Dart at unroll factor one. This supports an efficient checked API as well as
a smaller, separately measured benefit from removing checks under proved
contracts. It does not establish C-equivalent performance from Lean verification.

[Recorded numerical analyses](windows_results_2026-10-24.json) retain all
configuration summaries from every run, the primary run's seven per-round
timings per configuration, paired contrasts, code-generation counts, toolchain
flags, checksums, and source/binary/platform SHA-256 provenance. Binaries and
CSV files are excluded. Full local logs and assembly remain in the ignored
`controlled-output*` directories.

Source hashes identify the measured working-tree bytes. Git's configured
line-ending normalization can change those hashes on a fresh checkout without
changing the source's meaning.

## Machine and method

- AMD Ryzen 7 8700F, 8 cores / 16 logical processors; AMD64 family 25, model 117,
  stepping 2; Windows x64 build 26200.
- Dart SDK 3.11.4 stable, revision
  `02abc57898bebc334a997e609ce5827c8ef207d7`; AOT via `dart compile exe`.
- LLVM-MinGW Clang 23.1.4, target `x86_64-w64-windows-gnu`, LLVM revision
  `7a941dfb2877a0b8cf30323fefa85ad019e0b0f5` (portable 20261020 distribution).
  Neither Clang nor GCC was initially on PATH; portable Clang was provisioned
  in the workspace. Python 3.11.13 and PowerShell 7.6.8 were available.
- C-control: `-O3 -ffp-contract=off -march=x86-64-v2 -fno-vectorize
  -fno-slp-vectorize -fno-unroll-loops`. C-128: `-O3 -ffp-contract=off
  -march=x86-64-v2`. C-native: `-O3 -ffp-contract=off -march=native`.
  No fast-math. Native selected `znver4` and can use AVX-512; C-128 is restricted
  to 128-bit SIMD. C buffers are nonoverlapping, `restrict` qualified, and have
  64-byte-aligned bases.
- Each frame multiplies 1,024 float32 samples by Hann coefficients. Timed
  trials use 4,096 frames and 128 repeats: 536,870,912 sample multiplications.
  Setup, preflight and two warm-up repeats are outside the timed interval.
- The primary confirmation started at 14:44:57 UTC. All children used logical
  CPU 2 (mask 4) and above-normal priority. Seven rounds ran all 21 configurations
  once in shuffled order, seed 20261024. The function-call and checksum-consume
  boundary is common within each language. Every Dart baseline used the same
  patched platform and common call signature.
- Other CPU-heavy workloads continued. Above-normal priority reduces
  descheduling but cannot remove shared-cache, bandwidth, SMT, or clock effects.
  Dart MADs were 1.8-7.2%; C-native scalar was noisier at 22.4%. These are
  observed medians, not hardware throughput limits. Earlier runs have different
  conditions/code layout; compute ratios within a run.

`u1` and `u4` mean one or four source scalar/vector operations per loop
iteration. SIMD u4 therefore covers 16 samples. Checked Dart uses per-access
checks. Unchecked Dart combines the existing
`@pragma('vm:unsafe:no-bounds-checks')` with the prototype unchecked load when
applicable. Interruptions and safepoints remain enabled. C-control prevents
automatic unrolling/vectorization while retaining explicit SSE operations;
C-128/C-native can optimize their nominal scalar source automatically.

## All implementations in the primary hop-441 confirmation

The Dart denominator is `dart / scalar-checked-u1` at 1.85583 ns/sample. The C
denominator is `c-128 / sse-u1` at 0.09204 ns/sample. Lower ns/sample and lower
slowdown are better; higher speedup is better. Input shift one is a physical
four-byte shift with identical input values.

| Implementation | Hop | Input shift (floats) | ns/sample | Speedup vs Dart scalar | Slowdown vs fastest C | MAD % |
|---|---:|---:|---:|---:|---:|---:|
| c-128 / scalar-u1 | 441 | 0 | 0.09553 | 19.43x | 1.04x | 5.8 |
| c-128 / sse-u1 | 441 | 0 | 0.09204 | 20.16x | 1.00x | 3.0 |
| c-control / scalar-u1 | 441 | 0 | 0.40543 | 4.58x | 4.41x | 3.3 |
| c-control / scalar-u4 | 441 | 0 | 0.30726 | 6.04x | 3.34x | 4.4 |
| c-control / sse-u1 | 441 | 0 | 0.11730 | 15.82x | 1.27x | 5.4 |
| c-control / sse-u1 | 441 | 1 | 0.12202 | 15.21x | 1.33x | 7.4 |
| c-control / sse-u4 | 441 | 0 | 0.09433 | 19.67x | 1.02x | 5.4 |
| c-native / scalar-u1 | 441 | 0 | 0.11304 | 16.42x | 1.23x | 22.4 |
| c-native / sse-u1 | 441 | 0 | 0.09820 | 18.90x | 1.07x | 5.2 |
| dart / packed-checked-u1 | 441 | 0 | 1.88505 | 0.98x | 20.48x | 3.4 |
| dart / packed-checked-u4 | 441 | 0 | 1.86069 | 1.00x | 20.22x | 3.4 |
| dart / packed-unchecked-u1 | 441 | 0 | 1.77297 | 1.05x | 19.26x | 1.9 |
| dart / packed-unchecked-u4 | 441 | 0 | 1.76017 | 1.05x | 19.12x | 1.8 |
| dart / scalar-checked-u1 | 441 | 0 | 1.85583 | 1.00x | 20.16x | 3.0 |
| dart / scalar-checked-u4 | 441 | 0 | 1.34041 | 1.38x | 14.56x | 6.1 |
| dart / scalar-unchecked-u1 | 441 | 0 | 1.17650 | 1.58x | 12.78x | 2.3 |
| dart / scalar-unchecked-u4 | 441 | 0 | 0.89306 | 2.08x | 9.70x | 4.2 |
| dart / unaligned-checked-u1 | 441 | 0 | 0.57464 | 3.23x | 6.24x | 4.3 |
| dart / unaligned-checked-u4 | 441 | 0 | 0.54663 | 3.40x | 5.94x | 7.2 |
| dart / unaligned-unchecked-u1 | 441 | 0 | 0.43369 | 4.28x | 4.71x | 6.3 |
| dart / unaligned-unchecked-u4 | 441 | 0 | 0.27906 | 6.65x | 3.03x | 6.6 |

## What closes the gap

| Controlled comparison, hop 441 | Ratio of medians |
|---|---:|
| Checked packed u1 -> checked unaligned u1 | 3.28x |
| Checked unaligned u1 -> unchecked unaligned u1 | 1.33x |
| Unchecked unaligned u1 -> unchecked unaligned u4 | 1.55x |
| Unchecked packed u4 -> unchecked unaligned u4 | 6.31x |
| Checked packed u1 -> unchecked unaligned u4 | 6.75x |
| Checked scalar u1 -> unchecked unaligned u4 | 6.65x |

For the matched unchecked/u4 packing comparison, same-round speedups have
median 6.42x and observed range 5.08-8.06x; that range is not a confidence
interval. Unrolling the checked load did not show a clear paired improvement.
The best Dart result is 2.96x slower than C-control SSE u4 as well as 3.03x
slower than the fastest optimized C row. Both those C comparators use 128-bit
SIMD, so wider vectors cannot explain the entire remaining gap.

Measured Dart disassembly gives a more specific explanation:

- **Vector packing and instruction selection:** scalar Dart converts float32
  values to doubles, multiplies with `mulsd`, then converts back. Packed Dart
  constructs vectors through scalar lane conversions and stack stores. The
  prototype emits direct `movups` loads, `mulps`, and vector stores; the dynamic
  SDK dispatch and result cast inline away. Its unchecked u1/u4 kernels have
  one/four packed multiplies and zero float/double conversions. Stack-based
  packing is not a heap allocation.
- **Unaligned accesses:** the load accepts all byte phases. At hop 441, frame
  starts cycle through four float-alignment phases. The C-control physical-shift
  experiment showed no consistent large penalty across rounds. It also changes
  cache-line crossings and cache-set mapping, so it cannot identify a single
  instruction's latency. The results attribute the large packed gap primarily
  to the Dart load/packing lowering, rather than hardware unaligned-load cost.
- **Bounds checks:** unchecked kernels have zero bounds-error paths. The
  checked unaligned kernel retains two input byte-endpoint checks plus Hann
  and output checks per vector operation. A safe pre-loop range guard in the
  larger suite did not make the current compiler remove per-access checks.
  Their removal helps, but is a much smaller effect than efficient loads.
- **Unrolling and other optimization:** explicit unrolling helps the unchecked
  direct-load loop. The Dart loop still has pointer/address calculations,
  output-writability checks, and safepoints. Optimized C uses stronger loop
  transformations and different addressing; native scalar source additionally
  uses wider SIMD. The experiment does not quantify each remaining compiler
  effect independently.
- **Allocation:** buffers and the ByteData view are created before timing.
  The measured kernel paths contain no allocation calls and no native/load
  helper or FFI calls. Allocation and FFI overhead do not explain this gap.

## Correctness and prototype scope

The final 21 configurations each passed 4,194,304 bitwise output comparisons
against scalar within the same language. All 147 timed trials printed exactly
`-255.783023190`, including C and Dart. The independent raw-load test passed
784 vector reads across all 16 byte offsets, nonzero view offsets, read-only
views, last-valid reads, signed zero, infinities, subnormals, and NaN payloads.
All 40 invalid checked reads were rejected. Invalid unchecked reads were not
executed. No final benchmark compilation or correctness failures remain.

The initial stock compile produced a telemetry permission error under the
sandbox after emitting its executable; subsequent commands with authorized
permissions succeeded. The missing C compiler was supplied as a portable
workspace tool. No original benchmark source repair was necessary.

The timed kernel stays in Dart. `sdk_unaligned_load.patch` adds checked and
unchecked native-endian ByteData methods backed by the VM's existing vector
load intrinsic. `patch_unaligned_platform.dart` applies the equivalent change
to a separate platform kernel; existing SDK methods and compiler/runtime
executables are unchanged. The installed SDK platform hash remained
`37131d49b2220f61d1bc8bff30b7c2f002e83d21b23137e65938d9c95d2b7881`;
the experimental platform hash is
`476892b76e47402f753ab8dc8502724bc7b7b0144377e26f6ec8143515107921`.
The source-equivalent SDK patch and all prototype/test/runner sources are
included; platform binaries are excluded.

The unchecked operation requires a live backing view and
`0 <= byteOffset <= bytes.lengthInBytes - 16`, with the benchmark's ByteData
view referring to the intended sample buffer. The existing SDK intrinsic
performs the load. A Lean-verified feature could prove the required range,
alias/view and lifetime contracts and authorize removal of redundant checks.
No Lean proof or production unsafe feature was implemented here. Efficient
checked vector access accounts for the largest demonstrated improvement;
verification alone does not supply SIMD lowering, alias analysis, instruction
scheduling, or all the loop transformations still separating Dart from C.
These measurements cover window multiplication, not FFTs or full STFT analysis.

## Original requested baseline

The original PowerShell command and analyzer completed with 4,096 frames,
128 repeats and seven trials. The following medians predate the controlled
harness; they should not be divided by primary-confirmation timings. Printed
checksums match between every language/mode at each hop:
`-255.783023` for 441 and `-1860.507983` for 440. This runner did not retain
per-trial spreads. `results.csv` is unchanged and excluded from the commit.

| Implementation | Hop | Input shift (floats) | ns/sample | Speedup vs Dart scalar | Slowdown vs fastest C | MAD % |
|---|---:|---:|---:|---:|---:|---:|
| dart / scalar | 441 | 0 | 1.33278 | 1.00x | 16.91x | n/a |
| dart / packed | 441 | 0 | 1.73771 | 0.77x | 22.05x | n/a |
| c-128 / scalar | 441 | 0 | 0.07880 | 16.91x | 1.00x | n/a |
| c-128 / sse | 441 | 0 | 0.08671 | 15.37x | 1.10x | n/a |
| c-native / scalar | 441 | 0 | 0.08472 | 15.73x | 1.08x | n/a |
| c-native / sse | 441 | 0 | 0.08124 | 16.41x | 1.03x | n/a |
| dart / scalar | 440 | 0 | 1.51176 | 1.00x | 12.75x | n/a |
| dart / packed | 440 | 0 | 1.79926 | 0.84x | 15.17x | n/a |
| dart / aligned | 440 | 0 | 0.47429 | 3.19x | 4.00x | n/a |
| c-128 / scalar | 440 | 0 | 0.11860 | 12.75x | 1.00x | n/a |
| c-128 / sse | 440 | 0 | 0.12497 | 12.10x | 1.05x | n/a |
| c-native / scalar | 440 | 0 | 0.12968 | 11.66x | 1.09x | n/a |
| c-native / sse | 440 | 0 | 0.13652 | 11.07x | 1.15x | n/a |

The first controlled bounds/packing/unrolling experiment used 48 configurations
and passed 336 timed trials, with exact printed checksums `-255.783023190`
(441) and `-1860.507982910` (440). It found scalar u1 check removal 1.57x,
packed u1 check removal 1.04x, checked scalar unrolling 1.28x, and hop-440
checked packed-to-direct loads 5.46x. Its best aligned hop-440 Dart result was
0.16253 ns/sample, 3.96x slower than that run's fastest C. Its call signature
predates the unaligned-load extension. All 48 rows, including guarded variants
and input-shift controls, are retained in the numerical archive.

The 60-configuration unaligned suite passed 420 trials, then the focused
normal-priority confirmation passed 147 trials. Both had substantial host
scheduling noise; their full summaries are retained in the archive and do not
supply the headline ratios. Source/SDK hashes identify the primary measured
inputs. The original baseline, historical runs, and primary confirmation are
kept distinct rather than pooled into a single ranking.

## Reproduction and source changes

See [README](README.md#pure-dart-unaligned-vector-load-prototype) for the exact
SDK-source preparation and dependencies. After creating the separate platform
kernel, run from the repository root, substituting the Dart/Clang paths:

```powershell
python .\dart-eardea-simd-comparison\run_controlled.py --dart <dart.exe> --cc <clang.exe> --platform .\dart-eardea-simd-comparison\controlled-output-sdk\vm_platform_product_unaligned.dill --families scalar packed unaligned --hops 441 --checks checked unchecked --frames 4096 --repeats 128 --trials 7 --cpu 2 --priority above-normal --output .\dart-eardea-simd-comparison\controlled-output-unaligned-priority
python .\dart-eardea-simd-comparison\analyze_controlled.py .\dart-eardea-simd-comparison\controlled-output-unaligned-priority
```

Choose a fresh output directory; the runner refuses to overwrite existing raw
trials. The original benchmark files remain unchanged. Added sources provide
the controlled C/Dart kernels, generated variants, runner/analyzer, isolated
SDK transformer, source-equivalent SDK patch, and vector-load correctness test.
Documentation and the ignored-output rule are updated. No GitHub Actions
workflow is created or modified.
