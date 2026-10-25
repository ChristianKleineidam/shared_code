// Diagnostic kernels, not Lean-verified code. Only the unchecked kernels carry
// no-bounds-checks. Interrupt/safepoint checks remain enabled in every variant.
import 'dart:math' as math;
import 'dart:typed_data';
import 'window_bench.dart' as baseline;
import 'unaligned_load.dart';

part 'controlled_kernels.g.dart';

const width = baseline.width;
typedef WindowKernel = void Function(
    Float32List, Float32List, Float32List,
    Float32x4List, Float32x4List, Float32x4List, int, ByteData);

double runControlled(WindowKernel kernel, Float32List samples, Float32List hann,
    Float32List output, Float32x4List inputVectors, Float32x4List hannVectors,
    Float32x4List outputVectors, ByteData sampleBytes, int frames, int hop, int repeats) {
  var sum = 0.0;
  for (var repeat = 0; repeat < repeats; repeat++) {
    for (var frame = 0; frame < frames; frame++) {
      kernel(samples, hann, output, inputVectors, hannVectors, outputVectors,
          frame * hop, sampleBytes);
      sum += baseline.consumeFrame(output, frame);
    }
  }
  return sum;
}

void main(List<String> args) {
  final mode = baseline.optionString(args, 'mode', 'scalar-checked-u1');
  final frames = baseline.optionInt(args, 'frames', 4096);
  final hop = baseline.optionInt(args, 'hop', 441);
  final repeats = baseline.optionInt(args, 'repeats', 128);
  final verify = baseline.optionString(args, 'verify', 'full');
  final kernel = controlledKernels[mode];
  if (kernel == null || frames < 1 || hop < 1 || repeats < 1 ||
      !['full', 'checksum'].contains(verify) ||
      (mode.startsWith('aligned-') && hop % 4 != 0)) {
    throw ArgumentError('Invalid controlled benchmark arguments');
  }
  // Check the complete accessed range once before invoking unchecked code.
  final count = (frames - 1) * hop + width;
  final samples = Float32List(count);
  final hann = Float32List(width);
  final output = Float32List(width);
  for (var i = 0; i < count; i++) {
    samples[i] = ((i * 73) % 4096 - 2048) / 2048.0;
  }
  for (var i = 0; i < width; i++) {
    hann[i] = 0.5 - 0.5 * math.cos(2.0 * math.pi * i / (width - 1));
  }
  if ((frames - 1) * hop > samples.length - width ||
      hann.length != width || output.length != width) {
    throw StateError('Invalid buffer layout');
  }
  final inputVectors = Float32x4List.view(samples.buffer, 0, count ~/ 4);
  final hannVectors = Float32x4List.view(hann.buffer);
  final outputVectors = Float32x4List.view(output.buffer);
  final sampleBytes = ByteData.view(samples.buffer, samples.offsetInBytes, samples.lengthInBytes);
  if (verify == 'full') {
    final reference = Float32List(width);
    final actualBits = Uint32List.view(output.buffer);
    final referenceBits = Uint32List.view(reference.buffer);
    for (var frame = 0; frame < frames; frame++) {
      baseline.scalarWindow(samples, hann, reference, frame * hop);
      kernel(samples, hann, output, inputVectors, hannVectors, outputVectors,
          frame * hop, sampleBytes);
      for (var i = 0; i < width; i++) {
        if (actualBits[i] != referenceBits[i]) {
          throw StateError('Element mismatch: $mode frame=$frame sample=$i');
        }
      }
    }
  }
  if (args.contains('--verify-only')) {
    if (verify != 'full') throw ArgumentError('verify-only requires full validation');
    print('Verified $mode hop=$hop: ${frames * width} float32 outputs bitwise');
    return;
  }
  final reference = runControlled(scalarCheckedU1, samples, hann, output,
      inputVectors, hannVectors, outputVectors, sampleBytes, frames, hop, 1);
  final candidate = runControlled(kernel, samples, hann, output,
      inputVectors, hannVectors, outputVectors, sampleBytes, frames, hop, 1);
  if (!candidate.isFinite || (reference - candidate).abs() > frames * 1e-6) {
    throw StateError('Checksum mismatch: $mode $candidate vs $reference');
  }
  runControlled(kernel, samples, hann, output, inputVectors,
      hannVectors, outputVectors, sampleBytes, frames, hop, 2);
  final timer = Stopwatch()..start();
  final checksum = runControlled(kernel, samples, hann, output, inputVectors,
      hannVectors, outputVectors, sampleBytes, frames, hop, repeats);
  timer.stop();
  final seconds = timer.elapsedMicroseconds / 1e6;
  final ns = seconds * 1e9 / (frames * repeats * width);
  print('dart,$mode,$hop,$frames,$repeats,1,'
      '${seconds.toStringAsFixed(9)},${ns.toStringAsFixed(8)},'
      '${checksum.toStringAsFixed(9)}');
}
