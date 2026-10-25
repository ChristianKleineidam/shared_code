# Local C-only results (not a Dart speed comparison)

The container used to assemble this benchmark had GCC 14.2.0 and an AMD EPYC
9V74 x86_64 CPU. It did not have a Dart compiler, so **there are no Dart
measurements** here. Values are from 4,096 overlapping frames, 1,024 float32
samples per frame, 128 repeats, and 7 trials (reported median).

| Hop | C target | C algorithm | ns/output sample |
|---:|---|---|---:|
| 441 | `-march=x86-64-v2` | scalar (auto-vectorized) | 0.09339 |
| 441 | `-march=x86-64-v2` | explicit SSE (`_mm_loadu_ps`) | 0.09279 |
| 441 | `-march=native` | scalar (auto-vectorized) | 0.06547 |
| 441 | `-march=native` | explicit SSE (`_mm_loadu_ps`) | 0.09792 |
| 440 | `-march=x86-64-v2` | scalar (auto-vectorized) | 0.09054 |
| 440 | `-march=x86-64-v2` | explicit SSE (`_mm_loadu_ps`) | 0.08395 |
| 440 | `-march=native` | scalar (auto-vectorized) | 0.06703 |
| 440 | `-march=native` | explicit SSE (`_mm_loadu_ps`) | 0.08361 |

The native scalar C build was the fastest here because GCC used wider SIMD
(AVX-512 was available). The explicitly written SSE code restricted itself to
128-bit registers. This example demonstrates **why we cannot assume writing
lower-level C intrinsics automatically makes code faster**. It does not yet
show a Dart/C gap or a performance benefit from a hypothetical Dart feature.

The live runner overwrites `results.csv` with measurements from your own host.
