// Standalone C comparison for the same STFT windowing kernel.
// Compile x86_64: clang -O3 -march=native -ffp-contract=off window_bench.c -lm -o window_bench_c
// SSE2 intrinsics are mandatory on x86_64; _mm_loadu_ps handles unaligned frames.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(_WIN32)
#  include <windows.h>
#endif
#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
#  define HAS_SSE 1
#  include <xmmintrin.h>
#else
#  define HAS_SSE 0
#endif
#if defined(_MSC_VER)
#  define NOINLINE __declspec(noinline)
#  define RESTRICT __restrict
#else
#  define NOINLINE __attribute__((noinline))
#  define RESTRICT restrict
#endif

#define WIDTH 1024

static int option_int(int argc, char **argv, const char *key, int fallback) {
  size_t n = strlen(key);
  for (int i = 1; i < argc; i++) {
    if (strncmp(argv[i], key, n) == 0 && argv[i][n] == '=') {
      return atoi(argv[i] + n + 1);
    }
  }
  return fallback;
}
static const char *option_string(int argc, char **argv, const char *key, const char *fallback) {
  size_t n = strlen(key);
  for (int i = 1; i < argc; i++) {
    if (strncmp(argv[i], key, n) == 0 && argv[i][n] == '=') {
      return argv[i] + n + 1;
    }
  }
  return fallback;
}
static double seconds_now(void) {
#if defined(_WIN32)
  LARGE_INTEGER freq, count;
  QueryPerformanceFrequency(&freq);
  QueryPerformanceCounter(&count);
  return (double)count.QuadPart / (double)freq.QuadPart;
#else
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (double)ts.tv_sec + ts.tv_nsec * 1e-9;
#endif
}

NOINLINE static void scalar_window(const float * RESTRICT input,
                                   const float * RESTRICT hann,
                                   float * RESTRICT out, int offset) {
  const float * RESTRICT a = input + offset;
  for (int i = 0; i < WIDTH; i++) out[i] = a[i] * hann[i];
}

#if HAS_SSE
NOINLINE static void sse_window(const float * RESTRICT input,
                                const float * RESTRICT hann,
                                float * RESTRICT out, int offset) {
  const float * RESTRICT a = input + offset;
  for (int i = 0; i < WIDTH; i += 4) {
    __m128 x = _mm_loadu_ps(a + i);
    __m128 w = _mm_loadu_ps(hann + i);
    _mm_storeu_ps(out + i, _mm_mul_ps(x, w));
  }
}
#endif

NOINLINE static double consume_frame(const float *out, int frame) {
  int a = (frame * 13) & (WIDTH - 1);
  return (double)out[a] +
    (double)out[(a + 341) & (WIDTH - 1)] +
    (double)out[(a + 682) & (WIDTH - 1)];
}

static double run_frames(const char *mode, const float *input, const float *hann,
                         float *out, int frames, int hop, int repeats) {
  double sum = 0;
  for (int r = 0; r < repeats; r++) {
    for (int frame = 0; frame < frames; frame++) {
      int offset = frame * hop;
      if (strcmp(mode, "scalar") == 0) {
        scalar_window(input, hann, out, offset);
#if HAS_SSE
      } else if (strcmp(mode, "sse") == 0) {
        sse_window(input, hann, out, offset);
#endif
      } else {
        fprintf(stderr, "Unsupported mode %s\n", mode);
        exit(2);
      }
      sum += consume_frame(out, frame);
    }
  }
  return sum;
}
static int compare_double(const void *a, const void *b) {
  double x = *(const double *)a, y = *(const double *)b;
  return x < y ? -1 : x > y ? 1 : 0;
}

int main(int argc, char **argv) {
  const char *mode = option_string(argc, argv, "--mode", "scalar");
  const char *backend = option_string(argc, argv, "--backend", "c");
  int hop = option_int(argc, argv, "--hop", 441);
  int frames = option_int(argc, argv, "--frames", 4096);
  int repeats = option_int(argc, argv, "--repeats", 32);
  int trials = option_int(argc, argv, "--trials", 5);
  if (hop <= 0 || frames <= 0 || repeats <= 0 || trials <= 0) return 2;
  if (frames > (INT32_MAX - WIDTH) / hop) return 2;
  size_t count = (size_t)(frames - 1) * (size_t)hop + WIDTH;
  float *input = (float *)malloc(count * sizeof(float));
  float *hann = (float *)malloc(WIDTH * sizeof(float));
  float *out = (float *)malloc(WIDTH * sizeof(float));
  double *times = (double *)malloc((size_t)trials * sizeof(double));
  if (!input || !hann || !out || !times) return 2;
  for (size_t i = 0; i < count; i++) {
    input[i] = (float)(((int)(i * 73 % 4096) - 2048) / 2048.0);
  }
  for (int i = 0; i < WIDTH; i++) {
    hann[i] = (float)(0.5 - 0.5 * cos(2.0 * 3.14159265358979323846 * i / (WIDTH - 1)));
  }
  double reference = run_frames("scalar", input, hann, out, frames, hop, 1);
  double candidate = run_frames(mode, input, hann, out, frames, hop, 1);
  if (fabs(reference - candidate) > frames * 1e-6) {
    fprintf(stderr, "Checksum mismatch: %s %.12f vs %.12f\n", mode, candidate, reference);
    return 2;
  }
  run_frames(mode, input, hann, out, frames, hop, 2);
  double checksum = 0;
  for (int trial = 0; trial < trials; trial++) {
    double t0 = seconds_now();
    checksum = run_frames(mode, input, hann, out, frames, hop, repeats);
    times[trial] = seconds_now() - t0;
  }
  qsort(times, (size_t)trials, sizeof(double), compare_double);
  double seconds = times[trials / 2];
  printf("%s,%s,%d,%d,%d,%d,%.9f,%.5f,%.6f\n", backend, mode, hop,
         frames, repeats, trials, seconds,
         seconds * 1e9 / ((double)frames * repeats * WIDTH), checksum);
  free(times); free(input); free(hann); free(out);
  return 0;
}
