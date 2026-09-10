/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_native_solver.h"
#include <complex.h>
#include <float.h>
#include <math.h>
#include <string.h>

#include "glrt_native_gram.inc"

#define NATIVE_SAMPLES 79200U
#define NATIVE_RATE 60000000U
#define PI 0x1.921fb54442d18p+1

static int canonical(const uint32_t *w, unsigned count, unsigned bits, int sign)
{
    unsigned high_bits = bits-32*(count-1);
    uint32_t high = w[count-1], mask = UINT32_MAX << high_bits;
    uint32_t extension = sign && (high & (1U << (high_bits-1))) ? mask : 0;
    return (high & mask) == extension;
}

static double signed_words(const uint32_t *w, unsigned count)
{
    double value = (double)w[count-1];
    unsigned n = count-1;
    if (w[count-1] & 0x80000000U)
        value -= 0x1p32;
    while (n)
        value = value*0x1p32 + w[--n];
    return value;
}

/* Compute (N-1)*reference - 2*prefix in exact signed 96-bit arithmetic before
 * conversion. In particular, a nearly cancelled centered moment must not lose
 * its low bits by subtracting two large rounded doubles. No ARM __int128. */
static double centered(const uint32_t *reference, const uint32_t *prefix)
{
    uint32_t a[3] = {reference[0], reference[1],
                     reference[1] & 0x80000000U ? UINT32_MAX : 0};
    uint32_t product[3], shifted[3], difference[3];
    uint64_t carry = 0, borrow = 0;
    unsigned n;
    for (n=0; n<3; n++) {
        uint64_t term = (uint64_t)a[n]*(NATIVE_SAMPLES-1) + carry;
        product[n] = (uint32_t)term;
        carry = term >> 32;
        shifted[n] = (prefix[n] << 1) | (n ? prefix[n-1] >> 31 : 0);
    }
    for (n=0; n<3; n++) {
        uint64_t sub = (uint64_t)shifted[n]+borrow;
        difference[n] = (uint32_t)((uint64_t)product[n]-sub);
        borrow = (uint64_t)product[n] < sub;
    }
    return signed_words(difference,3);
}

static double norm2(double complex z) { return creal(z)*creal(z)+cimag(z)*cimag(z); }
static double clip(double x, double low, double high) { return fmax(low,fmin(high,x)); }

static int solve(const uint32_t w[32], struct glrt_native_estimate *out, int capture)
{
    double complex g[3][3], p[3], amplitude, residual[2];
    double norm, energy, gain, h00, h01, h11, r0, r1, discriminant, eigen_low, eigen_high;
    double determinant, correction[3] = {1,0,0}, model_norm, predicted;
    unsigned i,j;
    uint64_t start;
    if (!w || !out)
        return -1;
    memset(out,0,sizeof(*out));
    if (!w[2] || w[25] != NATIVE_RATE || w[26] != NATIVE_SAMPLES ||
        w[7] > NATIVE_SAMPLES || (!w[8] && w[7] != NATIVE_SAMPLES))
        return -1;
    if (capture) {
        if (w[0] != 0x474c4e31U || w[27] != 1 || w[30] || w[31] ||
            (w[8] & ~0x7ffU) || w[28] != w[29] || w[28] > NATIVE_SAMPLES ||
            w[7] > w[28] || (!w[8] && w[28] != NATIVE_SAMPLES))
            return -1;
    } else if (w[0] != 0x474c5331U || w[27] >= 64 || w[28] || w[29] ||
               w[30] || w[31] || (w[8] & ~0x3ffU)) {
        return -1;
    }
    start = ((uint64_t)w[4] << 32) | w[3];
    if ((capture ? w[28] : w[7]) && start > UINT64_MAX-((capture ? w[28] : w[7])-1))
        return -1;
    for (i=9; i<17; i+=2)
        if (!canonical(w+i,2,52,1)) return -1;
    if (!canonical(w+17,3,69,1) || !canonical(w+20,3,69,1) || !canonical(w+23,2,53,0))
        return -1;
    if (!w[7])
        for (i=9; i<25; i++)
            if (w[i]) return -1;
    predicted = ((double)w[6] - (w[6] & 0x80000000U ? 0x1p32 : 0))*NATIVE_RATE/0x1p32;
    out->cfo_hz = predicted;
    if (w[8]) out->rejection |= GLRT_NATIVE_FAULT;
    if (w[7] != NATIVE_SAMPLES) out->rejection |= GLRT_NATIVE_INCOMPLETE;
    /* Partial moments cannot be paired with the full-pilot Gram matrix. */
    if (out->rejection) return 0;
    if (fabs(predicted)+250 >= NATIVE_RATE/2) {
        out->rejection |= GLRT_NATIVE_OUTSIDE_LOCAL;
        return 0;
    }
    for (i=0; i<3; i++)
        for (j=0; j<3; j++)
            g[i][j] = native_gram[i][j][0] + I*native_gram[i][j][1];
    p[0] = signed_words(w+9,2) + I*signed_words(w+11,2);
    p[1] = signed_words(w+13,2) + I*signed_words(w+15,2);
    p[2] = -I*(PI*1000/NATIVE_RATE)*(centered(w+9,w+17) + I*centered(w+11,w+20));
    energy = (double)w[24]*0x1p32+w[23];
    norm = creal(g[0][0]);
    if (energy <= DBL_MIN || norm <= DBL_MIN) {
        out->rejection |= GLRT_NATIVE_ZERO_ENERGY;
        return 0;
    }
    amplitude = p[0]/norm;
    gain = norm2(amplitude);
    out->coherence = clip(norm2(p[0])/(norm*energy),0,1);
    out->linearized_coherence = out->coherence;
    h00 = gain*creal(g[1][1]-g[1][0]*g[0][1]/norm);
    h01 = gain*creal(g[1][2]-g[1][0]*g[0][2]/norm);
    h11 = gain*creal(g[2][2]-g[2][0]*g[0][2]/norm);
    for (i=0; i<2; i++) residual[i] = p[i+1]-g[i+1][0]*p[0]/norm;
    r0 = creal(conj(amplitude)*residual[0]);
    r1 = creal(conj(amplitude)*residual[1]);
    discriminant = hypot(h00-h11,2*h01);
    eigen_low = (h00+h11-discriminant)/2;
    eigen_high = (h00+h11+discriminant)/2;
    determinant = h00*h11-h01*h01;
    if (eigen_low <= 1e-8*fmax(eigen_high,energy*1e-15) || determinant <= 0) {
        out->rejection |= GLRT_NATIVE_UNIDENTIFIABLE;
    } else {
        double delay = (h11*r0-h01*r1)/determinant;
        double cfo = (h00*r1-h01*r0)/determinant;
        if (!isfinite(delay) || !isfinite(cfo)) {
            out->rejection |= GLRT_NATIVE_NUMERICAL;
            return 0;
        }
        if (fabs(delay) >= .25 || fabs(cfo) >= .25)
            out->rejection |= GLRT_NATIVE_OUTSIDE_LOCAL;
        correction[1] = clip(delay,-.25,.25);
        correction[2] = clip(cfo,-.25,.25);
        out->delay_correction_s = correction[1]*1e-6;
        out->residual_cfo_hz = correction[2]*1000;
        out->cfo_hz = predicted+out->residual_cfo_hz;
        model_norm = 0;
        for (i=0; i<3; i++)
            for (j=0; j<3; j++) model_norm += correction[i]*creal(g[i][j])*correction[j];
        if (model_norm > DBL_MIN)
            out->linearized_coherence = clip(norm2(p[0]+correction[1]*p[1]+correction[2]*p[2]) /
                                               (model_norm*energy),0,1);
    }
    if (out->coherence < .05) out->rejection |= GLRT_NATIVE_LOW_COHERENCE;
    return 0;
}

int glrt_native_solve(const uint32_t w[32], struct glrt_native_estimate *out)
{
    return solve(w,out,0);
}

int glrt_native_solve_capture(const uint32_t w[32], struct glrt_native_estimate *out)
{
    return solve(w,out,1);
}
