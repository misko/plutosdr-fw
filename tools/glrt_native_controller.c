/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_native_controller.h"
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

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
        command(c,"native_schedule_command","2\n");
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
    c->deadline = now+seconds;
    c->slots[0].batch = *b;
    c->next_tag = b->tag+1;
    glrt_native_trend_reset(&c->trend,b->epoch);
    return 0;
}

static int submit(struct glrt_native_controller *c, unsigned slot,
                  const struct glrt_native_batch *b, uint32_t first, uint64_t latest)
{
    char encoded[256], record[320], raw[512];
    uint64_t start;
    uint32_t phase, w[20];
    double now;
    int n = glrt_native_batch_encode(b,encoded,sizeof(encoded));
    if (n < 0 || glrt_native_prediction(b,0,&start,&phase) ||
        start <= latest || start-latest < 6000) return GLRT_NATIVE_DEADLINE;
    n = snprintf(record,sizeof(record),"frame %" PRIu32 " %s",first,encoded);
    if (n < 0 || (size_t)n >= sizeof(record)) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (c->ports.retain(c->ports.context,"descriptor",record,(size_t)n))
        return GLRT_NATIVE_RETENTION_ERROR;
    /* Storage can block. Re-read the source after retention, rather than
     * submitting against the pre-retention source snapshot. Hardware still
     * accounts any lateness caused by preemption during the final write. */
    n = c->ports.read(c->ports.context,"native_schedule_snapshot",raw,sizeof(raw));
    if (n <= 0 || (size_t)n > sizeof(raw)) return GLRT_NATIVE_IO_ERROR;
    if (glrt_native_snapshot_parse(raw,(size_t)n,w)) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (w[2] != b->epoch || w[6] || (w[5]&48) != 48 ||
        w[9] || w[10] || w[11] || w[12] || w[13]) return GLRT_NATIVE_SOURCE_LOST;
    if (w[7] != c->configured || w[15] != c->sequence || !(w[5]&1))
        return GLRT_NATIVE_PROTOCOL_ERROR;
    latest = ((uint64_t)w[4]<<32)|w[3];
    now = c->ports.clock(c->ports.context);
    if (!isfinite(now)) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (now >= c->deadline || start <= latest || start-latest < 6000)
        return GLRT_NATIVE_DEADLINE;
    /* Track even an uncertain submission, so its eventual heads can be
     * retained/associated during cancellation. Never retry SUBMIT. */
    c->slots[slot] = (struct glrt_native_owned_batch){*b,first,0,1};
    c->next_frame = first+b->repeats;
    if (command(c,"native_schedule_submit",encoded)) return GLRT_NATIVE_IO_ERROR;
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
    int n = c->ports.read(c->ports.context,"native_schedule_result",raw,sizeof(raw));
    if (n <= 0 || (size_t)n > sizeof(raw)) return GLRT_NATIVE_IO_ERROR;
    if (c->ports.retain(c->ports.context,"head",raw,(size_t)n)) return GLRT_NATIVE_RETENTION_ERROR;
    if (glrt_native_head_parse(raw,(size_t)n,&epoch,words)) return GLRT_NATIVE_PROTOCOL_ERROR;
    for (i=0; i<2; i++)
        if (c->slots[i].occupied && c->slots[i].batch.tag == words[2]) owner = c->slots+i;
    if (!owner || glrt_native_associated_solve(&owner->batch,epoch,c->sequence,words,&e) ||
        (!c->stopping && words[27] != owner->received)) return GLRT_NATIVE_PROTOCOL_ERROR;
    n = snprintf(fitted,sizeof(fitted),"%" PRIu32 " %" PRIu32 " %" PRIu32
        " %.17g %.17g %.17g %.17g %.17g %" PRIu32 "\n",epoch,c->sequence,
        owner->first_frame+words[27],e.delay_correction_s,e.residual_cfo_hz,e.cfo_hz,
        e.coherence,e.linearized_coherence,e.rejection);
    if (n < 0 || (size_t)n >= sizeof(fitted)) return GLRT_NATIVE_PROTOCOL_ERROR;
    if (c->ports.retain(c->ports.context,"estimate",fitted,(size_t)n)) return GLRT_NATIVE_RETENTION_ERROR;
    if (!c->stopping && glrt_native_trend_observe(&c->trend,epoch,
            owner->first_frame+words[27],((uint64_t)words[4]<<32)|words[3],&e) < 0)
        stop(c,GLRT_NATIVE_SOURCE_LOST);
    snprintf(ack,sizeof(ack),"%08" PRIx32 " %08" PRIx32 "\n",epoch,c->sequence);
    if (command(c,"native_schedule_pop",ack)) return GLRT_NATIVE_IO_ERROR;
    c->sequence++;
    owner->received++;
    if (owner->received == owner->batch.repeats) owner->occupied = 0;
    return 0;
}

int glrt_native_controller_tick(struct glrt_native_controller *c)
{
    char raw[512];
    uint32_t w[20];
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
    n = c->ports.read(c->ports.context,"native_schedule_snapshot",raw,sizeof(raw));
    if (n <= 0 || (size_t)n > sizeof(raw)) return finish_error(c,GLRT_NATIVE_IO_ERROR);
    if (glrt_native_snapshot_parse(raw,(size_t)n,w)) return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
    if (c->clearing) {
        if (!glrt_native_snapshot_drained(w) || w[7] || w[6] || (w[5]&16))
            return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
        if (c->ports.retain(c->ports.context,"final",raw,(size_t)n))
            return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
        c->done = 1;
        return c->failure;
    }
    latest = ((uint64_t)w[4]<<32)|w[3];
    if (w[2] != c->trend.epoch) return finish_error(c,GLRT_NATIVE_SOURCE_LOST);
    if (w[6] || (w[5]&48) != 48 || w[9] || w[10] || w[11] || w[12] || w[13])
        stop(c,GLRT_NATIVE_SOURCE_LOST);
    if (!c->started) {
        if (c->stopping || !glrt_native_snapshot_drained(w) || w[7] || !(w[5]&1))
            return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
        if (c->ports.retain(c->ports.context,"initial",raw,(size_t)n))
            return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
        c->started = 1;
        rc = submit(c,0,&c->slots[0].batch,0,latest);
        if (rc) stop(c,rc);
        return GLRT_NATIVE_RUNNING;
    }
    if (!c->stopping && (w[7] != c->configured || w[15] != c->sequence))
        return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
    if (c->stopping && !c->cancelled) {
        if (c->ports.retain(c->ports.context,"stopping",raw,(size_t)n))
            return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
        c->cancelled = 1;
        if (command(c,"native_schedule_command","2\n")) return finish_error(c,GLRT_NATIVE_IO_ERROR);
        return GLRT_NATIVE_RUNNING;
    }
    if (w[16]) {
        rc = consume(c);
        if (rc) return finish_error(c,rc);
        return GLRT_NATIVE_RUNNING; /* Refresh snapshot after POP before SUBMIT. */
    }
    if (glrt_native_snapshot_drained(w) && (c->stopping || c->next_frame == c->frames)) {
        if (c->ports.retain(c->ports.context,"drained",raw,(size_t)n))
            return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
        c->clearing = 1;
        if (command(c,"native_schedule_command","4\n")) return finish_error(c,GLRT_NATIVE_IO_ERROR);
        return GLRT_NATIVE_RUNNING;
    }
    if (!c->stopping && (w[5]&1) && c->next_frame < c->frames) {
        for (i=0; i<2; i++) if (!c->slots[i].occupied) {
            struct glrt_native_batch b;
            double rate;
            uint32_t count = c->frames-c->next_frame;
            if (count > 16) count = 16;
            if (c->next_tag == UINT32_MAX) return finish_error(c,GLRT_NATIVE_PROTOCOL_ERROR);
            if (!glrt_native_trend_batch(&c->trend,c->next_frame,count,c->next_tag,
                    c->slots[0].batch.seed,&b,&rate)) {
                if (c->ports.retain(c->ports.context,"before_submit",raw,(size_t)n))
                    return finish_error(c,GLRT_NATIVE_RETENTION_ERROR);
                rc = submit(c,i,&b,c->next_frame,latest);
                c->next_tag++;
                if (rc) stop(c,rc);
            } else if (glrt_native_snapshot_drained(w)) stop(c,GLRT_NATIVE_ACQUISITION_LOST);
            break;
        }
    }
    return GLRT_NATIVE_RUNNING;
}
