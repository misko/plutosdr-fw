/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_NATIVE_SOLVER_H
#define GLRT_NATIVE_SOLVER_H
#include <stdint.h>

enum glrt_native_rejection {
    GLRT_NATIVE_FAULT = 1,
    GLRT_NATIVE_INCOMPLETE = 2,
    GLRT_NATIVE_ZERO_ENERGY = 4,
    GLRT_NATIVE_NUMERICAL = 8,
    GLRT_NATIVE_UNIDENTIFIABLE = 16,
    GLRT_NATIVE_OUTSIDE_LOCAL = 32,
    GLRT_NATIVE_LOW_COHERENCE = 64
};

struct glrt_native_estimate {
    double delay_correction_s;
    double residual_cfo_hz;
    double cfo_hz;
    double coherence;
    double linearized_coherence;
    uint32_t rejection;
};

/* CPU-endian GLS1 words. Caller must validate source epoch, descriptor and
 * sequence association before using a correction. Returns -1 for a malformed
 * packet; otherwise rejection==0 means a supported LOCAL linearized fit.
 * This does not certify acquisition, physical epochs or Doppler truth.
 * Native start remains an integer in the caller; delay is a separate offset.
 */
int glrt_native_solve(const uint32_t words[32], struct glrt_native_estimate *out);

/* GLN1 original-IQ result, with its own capture flags/counts/fault validation.
 * The caller must bind tag/start/phase and independently replay the saved IQ.
 * Uses the same full-pilot numerical fit and rejection gates as GLS1, without
 * rewriting the persisted packet into another wire contract. Supported local
 * fits do not by themselves establish acquisition or physical continuity. */
int glrt_native_solve_capture(const uint32_t words[32], struct glrt_native_estimate *out);
#endif
