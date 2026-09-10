/* SPDX-License-Identifier: GPL-2.0 */
/* Saved-packet CPU benchmark. No radio, sysfs, network or firmware access. */
#define _POSIX_C_SOURCE 200809L
#include "glrt_native_solver.h"
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include <time.h>

static double seconds(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC,&now)) exit(2);
    return now.tv_sec+now.tv_nsec*1e-9;
}

int main(int argc, char **argv)
{
    uint32_t records[64][32];
    struct glrt_native_estimate estimate;
    unsigned count=0,word,iteration,iterations,n;
    double begin,elapsed,checksum=0;
    char *end;
    unsigned long requested;
    FILE *input;
    if (argc != 3) return 2;
    requested = strtoul(argv[2],&end,10);
    if (*end || requested < 1 || requested > 1000000) return 2;
    iterations = (unsigned)requested;
    input = fopen(argv[1],"r");
    if (!input) return 2;
    while (count < 64) {
        int rc = fscanf(input,"%" SCNx32,&records[count][0]);
        if (rc == EOF) break;
        if (rc != 1) return 2;
        for (word=1; word<32; word++)
            if (fscanf(input,"%" SCNx32,&records[count][word]) != 1) return 2;
        if (glrt_native_solve(records[count],&estimate)) return 2;
        count++;
    }
    if (!count || fscanf(input,"%" SCNx32,&word) != EOF) return 2;
    fclose(input);
    printf("{\"records\":[");
    for (n=0; n<count; n++) {
        if (glrt_native_solve(records[n],&estimate)) return 2;
        printf("%s{\"delay_s\":%.17g,\"residual_hz\":%.17g,\"cfo_hz\":%.17g,"
               "\"coherence\":%.17g,\"linearized_coherence\":%.17g,\"rejection\":%" PRIu32 "}",
               n ? "," : "", estimate.delay_correction_s,estimate.residual_cfo_hz,
               estimate.cfo_hz,estimate.coherence,estimate.linearized_coherence,estimate.rejection);
    }
    begin = seconds();
    for (iteration=0; iteration<iterations; iteration++) {
        if (glrt_native_solve(records[iteration%count],&estimate)) return 2;
        checksum += estimate.delay_correction_s+estimate.residual_cfo_hz+estimate.rejection;
        if (!(iteration%1024) && seconds()-begin > 10) return 3;
    }
    elapsed = seconds()-begin;
    printf("],\"calls\":%u,\"elapsed_s\":%.9g,\"mean_us\":%.9g,\"checksum\":%.17g,"
           "\"scope\":\"solver_only_no_io_or_feedback\"}\n",
           iterations,elapsed,elapsed*1e6/iterations,checksum);
    return 0;
}
