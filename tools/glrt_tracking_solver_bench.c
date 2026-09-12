/* SPDX-License-Identifier: GPL-2.0 */
/* Bounded saved-moment CPU benchmark. No devices, RF, network or firmware I/O. */
#define _POSIX_C_SOURCE 200809L
#include "glrt_native_solver.h"
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include <time.h>

struct entry { uint32_t rate, phase; struct glrt_tracking_moments moments; };

static double seconds(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC,&now)) exit(2);
    return now.tv_sec+now.tv_nsec*1e-9;
}

int main(int argc, char **argv)
{
    struct entry records[64];
    struct glrt_native_estimate out;
    unsigned count=0,n,k,iterations,iteration;
    unsigned long requested;
    double begin,elapsed,checksum=0;
    char *end;
    FILE *input;
    if (argc != 3) return 2;
    requested = strtoul(argv[2],&end,10);
    if (*end || requested < 1 || requested > 1000000) return 2;
    iterations = (unsigned)requested;
    input = fopen(argv[1],"r");
    if (!input) return 2;
    while (count < 64) {
        struct entry *r = &records[count];
        struct glrt_tracking_moments *m = &r->moments;
        int rc = fscanf(input,"%" SCNx32,&r->rate);
        if (rc == EOF) break;
        if (rc != 1 || fscanf(input,"%" SCNx32 " %" SCNx64 " %" SCNx32 " %" SCNx32 " %" SCNx32,
            &r->phase,&m->start,&m->count,&m->fault,&m->phase_step) != 5) return 2;
        for (k=0; k<16; k++) if (fscanf(input,"%" SCNx32,&m->words[k]) != 1) return 2;
        if (glrt_tracking_solve(r->rate,r->phase,m,&out)) return 2;
        count++;
    }
    if (!count || fscanf(input,"%x",&k) != EOF) return 2;
    fclose(input);
    printf("{\"records\":[");
    for (n=0; n<count; n++) {
        const struct entry *r = &records[n];
        const struct glrt_tracking_profile *profile = glrt_tracking_profile_get(r->rate,r->phase);
        if (!profile || glrt_tracking_solve(r->rate,r->phase,&r->moments,&out)) return 2;
        printf("%s{\"rate_hz\":%" PRIu32 ",\"reference_phase\":%" PRIu32
            ",\"bank_sha256\":\"%s\",\"delay_s\":%.17g,\"residual_hz\":%.17g,\"cfo_hz\":%.17g,"
            "\"coherence\":%.17g,\"linearized_coherence\":%.17g,\"rejection\":%" PRIu32 "}",
            n ? "," : "",r->rate,r->phase,profile->bank_sha256,out.delay_correction_s,
            out.residual_cfo_hz,out.cfo_hz,out.coherence,out.linearized_coherence,out.rejection);
    }
    begin = seconds();
    for (iteration=0; iteration<iterations; iteration++) {
        const struct entry *r = &records[iteration%count];
        if (glrt_tracking_solve(r->rate,r->phase,&r->moments,&out)) return 2;
        checksum += out.delay_correction_s+out.residual_cfo_hz+out.rejection;
        if (!(iteration%1024) && seconds()-begin > 10) return 3;
    }
    elapsed = seconds()-begin;
    printf("],\"calls\":%u,\"elapsed_s\":%.9g,\"mean_us\":%.9g,\"checksum\":%.17g,"
        "\"scope\":\"multirate_solver_only_no_io_or_feedback\"}\n",
        iterations,elapsed,elapsed*1e6/iterations,checksum);
    return 0;
}
