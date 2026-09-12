/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_schedule.h"

#define MASK48 UINT64_C(0xffffffffffff)

int glrt_tracking_batch_valid(const struct glrt_tracking_batch *tracking)
{
    const struct glrt_tracking_profile *p;
    const struct glrt_native_batch *b;
    uint32_t stride, minimum, issue;
    uint64_t maximum;
    if (!tracking || !(p=glrt_tracking_profile_get(tracking->rate,0))) return 0;
    b=&tracking->prediction;
    stride=60000000U/p->rate;
    minimum=(64+stride-1)/stride;
    issue=(512+stride-1)/stride;
    maximum=UINT64_C(81000)*65536*p->rate/60000000;
    return b->epoch && b->tag && b->repeats && b->repeats<=64 &&
        b->start>=issue && b->expires>=b->start && b->fraction<=65535 &&
        b->period>=(uint64_t)(p->samples+2*minimum)*65536 && b->period<=maximum &&
        b->step<=MASK48 && b->delta<=MASK48;
}

int glrt_tracking_prediction(const struct glrt_tracking_batch *tracking, unsigned repeat,
                            struct glrt_tracking_job *out)
{
    const struct glrt_native_batch *b;
    const struct glrt_tracking_profile *p;
    struct glrt_tracking_job job;
    uint64_t advance, whole, carrier;
    uint32_t fraction, units, remainder, quantum, odd;
    if (!out || !glrt_tracking_batch_valid(tracking)) return -1;
    b=&tracking->prediction;
    if (repeat>=b->repeats) return -1;
    p=glrt_tracking_profile_get(tracking->rate,0);
    advance=b->fraction+repeat*b->period;
    whole=advance>>16;
    if (b->start>UINT64_MAX-whole) return -1;
    job.start=b->start+whole;
    fraction=(uint32_t)(advance&65535);
    quantum=65536/p->reference_phases;
    units=fraction/quantum;
    remainder=fraction%quantum;
    odd=p->reference_phases==1 ? (uint32_t)(job.start&1) : units&1;
    units+=remainder>quantum/2 || (remainder==quantum/2 && odd);
    if (units==p->reference_phases) {
        if (job.start==UINT64_MAX) return -1;
        job.start++;
        units=0;
    }
    job.reference_phase=units;
    if (job.start>UINT64_MAX-(p->samples-1) || job.start+p->samples-1>b->expires) return -1;
    carrier=(b->step+repeat*b->delta)&MASK48;
    fraction=(uint32_t)(carrier&65535);
    carrier>>=16;
    carrier+=fraction>32768 || (fraction==32768 && (carrier&1));
    job.phase_step=(uint32_t)carrier;
    *out=job;
    return 0;
}
