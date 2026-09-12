/* SPDX-License-Identifier: GPL-2.0 */
#define _POSIX_C_SOURCE 200809L
#include "glrt_capture_source.h"
#include <errno.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>

#define RATE 2500000U

static uint64_t pair(const uint32_t *words, unsigned index)
{
    return words[index]|((uint64_t)words[index+1]<<32);
}

static int number(const char *text, unsigned base, uint64_t maximum, uint64_t *out)
{
    const char *at;
    char *end;
    uintmax_t value;
    if (!text || !*text) return -1;
    for (at=text;*at;at++)
        if (!(*at>='0' && *at<='9') && !(base==16 &&
            ((*at>='a' && *at<='f') || (*at>='A' && *at<='F')))) return -1;
    errno=0; value=strtoumax(text,&end,base);
    if (errno || *end || value>maximum) return -1;
    *out=(uint64_t)value;
    return 0;
}

static int parse_snapshot(const char *data, size_t size, struct glrt_capture_snapshot *out,
    int iq_tracking)
{
    char raw[4096], *fields[78], *save, *token;
    struct glrt_capture_snapshot s;
    uint64_t header[12], value, total=0;
    unsigned i;
    if (!data || !out || !size || size>=sizeof(raw) || memchr(data,0,size)) return -1;
    memcpy(raw,data,size);raw[size]=0;
    token=strtok_r(raw," \t\r\n",&save);
    for (i=0;i<78;i++) {
        if (!token) return -1;
        fields[i]=token;token=strtok_r(NULL," \t\r\n",&save);
    }
    if (token || strcmp(fields[0],iq_tracking ? "GLI1" : "GLA1") || strcmp(fields[1],"00010000")) return -1;
    for (i=2;i<14;i++) {
        if (i==7) {
            const char *digits=fields[i]+(fields[i][0]=='-');
            if (number(digits,10,fields[i][0]=='-' ? UINT64_C(2147483648) : 0,&value)) return -1;
            header[i-2]=value;
        } else if (number(fields[i],10,i>=8 && i<=12 ? UINT64_MAX : UINT32_MAX,&header[i-2]))
            return -1;
    }
    if ((iq_tracking ? (header[0]!=30000000 && header[0]!=60000000) : header[0]!=RATE) ||
        header[1]!=RATE || !header[2] || header[3]>1) return -1;
    memset(&s,0,sizeof(s));
    s.generation=(uint32_t)header[2];s.recovery_failed=(uint32_t)header[3];
    s.readback_rate=(uint32_t)header[4];s.dma_error=(int32_t)-(int64_t)header[5];
    for (i=0;i<5;i++) s.cpu[i]=header[6+i];
    s.cpu_fault=(uint32_t)header[11];
    for (i=0;i<64;i++) {
        if (strlen(fields[14+i])!=8 || number(fields[14+i],16,UINT32_MAX,&value)) return -1;
        s.words[i]=(uint32_t)value;
    }
    if (s.words[62]!=header[0] || s.words[63]!=(iq_tracking ? header[0]/30000000*636 : 0) ||
        s.words[19]>>12 || s.words[23]>1 ||
        s.words[48]>>16 || s.words[49]>>14 || s.words[52]>>11 || s.words[61]>>4 ||
        s.words[57]>65536 || s.words[58]>65536 || s.words[59]>65536 || s.words[60]>1) return -1;
    if (!(s.cpu_fault&1)) {
        for (i=1;i<5;i++) {
            if (s.cpu[i]>UINT64_MAX-total) return -1;
            total+=s.cpu[i];
        }
        if (s.cpu[0]!=total) return -1;
    }
    *out=s;
    return 0;
}

int glrt_capture_snapshot_parse(const char *data, size_t size, struct glrt_capture_snapshot *out)
{
    return parse_snapshot(data,size,out,0);
}

int glrt_iq_tracking_snapshot_parse(const char *data, size_t size, struct glrt_capture_snapshot *out)
{
    return parse_snapshot(data,size,out,1);
}

static int healthy(const struct glrt_capture_snapshot *s, uint32_t visit)
{
    unsigned i;
    const uint32_t *w=s->words;
    if (!s->generation || s->words[62]!=RATE || s->words[63] ||
        s->recovery_failed || s->dma_error || s->readback_rate!=RATE || s->cpu_fault ||
        w[20]!=visit || w[17] || w[18] || w[44]!=w[45] || w[46]!=w[47]) return 0;
    for (i=30;i<40;i++) if (w[i]) return 0;
    for (i=50;i<57;i++) if (w[i]) return 0;
    return !w[61];
}

int glrt_capture_source_begin(struct glrt_capture_source *c, uint32_t visit,
    uint64_t samples, const struct glrt_capture_snapshot *baseline)
{
    if (!c) return -1;
    memset(c,0,sizeof(*c));
    if (!visit || !samples || !baseline || !healthy(baseline,visit) ||
        (baseline->words[19]&31) || pair(baseline->words,4) || pair(baseline->words,6)) return -1;
    c->baseline=*baseline;c->visit=visit;c->limit=samples;c->valid=1;
    c->generation=baseline->generation;
    c->cpu_read=baseline->cpu[0];c->cpu_pushed=baseline->cpu[1];
    return 0;
}

int glrt_capture_source_take(struct glrt_capture_source *c, const struct glrt_capture_snapshot *s,
    size_t samples, uint64_t *first, uint64_t *source_now)
{
    uint64_t origin, admitted, delivered, latest, end;
    unsigned i;
    if (first) *first=0;
    if (source_now) *source_now=0;
    if (!c) return -1;
    if (!c->valid || !s || !first || !source_now || !samples || !healthy(s,c->visit) ||
        c->received>c->limit || samples>c->limit-c->received) goto fault;
    for (i=2;i<5;i++) if (s->cpu[i]!=c->baseline.cpu[i]) goto fault;
    if (s->cpu[0]<c->cpu_read || s->cpu[1]<c->cpu_pushed ||
        !(uint32_t)(s->generation-c->generation) ||
        (uint32_t)(s->generation-c->generation)>UINT32_MAX/2) goto fault;
    origin=pair(s->words,0);admitted=pair(s->words,4);delivered=pair(s->words,6);
    latest=pair(s->words,42);
    if (!(s->words[19]&8) || !admitted || admitted>c->limit || delivered>admitted ||
        admitted<c->admitted || delivered<c->delivered ||
        origin>UINT64_MAX-admitted || pair(s->words,2)!=origin+admitted-1 ||
        latest<origin+admitted-1 || latest==UINT64_MAX ||
        delivered<c->received+samples || (c->bound && (origin!=c->first || latest<c->last_source))) goto fault;
    end=origin+c->received+samples;
    *first=origin+c->received;*source_now=latest+1;
    c->first=origin;c->received=end-origin;c->last_source=latest;c->bound=1;
    c->admitted=admitted;c->delivered=delivered;c->generation=s->generation;
    c->cpu_read=s->cpu[0];c->cpu_pushed=s->cpu[1];
    return 0;
fault:
    c->valid=0;
    return -1;
}
