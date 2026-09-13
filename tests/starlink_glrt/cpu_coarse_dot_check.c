/* Component-owned arithmetic check, also run by the bounded ARM benchmark.
 * Include after glrt_cpu_coarse.c so its private scalar/NEON kernel is tested. */
static int check_dot11(void)
{
    static const int16_t iq_edges[4]={-32768,32767,-1,0};
    static const int16_t c_edges[4]={-2048,2047,-1,0};
    uint32_t state=UINT32_C(0x85143329);
    unsigned trial,t;
    for(trial=0;trial<10064;trial++) {
        int16_t storage[38],coefficients[11][2];
        int16_t *iq=storage+2*(trial%8);
        int32_t re,im;
        int64_t expected_re=0,expected_im=0;
        for(t=0;t<22;t++) {
            if(trial<64) {
                iq[t]=iq_edges[(trial/16+(trial/4)*t)%4];
                coefficients[t/2][t%2]=c_edges[(trial+t*(trial/16))%4];
            } else {
                state=state*UINT32_C(1664525)+UINT32_C(1013904223);
                iq[t]=(int16_t)((int32_t)(state>>16)-32768);
                state=state*UINT32_C(1664525)+UINT32_C(1013904223);
                coefficients[t/2][t%2]=(int16_t)((int32_t)(state>>20)-2048);
            }
        }
        for(t=0;t<11;t++) {
            int64_t i=iq[2*t],q=iq[2*t+1],a=coefficients[t][0],b=coefficients[t][1];
            expected_re+=i*a+q*b;expected_im+=q*a-i*b;
        }
        dot11(iq,coefficients,&re,&im);
        if(re!=expected_re || im!=expected_im) return -1;
    }
    return 0;
}
