/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_cpu_coarse.h"
#include <math.h>
#include <string.h>

static uint32_t root(uint64_t n)
{
    uint64_t r=(uint64_t)sqrt((double)n);
    /* Correct floating conversion at perfect-square boundaries. Supported
     * CI16/CI12 powers are below 2^63, so these products cannot wrap u64. */
    while(r*r>n) r--;
    while((r+1)*(r+1)<=n) r++;
    return (uint32_t)r;
}

static unsigned distance(unsigned a, unsigned b)
{
    return a>b ? a-b : b-a;
}

static int better(const struct glrt_cpu_coarse_peak *a, const struct glrt_cpu_coarse_peak *b)
{
    if(a->score!=b->score) return a->score>b->score;
    if(distance(a->frequency,5)!=distance(b->frequency,5))
        return distance(a->frequency,5)<distance(b->frequency,5);
    if(a->epoch!=b->epoch) return a->epoch<b->epoch;
    return a->frequency<b->frequency;
}

int glrt_cpu_coarse_search(struct glrt_cpu_coarse_workspace *w, const int16_t *iq,
    const int16_t c[12][11][11][2], int (*poll)(void *), void *context)
{
    static const unsigned offsets[5]={0,3333,6667,10000,13333};
    uint64_t energy[12][11];
    unsigned e,s,f,r,t,k;
    if(!w) return -1;
    memset(w,0,sizeof(*w));
    if(!iq || !c || !poll || poll(context)) return -1;
    for(s=0;s<12;s++) for(f=0;f<11;f++) {
        uint64_t sum=0;
        for(t=0;t<11;t++) for(k=0;k<2;k++) {
            int64_t v=c[s][f][t][k];
            if(v < -2048 || v > 2047) return -1;
            sum+=(uint64_t)(v*v);
        }
        energy[s][f]=sum;
    }
    for(e=0;e<GLRT_CPU_COARSE_EPOCHS;e++) {
        uint32_t totals[11]={0};
        unsigned support=0;
        if(!(e%16) && poll(context)) return -1;
        for(s=0;s<12;s++) for(r=0;r<5;r++) {
            unsigned start=e+22+286*s+offsets[r];
            uint64_t observed=0;
            if(start+11>GLRT_CPU_COARSE_SAMPLES) continue;
            support++;
            for(t=0;t<11;t++) {
                int64_t i=iq[2*(start+t)], q=iq[2*(start+t)+1];
                observed+=(uint64_t)(i*i+q*q);
            }
            for(f=0;f<11;f++) {
                int64_t re=0,im=0;
                uint32_t numerator,denominator;
                uint64_t score;
                for(t=0;t<11;t++) {
                    int64_t i=iq[2*(start+t)],q=iq[2*(start+t)+1];
                    int64_t a=c[s][f][t][0],b=c[s][f][t][1];
                    re+=i*a+q*b;im+=q*a-i*b;
                }
                numerator=root((uint64_t)(re*re)+(uint64_t)(im*im));
                denominator=root(observed*energy[s][f]);
                score=denominator ? ((uint64_t)numerator<<16)/denominator : 0;
                totals[f]+=(uint32_t)(score>65536 ? 65536 : score);
            }
        }
        for(f=0;f<11;f++) w->grid[f][e]=support ? totals[f]/support : 0;
        w->completed_epochs=e+1;
    }
    for(k=0;k<8;k++) {
        struct glrt_cpu_coarse_peak best={0,0,0};
        for(f=0;f<11;f++) for(e=0;e<GLRT_CPU_COARSE_EPOCHS;e++) {
            struct glrt_cpu_coarse_peak p={e,f,w->grid[f][e]};
            uint32_t left=e ? w->grid[f][e-1] : 0;
            uint32_t right=e+1<GLRT_CPU_COARSE_EPOCHS ? w->grid[f][e+1] : 0;
            if(!p.score || p.score<left || p.score<right || (p.score==left && p.score==right)) continue;
            for(r=0;r<k;r++) {
                unsigned d=distance(e,w->peaks[r].epoch);
                if(d>GLRT_CPU_COARSE_EPOCHS/2) d=GLRT_CPU_COARSE_EPOCHS-d;
                if(d<20 && distance(f,w->peaks[r].frequency)<=1) break;
            }
            if(r==k && better(&p,&best)) best=p;
        }
        if(!best.score) break;
        w->peaks[k]=best;
    }
    if(poll(context)) { memset(w->peaks,0,sizeof(w->peaks)); return -1; }
    w->count=k;
    return 0;
}
