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

/* Internal multirate port, not a persisted packet or an alternate GLN1/GLS1
 * interpretation. Profile and raw moment association belong to the caller. */
struct glrt_tracking_profile {
    uint32_t rate, samples, reference_phase, reference_phases;
    double reference_delay_s;
    const char *bank_sha256;
};

struct glrt_tracking_moments {
    uint64_t start;
    uint32_t count, fault, phase_step;
    /* CPU-endian least-significant words first: signed reference I/Q (2 each),
     * signed delay I/Q (2 each), signed prefix I/Q (3 each), energy (2).
     * Each field must canonically extend its actual rate-specific RTL width. */
    uint32_t words[16];
};

/* NULL for unsupported rate/phase. All returned profiles are immutable and
 * bind the exact ROM hash, Q11 Gram matrix, native count and phase delay. */
const struct glrt_tracking_profile *glrt_tracking_profile_get(uint32_t rate, uint32_t phase);
/* Returns local corrections about the selected reference, not an absolute
 * frame epoch. Keep start integer; add reference_delay_s separately. A -1
 * return sets out.rejection=FAULT and cannot leave a stale supported result. */
int glrt_tracking_solve(uint32_t rate, uint32_t phase,
    const struct glrt_tracking_moments *moments, struct glrt_native_estimate *out);
#endif
