/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_visit.h"
#include <string.h>

static int upper(uint64_t hz)
{
    return hz==UINT64_C(1190312500) || hz==UINT64_C(1440312500) ||
        hz==UINT64_C(1690312500) || hz==UINT64_C(1940312500);
}
static int guard(const struct glrt_visit_ports *p,uint64_t deadline,uint64_t *last)
{
    uint64_t now=p->clock_ns(p->context);int cancelled=p->cancelled(p->context);
    if(cancelled) return GLRT_VISIT_CANCELLED;
    if(!now || now<*last || now>=deadline) return GLRT_VISIT_DEADLINE;
    *last=now;return 0;
}
static int inspect(const struct glrt_visit_ports *p,uint32_t rate,struct glrt_visit_state *s)
{
    memset(s,0,sizeof(*s));
    if(p->inspect(p->context,s) || s->rate!=rate || s->idle!=1 || s->fixed_rf_valid!=1)
        return GLRT_VISIT_SOURCE;
    return 0;
}
static int close_lo(uint64_t a,uint64_t b) { return a>=b ? a-b<=16 : b-a<=16; }

int glrt_tracking_visit_run(const struct glrt_visit_ports *p,uint32_t rate,const uint64_t lo[2])
{
    struct glrt_visit_state before,tuned,after;
    uint64_t last,deadline;int rc;
    if(!p || !p->clock_ns || !p->cancelled || !p->inspect || !p->tune || !p->run || !p->retain ||
       !lo || !upper(lo[0]) || !upper(lo[1]) || lo[0]==lo[1] ||
       (rate!=30000000 && rate!=60000000)) return GLRT_VISIT_INVALID;
    last=p->clock_ns(p->context);
    if(!last || last>UINT64_MAX-UINT64_C(60000000000)) return GLRT_VISIT_DEADLINE;
    deadline=last+UINT64_C(60000000000);
    for(unsigned n=0;n<2;n++) {
        if((rc=guard(p,deadline,&last)) || (rc=inspect(p,rate,&before))) return rc;
        if(n && (before.epoch!=after.epoch || before.native_latest<after.native_latest || before.lo_hz!=after.lo_hz))
            return GLRT_VISIT_SOURCE;
        if(p->retain(p->context,"before_tune",n,0,&before)) return GLRT_VISIT_RETENTION;
        if((rc=guard(p,deadline,&last))) return rc;
        if(p->tune(p->context,lo[n])) return GLRT_VISIT_TUNE;
        if((rc=inspect(p,rate,&tuned))) return rc;
        if(tuned.epoch!=before.epoch || tuned.native_latest<before.native_latest || !close_lo(tuned.lo_hz,lo[n]))
            return GLRT_VISIT_SOURCE;
        if(p->retain(p->context,"tuned",n,0,&tuned)) return GLRT_VISIT_RETENTION;
        if((rc=guard(p,deadline,&last))) return rc;
        rc=p->run(p->context,n,deadline);
        /* Verify and retain cleanup even if the child failed. Only successful
         * capture or the explicit clean-loss disposition permits another tune;
         * an arbitrary failure is never promoted merely because hardware is idle. */
        if(inspect(p,rate,&after)) return GLRT_VISIT_SOURCE;
        if(after.lo_hz!=tuned.lo_hz || after.epoch<tuned.epoch || after.native_latest<tuned.native_latest)
            return GLRT_VISIT_SOURCE;
        if(p->retain(p->context,"after_run",n,rc,&after)) return GLRT_VISIT_RETENTION;
        if(rc && rc!=GLRT_VISIT_CLEAN_LOSS) return GLRT_VISIT_RUN;
        if(after.epoch==tuned.epoch || after.native_latest==tuned.native_latest) return GLRT_VISIT_SOURCE;
        if((rc=guard(p,deadline,&last))) return rc;
    }
    return GLRT_VISIT_DONE;
}
