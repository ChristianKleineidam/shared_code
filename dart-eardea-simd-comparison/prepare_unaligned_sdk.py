#!/usr/bin/env python3
"""Patch a separate SDK platform kernel, preserving all installed SDK files."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dart', type=Path, required=True)
    parser.add_argument('--sdk-source', type=Path, required=True,
                        help='Exact installed SDK revision; pkg/kernel and pkg/_fe_analyzer_shared required')
    parser.add_argument('--packages', type=Path, required=True,
                        help='Existing package_config.json resolving meta/source_span and their dependencies')
    parser.add_argument('--output', type=Path, default=ROOT / 'controlled-output-sdk')
    args = parser.parse_args()
    sdk = args.dart.resolve().parent.parent
    platform = sdk / 'lib/_internal/vm_platform_product.dill'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    patched = output / 'vm_platform_product_unaligned.dill'
    if patched.exists():
        parser.error('Patched platform already exists; choose another --output directory')
    original_hash = sha256(platform)
    config_file = args.packages.resolve()
    config = json.loads(config_file.read_text(encoding='utf-8'))
    packages = {p['name']: dict(p, rootUri=urljoin(config_file.as_uri(), p['rootUri']))
                for p in config['packages']}
    for name in ('kernel', '_fe_analyzer_shared'):
        source = args.sdk_source.resolve() / 'pkg' / name
        if not (source / 'lib').is_dir():
            parser.error(f'Missing SDK source package {source}')
        packages[name] = dict(name=name, rootUri=source.as_uri() + '/',
                              packageUri='lib/', languageVersion='3.6')
    package_config = output / 'package_config.json'
    package_config.write_text(json.dumps(dict(configVersion=2, packages=list(packages.values())),
                                        indent=2), encoding='utf-8')
    command = [str(args.dart.resolve()), f'--packages={package_config}',
               str(ROOT / 'patch_unaligned_platform.dart'), str(platform), str(patched)]
    subprocess.run(command, check=True, cwd=ROOT)
    assert sha256(platform) == original_hash, 'Installed platform unexpectedly changed'
    source_file = sdk / 'lib/_internal/vm/lib/typed_data_patch.dart'
    original = source_file.read_text(encoding='utf-8')
    anchor = '  Float32x4 getFloat32x4(int byteOffset, [Endian endian = Endian.big]) {'
    start = original.index(anchor)
    end = original.index('\n  void setFloat32x4(', start)
    addition = '''
  // Prototype only: 16 bytes in native endian; byte alignment is unrestricted.
  Float32x4 loadFloat32x4Unaligned(int byteOffset) {
    _byteDataByteOffsetCheck(this, byteOffset + 15, length);
    byteOffset = _byteDataByteOffsetCheck(this, byteOffset, length);
    return _typedData._getFloat32x4(offsetInBytes + byteOffset);
  }

  // Requires 0 <= byteOffset <= lengthInBytes - 16 and valid backing storage.
  Float32x4 unsafeLoadFloat32x4Unaligned(int byteOffset) {
    return _typedData._getFloat32x4(offsetInBytes + byteOffset);
  }
'''
    modified = original[:end] + addition + original[end:]
    diff = ''.join(difflib.unified_diff(original.splitlines(True), modified.splitlines(True),
                                      fromfile='a/runtime/lib/typed_data_patch.dart',
                                      tofile='b/runtime/lib/typed_data_patch.dart'))
    (output / 'sdk-source.patch').write_text(diff, encoding='utf-8')
    metadata = dict(sdk_revision=(sdk / 'revision').read_text().strip(),
                    original_platform=str(platform), original_sha256=original_hash,
                    patched_platform=str(patched), patched_sha256=sha256(patched),
                    kernel_source=str(args.sdk_source.resolve()),
                    transformer_sha256=sha256(ROOT / 'patch_unaligned_platform.dart'),
                    implementation='Added two SDK Dart methods in the platform kernel; VM/compiler binaries unchanged',
                    contract='Native endian; checked method validates both endpoints of 16-byte read; unchecked caller proves range')
    (output / 'sdk-patch-metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
