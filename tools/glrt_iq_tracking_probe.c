/* SPDX-License-Identifier: GPL-2.0 */
/* Bounded ARM-local GLI1 transport commissioning. Arbitrary scheduled pilots
 * test native arithmetic/retirement; they are not acquired or supported locks.
 * Caller holds radio leases and has calibrated the exact RX clock. */
#define _POSIX_C_SOURCE 200809L
#include "glrt_iq_tracking_source.h"
#include "glrt_tracking_transport.h"
#include <iio.h>
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define CHUNK 16384U
#define BLOCKS 160U
static volatile sig_atomic_t interrupted;
static void stop(int value) { (void)value; interrupted=1; }
static uint64_t wide(const uint32_t *w) { return w[0]|((uint64_t)w[1]<<32); }
static int attr(struct iio_device *d,const char *key,char text[4096],FILE *journal)
{
    ssize_t n=iio_device_attr_read(d,key,text,4096);
    if(n<=0 || n>=4096) return -1;
    if(!text[n-1]) n--;
    if(memchr(text,0,(size_t)n)) return -1;
    text[n]=0;
    if(journal && (fprintf(journal,"%s %s\n",key,text)<0 || fflush(journal))) return -1;
    return (int)n;
}
static int is_attr(struct iio_device *d,const char *key,const char *expected)
{
    char text[4096];int n=attr(d,key,text,NULL);
    while(n>0 && (text[n-1]=='\n' || text[n-1]=='\r')) text[--n]=0;
    return n>0 && !strcmp(text,expected);
}
static int snapshot(struct iio_device *d,uint32_t w[24],FILE *journal)
{
    char text[4096];int n=attr(d,"tracking_snapshot",text,journal);
    return n>0 ? glrt_tracking_snapshot_parse(text,(size_t)n,w) : -1;
}
static int drain(struct iio_device *d,const struct glrt_tracking_batch *batch,
                 uint32_t *count,FILE *journal,int strict)
{
    uint32_t w[24],head[32],epoch;char text[4096];int n;
    struct glrt_native_estimate estimate;
    if(snapshot(d,w,journal)) return -1;
    while(w[16]) {
        n=attr(d,"tracking_result",text,journal);
        if(n<=0 || glrt_tracking_head_parse(text,(size_t)n,&epoch,head) ||
           glrt_tracking_associated_solve(batch,epoch,*count,head,&estimate)) return -1;
        if(strict && (head[8] || head[7]!=batch->rate*33U/25000U)) return -1;
        n=snprintf(text,sizeof(text),"%08" PRIx32 " %08" PRIx32,epoch,*count);
        if(n<=0 || iio_device_attr_write(d,"tracking_pop",text)<0) return -1;
        (*count)++;
        if(snapshot(d,w,journal)) return -1;
    }
    return 0;
}
int main(int argc,char **argv)
{
    struct iio_context *ctx=NULL;
    struct iio_device *iq=NULL,*phy=NULL;
    struct iio_buffer *buffer=NULL;
    struct glrt_capture_snapshot capture;
    struct glrt_iq_tracking_source source;
    struct glrt_tracking_batch batch={0};
    struct sigaction action={0};
    uint32_t rate,visit=9122001,w[24],count=0,block=0;
    uint64_t first=0,now=0;
    FILE *journal=NULL,*samples=NULL;
    char text[4096],label[80];int n,rc=1,submitted=0;
    const char *stage="arguments";
#define NEED(x,s) do { stage=s; if(!(x)) goto done; } while(0)
    if(argc!=5 || (strcmp(argv[1],"30000000") && strcmp(argv[1],"60000000"))) {
        fprintf(stderr,"usage: %s 30000000|60000000 SERIAL NEW_JOURNAL NEW_IQ_FILE\n",argv[0]);return 2;
    }
    rate=(uint32_t)strtoul(argv[1],NULL,10);
    action.sa_handler=stop;sigemptyset(&action.sa_mask);
    NEED(!sigaction(SIGALRM,&action,NULL) && !sigaction(SIGTERM,&action,NULL),"signals");
    alarm(15);
    NEED((journal=fopen(argv[3],"wx")) && (samples=fopen(argv[4],"wbx")),"new_evidence");
    NEED((ctx=iio_create_local_context())!=NULL,"local_context");
    snprintf(label,sizeof(label),"glrt-iq-tracking-r%u-v1",rate);
    NEED(iio_context_get_attr_value(ctx,"hw_serial") &&
         !strcmp(iio_context_get_attr_value(ctx,"hw_serial"),argv[2]) &&
         iio_context_get_attr_value(ctx,"fw_version") &&
         !strcmp(iio_context_get_attr_value(ctx,"fw_version"),label),"identity");
    NEED(!iio_context_set_timeout(ctx,2000),"timeout");
    iq=iio_context_find_device(ctx,"starlink-glrt-iq");
    phy=iio_context_find_device(ctx,"ad9361-phy");
    NEED(iq && phy && !iio_context_find_device(ctx,"starlink-glrt-events"),"inventory");
    NEED(is_attr(iq,"capture_abi","GLI1-1.0-upper-only") &&
         is_attr(iq,"tracking_abi","GLT1-1.0"),"abi");
    {
        long long actual,tx;
        struct iio_channel *rx=iio_device_find_channel(phy,"voltage0",false);
        struct iio_channel *lo=iio_device_find_channel(phy,"altvoltage1",true);
        NEED(rx && lo && !iio_channel_attr_read_longlong(rx,"sampling_frequency",&actual) &&
             !iio_channel_attr_read_longlong(lo,"powerdown",&tx) && actual==rate && tx==1,"rx_clock_tx_idle");
    }
    NEED(!snapshot(iq,w,journal) && glrt_tracking_snapshot_drained(w) && !w[6],"initial_tracking_idle");
    batch.rate=rate;batch.prediction.tag=visit;
    NEED(iio_device_get_channels_count(iq)==2,"scan_count");
    for(unsigned k=0;k<2;k++) {
        struct iio_channel *ch=iio_device_get_channel(iq,k);
        const struct iio_data_format *fmt=iio_channel_get_data_format(ch);
        NEED(iio_channel_is_scan_element(ch) && !iio_channel_is_output(ch) &&
             iio_channel_get_index(ch)==(long)k && fmt && fmt->bits==16 && fmt->length==16 &&
             fmt->is_signed && !fmt->is_be && !fmt->shift && !fmt->with_scale && fmt->repeat==1,"scan_format");
        iio_channel_enable(ch);
    }
    NEED(iio_device_attr_write_longlong(iq,"capture_visit_id",visit)==0 &&
         iio_device_attr_write_longlong(iq,"capture_sample_limit",CHUNK*BLOCKS)==0 &&
         iio_device_set_kernel_buffers_count(iq,4)==0,"capture_setup");
    NEED((buffer=iio_device_create_buffer(iq,CHUNK,false))!=NULL,"start");
    n=attr(iq,"capture_baseline_snapshot",text,journal);
    NEED(n>0 && !glrt_iq_tracking_snapshot_parse(text,(size_t)n,&capture) &&
         !glrt_iq_tracking_source_begin(&source,visit,CHUNK*BLOCKS,&capture),"baseline");
    for(block=0;block<BLOCKS;block++) {
        ssize_t bytes;
        NEED(!interrupted,"wall_deadline");
        bytes=iio_buffer_refill(buffer);
        NEED(bytes==4*CHUNK && iio_buffer_step(buffer)==4 &&
             (char *)iio_buffer_end(buffer)-(char *)iio_buffer_start(buffer)==bytes,"refill");
        n=attr(iq,"capture_snapshot",text,journal);
        NEED(n>0 && !glrt_iq_tracking_snapshot_parse(text,(size_t)n,&capture) &&
             !glrt_iq_tracking_source_take(&source,&capture,CHUNK,&first,&now),"contiguous_source");
        NEED(fwrite(iio_buffer_start(buffer),1,(size_t)bytes,samples)==(size_t)bytes,"retain_iq");
        if(!submitted) {
            /* GLI1 source epochs require the continuous IQ visit to be active. */
            NEED(iio_device_attr_write_longlong(iq,"tracking_command",16)==0,"rebase");
            NEED(!snapshot(iq,w,journal) && !w[6] && w[20]==rate && w[2],"live_tracking_source");
            batch.prediction.epoch=w[2];
            batch.prediction.start=wide(w+3)+rate/10;
            batch.prediction.period=((uint64_t)rate<<16)/750;
            batch.prediction.repeats=16;
            batch.prediction.expires=batch.prediction.start+rate/10;
            n=glrt_tracking_batch_encode(&batch,text,sizeof(text));
            NEED(n>0 && fprintf(journal,"submit %s",text)>0 && !fflush(journal),"retain_submit");
            NEED(iio_device_attr_write(iq,"tracking_submit",text)>0,"submit");
            submitted=1;
        }
        NEED(!drain(iq,&batch,&count,journal,1),"native_result_retirement");
        NEED(!snapshot(iq,w,journal) && (!w[6] ||
             (w[6]==8 && !(capture.words[19]&3) &&
              wide(capture.words+4)==CHUNK*BLOCKS && wide(capture.words+6)==CHUNK*BLOCKS)),
             "fault_only_after_finite_source_stop");
    }
    NEED(count==16 && !snapshot(iq,w,journal) && glrt_tracking_snapshot_drained(w) &&
         w[6]==8 && !(capture.words[19]&3) && wide(capture.words+4)==CHUNK*BLOCKS &&
         wide(capture.words+6)==CHUNK*BLOCKS && !w[18] && !w[19] &&
         w[7]==16 && w[8]==16 && w[14]==16 && w[15]==16,
         "all_native_results_complete");
    rc=0;
done:
    if(iq && submitted) {
        if(iio_device_attr_write_longlong(iq,"tracking_command",2)<0 ||
           drain(iq,&batch,&count,journal,0) || snapshot(iq,w,journal) ||
           !glrt_tracking_snapshot_drained(w)) rc=1;
    }
    if(buffer) { iio_buffer_destroy(buffer);buffer=NULL; }
    if(iq && journal) {
        if(attr(iq,"capture_final_snapshot",text,journal)<0) rc=1;
        if(attr(iq,"capture_final_extension_snapshot",text,journal)<0) rc=1;
        if(iio_device_attr_write_longlong(iq,"tracking_command",4)<0 ||
           snapshot(iq,w,journal) || !glrt_tracking_snapshot_drained(w) ||
           (w[5]&16) || w[6] || w[7]) rc=1;
    }
    if(ctx) iio_context_destroy(ctx);
    if(samples && fclose(samples)) rc=1;
    if(journal && fclose(journal)) rc=1;
    alarm(0);
    printf("{\"scope\":\"arm_iq_and_arbitrary_native_jobs\",\"rate\":%u,\"status\":%d,"
           "\"stage\":\"%s\",\"blocks\":%u,\"results\":%u,\"tracking_lock_claimed\":false}\n",
           rate,rc,stage,block,count);
    return rc;
}
