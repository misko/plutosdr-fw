/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_native_schedule.h"
#include <ctype.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#define MASK48 UINT64_C(0xffffffffffff)
#define SAMPLES 79200U

int glrt_native_batch_valid(const struct glrt_native_batch *b)
{
    return b && b->epoch && b->tag && b->repeats && b->repeats <= 64 &&
        b->start >= 512 && b->expires >= b->start && b->fraction <= 65535 &&
        b->period >= UINT64_C(79328)*65536 && b->period <= UINT64_C(81000)*65536 &&
        b->step <= MASK48 && b->delta <= MASK48;
}

int glrt_native_batch_encode(const struct glrt_native_batch *b, char *text, size_t size)
{
    int n;
    if (!glrt_native_batch_valid(b) || !text || !size) return -1;
    n = snprintf(text,size,"%" PRIx32 " %" PRIx32 " %" PRIx64 " %" PRIx32
        " %" PRIx64 " %" PRIx64 " %" PRIx64 " %" PRIx32 " %" PRIx32 " %" PRIx64 "\n",
        b->epoch,b->tag,b->start,b->fraction,b->period,b->step,b->delta,b->seed,b->repeats,b->expires);
    if (n < 0 || (size_t)n >= size) {
        text[0] = 0;
        return -1;
    }
    return n;
}

int glrt_native_prediction(const struct glrt_native_batch *b, unsigned repeat,
                           uint64_t *start, uint32_t *step)
{
    uint64_t advance, whole, carrier, rounded;
    uint32_t fraction;
    if (!glrt_native_batch_valid(b) || repeat >= b->repeats || !start || !step) return -1;
    /* At most 63 periods; these products fit u64 even for modulo-48 delta. */
    advance = b->fraction+repeat*b->period;
    whole = advance >> 16;
    fraction = (uint32_t)(advance & 65535);
    if (b->start > UINT64_MAX-whole) return -1;
    rounded = b->start+whole;
    if (fraction > 32768 || (fraction == 32768 && (rounded & 1))) {
        if (rounded == UINT64_MAX) return -1;
        rounded++;
    }
    if (rounded > UINT64_MAX-(SAMPLES-1) || rounded+SAMPLES-1 > b->expires) return -1;
    carrier = (b->step+repeat*b->delta) & MASK48;
    fraction = (uint32_t)(carrier & 65535);
    carrier >>= 16;
    carrier += fraction > 32768 || (fraction == 32768 && (carrier & 1));
    *start = rounded;
    *step = (uint32_t)carrier;
    return 0;
}

static int parse_words(const char *text, size_t size, const char *prefix,
                       unsigned count, uint32_t *words)
{
    size_t pos = strlen(prefix);
    unsigned i, digit;
    if (!text || size <= pos || memcmp(text,prefix,pos) || !isspace((unsigned char)text[pos]))
        return -1;
    for (i=0; i<count; i++) {
        uint32_t value = 0;
        while (pos < size && isspace((unsigned char)text[pos])) pos++;
        if (size-pos < 8) return -1;
        for (digit=0; digit<8; digit++) {
            unsigned char c = (unsigned char)text[pos++];
            unsigned nibble;
            if (c >= '0' && c <= '9') nibble = c-'0';
            else if (c >= 'a' && c <= 'f') nibble = c-'a'+10;
            else if (c >= 'A' && c <= 'F') nibble = c-'A'+10;
            else return -1;
            value = (value << 4) | nibble;
        }
        words[i] = value;
        if (pos < size && !isspace((unsigned char)text[pos])) return -1;
    }
    while (pos < size && isspace((unsigned char)text[pos])) pos++;
    return pos == size ? 0 : -1;
}

int glrt_native_head_parse(const char *text, size_t size, uint32_t *epoch, uint32_t w[32])
{
    uint32_t parsed[34];
    if (!epoch || !w || parse_words(text,size,"GLS1",34,parsed) ||
        parsed[0] != 0x10000 || !parsed[1]) return -1;
    *epoch = parsed[1];
    memcpy(w,parsed+2,32*sizeof(*w));
    return 0;
}

static int snapshot_valid(const uint32_t *w)
{
    uint64_t terminal = 0;
    unsigned n;
    if (!w || w[0] != 0x474c5331U || !w[1] || (w[5] & ~0xffU) || (w[6] & ~0xfU))
        return 0;
    for (n=8; n<14; n++) terminal += w[n];
    return terminal <= w[7] && w[15] <= w[14] && w[14] <= w[8] && w[8]-w[14] <= 1 &&
        w[16] == w[14]-w[15] && w[16] <= w[17] && w[17] <= 64;
}

int glrt_native_snapshot_parse(const char *text, size_t size, uint32_t w[20])
{
    uint32_t parsed[21];
    if (!w || parse_words(text,size,"GLS1SNAP",21,parsed) ||
        parsed[0] != 0x10000 || !snapshot_valid(parsed+1)) return -1;
    memcpy(w,parsed+1,20*sizeof(*w));
    return 0;
}

int glrt_native_snapshot_drained(const uint32_t w[20])
{
    uint64_t terminal = 0;
    unsigned n;
    if (!snapshot_valid(w) || (w[5] & 4) || w[16]) return 0;
    for (n=8; n<14; n++) terminal += w[n];
    return terminal == w[7] && w[8] == w[14] && w[14] == w[15];
}

int glrt_native_associated_solve(const struct glrt_native_batch *b,
    uint32_t epoch, uint32_t sequence, const uint32_t w[32], struct glrt_native_estimate *out)
{
    uint64_t start;
    uint32_t step;
    int rc;
    if (!out) return -1;
    /* A failed association cannot leave an earlier supported fit in output. */
    memset(out,0,sizeof(*out));
    out->rejection = GLRT_NATIVE_FAULT;
    if (!w || !b || epoch != b->epoch || w[1] != sequence || w[2] != b->tag ||
        glrt_native_prediction(b,w[27],&start,&step) || w[5] != b->seed || w[6] != step ||
        (((uint64_t)w[4] << 32) | w[3]) != start) return -1;
    rc = glrt_native_solve(w,out);
    if (rc) out->rejection = GLRT_NATIVE_FAULT;
    return rc;
}
