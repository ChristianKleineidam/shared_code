// Standalone benchmark of a kernel from an STFT preprocessing workload.
// Compare release AOT Dart vs the same algorithm in optimized C/SSE2.
// Run via: dart compile exe window_bench.dart -o window_bench_dart
import 'dart:math' as math;
import 'dart:typed_data';

const int width = 1024;

int optionInt(List<String> args, String name, int fallback) {
  final prefix = '--$name=';
  for (final arg in args) {
    if (arg.startsWith(prefix)) return int.parse(arg.substring(prefix.length));
  }
  return fallback;
}

String optionString(List<String> args, String name, String fallback) {
  final prefix = '--$name=';
  for (final arg in args) {
    if (arg.startsWith(prefix)) return arg.substring(prefix.length);
  }
  return fallback;
}

// Scalar Dart version of one STFT-window multiply.
@pragma('vm:never-inline')
void scalarWindow(Float32List samples, Float32List hann, Float32List result,
    int offset) {
  for (var i = 0; i < width; ++i) {
    result[i] = samples[offset + i] * hann[i];
  }
}

// Safe Dart SIMD, but gathers samples as four scalar lanes because the frame's
// starting offset is not necessarily a multiple of 16 bytes.
@pragma('vm:never-inline')
void packedWindow(Float32List samples, Float32x4List hannVectors,
    Float32x4List resultVectors, int offset) {
  for (var j = 0; j < width ~/ 4; ++j) {
    final i = offset + j * 4;
    final sampleVector = Float32x4(
      samples[i], samples[i + 1], samples[i + 2], samples[i + 3]);
    resultVectors[j] = sampleVector * hannVectors[j];
  }
}

// Safe aligned loads using a vector view, which can only be used when the
// window's offset is a multiple of 4 float32 elements.
@pragma('vm:never-inline')
void alignedWindow(Float32x4List samplesVectors, Float32x4List hannVectors,
    Float32x4List resultVectors, int offset) {
  final base = offset ~/ 4;
  for (var j = 0; j < width ~/ 4; ++j) {
    resultVectors[j] = samplesVectors[base + j] * hannVectors[j];
  }
}

// Explicitly call across a no-inline boundary to keep all frame output stores
// observable to the optimizer, without timing full-spectrum analysis.
@pragma('vm:never-inline')
double consumeFrame(Float32List result, int frame) {
  final a = (frame * 13) & (width - 1);
  return result[a] +
      result[(a + 341) & (width - 1)] +
      result[(a + 682) & (width - 1)];
}

double runFrames(String mode, Float32List samples, Float32List hann,
    Float32List output, Float32x4List inputVectors,
    Float32x4List hannVectors, Float32x4List outputVectors, int frames, int hop,
    int repeats) {
  var sum = 0.0;
  for (var r = 0; r < repeats; ++r) {
    for (var frame = 0; frame < frames; ++frame) {
      final offset = frame * hop;
      if (mode == 'scalar') {
        scalarWindow(samples, hann, output, offset);
      } else if (mode == 'packed') {
        packedWindow(samples, hannVectors, outputVectors, offset);
      } else if (mode == 'aligned') {
        alignedWindow(inputVectors, hannVectors, outputVectors, offset);
      } else {
        throw ArgumentError('Unknown mode: $mode');
      }
      sum += consumeFrame(output, frame);
    }
  }
  return sum;
}

void main(List<String> args) {
  final mode = optionString(args, 'mode', 'scalar');
  final frames = optionInt(args, 'frames', 4096);
  final hop = optionInt(args, 'hop', 441);
  final repeats = optionInt(args, 'repeats', 32);
  final trials = optionInt(args, 'trials', 5);
  if (!['scalar', 'packed', 'aligned'].contains(mode) ||
      frames < 1 || hop < 1 || repeats < 1 || trials < 1 ||
      (mode == 'aligned' && hop % 4 != 0)) {
    throw ArgumentError('Invalid arguments or aligned mode on unaligned hop');
  }

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
  final inputVectors = Float32x4List.view(
      samples.buffer, samples.offsetInBytes, samples.length ~/ 4);
  final hannVectors = Float32x4List.view(
      hann.buffer, hann.offsetInBytes, width ~/ 4);
  final outputVectors = Float32x4List.view(
      output.buffer, output.offsetInBytes, width ~/ 4);

  // Verify SIMD path against the ordinary Dart implementation before timing.
  final reference = runFrames('scalar', samples, hann, output, inputVectors,
      hannVectors, outputVectors, frames, hop, 1);
  final candidate = runFrames(mode, samples, hann, output, inputVectors,
      hannVectors, outputVectors, frames, hop, 1);
  if ((reference - candidate).abs() > frames * 1e-6) {
    throw StateError('Checksum mismatch: $mode $candidate vs $reference');
  }

  // Warm up the kernel even for JIT runs. AOT is the intended comparison.
  runFrames(mode, samples, hann, output, inputVectors, hannVectors,
      outputVectors, frames, hop, 2);

  final times = <double>[];
  var checksum = 0.0;
  for (var trial = 0; trial < trials; trial++) {
    final sw = Stopwatch()..start();
    checksum = runFrames(mode, samples, hann, output, inputVectors,
        hannVectors, outputVectors, frames, hop, repeats);
    sw.stop();
    times.add(sw.elapsedMicroseconds / 1e6);
  }
  times.sort();
  final seconds = times[times.length ~/ 2];
  final nsPerElement = seconds * 1e9 / (frames * repeats * width);
  print('dart,$mode,$hop,$frames,$repeats,$trials,'
      '${seconds.toStringAsFixed(9)},'
      '${nsPerElement.toStringAsFixed(5)},'
      '${checksum.toStringAsFixed(6)}');
}
