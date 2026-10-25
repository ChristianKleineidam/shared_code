# Dart SIMD versus optimized C: Eardea-like STFT windowing

The measured kernel multiplies each overlapping 1,024-sample frame by a Hann
window. It isolates one real production operation from Eardea's beat-analysis
STFT preprocessing. It **does not benchmark full FFTs**, and the C code is
**not proof-verified Dart**. It gives a realistic comparison against one
possible lower-level optimization target, not a performance guarantee.

[Windows results, 2026-10-24](WINDOWS_RESULTS_2026-10-24.md) records the full
comparison, controlled unaligned-load experiment, correctness checks, and
implications for Lean-verified unsafe Dart. The accompanying
[numerical archive](windows_results_2026-10-24.json) preserves every run's
configuration summaries and the primary confirmation's per-round timings.

- `hop=441` matches Eardea's beat-analysis STFT and makes three of every four
  frames start at an unaligned 16-byte address. Safe `Float32x4List.view` cannot
  start there; Dart `packed` gathers four scalar lanes.
- `hop=440` is a control case in which `Float32x4List.view` permits directly
  vectorizing input frames in `aligned` mode.
- Dart scalar, Dart packed SIMD, Dart aligned SIMD (440 only), C scalar and C
  SSE intrinsics use the same algorithm, 1,024 floats per window and same
  checksum strategy.
- `C scalar` may auto-vectorize under `-O3` (this is intended). `C sse`
  explicitly uses `_mm_loadu_ps` and `_mm_mul_ps`. C uses `restrict` on its
  nonoverlapping buffers. Two C targets are built: `c-128` with only 128-bit
  x86 SIMD instructions available to the optimizer, and `c-native` with all
  instructions of the benchmarking CPU (possibly AVX2/AVX512).

## Windows x64 (PowerShell)

Requires Dart SDK and LLVM clang or GCC on PATH. Run from this directory:

```powershell
pwsh -NoProfile -File .\run_windows.ps1
```

Use a release-like AOT executable (`dart compile exe`), not just `dart run`.
Custom configurations:

```powershell
pwsh -NoProfile -File .\run_windows.ps1 -Frames 4096 -Repeats 128 -Trials 7
python .\analyze_results.py
```

## Linux x86_64

Requires clang or gcc. Dart is optional; C-only results are produced if
Dart is unavailable.

```bash
./run_linux.sh 4096 128 7
python3 analyze_results.py
```

## Interpretation

Each row is a median of repeated time measurements. `ns_per_sample` is lower
when faster. Check the checksum across language/modes for each hop and allow
small floating-point differences from the Hann calculation. Compare same-hop
rows and appropriate ISA-target rows only. `c-native` is an upper-performance
reference that may exploit wider registers than current 128-bit Dart SIMD.
If a Dart scalar or aligned SIMD path is already competitive with C SIMD,
the proposed `verifiedUnsafe` feature has no established performance case
**for this kernel**. If a significant gap remains, investigate generated
code, allocations and address-alignment restrictions before attributing
the gap to the absence of unsafe blocks. Measure on Windows and Android
hardware relevant to Eardea before making general speedup claims.

Run `python analyze_results.py` to compare results, check cross-language
checksums and calculate time ratios once you have both Dart and C rows.
`LOCAL_C_ONLY_RESULTS.md` records the limited native measurements made when
assembling the package.

Compiled binaries and generated CSV data are ignored by Git. The
`window_bench.dart` and `window_bench.c` sources are standalone with no
third-party dependencies, aside from standard Dart and C runtimes.

Potential follow-up: benchmark the complete **fftea-backed STFT** against a
semantically matched C FFT implementation, explicitly accounting for cached
FFT plans, FFT algorithm choice, precision, data packing, and output parity.

## Controlled ablations

The original sources, runner, and `results.csv` remain a separate baseline.
`run_controlled.py` builds an additional suite to separate three effects:

- **Bounds checks:** each Dart kernel has checked, safely range-guarded, and
  unchecked versions. The unchecked version uses the existing AOT-only
  `@pragma('vm:unsafe:no-bounds-checks')`. This is an experimental diagnostic,
  **not a Lean proof or a production safety guarantee**. All buffers and frame
  ranges are validated before unchecked kernels are entered. No variant
  disables interruption, safepoint, or stack checks.
- **Packing:** scalar, four-scalar-lane `Float32x4` construction, and direct
  vector loads have the same input, window, output, and consumption boundary.
  In the original three-family suite, packed versus direct loads is a same-hop
  comparison at **440 only**. The later unaligned-load prototype below adds
  that controlled comparison at hop 441.
- **Unrolling:** each Dart kernel and each controlled C kernel processes one
  or four scalar/vector operations per loop iteration. C-control disables
  automatic vectorization and automatic unrolling; its explicit SSE operations
  remain SIMD. C-128 and C-native retain the original optimizing flags as
  reference targets. Scalar C-control consequently measures actual scalar C.

The Dart loop bodies are generated mechanically so the variants differ only
in guards, the unchecked annotation, and unroll factor. Regenerate them with
`python generate_controlled_kernels.py`; `--check` detects stale generated code.
Original baseline C helpers and kernels are included by `controlled_bench.c`.

Run the original three-family suite from the repository root with Dart, Clang,
and Python on PATH:

```powershell
python .\dart-eardea-simd-comparison\run_controlled.py --frames 4096 --repeats 128 --trials 7 --cpu 2
python .\dart-eardea-simd-comparison\analyze_controlled.py
```

Use `--dart <dart.exe>` and `--cc <clang.exe>` to select explicit toolchains.
The tested configuration uses LLVM-MinGW Clang with `llvm-objdump` alongside
the compiler. `--cpu` selects a logical CPU; only the runner and its children
are pinned. `--cpu -1` leaves affinity unchanged. The runner does not change
system power settings. The default process priority is unchanged; the optional
`--priority above-normal` applies only to benchmark children on Windows. An occupied SMT sibling and
other desktop activity can still affect measurements.

Before timing, every configuration is checked bitwise against its language's
original scalar kernel for every output element of every frame. Cross-language
checksums are checked separately to an absolute tolerance of `1e-6`, accounting
for printed precision. This is test evidence for these inputs, not a proof for
arbitrary floating-point values or buffers.

Every round runs every configuration once in a seeded shuffled order. Each
process initializes buffers, checks its checksum, warms up for two repeats,
then reports one timed trial. Reported medians, MAD percentages, min/max values,
and same-round paired ratios retain the raw measurements. A paired ratio above
one means the second variant is faster; its min/max is observed round spread,
not a confidence interval. The baseline for speedup is checked scalar Dart at
the same hop. The C denominator is the fastest median at that hop.

C input, Hann, and output bases are explicitly aligned to 64 bytes. A separate
SSE input-shift control moves the physical input address by four bytes while
keeping the input values, hop, Hann, and output alignment unchanged. At hop
440 this changes all frame starts from aligned to unaligned; at hop 441 it
rotates the existing four phases. This also changes cache-line crossings and
relative cache-set mapping, so it does not isolate a single CPU instruction's
latency.

`controlled-output/` contains the raw trials, summary CSV, structured analysis,
verification log, toolchain/affinity/source-hash metadata, generated C assembly,
and disassembly of the **measured** Dart and C binaries. The analyzer verifies
that all 18 Dart kernels are present and unchecked kernels have no remaining
bounds-error paths. The runner refuses to overwrite an existing `raw.csv`;
use `--output .\dart-eardea-simd-comparison\controlled-output-new` for another run.
All `controlled-output*` directories are ignored by Git. No workflow is needed.

The existing unsafe pragma can establish how much check removal helps with the
current Dart backend. A Lean-verified feature could make such transformations
conditional on proved contracts, but SIMD load support, packing elimination,
alias analysis, and instruction scheduling still require compiler work. See
[Dart VM pragma documentation](https://github.com/dart-lang/sdk/blob/3.11.4/runtime/docs/pragmas.md).

### Windows measurement, 2026-10-24

Ryzen 7 8700F, Windows x64 build 26200, Dart 3.11.4 AOT, LLVM-MinGW
Clang 23.1.4. The runner was pinned to logical CPU 2 (affinity mask 4), with
4096 frames, 128 repeats, seven shuffled rounds, and seed 20261024.
All 48 preflight configurations passed 4,194,304 bitwise element comparisons
each. All 336 timed trials passed cross-language checksum parity. Their
printed checksums were -255.783023190 (441) and -1860.507982910 (440).

Selected medians in ns/sample; ratios use this controlled harness, not the
earlier unpinned baseline run:

| Matched comparison | Hop | Before | After | Speedup |
|---|---:|---:|---:|---:|
| Scalar checked -> unchecked, u1 | 441 | 1.17383 | 0.74786 | 1.57x |
| Packed checked -> unchecked, u1 | 441 | 1.59059 | 1.52770 | 1.04x |
| Scalar checked u1 -> checked u4 | 441 | 1.17383 | 0.91622 | 1.28x |
| Scalar unchecked u1 -> unchecked u4 | 441 | 0.74786 | 0.57694 | 1.30x |
| Direct checked -> unchecked, u1 | 440 | 0.29487 | 0.21697 | 1.36x |
| Direct unchecked u1 -> unchecked u4 | 440 | 0.21697 | 0.16253 | 1.33x |
| Packed -> direct, checked u1 | 440 | 1.60890 | 0.29487 | 5.46x |
| Packed -> direct, unchecked u1 | 440 | 1.51715 | 0.21697 | 6.99x |

Disassembly confirms zero remaining bounds-error paths in all six unchecked
Dart kernels, while safely guarded kernels retain their per-access checks.
Packed construction still converts four lanes to doubles and back and builds
the vector through stack stores. No successful kernel path allocates on the
heap. Direct vector kernels retain pointer/address work, a writable-buffer
check, and loop safepoints after bounds checks are removed.

The fastest measured C-native medians were 0.04345 (441) and 0.04107 (440).
The best scalar Dart kernel at hop 441 remains 13.28x slower; direct unchecked
u4 at hop 440 remains 3.96x slower. Against the fastest 128-bit-only C rows,
those gaps are 8.62x and 2.57x. C-control's physical four-byte input shift
showed no consistent penalty across paired rounds; this does not support
attributing the large Dart packed gap to hardware unaligned-load cost.

Bounds-check removal therefore has a measured, limited benefit with this
backend. Unrolling is also available in safe Dart. The larger packing gap
requires improved vector-load/packing code generation, including an unaligned
load capability for hop 441. That first measurement predates the prototype
below, so its hop-440 results alone cannot establish the unaligned load's speed.
Lean verification could
justify unchecked operations under proved contracts; this experiment verifies
neither those contracts nor a new compiler lowering. Typical Dart timing MADs
were approximately 1-4%; some C rows were noisier (up to 19%). Raw trials,
paired-round ranges, complete ratios, and measured-binary disassembly are in
the ignored `controlled-output/` directory.

## Pure-Dart unaligned vector-load prototype

`unaligned_load.dart` exposes checked and unchecked native-endian 16-byte loads
from `ByteData`, including addresses that are not divisible by 16. The timed
windowing loop, multiplication, and output stores remain Dart. There is no FFI
call and no native C windowing helper in the Dart measurement.

The installed Dart 3.11.4 VM already contains an undocumented
`_ByteDataView.getFloat32x4` method that lowers to an unaligned load. Dynamic
invocation can reach it, and AOT inlines the dispatch and cast. However, its
two byte-range checks survive the caller's no-bounds-checks pragma. The isolated
SDK patch adds two methods to `_ByteDataView`:

```dart
Float32x4 loadFloat32x4Unaligned(int byteOffset) {
  _byteDataByteOffsetCheck(this, byteOffset + 15, length);
  byteOffset = _byteDataByteOffsetCheck(this, byteOffset, length);
  return _typedData._getFloat32x4(offsetInBytes + byteOffset);
}

Float32x4 unsafeLoadFloat32x4Unaligned(int byteOffset) {
  return _typedData._getFloat32x4(offsetInBytes + byteOffset);
}
```

These are experimental SDK methods, not supported public Dart APIs. They use
native byte order. The unchecked method requires a valid backing view and
`0 <= byteOffset <= bytes.lengthInBytes - 16`. The benchmark also requires the
ByteData view to refer to the same sample buffer. Buffers stay managed by Dart;
the existing VM intrinsic handles the actual memory access.

`patch_unaligned_platform.dart` reads the installed platform kernel, clones the
original method into two new methods, omits the input checks only in the
unchecked method, and writes a **new** platform kernel. The installed SDK,
its compiler/runtime executables, and all existing SDK methods remain unchanged.
`prepare_unaligned_sdk.py` produces a reviewable `sdk-source.patch` equivalent
to the kernel transformation and a hash manifest. No complete SDK rebuild or
machine-code patch is needed.

Preparation requires `pkg/kernel` and `pkg/_fe_analyzer_shared` from the exact
installed SDK revision, plus an existing package configuration resolving their
dependencies (for this run, Flutter tools' package configuration). From the
repository root, substituting the local paths:

```powershell
python .\dart-eardea-simd-comparison\prepare_unaligned_sdk.py --dart <dart.exe> --sdk-source <matching-sdk-source> --packages <package_config.json>
python .\dart-eardea-simd-comparison\run_controlled.py --dart <dart.exe> --cc <clang.exe> --platform .\dart-eardea-simd-comparison\controlled-output-sdk\vm_platform_product_unaligned.dill --families scalar packed aligned unaligned --frames 4096 --repeats 128 --trials 7 --cpu 2 --output .\dart-eardea-simd-comparison\controlled-output-unaligned
python .\dart-eardea-simd-comparison\analyze_controlled.py .\dart-eardea-simd-comparison\controlled-output-unaligned
```

All Dart baselines in this run use the same patched platform and common call
signature. Every family has checked, guarded, and unchecked kernels, with
source unroll factors one and four. Unaligned checked/guarded kernels retain
two input byte-range checks plus Hann/output checks per vector. Unchecked
unaligned kernels use the new unchecked SDK method and remove Hann/output
bounds checks with the existing pragma. All variants retain VM interruption
and safepoint checks.

`verify_unaligned_load.dart` tests all 16 byte alignments, nonzero view offsets,
read-only views, last-valid reads, signed zero, infinities, subnormals, and NaN
payload preservation. It tests invalid ranges only through the checked method.
The runner additionally compares every window output element against scalar
Dart before timing. Its disassembly checks require inline SIMD multiplication,
no float/double lane conversions, no allocation calls, no load-helper/native/FFI
calls, and zero bounds-error paths in unchecked kernels. Inspect the generated
`dart-kernels.txt` to distinguish the remaining normal VM slow paths.

The preceding 48-configuration measurement is historical. The unaligned suite
has 60 configurations and writes separate artifacts; compare implementations
within one run because the common Dart call signature and code layout changed.
For a focused confirmation, add `--hops 441 --checks checked unchecked` and
use `--families scalar packed unaligned`. All measured variants receive the
same selected CPU affinity and priority. Above-normal priority reduces CPU
descheduling from normal-priority work; it cannot eliminate shared-cache,
memory-bandwidth, SMT-sibling, or power/frequency interference.

### Hop-441 prototype result, 2026-10-24

The full 60-configuration run passed 420 timed trials but had large scheduling
outliers. A normal-priority, hop-441 confirmation also remained noisy. The
final confirmation uses 21 configurations, seven shuffled rounds, the original
4096 frames / 128 repeats, logical CPU 2, and above-normal priority applied
equally to every benchmark child. Other CPU-heavy host workloads continued;
this is not an idle-machine measurement. Both normal-priority runs are retained.
The measured Dart kernel disassembly is identical across confirmations.

Use `controlled-output-unaligned-priority/` for this comparison. Its Dart timing
MADs are 1.8-7.2%; the native C auto-vectorized row remains noisier (22.4%).
Ryzen 7 8700F, Dart 3.11.4 AOT, Clang 23.1.4, and all compiler flags otherwise
match the controlled methodology above. Medians in ns/sample:

| Implementation | u1 | u4 |
|---|---:|---:|
| Dart scalar, checked | 1.85583 | 1.34041 |
| Dart scalar, unchecked | 1.17650 | 0.89306 |
| Dart packed, checked | 1.88505 | 1.86069 |
| Dart packed, unchecked | 1.77297 | 1.76017 |
| Dart unaligned load, checked | 0.57464 | 0.54663 |
| Dart unaligned load, unchecked | 0.43369 | 0.27906 |
| C-control SSE, no automatic unrolling | 0.11730 | 0.09433 |

The fastest optimized C row is C-128 SSE at 0.09204 ns/sample. The best Dart
prototype is 3.03x slower than that row, or 2.96x slower than C-control's
matching four-way SSE kernel. This gap remains with both sides using 128-bit
SIMD; it cannot be explained solely by C's access to wider SIMD.

Ratios of medians: the checked load alone is 3.28x faster than checked packed
u1, so a safe unaligned-load API already provides a substantial gain. Removing
bounds checks adds 1.33x for u1, and unrolling the unchecked load adds 1.55x.
Against packed code with the same unchecked/u4 controls, the prototype is
6.31x faster. From checked packed u1 to unchecked unaligned u4, the total is
6.75x. The same-round ratio for the matched unchecked/u4 comparison has median
6.42x, with an observed range of 5.08-8.06x; that range is not a confidence
interval. Unrolling the checked load alone did not show a clear improvement.

All 21 configurations passed 4,194,304 bitwise element comparisons each, and
all 147 timed checksums were exactly -255.783023190 as printed. The separate
raw-load test passed 784 loads and rejected 40 invalid checked reads. The
measured unchecked prototype kernels have zero bounds-error paths, no lane
conversions, no allocation calls, and no load-helper/native/FFI calls. The
inner loops contain direct `movups` loads, `mulps`, and vector stores. They
retain pointer/address calculations, output writability checks, and safepoints.

The result supports adding an efficient checked unaligned-load operation and
measures a further benefit from eliminating proved-redundant checks. A
Lean-verified feature could justify that latter step under an appropriate
memory/view contract. No Lean proof was implemented, and these measurements
do not establish C-equivalent performance or a full-STFT speedup. The remaining
loop-code differences require additional compiler optimization work.

The pinned source-equivalent SDK change is also retained as
`sdk_unaligned_load.patch`; the reproducible platform transformer, raw trials,
source/binary hashes, SDK hash manifest, and measured disassembly provide the
implementation and evidence. Installed SDK files and the original benchmark
CSV remain unchanged.
