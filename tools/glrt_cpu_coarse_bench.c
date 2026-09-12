/* SPDX-License-Identifier: GPL-2.0 */
/* Saved IQ only: no IIO, no acquisition decision, no tracking submission. */
#define _POSIX_C_SOURCE 200809L
#include "glrt_cpu_coarse.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
static double clock_s(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) exit(2);
    return t.tv_sec+1e-9*t.tv_nsec;
}
static int poll(void *deadline) { return clock_s()>=*(double *)deadline; }
int main(int argc,char **argv)
{
    struct glrt_cpu_coarse_workspace *w;
    int16_t c[12][11][11][2],iq[28000];
    FILE *bank,*data,*grid;
    double deadline;
    alarm(25);
    if(argc!=4 || !(bank=fopen(argv[1],"rb")) || fread(c,sizeof(c),1,bank)!=1 ||
       fgetc(bank)!=EOF || fclose(bank) || !(data=fopen(argv[2],"rb")) ||
       !(grid=fopen(argv[3],"wbx")) || !(w=malloc(sizeof(*w)))) return 2;
    deadline=clock_s()+20;
    printf("{\"scope\":\"saved_iq_blind_coarse_proposals\",\"windows\":[");
    for(unsigned i=0;i<4;i++) {
        double started,elapsed;
        if(fread(iq,sizeof(iq),1,data)!=1) return 2;
        started=clock_s();
        if(glrt_cpu_coarse_search(w,iq,c,poll,&deadline)) return 1;
        elapsed=clock_s()-started;
        if(fwrite(w->grid,sizeof(w->grid),1,grid)!=1) return 2;
        printf("%s{\"window\":%u,\"milliseconds\":%.9g,\"peaks\":[",i ? "," : "",i,elapsed*1000);
        for(unsigned j=0;j<w->count;j++)
            printf("%s[%u,%u,%u]",j ? "," : "",w->peaks[j].epoch,w->peaks[j].frequency,w->peaks[j].score);
        printf("]}");fflush(stdout);
    }
    printf("],\"tracking_lock_claimed\":false}\n");
    free(w);
    return fclose(data) || fclose(grid) ? 2 : 0;
}
