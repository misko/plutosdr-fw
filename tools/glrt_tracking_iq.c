/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_iq.h"
#include <string.h>

/* Floor division gives the signed shift used by the FPGA without relying on
 * implementation-defined right shifts of negative C integers. Values are
 * bounded by the CI16 CORDIC input geometry, far from INT32_MIN. */
static int32_t floor_shift(int32_t value, unsigned bits)
{
    if(value>=0) return (int32_t)((uint32_t)value>>bits);
    return -(int32_t)(((uint32_t)(-value)+((UINT32_C(1)<<bits)-1))>>bits);
}

static int32_t round_q4(int32_t value)
{
    int32_t q=floor_shift(value,4), r=value-q*16;
    return q+(r>8 || (r==8 && q%2!=0));
}

static void rotate(int16_t i, int16_t q, uint32_t phase, int32_t *a, int32_t *b)
{
    static const int32_t angles[16]={32768,19344,10221,5188,2604,1303,652,326,
                                    163,81,41,20,10,5,3,1};
    uint32_t angle=(UINT32_C(0)-phase)>>14;
    int32_t x=(int32_t)i*16,y=(int32_t)q*16,z;
    unsigned stage;
    if(((angle>>17)^(angle>>16))&1) {
        x=-x;y=-y;angle^=UINT32_C(1)<<17;
    }
    z=angle<(UINT32_C(1)<<17) ? (int32_t)angle : (int32_t)angle-262144;
    for(stage=0;stage<16;stage++) {
        int32_t sx=floor_shift(x,stage),sy=floor_shift(y,stage);
        if(z>=0) { x-=sy;y+=sx;z-=angles[stage]; }
        else { x+=sy;y-=sx;z+=angles[stage]; }
    }
    *a=round_q4(x);*b=round_q4(y);
}

int glrt_tracking_iq_moments_2500000(const int16_t *iq, const int16_t *reference,
    size_t count, uint64_t start, uint32_t phase_seed, uint32_t phase_step,
    struct glrt_tracking_moments *out)
{
    struct glrt_tracking_moments result;
    int64_t sums[7]={0,0,0,0,0,0,0};
    uint32_t phase=phase_seed;
    size_t n,k,word=0;
    if(!iq || !reference || !out || count!=3300 || start>UINT64_MAX-(count-1)) return -1;
    memset(&result,0,sizeof(result));
    result.start=start;result.count=3300;result.phase_step=phase_step;
    for(n=0;n<count;n++,phase+=phase_step) {
        int32_t a,b;
        int64_t ri=reference[4*n],rq=reference[4*n+1];
        int64_t di=reference[4*n+2],dq=reference[4*n+3];
        int64_t real,imag,weight=(int64_t)(count-1-n);
        rotate(iq[2*n],iq[2*n+1],phase,&a,&b);
        real=a*ri+b*rq;imag=b*ri-a*rq;
        sums[0]+=real;sums[1]+=imag;
        sums[2]+=-a*di-b*dq;sums[3]+=a*dq-b*di;
        sums[4]+=weight*real;sums[5]+=weight*imag;
        sums[6]+=(int64_t)a*a+(int64_t)b*b;
    }
    /* CI18 rotations and CI16 references give <2^35 products. At 3300
     * samples even weighted sums fit signed 64 bits; higher rates are not
     * accepted by this routine. Canonically extend the two 96-bit fields. */
    for(k=0;k<7;k++) {
        result.words[word++]=(uint32_t)(uint64_t)sums[k];
        result.words[word++]=(uint32_t)((uint64_t)sums[k]>>32);
        if(k==4 || k==5) result.words[word++]=sums[k]<0 ? UINT32_MAX : 0;
    }
    *out=result;
    return 0;
}
