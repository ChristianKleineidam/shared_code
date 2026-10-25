// Reuse the original helpers and kernels without editing the baseline source.
#define main original_benchmark_main
#include "window_bench.c"
#undef main

typedef void (*window_kernel)(const float *, const float *, float *, int);

NOINLINE static void scalar_u4(const float * RESTRICT input,
    const float * RESTRICT hann, float * RESTRICT out, int offset) {
  const float *a = input + offset;
  for (int i = 0; i < WIDTH; i += 4) {
    out[i] = a[i] * hann[i];
    out[i + 1] = a[i + 1] * hann[i + 1];
    out[i + 2] = a[i + 2] * hann[i + 2];
    out[i + 3] = a[i + 3] * hann[i + 3];
  }
}

NOINLINE static void sse_u4(const float * RESTRICT input,
    const float * RESTRICT hann, float * RESTRICT out, int offset) {
  const float *a = input + offset;
  for (int i = 0; i < WIDTH; i += 16) {
    _mm_storeu_ps(out + i, _mm_mul_ps(_mm_loadu_ps(a + i), _mm_loadu_ps(hann + i)));
    _mm_storeu_ps(out + i + 4, _mm_mul_ps(_mm_loadu_ps(a + i + 4), _mm_loadu_ps(hann + i + 4)));
    _mm_storeu_ps(out + i + 8, _mm_mul_ps(_mm_loadu_ps(a + i + 8), _mm_loadu_ps(hann + i + 8)));
    _mm_storeu_ps(out + i + 12, _mm_mul_ps(_mm_loadu_ps(a + i + 12), _mm_loadu_ps(hann + i + 12)));
  }
}

static double run_controlled(window_kernel kernel, const float *input,
    const float *hann, float *out, int frames, int hop, int repeats) {
  double sum = 0;
  for (int r = 0; r < repeats; r++) {
    for (int frame = 0; frame < frames; frame++) {
      kernel(input, hann, out, frame * hop);
      sum += consume_frame(out, frame);
    }
  }
  return sum;
}

// Allocate enough padding to choose a known 64-byte boundary and phase.
static float *aligned_float_buffer(size_t count, int shift, void **allocation) {
  *allocation = malloc((count + 32) * sizeof(float));
  if (!*allocation) return NULL;
  uintptr_t address = ((uintptr_t)*allocation + 63) & ~(uintptr_t)63;
  return (float *)address + shift;
}

int main(int argc, char **argv) {
  const char *mode = option_string(argc, argv, "--mode", "scalar-u1");
  const char *backend = option_string(argc, argv, "--backend", "c-control");
  const char *verify = option_string(argc, argv, "--verify", "full");
  int frames = option_int(argc, argv, "--frames", 4096);
  int hop = option_int(argc, argv, "--hop", 441);
  int repeats = option_int(argc, argv, "--repeats", 128);
  int shift = option_int(argc, argv, "--input-shift", 0);
  window_kernel kernel = NULL;
  if (strcmp(mode, "scalar-u1") == 0) kernel = scalar_window;
  if (strcmp(mode, "scalar-u4") == 0) kernel = scalar_u4;
  if (strcmp(mode, "sse-u1") == 0) kernel = sse_window;
  if (strcmp(mode, "sse-u4") == 0) kernel = sse_u4;
  if (!kernel || frames < 1 || hop < 1 || repeats < 1 || shift < 0 || shift > 15 ||
      frames > (INT32_MAX - WIDTH) / hop ||
      (strcmp(verify, "full") != 0 && strcmp(verify, "checksum") != 0)) return 2;
  size_t count = (size_t)(frames - 1) * hop + WIDTH;
  void *input_allocation, *hann_allocation, *out_allocation;
  float *input = aligned_float_buffer(count, shift, &input_allocation);
  float *hann = aligned_float_buffer(WIDTH, 0, &hann_allocation);
  float *out = aligned_float_buffer(WIDTH, 0, &out_allocation);
  if (!input || !hann || !out) return 2;
  for (size_t i = 0; i < count; i++)
    input[i] = (float)(((int)(i * 73 % 4096) - 2048) / 2048.0);
  for (int i = 0; i < WIDTH; i++)
    hann[i] = (float)(0.5 - 0.5 * cos(2.0 * 3.14159265358979323846 * i / (WIDTH - 1)));
  if (strcmp(verify, "full") == 0) {
    float reference[WIDTH];
    for (int frame = 0; frame < frames; frame++) {
      scalar_window(input, hann, reference, frame * hop);
      kernel(input, hann, out, frame * hop);
      if (memcmp(reference, out, sizeof(reference)) != 0) {
        fprintf(stderr, "Element mismatch: %s frame=%d\n", mode, frame);
        return 2;
      }
    }
  }
  for (int i = 1; i < argc; i++) {
    if (strcmp(argv[i], "--verify-only") == 0) {
      if (strcmp(verify, "full") != 0) return 2;
      printf("Verified %s hop=%d shift=%d: %zu float32 outputs bitwise\n",
          mode, hop, shift, (size_t)frames * WIDTH);
      free(input_allocation); free(hann_allocation); free(out_allocation);
      return 0;
    }
  }
  double reference = run_controlled(scalar_window, input, hann, out, frames, hop, 1);
  double candidate = run_controlled(kernel, input, hann, out, frames, hop, 1);
  if (!isfinite(candidate) || fabs(reference - candidate) > frames * 1e-6) return 2;
  run_controlled(kernel, input, hann, out, frames, hop, 2);
  double start = seconds_now();
  double checksum = run_controlled(kernel, input, hann, out, frames, hop, repeats);
  double seconds = seconds_now() - start;
  printf("%s,%s,%d,%d,%d,1,%.9f,%.8f,%.9f\n", backend, mode, hop,
      frames, repeats, seconds, seconds * 1e9 / ((double)frames * repeats * WIDTH), checksum);
  free(input_allocation); free(hann_allocation); free(out_allocation);
  return 0;
}
