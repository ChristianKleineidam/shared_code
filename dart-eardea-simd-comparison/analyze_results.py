#!/usr/bin/env python3
"""Summarize like-for-like hop measurements and basic checksum parity."""
import csv
from pathlib import Path

rows = []
with (Path(__file__).parent / 'results.csv').open(newline='', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        row['hop'] = int(row['hop'])
        row['ns_per_sample'] = float(row['ns_per_sample'])
        row['checksum'] = float(row['checksum'])
        rows.append(row)
for hop in sorted({r['hop'] for r in rows}, reverse=True):
    group = [r for r in rows if r['hop'] == hop]
    native_scalar = next((r for r in group if r['backend'] == 'c-native' and r['mode'] == 'scalar'), None)
    baseline = native_scalar or next(r for r in group if r['backend'].startswith('c') and r['mode'] == 'scalar')
    reference_checksum = baseline['checksum']
    print(f'\nHop {hop}: C baseline {baseline["backend"]}/{baseline["mode"]} = {baseline["ns_per_sample"]:.4f} ns/sample')
    print(f'{"Backend/mode":28} {"ns/sample":>12} {"time vs C":>12} {"checksum":>16} {"parity":>8}')
    for r in sorted(group, key=lambda r: r['ns_per_sample']):
        delta = abs(r['checksum'] - reference_checksum)
        tolerance = max(0.02, abs(reference_checksum) * 1e-4)
        parity = 'OK' if delta <= tolerance else 'CHECK'
        ratio = r['ns_per_sample'] / baseline['ns_per_sample']
        print(f'{r["backend"] + "/" + r["mode"]:28} {r["ns_per_sample"]:12.4f} {ratio:11.2f}x {r["checksum"]:16.5f} {parity:>8}')
print('\nRatios are relative to C native scalar on the same host/hop. Lower is faster.')
print('This is a windowing kernel benchmark, NOT a complete FFT or proof-verified implementation.')
