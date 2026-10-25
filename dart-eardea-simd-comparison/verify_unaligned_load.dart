// Validate raw load semantics independently of Hann-window multiplication.
import 'dart:typed_data';
import 'unaligned_load.dart';

void main() {
  final patterns = <List<int>>[
    [0, 0x80000000, 0x3f800000, 0x7f800000],
    [0xff800000, 0x7fc12345, 0x00000001, 0x7f7fffff],
    [0x7fa12345, 0x807fffff, 0xbf800000, 0x00800000],
  ];
  final vector = Float32x4List(1);
  final bits = Uint32List.view(vector.buffer);
  var loads = 0;
  var rejected = 0;
  for (final base in [0, 1, 7, 16]) {
    final storage = Uint8List(128);
    final writable = ByteData.view(storage.buffer, base, 80);
    for (final readOnly in [false, true]) {
      final bytes = readOnly ? writable.asUnmodifiableView() : writable;
      for (var phase = 0; phase < 16; phase++) {
        for (final pattern in patterns) {
          for (var lane = 0; lane < 4; lane++) {
            writable.setUint32(phase + lane * 4, pattern[lane], Endian.host);
          }
          for (final unchecked in [false, true]) {
            vector[0] = unchecked
                ? loadUnalignedUnchecked(bytes, phase)
                : loadUnalignedChecked(bytes, phase);
            for (var lane = 0; lane < 4; lane++) {
              if (bits[lane] != pattern[lane]) {
                throw StateError('Bit mismatch: base=$base phase=$phase lane=$lane unchecked=$unchecked');
              }
            }
            loads++;
          }
        }
      }
      // Last valid 16-byte span must succeed in both versions.
      vector[0] = loadUnalignedChecked(bytes, bytes.lengthInBytes - 16);
      vector[0] = loadUnalignedUnchecked(bytes, bytes.lengthInBytes - 16);
      loads += 2;
      // Invalid addresses are tested only through the checked interface.
      for (final offset in [-17, -1, bytes.lengthInBytes - 15,
                           bytes.lengthInBytes, 1 << 62]) {
        try {
          vector[0] = loadUnalignedChecked(bytes, offset);
        } on RangeError {
          rejected++;
          continue;
        }
        throw StateError('Invalid byte offset accepted: $offset');
      }
    }
  }
  print('PASS: $loads vector loads; all byte phases, nonzero view offsets, '
      'read-only views, NaN payloads, infinities, subnormals, and signed zero.');
  print('PASS: $rejected invalid checked reads rejected.');
}
