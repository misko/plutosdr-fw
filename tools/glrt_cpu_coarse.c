/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_cpu_coarse.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>
#ifdef __ARM_NEON
#include <arm_neon.h>
#endif

static void dot11(const int16_t *iq,const int16_t c[11][2],int32_t *real,int32_t *imag)
{
    unsigned t=0;
    int32_t re=0,im=0;
#ifdef __ARM_NEON
    int32x4_t vr=vdupq_n_s32(0),vi=vdupq_n_s32(0);
    for(;t<8;t+=4) {
        int16x4x2_t x=vld2_s16(iq+2*t),a=vld2_s16(c[t]);
        vr=vmlal_s16(vr,x.val[0],a.val[0]);
        vr=vmlal_s16(vr,x.val[1],a.val[1]);
        vi=vmlal_s16(vi,x.val[1],a.val[0]);
        vi=vmlsl_s16(vi,x.val[0],a.val[1]);
    }
    {
        int32x2_t r=vadd_s32(vget_low_s32(vr),vget_high_s32(vr));
        int32x2_t i=vadd_s32(vget_low_s32(vi),vget_high_s32(vi));
        re=vget_lane_s32(vpadd_s32(r,r),0);
        im=vget_lane_s32(vpadd_s32(i,i),0);
    }
#endif
    /* Even CI16 rails with full CI12 coefficients fit signed i32:
     * 11 * 2 * 32768 * 2048 = 1,476,395,008. Every SIMD lane and
     * intermediate horizontal sum is bounded by a subset of those terms. */
    for(;t<11;t++) {
        int32_t i=iq[2*t],q=iq[2*t+1],a=c[t][0],b=c[t][1];
        re+=i*a+q*b;im+=q*a-i*b;
    }
    *real=re;*imag=im;
}

static uint32_t root(uint64_t n)
{
    /* The square root fits u32. Avoid ARM's software double-to-u64 helper. */
    double value=(double)(uint32_t)(n>>32)*4294967296.0+(double)(uint32_t)n;
    uint32_t r=(uint32_t)sqrt(value);
    /* Correct floating conversion at perfect-square boundaries. Supported
     * CI16/CI12 powers are below 2^63, so these products cannot wrap u64. */
    while((uint64_t)r*r>n) r--;
    while((uint64_t)(r+1)*(r+1)<=n) r++;
    return r;
}

static uint32_t ratio_q16(uint32_t numerator, uint32_t denominator)
{
    uint64_t scaled;
    uint32_t q;
    if(!denominator) return 0;
    if(numerator>=denominator) return 65536;
    scaled=(uint64_t)numerator<<16;
    /* Both operands are exactly representable in double. Correct the VFP
     * quotient with integer products, preserving the exact saturated floor
     * while avoiding the Cortex-A9 software u64 division routine. */
    q=(uint32_t)(((double)numerator*65536.0)/(double)denominator);
    while((uint64_t)q*denominator>scaled) q--;
    while((uint64_t)(q+1)*denominator<=scaled) q++;
    return q;
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

int glrt_cpu_coarse_grid(uint32_t grid[11][GLRT_CPU_COARSE_EPOCHS], const int16_t *iq,
    const int16_t c[12][11][11][2], unsigned begin, unsigned end,
    uint32_t *completed, int (*poll)(void *), void *context)
{
    static const unsigned offsets[5]={0,3333,6667,10000,13333};
    uint64_t energy[12][11];
    unsigned e,s,f,r,t,k;
    if(completed) *completed=0;
    if(!grid || !completed || begin>=end || end>GLRT_CPU_COARSE_EPOCHS ||
       !iq || !c || !poll || poll(context)) return -1;
    for(s=0;s<12;s++) for(f=0;f<11;f++) {
        uint64_t sum=0;
        for(t=0;t<11;t++) for(k=0;k<2;k++) {
            int64_t v=c[s][f][t][k];
            if(v < -2048 || v > 2047) return -1;
            sum+=(uint64_t)(v*v);
        }
        energy[s][f]=sum;
    }
    for(e=begin;e<end;e++) {
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
                /* 11 * 2 * 32768 * 2048 = 1,476,395,008, below INT32_MAX.
                 * Keep the dot products in bounded i32, widen before squaring. */
                int32_t re=0,im=0;
                uint32_t numerator,denominator;
                dot11(iq+2*start,c[s][f],&re,&im);
                numerator=root((uint64_t)((int64_t)re*re)+(uint64_t)((int64_t)im*im));
                denominator=root(observed*energy[s][f]);
                totals[f]+=ratio_q16(numerator,denominator);
            }
        }
        for(f=0;f<11;f++) grid[f][e]=support ? totals[f]/support : 0;
        *completed=e-begin+1;
    }
    return 0;
}

static void sift(struct glrt_cpu_coarse_peak *heap,unsigned length,unsigned parent)
{
    struct glrt_cpu_coarse_peak value=heap[parent];
    while(2*parent+1<length) {
        unsigned child=2*parent+1;
        if(child+1<length && better(&heap[child+1],&heap[child])) child++;
        if(!better(&heap[child],&value)) break;
        heap[parent]=heap[child];parent=child;
    }
    heap[parent]=value;
}

int glrt_cpu_coarse_select_bounded(const struct glrt_cpu_coarse_workspace *w,
    struct glrt_cpu_coarse_peak *peaks, unsigned budget, uint32_t *count,
    int (*poll)(void *), void *context)
{
    unsigned k=0,f,e,r,length=0;
    struct glrt_cpu_coarse_peak *heap=NULL;
    if(count) *count=0;
    if(!peaks || !budget || budget>80) return -1;
    memset(peaks,0,budget*sizeof(*peaks));
    if(!w || !count || !poll || w->completed_epochs!=GLRT_CPU_COARSE_EPOCHS) return -1;
    if(poll(context)) goto failed;
    /* Bounded 429.7-KiB temporary storage, not the capture-thread stack.
     * Heap order is the exact existing score/tie order. Suppressed maxima
     * are discarded only after all preceding selected maxima are known. */
    heap=malloc(11*GLRT_CPU_COARSE_EPOCHS*sizeof(*heap));
    if(!heap) goto failed;
    for(f=0;f<11;f++) for(e=0;e<GLRT_CPU_COARSE_EPOCHS;e++) {
            struct glrt_cpu_coarse_peak p={e,f,w->grid[f][e]};
            uint32_t left=e ? w->grid[f][e-1] : 0;
            uint32_t right=e+1<GLRT_CPU_COARSE_EPOCHS ? w->grid[f][e+1] : 0;
            if(!(e%256) && poll(context)) goto failed;
            if(!p.score || p.score<left || p.score<right || (p.score==left && p.score==right)) continue;
            heap[length++]=p;
    }
    for(r=length/2;r;r--) {
        if(!(r%256) && poll(context)) goto failed;
        sift(heap,length,r-1);
    }
    while(length && k<budget) {
            struct glrt_cpu_coarse_peak p=heap[0];
            if(poll(context)) goto failed;
            heap[0]=heap[--length];
            if(length) sift(heap,length,0);
            for(r=0;r<k;r++) {
                unsigned d=distance(p.epoch,peaks[r].epoch);
                if(d>GLRT_CPU_COARSE_EPOCHS/2) d=GLRT_CPU_COARSE_EPOCHS-d;
                if(d<20 && distance(p.frequency,peaks[r].frequency)<=1) break;
            }
            if(r==k) peaks[k++]=p;
    }
    if(poll(context)) goto failed;
    *count=k;
    free(heap);
    return 0;
failed:
    free(heap);
    memset(peaks,0,budget*sizeof(*peaks));
    return -1;
}

int glrt_cpu_coarse_select(struct glrt_cpu_coarse_workspace *w, int (*poll)(void *), void *context)
{
    if(!w) return -1;
    return glrt_cpu_coarse_select_bounded(w,w->peaks,8,&w->count,poll,context);
}

int glrt_cpu_coarse_search(struct glrt_cpu_coarse_workspace *w, const int16_t *iq,
    const int16_t c[12][11][11][2], int (*poll)(void *), void *context)
{
    if(!w) return -1;
    memset(w,0,sizeof(*w));
    if(glrt_cpu_coarse_grid(w->grid,iq,c,0,GLRT_CPU_COARSE_EPOCHS,
                           &w->completed_epochs,poll,context)) return -1;
    return glrt_cpu_coarse_select(w,poll,context);
}
