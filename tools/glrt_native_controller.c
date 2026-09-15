/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_native_controller.h"
#include "glrt_tracking_transport.h"
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static const char *attribute(const struct glrt_native_controller *c,
                            const char *legacy, const char *tracking)
{
    return c->tracking ? tracking : legacy;
}

static int prediction(const struct glrt_native_controller *c,
    const struct glrt_native_batch *b, unsigned repeat, uint64_t *start, uint32_t *step)
{
    struct glrt_tracking_batch batch = {*b,c->trend.rate};
    struct glrt_tracking_job job;
    if (!c->tracking) return glrt_native_prediction(b,repeat,start,step);
    if (glrt_tracking_prediction(&batch,repeat,&job)) return -1;
    *start = job.start;
    *step = job.phase_step;
    return 0;
}

static int snapshot_parse(const struct glrt_native_controller *c,
                          const char *raw, size_t size, uint32_t w[24])
{
    if (!c->tracking) return glrt_native_snapshot_parse(raw,size,w);
    return glrt_tracking_snapshot_parse(raw,size,w) || w[20] != c->trend.rate ? -1 : 0;
}

static int snapshot_drained(const struct glrt_native_controller *c, const uint32_t w[24])
{
    return c->tracking ? glrt_tracking_snapshot_drained(w) : glrt_native_snapshot_drained(w);
}

static uint32_t last_authorized_support(const struct glrt_native_controller *c)
{
    uint32_t last=c->trend.history.last_supported;
    if(c->authority_valid && c->authority.history.last_supported>last)
        last=c->authority.history.last_supported;
    return last;
}

static int command(struct glrt_native_controller *c, const char *name, const char *text)
{
    size_t n = strlen(text);
    return c->ports.write(c->ports.context,name,text,n) == (int)n ? 0 : -1;
}

static void stop(struct glrt_native_controller *c, int reason)
{
    if (!c->stopping) c->cleanup_deadline = c->ports.clock(c->ports.context)+5;
    c->stopping = 1;
    if (!c->failure) c->failure = reason;
}

static int finish_error(struct glrt_native_controller *c, int reason)
{
    stop(c,reason);
    if (!c->cancelled) {
        /* At most one attempt: uncertain cancellation never permits a new
         * descriptor or POP. All submitted descriptors also expire finitely. */
        c->cancelled = 1;
        command(c,attribute(c,"native_schedule_command","tracking_command"),"2\n");
    }
    c->done = 1;
    return c->failure;
}

void glrt_native_controller_request_stop(struct glrt_native_controller *c)
{
    if (c && !c->done) stop(c,GLRT_NATIVE_DEADLINE);
}

int glrt_native_controller_init(struct glrt_native_controller *c,
    const struct glrt_native_ports *p, const struct glrt_native_batch *b,
    uint32_t frames, double seconds)
{
    uint64_t last;
    uint32_t step;
    double now;
    if (!c || !p || !p->read || !p->write || !p->retain || !p->clock ||
        !glrt_native_batch_valid(b) || frames < b->repeats || frames > 225000 ||
        b->tag == UINT32_MAX || !(seconds > 0 && seconds <= 300) ||
        glrt_native_prediction(b,b->repeats-1,&last,&step)) return -1;
    now = p->clock(p->context);
    if (!isfinite(now)) return -1;
    memset(c,0,sizeof(*c));
    c->ports = *p;
    c->frames = frames;
    c->frame_stride = 1;
    c->result_limit = frames;
    c->deadline = now+seconds;
    c->slots[0].batch = *b;
    c->next_tag = b->tag+1;
    glrt_tracking_trend_reset(&c->trend,b->epoch,60000000);
    return 0;
}

int glrt_tracking_controller_init(struct glrt_native_controller *c,
    const struct glrt_native_ports *p, const struct glrt_tracking_batch *b,
    uint32_t frames, double seconds)
{
    double now;
    struct glrt_tracking_job last;
    if (!c || !p || !p->read || !p->write || !p->retain || !p->clock ||
        !glrt_tracking_batch_valid(b) || frames < b->prediction.repeats || frames > 225000 ||
        b->prediction.tag == UINT32_MAX || !(seconds > 0 && seconds <= 300) ||
        glrt_tracking_prediction(b,b->prediction.repeats-1,&last)) return -1;
    now = p->clock(p->context);
    if (!isfinite(now)) return -1;
    memset(c,0,sizeof(*c));
    c->ports = *p;
    c->frames = frames;
    c->frame_stride = 1;
    c->result_limit = frames;
    c->deadline = now+seconds;
    c->slots[0].batch = b->prediction;
    c->next_tag = b->prediction.tag+1;
    c->tracking = 1;
    return glrt_tracking_trend_reset(&c->trend,b->prediction.epoch,b->rate);
}

int glrt_tracking_controller_init_handoff(struct glrt_native_controller *c,
    const struct glrt_native_ports *p, const struct glrt_tracking_batch *b,
    const struct glrt_tracking_trend *history, uint32_t first,
    uint32_t frames, double seconds)
{
    struct glrt_tracking_batch predicted;
    struct glrt_tracking_trend retained;
    char expected[256], supplied[256];
    double slope;
    if (!glrt_tracking_batch_valid(b) ||
        !glrt_tracking_trend_handoff_valid(history,first,frames) ||
        history->rate!=b->rate || history->history.epoch!=b->prediction.epoch ||
        glrt_tracking_trend_batch(history,first,b->prediction.repeats,
            b->prediction.tag,b->prediction.seed,&predicted,&slope) ||
        glrt_tracking_batch_encode(&predicted,expected,sizeof(expected))<0 ||
        glrt_tracking_batch_encode(b,supplied,sizeof(supplied))<0 || strcmp(expected,supplied)) return -1;
    retained=*history;
    if (glrt_tracking_controller_init(c,p,b,frames,seconds)) return -1;
    c->trend=retained;
    c->next_frame=first; c->frames=first+frames; c->handoff_pending=1;
    return 0;
}

int glrt_tracking_controller_init_handoff_strided(struct glrt_native_controller *c,
    const struct glrt_native_ports *p, const struct glrt_tracking_batch *b,
    const struct glrt_tracking_trend *history, uint32_t first,
    uint32_t measurements, uint32_t stride, double seconds)
{
    struct glrt_tracking_batch predicted;
    struct glrt_tracking_trend retained;
    char expected[256],supplied[256];
    uint32_t span;
    double slope;
    if(!measurements || measurements>225000 || stride<2 || stride>750 ||
       measurements>UINT32_MAX/stride || (span=measurements*stride)>UINT32_MAX-first ||
       !glrt_tracking_batch_valid(b) || b->prediction.repeats!=1 ||
       !glrt_tracking_trend_handoff_valid(history,first,span) ||
       history->rate!=b->rate || history->history.epoch!=b->prediction.epoch ||
       glrt_tracking_trend_batch(history,first,1,b->prediction.tag,b->prediction.seed,
           &predicted,&slope) ||
       glrt_tracking_batch_encode(&predicted,expected,sizeof(expected))<0 ||
       glrt_tracking_batch_encode(b,supplied,sizeof(supplied))<0 || strcmp(expected,supplied)) return -1;
    retained=*history;
    if(glrt_tracking_controller_init(c,p,b,measurements,seconds)) return -1;
    c->trend=retained;c->next_frame=first;c->frames=first+span;
    c->frame_stride=stride;c->result_limit=measurements;c->handoff_pending=1;
    return 0;
}

/* Canonical internal GLTH1 history: IEEE binary64 bits avoid decimal rounding
 * and preserve the predictor's physical ring order. 96 rows plus the fixed
 * header fit the existing 4096-byte retained-record bound. No native padding
 * or memory-endian representation is persisted. */
static int retain_history(struct glrt_native_controller *c,const char *kind,
    const struct glrt_tracking_trend *trend)
{
    const struct glrt_native_trend *h=&trend->history;
    char raw[4096];
    size_t length;
    unsigned i;
    int n;
    if (sizeof(double)!=8 || DBL_MANT_DIG!=53 || DBL_MAX_EXP!=1024)
        return GLRT_NATIVE_PROTOCOL_ERROR;
    n=snprintf(raw,sizeof(raw),"GLTH1 00010000 %08" PRIx32 " %08" PRIx32
        " %08" PRIx32 " %08" PRIx32 " %08" PRIx32 " %08" PRIx32 " %08" PRIx32
        " %016" PRIx64 " %08" PRIx32 " %08" PRIx32 "\n",trend->rate,h->epoch,
        c->next_frame,c->frames,h->first_frame,h->last_seen,h->last_supported,h->anchor,h->count,h->next);
    if (n<0 || (size_t)n>=sizeof(raw)) return GLRT_NATIVE_PROTOCOL_ERROR;
    length=(size_t)n;
    for (i=0;i<h->count;i++) {
        uint64_t offset, cfo;
        memcpy(&offset,&h->observations[i].offset_samples,8);
        memcpy(&cfo,&h->observations[i].cfo_hz,8);
        n=snprintf(raw+length,sizeof(raw)-length,"%08" PRIx32 "%016" PRIx64 "%016" PRIx64 "\n",
            h->observations[i].frame,offset,cfo);
        if (n<0 || (size_t)n>=sizeof(raw)-length) return GLRT_NATIVE_PROTOCOL_ERROR;
        length+=(size_t)n;
    }
    return c->ports.retain(c->ports.context,kind,raw,length) ?
        GLRT_NATIVE_RETENTION_ERROR : 0;
}

int glrt_tracking_controller_refresh_handoff(struct glrt_native_controller *c,
    const struct glrt_tracking_trend *history)
{
    struct glrt_tracking_trend retained;
    uint32_t previous;
    int rc;
    if(!c || !history || !c->tracking || !c->started || c->stopping || c->done ||
       c->handoff_pending || c->next_frame>=c->frames ||
       history->rate!=c->trend.rate || history->history.epoch!=c->trend.history.epoch)
        return -1;
    previous=c->authority_valid ? c->authority.history.last_supported :
        c->trend.history.last_supported;
    /* Advance this independent authority monotonically. It may trail a newer
     * native point: sparse native cadence can have the greatest frame ordinal
     * while lacking the eight recent observations needed to predict. Keep the
     * native predictor preferred, but retain a valid denser coarse history for
     * the exact next unowned frame when native prediction is underdetermined. */
    if(history->history.last_supported<=previous ||
       !glrt_tracking_trend_handoff_valid(history,c->next_frame,c->frames-c->next_frame) ||
       c->next_frame-history->history.last_supported>32)
        return -1;
    retained=*history;
    rc=retain_history(c,"tracking_authority",&retained);
    if(rc) { stop(c,rc);return rc; }
    c->authority=retained;c->authority_valid=1;c->acquisition_horizon_exhausted=0;
    c->authority_wait_until=0;
    return 0;
}

static int bootstrap_slice(const struct glrt_native_batch *original,
    uint32_t first, uint32_t count, uint32_t tag, struct glrt_native_batch *out)
{
    uint64_t advance, last;
    uint32_t step;
    if (!count || first >= original->repeats || count > original->repeats-first) return -1;
    /* The complete original horizon was checked before any I/O. Preserve its
     * fractional sample cadence and modulo-48 carrier ramp without doubles. */
    advance = original->fraction + first*original->period;
    if (original->start > UINT64_MAX-(advance>>16)) return -1;
    *out = *original;
    out->start += advance>>16;
    out->fraction = (uint32_t)(advance & 65535);
    out->step = (original->step+first*original->delta) & UINT64_C(0xffffffffffff);
    out->tag = tag;
    out->repeats = count;
    if (glrt_native_prediction(out,count-1,&last,&step)) return -1;
    out->expires = last+79199;
    return 0;
}

int glrt_native_controller_init_sliced(struct glrt_native_controller *c,
    const struct glrt_native_ports *p, const struct glrt_native_batch *b,
    uint32_t frames, double seconds)
{
    if (!b || b->repeats <= 16 || glrt_native_controller_init(c,p,b,frames,seconds)) return -1;
    c->bootstrap = *b;
    c->bootstrap_active = 1;
    return bootstrap_slice(b,0,12,b->tag,&c->slots[0].batch);
}

static void bootstrap_observe(struct glrt_native_controller *c, uint32_t frame,
    uint64_t start, const struct glrt_native_estimate *e)
{
    struct glrt_native_batch original;
    uint64_t difference;
    double samples, hz, predicted_hz;
    int64_t carrier;
    if (!c->bootstrap_active || e->rejection || frame >= c->bootstrap.repeats ||
        bootstrap_slice(&c->bootstrap,frame,1,c->bootstrap.tag,&original)) return;
    difference = start >= original.start ? start-original.start : original.start-start;
    if (difference > 32) return;
    samples = (start >= original.start ? (double)difference : -(double)difference)
        + e->delay_correction_s*60000000 - original.fraction/65536.0;
    carrier = (int64_t)original.step;
    if (carrier & (INT64_C(1)<<47)) carrier -= INT64_C(1)<<48;
    predicted_hz = carrier*(60000000.0/281474976710656.0);
    hz = e->cfo_hz-predicted_hz;
    /* Correct offsets only, never infer a rate from sparse startup results.
     * Rejected fits cannot move the prediction. Corrections stay inside the
     * original local basin and never move the external expiry boundary. */
    if (!isfinite(samples) || !isfinite(hz) || fabs(samples) > 15 || fabs(hz) > 250) return;
    c->bootstrap_delay_q16 = (int64_t)llround(samples*65536.0);
    c->bootstrap_cfo_q48 = (int64_t)llround(hz*(281474976710656.0/60000000.0));
    c->bootstrap_offset_valid = 1;
}

static void bootstrap_correct(struct glrt_native_controller *c, struct glrt_native_batch *b)
{
    struct glrt_native_batch corrected = *b;
    int64_t position = (int64_t)b->fraction+c->bootstrap_delay_q16;
    int64_t whole = position/65536, fraction = position%65536;
    uint64_t last;
    uint32_t step;
    if (fraction < 0) { fraction += 65536; whole--; }
    if ((whole < 0 && corrected.start < (uint64_t)-whole) ||
        (whole > 0 && corrected.start > UINT64_MAX-(uint64_t)whole)) return;
    if (whole < 0) corrected.start -= (uint64_t)-whole;
    else corrected.start += (uint64_t)whole;
    corrected.fraction = (uint32_t)fraction;
    corrected.step = (uint64_t)((int64_t)corrected.step+c->bootstrap_cfo_q48) & UINT64_C(0xffffffffffff);
    corrected.expires = c->bootstrap.expires;
    /* A positive correction at the very end may exceed the original expiry.
     * In that case retain the authorized uncorrected slice; never extend it. */
    if (glrt_native_prediction(&corrected,corrected.repeats-1,&last,&step)) return;
    corrected.expires = last+79199;
    *b = corrected;
}

static int submit(struct glrt_native_controller *c, unsigned slot,
                  const struct glrt_native_batch *b, uint32_t first, uint64_t latest)
{
    char encoded[256], record[320], raw[512];
    uint64_t start;
    uint32_t phase, w[24];
    const uint64_t lead = c->trend.rate/10000; /* 100 microseconds at every rate. */
    struct glrt_tracking_batch tracking_batch = {*b,c->trend.rate};
    double now;
    int n;
    if(c->frame_stride>1 && b->repeats!=1) return GLRT_NATIVE_PROTOCOL_ERROR;
    n = c->tracking ? glrt_tracking_batch_encode(&tracking_batch,encoded,sizeof(encoded)) :
        glrt_native_batch_encode(b,encoded,sizeof(encoded));
    if (n < 0 || prediction(c,b,0,&start,&phase) ||
        start <= latest || start-latest < lead) return GLRT_NATIVE_DEADLINE;
    n = snprintf(record,sizeof(record),"frame %" PRIu32 " %s",first,encoded);
    if (n < 0 || (size_t)n >= sizeof(record)) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (c->ports.retain(c->ports.context,"descriptor",record,(size_t)n))
        return GLRT_NATIVE_RETENTION_ERROR;
    /* Storage can block. Re-read the source after retention, rather than
     * submitting against the pre-retention source snapshot. Hardware still
     * accounts any lateness caused by preemption during the final write. */
    n = c->ports.read(c->ports.context,attribute(c,"native_schedule_snapshot","tracking_snapshot"),raw,sizeof(raw));
    if (n <= 0 || (size_t)n > sizeof(raw)) return GLRT_NATIVE_IO_ERROR;
    if (snapshot_parse(c,raw,(size_t)n,w)) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (w[2] != b->epoch || w[6] || (w[5]&48) != 48 ||
        w[9] || w[10] || w[11] || w[12] || w[13]) return GLRT_NATIVE_SOURCE_LOST;
    if (w[7] != c->configured || w[15] != c->sequence || !(w[5]&1))
        return GLRT_NATIVE_PROTOCOL_ERROR;
    latest = ((uint64_t)w[4]<<32)|w[3];
    now = c->ports.clock(c->ports.context);
    if (!isfinite(now)) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (now >= c->deadline || start <= latest || start-latest < lead)
        return GLRT_NATIVE_DEADLINE;
    /* Track even an uncertain submission, so its eventual heads can be
     * retained/associated during cancellation. Never retry SUBMIT. */
    c->slots[slot] = (struct glrt_native_owned_batch){*b,first,0,1};
    c->next_frame = first+(c->frame_stride>1 ? c->frame_stride : b->repeats);
    if (command(c,attribute(c,"native_schedule_submit","tracking_submit"),encoded)) return GLRT_NATIVE_IO_ERROR;
    c->configured += b->repeats;
    return 0;
}

static int consume(struct glrt_native_controller *c)
{
    char raw[512], ack[32], fitted[256];
    uint32_t epoch, words[32];
    struct glrt_native_estimate e;
    struct glrt_native_owned_batch *owner = NULL;
    unsigned i;
    int associated;
    int n = c->ports.read(c->ports.context,attribute(c,"native_schedule_result","tracking_result"),raw,sizeof(raw));
    if (n <= 0 || (size_t)n > sizeof(raw)) return GLRT_NATIVE_IO_ERROR;
    if (c->ports.retain(c->ports.context,"head",raw,(size_t)n)) return GLRT_NATIVE_RETENTION_ERROR;
    if (c->tracking ? glrt_tracking_head_parse(raw,(size_t)n,&epoch,words) :
        glrt_native_head_parse(raw,(size_t)n,&epoch,words)) return GLRT_NATIVE_PROTOCOL_ERROR;
    for (i=0; i<2; i++)
        if (c->slots[i].occupied && c->slots[i].batch.tag == words[2]) owner = c->slots+i;
    if (!owner) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (c->tracking) {
        struct glrt_tracking_batch b = {owner->batch,c->trend.rate};
        associated = glrt_tracking_associated_solve(&b,epoch,c->sequence,words,&e);
    } else associated = glrt_native_associated_solve(&owner->batch,epoch,c->sequence,words,&e);
    if (associated ||
        (!c->stopping && words[27] != owner->received)) return GLRT_NATIVE_PROTOCOL_ERROR;
    n = snprintf(fitted,sizeof(fitted),"%" PRIu32 " %" PRIu32 " %" PRIu32
        " %.17g %.17g %.17g %.17g %.17g %" PRIu32 "\n",epoch,c->sequence,
        owner->first_frame+words[27],e.delay_correction_s,e.residual_cfo_hz,e.cfo_hz,
        e.coherence,e.linearized_coherence,e.rejection);
    if (n < 0 || (size_t)n >= sizeof(fitted)) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (c->ports.retain(c->ports.context,"estimate",fitted,(size_t)n)) return GLRT_NATIVE_RETENTION_ERROR;
    if (!c->stopping) bootstrap_observe(c,owner->first_frame+words[27],
        ((uint64_t)words[4]<<32)|words[3],&e);
    if (!c->stopping) {
        uint32_t frame = owner->first_frame+words[27];
        uint32_t last=last_authorized_support(c);
        int exhausted = (c->trend.history.initialized || c->authority_valid) && frame > last &&
            frame-last == 32 && c->next_frame == frame+1 &&
            c->next_frame < c->frames &&
            (!c->bootstrap_active || c->next_frame >= c->bootstrap.repeats);
        int observed = c->tracking ? glrt_tracking_trend_observe(&c->trend,epoch,frame,
            ((uint64_t)words[4]<<32)|words[3],words[28],&e) :
            glrt_native_trend_observe(&c->trend.history,epoch,frame,
            ((uint64_t)words[4]<<32)|words[3],&e);
        if (observed < 0) stop(c,GLRT_NATIVE_SOURCE_LOST);
        /* At the last permitted repeat, its full-pilot result arrives too
         * late to authorize the next consecutive job with 100 microseconds lead.
         * Retain this measurement, then require a fresh acquisition. Check
         * wall/source faults and the drained inventory on the next tick first. */
        if (observed > 0 && exhausted) c->acquisition_horizon_exhausted = 1;
    }
    snprintf(ack,sizeof(ack),"%08" PRIx32 " %08" PRIx32 "\n",epoch,c->sequence);
    if (command(c,attribute(c,"native_schedule_pop","tracking_pop"),ack)) return GLRT_NATIVE_IO_ERROR;
    c->sequence++;
    owner->received++;
    if (owner->received == owner->batch.repeats) owner->occupied = 0;
    return 0;
}

int glrt_native_controller_tick(struct glrt_native_controller *c)
{
    char raw[512];
    uint32_t w[24];
    uint64_t latest;
    double now;
    int n, rc;
    unsigned i;
    if (!c) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (c->done) return c->failure;
    now = c->ports.clock(c->ports.context);
    if (!isfinite(now)) return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
    if (now >= c->deadline) stop(c,GLRT_NATIVE_DEADLINE);
    if (c->stopping && now >= c->cleanup_deadline) return finish_error(c,GLRT_NATIVE_DEADLINE);
    n = c->ports.read(c->ports.context,attribute(c,"native_schedule_snapshot","tracking_snapshot"),raw,sizeof(raw));
    if (n <= 0 || (size_t)n > sizeof(raw)) return finish_error(c,GLRT_NATIVE_IO_ERROR);
    if (snapshot_parse(c,raw,(size_t)n,w)) return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
    if (c->clearing) {
        if (!snapshot_drained(c,w) || w[7] || w[6] || (w[5]&16))
            return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
        if (c->ports.retain(c->ports.context,"final",raw,(size_t)n))
            return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
        c->done = 1;
        return c->failure;
    }
    latest = ((uint64_t)w[4]<<32)|w[3];
    if (w[2] != c->trend.history.epoch) return finish_error(c,GLRT_NATIVE_SOURCE_LOST);
    if (w[6] || (w[5]&48) != 48 || w[9] || w[10] || w[11] || w[12] || w[13])
        stop(c,GLRT_NATIVE_SOURCE_LOST);
    if (!c->started) {
        if (c->stopping || !snapshot_drained(c,w) || w[7] || !(w[5]&1))
            return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
        if (c->handoff_pending) {
            if(c->frame_stride>1) {
                char cadence[128];
                int cadence_n=snprintf(cadence,sizeof(cadence),"stride %" PRIu32 " results %" PRIu32
                    " first %" PRIu32 " end %" PRIu32 "\n",c->frame_stride,c->result_limit,
                    c->next_frame,c->frames);
                if(cadence_n<0 || (size_t)cadence_n>=sizeof(cadence) ||
                   c->ports.retain(c->ports.context,"tracking_cadence",cadence,(size_t)cadence_n))
                    return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
            }
            rc=retain_history(c,"tracking_handoff",&c->trend);
            if (rc) return finish_error(c,rc);
            c->handoff_pending=0;
        }
        if (c->ports.retain(c->ports.context,"initial",raw,(size_t)n))
            return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
        c->started = 1;
        rc = submit(c,0,&c->slots[0].batch,c->next_frame,latest);
        if (rc) stop(c,rc);
        return GLRT_NATIVE_RUNNING;
    }
    if (!c->stopping && (w[7] != c->configured || w[15] != c->sequence))
        return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
    if (!c->stopping && c->acquisition_horizon_exhausted && snapshot_drained(c,w))
        stop(c,GLRT_NATIVE_ACQUISITION_LOST);
    if (c->stopping && !c->cancelled) {
        if (c->ports.retain(c->ports.context,"stopping",raw,(size_t)n))
            return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
        c->cancelled = 1;
        if (command(c,attribute(c,"native_schedule_command","tracking_command"),"2\n")) return finish_error(c,GLRT_NATIVE_IO_ERROR);
        return GLRT_NATIVE_RUNNING;
    }
    if (w[16]) {
        rc = consume(c);
        if (rc) return finish_error(c,rc);
        return GLRT_NATIVE_RUNNING; /* Refresh snapshot after POP before SUBMIT. */
    }
    if (snapshot_drained(c,w) && (c->stopping || c->configured == c->result_limit)) {
        if (c->ports.retain(c->ports.context,"drained",raw,(size_t)n))
            return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
        c->clearing = 1;
        if (command(c,attribute(c,"native_schedule_command","tracking_command"),"4\n")) return finish_error(c,GLRT_NATIVE_IO_ERROR);
        return GLRT_NATIVE_RUNNING;
    }
    if (!c->stopping && (w[5]&1) && c->configured < c->result_limit) {
        for (i=0; i<2; i++) if (!c->slots[i].occupied) {
            struct glrt_native_batch b;
            double rate;
            uint32_t count = c->frame_stride>1 ? 1 : c->frames-c->next_frame;
            uint32_t authorized = last_authorized_support(c);
            int predicted;
            if (count > 16) count = 16;
            if(count>c->result_limit-c->configured) count=c->result_limit-c->configured;
            /* Use the remaining valid native horizon even when a full batch
             * would exceed it. No job may extend past last_supported + 32. */
            if ((c->trend.history.initialized || c->authority_valid) &&
                c->next_frame >= authorized && c->next_frame-authorized <= 32) {
                uint32_t remaining = 33-(c->next_frame-authorized);
                if (count > remaining) count = remaining;
            }
            if (c->next_tag == UINT32_MAX) return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
            if (c->tracking) {
                struct glrt_tracking_batch next;
                predicted = !glrt_tracking_trend_batch(&c->trend,c->next_frame,count,c->next_tag,
                    c->slots[0].batch.seed,&next,&rate);
                if (!predicted && c->authority_valid)
                    predicted = !glrt_tracking_trend_batch(&c->authority,c->next_frame,count,c->next_tag,
                        c->slots[0].batch.seed,&next,&rate);
                if (predicted) b = next.prediction;
            } else predicted = !glrt_native_trend_batch(&c->trend.history,c->next_frame,count,c->next_tag,
                    c->slots[0].batch.seed,&b,&rate);
            if (predicted) c->bootstrap_active = 0;
            else if (c->bootstrap_active && c->next_frame < c->bootstrap.repeats &&
                     (c->bootstrap_offset_valid || c->sequence+4 >= c->next_frame)) {
                /* Let the first supported result correct the continuation.
                 * Without one, queue with four unconsumed opportunities left
                 * instead of waiting until the preceding batch has ended. */
                count = c->bootstrap.repeats-c->next_frame;
                if (count > 4) count = 4;
                if (bootstrap_slice(&c->bootstrap,c->next_frame,count,c->next_tag,&b))
                    return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
                bootstrap_correct(c,&b);
                predicted = 1;
            }
            if (predicted) {
                c->authority_wait_until=0;
                if (c->ports.retain(c->ports.context,"before_submit",raw,(size_t)n))
                    return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
                rc = submit(c,i,&b,c->next_frame,latest);
                c->next_tag++;
                if (rc) stop(c,rc);
            } else if (snapshot_drained(c,w)) {
                /* A separately scheduled coarse observer can be one cadence
                 * behind the sparse native frontier even while it remains
                 * strongly supported. Give it ten 12-ms observer intervals
                 * to publish a newer authority, without extending the fixed
                 * 32-frame prediction horizon. The global deadline remains
                 * authoritative and a missing refresh still reacquires. */
                if(c->authority_valid && !c->authority_wait_until)
                    c->authority_wait_until=now+.12;
                else if(!c->authority_valid || now>=c->authority_wait_until)
                    stop(c,GLRT_NATIVE_ACQUISITION_LOST);
            }
            break;
        }
    }
    return GLRT_NATIVE_RUNNING;
}
