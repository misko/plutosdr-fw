/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_transport.h"
#include <ctype.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static uint32_t bank_id(uint32_t rate)
{
    return rate == 2500000 ? UINT32_C(0xdc509401) : UINT32_C(0xb04a2fab);
}

int glrt_tracking_batch_encode(const struct glrt_tracking_batch *t, char *text, size_t size)
{
    const struct glrt_native_batch *b;
    int n;
    if (!glrt_tracking_batch_valid(t) || !text || !size) return -1;
    b=&t->prediction;
    n=snprintf(text,size,"GLT1 %08" PRIx32 " %08" PRIx32 " %08" PRIx32
        " %" PRIx32 " %" PRIx32 " %" PRIx64 " %" PRIx32
        " %" PRIx64 " %" PRIx64 " %" PRIx64 " %" PRIx32 " %" PRIx32 " %" PRIx64 "\n",
        GLRT_TRACKING_VERSION,t->rate,bank_id(t->rate),b->epoch,b->tag,b->start,b->fraction,
        b->period,b->step,b->delta,b->seed,b->repeats,b->expires);
    if (n<0 || (size_t)n>=size) { text[0]=0; return -1; }
    return n;
}

int glrt_tracking_batch_parse(const char *text, size_t size, struct glrt_tracking_batch *out)
{
    struct glrt_tracking_batch candidate;
    struct glrt_tracking_job last;
    uint64_t v[13];
    size_t at=5;
    unsigned i;
    if (!out || !text || size<=5 || memcmp(text,"GLT1 ",5)) return -1;
    for (i=0;i<13;i++) {
        unsigned digits=0;
        uint64_t value=0;
        while (at<size && isspace((unsigned char)text[at])) at++;
        while (at<size && !isspace((unsigned char)text[at])) {
            unsigned char ch=(unsigned char)text[at++];
            unsigned digit;
            if (digits==16) return -1;
            if (ch>='0' && ch<='9') digit=ch-'0';
            else if (ch>='a' && ch<='f') digit=ch-'a'+10;
            else if (ch>='A' && ch<='F') digit=ch-'A'+10;
            else return -1;
            value=(value<<4)|digit;
            digits++;
        }
        if (!digits || (i<3 && digits!=8)) return -1;
        v[i]=value;
    }
    while (at<size && isspace((unsigned char)text[at])) at++;
    if (at!=size || v[0]!=GLRT_TRACKING_VERSION || v[1]>UINT32_MAX ||
        v[2]!=bank_id((uint32_t)v[1]) || v[3]>UINT32_MAX || v[4]>UINT32_MAX ||
        v[6]>65535 || v[10]>UINT32_MAX || v[11]>64) return -1;
    candidate.prediction=(struct glrt_native_batch){(uint32_t)v[3],(uint32_t)v[4],v[5],v[7],v[8],v[9],v[12],
        (uint32_t)v[6],(uint32_t)v[10],(uint32_t)v[11]};
    candidate.rate=(uint32_t)v[1];
    if (!glrt_tracking_batch_valid(&candidate) ||
        glrt_tracking_prediction(&candidate,candidate.prediction.repeats-1,&last)) return -1;
    *out=candidate;
    return 0;
}

static int parse_words(const char *text, size_t size, const char *prefix,
                       unsigned count, uint32_t *parsed)
{
    size_t pos=strlen(prefix);
    unsigned i,j;
    if (!text || size<=pos || memcmp(text,prefix,pos) ||
        !isspace((unsigned char)text[pos])) return -1;
    for (i=0;i<count;i++) {
        uint32_t value=0;
        while (pos<size && isspace((unsigned char)text[pos])) pos++;
        if (size-pos<8) return -1;
        for (j=0;j<8;j++) {
            unsigned char c=(unsigned char)text[pos++];
            unsigned digit;
            if (c>='0' && c<='9') digit=c-'0';
            else if (c>='a' && c<='f') digit=c-'a'+10;
            else if (c>='A' && c<='F') digit=c-'A'+10;
            else return -1;
            value=(value<<4)|digit;
        }
        parsed[i]=value;
        if (pos<size && !isspace((unsigned char)text[pos])) return -1;
    }
    while (pos<size && isspace((unsigned char)text[pos])) pos++;
    return pos==size ? 0 : -1;
}

int glrt_tracking_head_parse(const char *text, size_t size, uint32_t *epoch, uint32_t w[32])
{
    uint32_t parsed[34];
    if (!epoch || !w || parse_words(text,size,"GLT1",34,parsed) ||
        parsed[0]!=GLRT_TRACKING_VERSION || !parsed[1]) return -1;
    *epoch=parsed[1];
    memcpy(w,parsed+2,32*sizeof(*w));
    return 0;
}

static int snapshot_valid(const uint32_t *w)
{
    const struct glrt_tracking_profile *p;
    uint64_t terminal=0;
    unsigned n;
    if (!w || w[0]!=GLRT_TRACKING_MAGIC || !w[1] || (w[5]&~0xffU) || (w[6]&~0xfU) ||
        !(p=glrt_tracking_profile_get(w[20],0)) || w[21]!=p->samples ||
        w[22]!=bank_id(w[20]) || w[23]!=p->reference_phases) return 0;
    for (n=8;n<14;n++) terminal+=w[n];
    return terminal<=w[7] && w[15]<=w[14] && w[14]<=w[8] && w[8]-w[14]<=1 &&
        w[16]==w[14]-w[15] && w[16]<=w[17] && w[17]<=64;
}

int glrt_tracking_snapshot_parse(const char *text, size_t size, uint32_t w[24])
{
    uint32_t parsed[25];
    if (!w || parse_words(text,size,"GLT1SNAP",25,parsed) ||
        parsed[0]!=GLRT_TRACKING_VERSION || !snapshot_valid(parsed+1)) return -1;
    memcpy(w,parsed+1,24*sizeof(*w));
    return 0;
}

int glrt_tracking_snapshot_drained(const uint32_t w[24])
{
    uint64_t terminal=0;
    unsigned n;
    if (!snapshot_valid(w) || (w[5]&4) || w[16]) return 0;
    for (n=8;n<14;n++) terminal+=w[n];
    return terminal==w[7] && w[8]==w[14] && w[14]==w[15];
}

int glrt_tracking_associated_solve(const struct glrt_tracking_batch *t,
    uint32_t epoch, uint32_t sequence, const uint32_t w[32], struct glrt_native_estimate *out)
{
    const struct glrt_tracking_profile *p;
    struct glrt_tracking_job job;
    struct glrt_tracking_moments moments;
    if (!out) return -1;
    memset(out,0,sizeof(*out));
    out->rejection=GLRT_NATIVE_FAULT;
    if (!w || !t || !glrt_tracking_batch_valid(t) || w[0]!=GLRT_TRACKING_MAGIC ||
        epoch!=t->prediction.epoch || w[1]!=sequence || w[2]!=t->prediction.tag ||
        w[25]!=t->rate || w[29]!=bank_id(t->rate) || w[30]!=GLRT_TRACKING_VERSION || w[31] ||
        !(p=glrt_tracking_profile_get(t->rate,w[28])) || w[26]!=p->samples || (w[8]&~0x3ffU) ||
        glrt_tracking_prediction(t,w[27],&job) || w[28]!=job.reference_phase ||
        w[5]!=t->prediction.seed || w[6]!=job.phase_step ||
        (((uint64_t)w[4]<<32)|w[3])!=job.start) return -1;
    moments.start=job.start;
    moments.count=w[7];
    /* Scheduled abort/source faults remain in the retained packet. The solver
     * takes engine faults only; map either wrapper fault to generic failure,
     * then let it validate counts and canonical moments even on failed jobs. */
    moments.fault=(w[8]&0xffU) | ((w[8]&0x300U) ? 1U : 0U);
    moments.phase_step=w[6];
    memcpy(moments.words,w+9,sizeof(moments.words));
    return glrt_tracking_solve(t->rate,w[28],&moments,out);
}
