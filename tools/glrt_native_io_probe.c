/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_native_posix.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

/* Read-only radio probe plus temporary retained evidence. No command writes,
 * no RX start/rebase, no acquisition. Bounded to 512 snapshots / 5 seconds.
 * This measures idle sysfs/storage cost, not loaded 750 Hz controller jitter. */
int main(int argc, char **argv)
{
    struct glrt_native_posix io;
    struct glrt_native_ports p;
    uint32_t w[20];
    char raw[512];
    double start, read_sum=0, retain_sum=0, read_max=0, retain_max=0;
    unsigned k;
    int rc = 1;
    if (argc != 3) { fprintf(stderr,"usage: %s ATTESTED_SYSFS_DIRECTORY NEW_JOURNAL\n",argv[0]); return 2; }
    if (glrt_native_posix_open(&io,&p,argv[1],argv[2],1024*1024)) return 2;
    start = p.clock(p.context);
    for (k=0; k<512; k++) {
        double before = p.clock(p.context), after, elapsed;
        int n;
        if (!isfinite(before) || before-start > 5) goto done;
        n = p.read(p.context,"native_schedule_snapshot",raw,sizeof(raw));
        after = p.clock(p.context);
        elapsed = after-before;
        if (n <= 0 || !isfinite(after) || elapsed < 0 ||
            glrt_native_snapshot_parse(raw,(size_t)n,w) || !glrt_native_snapshot_drained(w) ||
            w[6] || w[7] || (w[5]&16)) goto done;
        read_sum += elapsed;
        if (elapsed > read_max) read_max = elapsed;
        before = p.clock(p.context);
        if (p.retain(p.context,"snapshot",raw,(size_t)n)) goto done;
        elapsed = p.clock(p.context)-before;
        if (!isfinite(elapsed) || elapsed < 0) goto done;
        retain_sum += elapsed;
        if (elapsed > retain_max) retain_max = elapsed;
    }
    if (p.clock(p.context)-start > 5) goto done;
    printf("{\"scope\":\"idle_snapshot_and_retention_only\",\"iterations\":512,"
           "\"read_mean_us\":%.9g,\"read_max_us\":%.9g,"
           "\"retain_mean_us\":%.9g,\"retain_max_us\":%.9g,\"journal_bytes\":%llu}\n",
           read_sum/512*1e6,read_max*1e6,retain_sum/512*1e6,retain_max*1e6,
           (unsigned long long)io.bytes);
    rc = 0;
done:
    if (glrt_native_posix_close(&io)) rc = 1;
    return rc;
}
