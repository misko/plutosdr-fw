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

static int run_plan(const struct glrt_visit_ports *p,uint32_t rate,const uint64_t *lo,
    unsigned count,unsigned first_number,uint64_t duration,int stop_on_loss,
    int followup,unsigned *selected)
{
    struct glrt_visit_state before,tuned,after;
    uint64_t last,deadline;int rc,outcome;
    if(!p || !p->clock_ns || !p->cancelled || !p->inspect || !p->tune || !p->run || !p->retain ||
       !lo || !count || count>4 || (!followup && count<2) || (stop_on_loss && !selected) ||
       (rate!=30000000 && rate!=60000000)) return GLRT_VISIT_INVALID;
    for(unsigned n=0;n<count;n++)
        if(!upper(lo[n]) || (n && lo[n]==lo[n-1])) return GLRT_VISIT_INVALID;
    last=p->clock_ns(p->context);
    if(!last || last>UINT64_MAX-duration) return GLRT_VISIT_DEADLINE;
    deadline=last+duration;
    for(unsigned n=0;n<count;n++) {
        if((rc=guard(p,deadline,&last)) || (rc=inspect(p,rate,&before))) return rc;
        if(n && (before.epoch!=after.epoch || before.native_latest<after.native_latest || before.lo_hz!=after.lo_hz))
            return GLRT_VISIT_SOURCE;
        unsigned number=first_number+n;
        if(p->retain(p->context,"before_tune",number,0,&before)) return GLRT_VISIT_RETENTION;
        if((rc=guard(p,deadline,&last))) return rc;
        if(p->tune(p->context,lo[n])) return GLRT_VISIT_TUNE;
        if((rc=inspect(p,rate,&tuned))) return rc;
        if(tuned.epoch!=before.epoch || tuned.native_latest<before.native_latest || !close_lo(tuned.lo_hz,lo[n]))
            return GLRT_VISIT_SOURCE;
        if(p->retain(p->context,"tuned",number,0,&tuned)) return GLRT_VISIT_RETENTION;
        if((rc=guard(p,deadline,&last))) return rc;
        outcome=p->run(p->context,number,deadline);
        /* Verify and retain cleanup even if the child failed. Only successful
         * capture or the explicit clean-loss disposition permits another tune;
         * an arbitrary failure is never promoted merely because hardware is idle. */
        if(inspect(p,rate,&after)) return GLRT_VISIT_SOURCE;
        if(after.lo_hz!=tuned.lo_hz || after.epoch<tuned.epoch || after.native_latest<tuned.native_latest)
            return GLRT_VISIT_SOURCE;
        if(p->retain(p->context,"after_run",number,outcome,&after)) return GLRT_VISIT_RETENTION;
        if(outcome && outcome!=GLRT_VISIT_CLEAN_LOSS && !(stop_on_loss && outcome==GLRT_VISIT_SIGNAL) &&
           !(followup && outcome==GLRT_VISIT_NO_TRACK))
            return GLRT_VISIT_RUN;
        if(after.epoch==tuned.epoch || after.native_latest==tuned.native_latest) return GLRT_VISIT_SOURCE;
        if((rc=guard(p,deadline,&last))) return rc;
        if(stop_on_loss && (outcome==GLRT_VISIT_CLEAN_LOSS || outcome==GLRT_VISIT_SIGNAL)) {
            *selected=n;return GLRT_VISIT_SIGNAL;
        }
        if(followup && outcome) return outcome;
    }
    return GLRT_VISIT_DONE;
}
int glrt_tracking_visit_plan_run(const struct glrt_visit_ports *p,uint32_t rate,const uint64_t *lo,unsigned count)
{
    return run_plan(p,rate,lo,count,0,UINT64_C(60000000000),0,0,NULL);
}
int glrt_tracking_visit_until_signal(const struct glrt_visit_ports *p,uint32_t rate,
    const uint64_t *lo,unsigned count,unsigned *selected)
{
    return run_plan(p,rate,lo,count,0,UINT64_C(60000000000),1,0,selected);
}
int glrt_tracking_visit_followup_run(const struct glrt_visit_ports *p,uint32_t rate,
    uint64_t lo,unsigned number)
{
    return run_plan(p,rate,&lo,1,number,UINT64_C(320000000000),0,1,NULL);
}
int glrt_tracking_visit_run(const struct glrt_visit_ports *p,uint32_t rate,const uint64_t lo[2])
{ return glrt_tracking_visit_plan_run(p,rate,lo,2); }
