#!/usr/bin/env python3
"""Build and run shuffled, paired Windows/x64 AOT and C ablations."""
import argparse
import csv
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timezone
from generate_controlled_kernels import FAMILIES

ROOT = Path(__file__).resolve().parent
FIELDS = ('backend', 'mode', 'hop', 'frames', 'repeats', 'trials',
          'median_seconds', 'ns_per_sample', 'checksum')


def command(args, **kwargs):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {args}\n'
                           f'{result.stdout}\n{result.stderr}')
    return result.stdout + result.stderr


def pin_cpu(cpu):
    if cpu < 0:
        return None
    mask = 1 << cpu
    if os.name == 'nt':
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        kernel32.SetProcessAffinityMask.restype = ctypes.c_int
        if not kernel32.SetProcessAffinityMask(kernel32.GetCurrentProcess(), mask):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.sched_setaffinity(0, {cpu})
    # Children inherit this process's affinity. No system-wide setting changes.
    return mask


def extract_dart_codegen(binary, output, objdump):
    data = binary.read_bytes()
    candidates = []
    offset = 0
    while (offset := data.find(b'\x7fELF', offset)) >= 0:
        if data[offset + 4:offset + 6] == b'\x02\x01' and len(data) >= offset + 64:
            kind, machine = struct.unpack_from('<HH', data, offset + 16)
            if kind == 3 and machine == 62:
                candidates.append(offset)
        offset += 4
    if len(candidates) != 1:
        raise RuntimeError(f'Expected one x64 ELF snapshot, found {candidates}')
    snapshot = output / 'dart-snapshot.elf'
    snapshot.write_bytes(data[candidates[0]:])
    names = [f'{family}{check.title()}U{unroll}'
             for family in FAMILIES
             for check in ('checked', 'guarded', 'unchecked') for unroll in (1, 4)]
    names += ['runControlled', 'consumeFrame']
    disassembly = command([objdump, '-d', '--x86-asm-syntax=intel',
                           '--disassemble-symbols=' + ','.join(names), snapshot])
    (output / 'dart-kernels.txt').write_text(disassembly, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dart', default=shutil.which('dart'))
    parser.add_argument('--cc', default=shutil.which('clang') or shutil.which('gcc'))
    parser.add_argument('--frames', type=int, default=4096)
    parser.add_argument('--repeats', type=int, default=128)
    parser.add_argument('--trials', type=int, default=7)
    parser.add_argument('--cpu', type=int, default=2, help='Logical CPU; -1 leaves affinity unchanged')
    parser.add_argument('--priority', choices=['normal', 'above-normal'], default='normal',
                        help='Windows benchmark-child priority; does not change other processes')
    parser.add_argument('--seed', type=int, default=20261024)
    parser.add_argument('--families', nargs='+', choices=FAMILIES, default=['scalar', 'packed', 'aligned'])
    parser.add_argument('--hops', nargs='+', type=int, default=[441, 440])
    parser.add_argument('--checks', nargs='+', choices=['checked', 'guarded', 'unchecked'],
                        default=['checked', 'guarded', 'unchecked'])
    parser.add_argument('--platform', type=Path, help='Isolated patched platform for unaligned kernels')
    parser.add_argument('--output', type=Path, default=ROOT / 'controlled-output')
    args = parser.parse_args()
    if not args.dart or not args.cc:
        parser.error('Dart and Clang/GCC are required; use --dart and --cc')
    if args.priority != 'normal' and os.name != 'nt':
        parser.error('The above-normal child-priority control requires Windows')
    if min(args.frames, args.repeats, args.trials) < 1:
        parser.error('frames, repeats and trials must be positive')
    if 'unaligned' in args.families and (not args.platform or not args.platform.is_file()):
        parser.error('Unaligned kernels require --platform pointing to the prepared SDK platform')
    if len(args.families) != len(set(args.families)) or 'scalar' not in args.families:
        parser.error('Use unique families and include scalar as the ratio reference')
    if (not all(hop > 0 for hop in args.hops) or len(args.hops) != len(set(args.hops)) or
            len(args.checks) != len(set(args.checks)) or 'checked' not in args.checks):
        parser.error('Use unique positive hops and unique check modes including checked')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'raw.csv').exists():
        parser.error(f'{output}/raw.csv already exists; choose a new --output directory')
    command([sys.executable, ROOT / 'generate_controlled_kernels.py', '--check'])
    suffix = '.exe' if os.name == 'nt' else ''
    dart_binary = output / ('controlled_dart' + suffix)
    clang = 'clang' in command([args.cc, '--version']).lower()
    disable = ['-fno-vectorize', '-fno-slp-vectorize', '-fno-unroll-loops'] if clang else [
        '-fno-tree-loop-vectorize', '-fno-tree-slp-vectorize', '-fno-unroll-loops']
    common = ['-O3', '-ffp-contract=off']
    flags = {
        'c-control': common + ['-march=x86-64-v2'] + disable,
        'c-128': common + ['-march=x86-64-v2'],
        'c-native': common + ['-march=native'],
    }
    metadata = {
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'commit': command(['git', 'rev-parse', 'HEAD']).strip(),
        'dart_version': command([args.dart, '--version']).strip(),
        'compiler_version': command([args.cc, '--version']).strip(),
        'python_version': sys.version,
        'cpu_identifier': os.environ.get('PROCESSOR_IDENTIFIER'),
        'logical_cpu': args.cpu, 'affinity_mask': None,
        'benchmark_priority': args.priority,
        'frames': args.frames, 'repeats': args.repeats, 'trials': args.trials,
        'seed': args.seed, 'c_flags': flags,
        'dart_families': args.families, 'dart_codegen_families': list(FAMILIES),
        'hops': args.hops, 'check_modes': args.checks,
        'platform': str(args.platform.resolve()) if args.platform else None,
        'platform_sha256': hashlib.sha256(args.platform.read_bytes()).hexdigest() if args.platform else None,
        'dart_command': [args.dart, 'compile', 'exe', 'controlled_bench.dart'],
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in ROOT.iterdir() if p.suffix in ('.dart', '.c', '.py')},
        'notes': ['Same function-call and consumeFrame boundary across each language.',
                  'Only kernels are unchecked; safepoint checks remain enabled.',
                  'Full per-element bitwise preflight for every configuration.',
                  'Each round runs every configuration once in shuffled order.',
                  'C input/hann/output base addresses aligned to 64 bytes; shift changes only input address.',
                  'Dart packed/aligned comparisons use identical data and hop=440.'],
    }
    if os.name == 'nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            metadata['cpu'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
        metadata['windows_version'] = str(sys.getwindowsversion())
    print('Building controlled variants...', flush=True)
    platform_options = [f'--extra-gen-kernel-options=--platform={args.platform.resolve()}'] if args.platform else []
    metadata['dart_command'] = [str(v) for v in [args.dart, 'compile', 'exe', ROOT / 'controlled_bench.dart',
                                                '-o', dart_binary, *platform_options]]
    build_log = command(metadata['dart_command'])
    if 'unaligned' in args.families:
        validation_binary = output / ('verify_unaligned_load' + suffix)
        build_log += command([args.dart, 'compile', 'exe', ROOT / 'verify_unaligned_load.dart',
                              '-o', validation_binary, *platform_options])
        validation_result = command([validation_binary])
        (output / 'unaligned-load-verification.txt').write_text(validation_result, encoding='utf-8')
        print(validation_result.strip(), flush=True)
    binaries = {'dart': dart_binary}
    for backend, target_flags in flags.items():
        binary = output / (backend + suffix)
        build_log += command([args.cc, *target_flags, ROOT / 'controlled_bench.c',
                              *([] if os.name == 'nt' else ['-lm']), '-o', binary])
        binaries[backend] = binary
        command([args.cc, *target_flags, '-S', '-masm=intel', ROOT / 'controlled_bench.c',
                 '-o', output / (backend + '.s')])
    (output / 'build.txt').write_text(build_log, encoding='utf-8')
    metadata['binary_sha256'] = {k: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for k, p in binaries.items()}
    objdump = Path(args.cc).resolve().parent / ('llvm-objdump' + suffix)
    if objdump.exists():
        extract_dart_codegen(dart_binary, output, objdump)
        for backend in flags:
            disassembly = command([objdump, '-d', '--x86-asm-syntax=intel',
                                   '--disassemble-symbols=scalar_window,scalar_u4,sse_window,sse_u4,run_controlled',
                                   binaries[backend]])
            (output / (backend + '-kernels.txt')).write_text(disassembly, encoding='utf-8')
    else:
        raise RuntimeError('llvm-objdump is required to verify the generated ablations')
    specs = []
    for hop in args.hops:
        for family in args.families:
            if family == 'aligned' and hop % 4:
                continue
            for check in args.checks:
                for unroll in (1, 4):
                    specs.append(('dart', f'{family}-{check}-u{unroll}', hop, 0))
        for mode in ('scalar-u1', 'scalar-u4', 'sse-u1', 'sse-u4'):
            specs.append(('c-control', mode, hop, 0))
        specs.append(('c-control', 'sse-u1', hop, 1))
        for backend in ('c-128', 'c-native'):
            for mode in ('scalar-u1', 'sse-u1'):
                specs.append((backend, mode, hop, 0))

    def invocation(spec):
        backend, mode, hop, shift = spec
        return [binaries[backend], f'--backend={backend}', f'--mode={mode}',
                f'--hop={hop}', f'--frames={args.frames}', f'--repeats={args.repeats}',
                f'--input-shift={shift}']

    child_options = {'creationflags': subprocess.ABOVE_NORMAL_PRIORITY_CLASS} if args.priority == 'above-normal' else {}
    metadata['affinity_mask'] = pin_cpu(args.cpu)
    preflight = []
    print(f'Verifying {len(specs)} configurations on logical CPU {args.cpu}...', flush=True)
    for spec in specs:
        result = command([*invocation(spec), '--verify=full', '--verify-only'], **child_options).strip()
        preflight.append(f'{spec}: {result}')
    (output / 'verification.txt').write_text('\n'.join(preflight) + '\n', encoding='utf-8')
    metadata['preflight_configurations'] = len(specs)
    metadata['outputs_checked_per_configuration'] = args.frames * 1024
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    rng = random.Random(args.seed)
    with (output / 'raw.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['round', 'order', 'input_shift', *FIELDS])
        writer.writeheader()
        for trial in range(1, args.trials + 1):
            schedule = specs.copy()
            rng.shuffle(schedule)
            for order, spec in enumerate(schedule, 1):
                result = command([*invocation(spec), '--verify=checksum'], **child_options).strip()
                records = list(csv.DictReader([','.join(FIELDS), result]))
                if len(records) != 1:
                    raise RuntimeError(f'Unexpected benchmark output: {result}')
                row = records[0]
                backend, mode, hop, shift = spec
                if (row['backend'], row['mode'], int(row['hop'])) != (backend, mode, hop):
                    raise RuntimeError(f'Wrong configuration returned: {result}')
                if not all(math.isfinite(float(row[key])) for key in
                           ('median_seconds', 'ns_per_sample', 'checksum')) or float(row['ns_per_sample']) <= 0:
                    raise RuntimeError(f'Invalid measurement: {result}')
                writer.writerow({'round': trial, 'order': order, 'input_shift': shift, **row})
                handle.flush()
            print(f'Round {trial}/{args.trials} complete ({len(specs)} configurations).', flush=True)
    print(command([sys.executable, ROOT / 'analyze_controlled.py', output]), flush=True)


if __name__ == '__main__':
    main()
