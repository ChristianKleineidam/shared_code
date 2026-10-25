#!/usr/bin/env python3
"""Summarize raw trials and paired ablation ratios; reject incomplete/parity failures."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import re
import statistics


def analyze(directory):
    metadata = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    with (directory / 'raw.csv').open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    groups = defaultdict(dict)
    checksums = defaultdict(list)
    for row in rows:
        key = (row['backend'], row['mode'], int(row['hop']), int(row['input_shift']))
        trial = int(row['round'])
        if trial in groups[key]:
            raise ValueError(f'Duplicate trial: {key}, round {trial}')
        if (int(row['frames']), int(row['repeats']), int(row['trials'])) != (
                metadata['frames'], metadata['repeats'], 1):
            raise ValueError('Mixed benchmark workloads')
        ns, checksum = float(row['ns_per_sample']), float(row['checksum'])
        if not math.isfinite(ns) or ns <= 0 or not math.isfinite(checksum):
            raise ValueError('Nonfinite checksum or invalid timing')
        groups[key][trial] = ns
        checksums[key[2]].append(checksum)
    if len(groups) != metadata['preflight_configurations']:
        raise ValueError('Missing configurations')
    expected_rounds = set(range(1, metadata['trials'] + 1))
    if any(set(trials) != expected_rounds for trials in groups.values()):
        raise ValueError('Missing trial rounds')
    for hop, values in checksums.items():
        if max(values) - min(values) > 1e-6:
            raise ValueError(f'Cross-language checksum mismatch: hop {hop}, {min(values)}..{max(values)}')
    medians = {key: statistics.median(trials.values()) for key, trials in groups.items()}
    summary = []
    for key, trials in groups.items():
        backend, mode, hop, shift = key
        median = medians[key]
        reference = medians['dart', 'scalar-checked-u1', hop, 0]
        fastest = min(value for k, value in medians.items() if k[2] == hop and k[0].startswith('c-'))
        summary.append(dict(backend=backend, mode=mode, hop=hop, input_shift=shift,
                            median_ns=median, min_ns=min(trials.values()), max_ns=max(trials.values()),
                            mad_pct=100 * statistics.median(abs(v - median) for v in trials.values()) / median,
                            speedup_vs_dart_scalar=reference / median,
                            slowdown_vs_fastest_c=median / fastest))
    summary.sort(key=lambda row: (-row['hop'], row['backend'], row['mode'], row['input_shift']))
    with (directory / 'summary.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)
    contrasts = []

    def contrast(label, before, after):
        if before not in groups or after not in groups:
            return
        ratios = [groups[before][r] / groups[after][r] for r in sorted(expected_rounds)]
        contrasts.append(dict(label=label, before=before, after=after,
                              ratio_of_medians=medians[before] / medians[after],
                              paired_median_speedup=statistics.median(ratios),
                              paired_min=min(ratios), paired_max=max(ratios)))

    for hop in (441, 440):
        for family in metadata.get('dart_families', ['scalar', 'packed', 'aligned']):
            for unroll in (1, 4):
                for before in ('checked', 'guarded'):
                    contrast(f'{hop} {family} u{unroll}: {before} -> unchecked',
                             ('dart', f'{family}-{before}-u{unroll}', hop, 0),
                             ('dart', f'{family}-unchecked-u{unroll}', hop, 0))
            for check in ('checked', 'guarded', 'unchecked'):
                contrast(f'{hop} {family} {check}: u1 -> u4',
                         ('dart', f'{family}-{check}-u1', hop, 0),
                         ('dart', f'{family}-{check}-u4', hop, 0))
        for family in ('scalar', 'sse'):
            contrast(f'{hop} C controlled {family}: u1 -> u4',
                     ('c-control', f'{family}-u1', hop, 0),
                     ('c-control', f'{family}-u4', hop, 0))
        contrast(f'{hop} C controlled: scalar -> SSE',
                 ('c-control', 'scalar-u1', hop, 0), ('c-control', 'sse-u1', hop, 0))
        contrast(f'{hop} C address: 64-byte aligned -> shifted 4 bytes',
                 ('c-control', 'sse-u1', hop, 0), ('c-control', 'sse-u1', hop, 1))
    for check in ('checked', 'guarded', 'unchecked'):
        for unroll in (1, 4):
            contrast(f'440 packing {check} u{unroll}: packed -> direct',
                     ('dart', f'packed-{check}-u{unroll}', 440, 0),
                     ('dart', f'aligned-{check}-u{unroll}', 440, 0))
            for hop in (441, 440):
                contrast(f'{hop} packing {check} u{unroll}: packed -> unaligned load',
                         ('dart', f'packed-{check}-u{unroll}', hop, 0),
                         ('dart', f'unaligned-{check}-u{unroll}', hop, 0))
    codegen = {}
    text = (directory / 'dart-kernels.txt').read_text(encoding='utf-8')
    for section in re.split(r'(?m)^[0-9a-f]+ <', text)[1:]:
        name, body = section.split('>:', 1)
        if not re.match(r'^(scalar|packed|aligned|unaligned)(Checked|Guarded|Unchecked)U[14]$', name):
            continue
        codegen[name] = dict(
            range_error_calls=len(re.findall(r'call.*RangeErrorShared', body)),
            float_to_double=body.count('cvtss2sd'), double_to_float=body.count('cvtsd2ss'),
            packed_multiply=len(re.findall(r'\bmulps\b', body)),
            double_multiply=len(re.findall(r'\bmulsd\b', body)),
            allocation_calls=len(re.findall(r'call.*Allocate', body)),
            native_or_load_calls=len(re.findall(r'call.*(?:NativeCall|Ffi|FFI|Float32x4Unaligned|getFloat32x4)', body)),
            stack_poll_sites=len(re.findall(r'cmp\s+rsp, qword ptr \[r14 \+ 0x48\]', body)))
    expected_kernels = 6 * len(metadata.get('dart_codegen_families', ['scalar', 'packed', 'aligned']))
    if len(codegen) != expected_kernels:
        raise ValueError(f'Expected {expected_kernels} disassembled Dart kernels, found {len(codegen)}')
    if any(v['range_error_calls'] for k, v in codegen.items() if 'Unchecked' in k):
        raise ValueError('Unchecked pragma failed to remove bounds checks')
    if 'unaligned' in metadata.get('dart_families', []):
        for check in ('Checked', 'Guarded', 'Unchecked'):
            for unroll in (1, 4):
                metric = codegen[f'unaligned{check}U{unroll}']
                if (metric['float_to_double'] or metric['double_to_float'] or
                        metric['native_or_load_calls'] or metric['allocation_calls'] or
                        metric['packed_multiply'] != unroll):
                    raise ValueError(f'Unaligned load was not inlined as intended: {check} u{unroll}')
    result = dict(summary=summary, contrasts=contrasts, codegen=codegen,
                  checksums={str(hop): dict(min=min(v), max=max(v)) for hop, v in checksums.items()})
    (directory / 'analysis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'Validated {len(rows)} trials / {len(groups)} configurations; checksum parity OK.')
    print('hop backend/mode shift | ns/sample | MAD% | speedup vs Dart | slowdown vs fastest C')
    for row in summary:
        print(f"{row['hop']} {row['backend']}/{row['mode']} +{row['input_shift']} | "
              f"{row['median_ns']:.5f} | {row['mad_pct']:.1f} | "
              f"{row['speedup_vs_dart_scalar']:.2f}x | {row['slowdown_vs_fastest_c']:.2f}x")
    print('Paired speedups (>1 means the second variant is faster):')
    for row in contrasts:
        print(f"{row['label']}: {row['paired_median_speedup']:.2f}x "
              f"[round range {row['paired_min']:.2f}..{row['paired_max']:.2f}]")
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, nargs='?', default=Path(__file__).with_name('controlled-output'))
    args = parser.parse_args()
    analyze(args.directory)
