/* SPDX-License-Identifier: GPL-2.0 */
/* Bounded receive-only local ingestion qualification, not a tracking daemon.
 * Caller must hold the exact radio lease and retain independent host review.
 * One DMA owner feeds the recent-IQ ring and evidence; no network IIO reader.
 */
#define _POSIX_C_SOURCE 200809L
#include "glrt_capture_source.h"
#include "glrt_tracking_iq_owner.h"
#include <iio.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define RATE 2500000U
#define MAX_SAMPLES (5U*RATE)
#define WIRE_SIZE 4096

static uint64_t ns(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) return 0;
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}

static int decimal(const char *s, uint32_t max, uint32_t *out)
{
    uint64_t n=0;
    if (!s || !*s) return -1;
    for (;*s;s++) {
        if (*s<'0' || *s>'9') return -1;
        n=n*10+(unsigned)(*s-'0');
        if (n>max) return -1;
    }
    if (!n) return -1;
    *out=(uint32_t)n;return 0;
}

static FILE *new_file(int directory, const char *name)
{
    int fd=openat(directory,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    FILE *f;
    if (fd<0) return NULL;
    f=fdopen(fd,"wb");
    if (!f) close(fd);
    return f;
}

/* The local 0.x backend includes its replacement trailing NUL in the count.
 * Accept that terminator, but never an embedded NUL hiding extra content. */
static int attribute_text(char *text, ssize_t n, size_t capacity)
{
    if (n<=0 || (size_t)n>=capacity) return -1;
    if (!text[n-1]) n--;
    if (memchr(text,0,(size_t)n)) return -1;
    while (n && isspace((unsigned char)text[n-1])) n--;
    text[n]=0;
    return n>0 ? (int)n : -1;
}

static int read_attr(const struct iio_device *device, const char *name, char *wire)
{
    ssize_t n=iio_device_attr_read(device,name,wire,WIRE_SIZE);
    return attribute_text(wire,n,WIRE_SIZE);
}

static int save_attr(int directory, const struct iio_device *device,
    const char *attr, const char *name, char *wire)
{
    FILE *f;
    int length=read_attr(device,attr,wire),failed;
    if (length<0 || !(f=new_file(directory,name))) return -1;
    failed=fwrite(wire,1,(size_t)length,f)!=(size_t)length || fputc('\n',f)==EOF;
    if (fclose(f)) failed=1;
    return failed ? -1 : length;
}

static int attr_is(const struct iio_device *d, const char *name, const char *expected)
{
    char text[WIRE_SIZE];
    return read_attr(d,name,text)>0 && !strcmp(text,expected);
}

static int identity(struct iio_context *ctx, const char *serial, const char *firmware)
{
    const char *s=iio_context_get_attr_value(ctx,"hw_serial");
    const char *f=iio_context_get_attr_value(ctx,"fw_version");
    return s && f && !strcmp(s,serial) && !strcmp(f,firmware);
}

static int scan(struct iio_device *device, unsigned count, unsigned bits, int signed_samples)
{
    unsigned n,seen=0;
    for (n=0;n<iio_device_get_channels_count(device);n++) {
        struct iio_channel *c=iio_device_get_channel(device,n);
        const struct iio_data_format *f;
        long index;
        iio_channel_disable(c);
        if (!iio_channel_is_scan_element(c)) continue;
        f=iio_channel_get_data_format(c);index=iio_channel_get_index(c);
        if (iio_channel_is_output(c) || index<0 || (unsigned long)index>=count ||
            (seen&(1U<<index)) || !f || f->bits!=bits || f->length!=bits || f->shift ||
            f->is_signed!=signed_samples || f->is_be || f->with_scale || f->repeat!=1) return -1;
        seen|=1U<<index;iio_channel_enable(c);
    }
    return seen==(1U<<count)-1 && iio_device_get_sample_size(device)==(ssize_t)(count*bits/8) ? 0 : -1;
}

/* Read all configuration fields used by the existing capture owner, so that
 * changes during reception cannot be mistaken for a continuous RF condition. */
static int rf_state(struct iio_context *ctx, char *out)
{
    static const char *names[]={"sampling_frequency","rf_bandwidth","gain_control_mode",
        "hardwaregain","rf_port_select","frequency","powerdown"};
    struct iio_device *phy=iio_context_find_device(ctx,"ad9361-phy");
    size_t used=0;
    unsigned i;
    if (!phy) return -1;
    for (i=0;i<7;i++) {
        char value[256];ssize_t n;int wrote;
        struct iio_channel *channel=iio_device_find_channel(phy,
            i<5 ? "voltage0" : i==5 ? "altvoltage0" : "altvoltage1",i>=5);
        if (!channel) return -1;
        n=iio_channel_attr_read(channel,names[i],value,sizeof(value));
        n=attribute_text(value,n,sizeof(value));
        if (n<0 || strchr(value,'\n') || strchr(value,'\r') ||
            (i==0 && strcmp(value,"2500000")) || (i==6 && strcmp(value,"1"))) return -1;
        wrote=snprintf(out+used,WIRE_SIZE-used,"%s=%s\n",names[i],value);
        if (wrote<0 || (size_t)wrote>=WIRE_SIZE-used) return -1;
        used+=(size_t)wrote;
    }
    return 0;
}

static int save_text(int directory, const char *name, const char *text)
{
    FILE *f=new_file(directory,name);int failed;
    if (!f) return -1;
    failed=fputs(text,f)==EOF;
    if (fclose(f)) failed=1;
    return failed ? -1 : 0;
}

static int drain_events(struct iio_buffer *buffer, FILE *stream, uint32_t visit,
    uint64_t *events, uint64_t *other)
{
    unsigned limit=2048;
    while (limit--) {
        uint32_t w[16];ssize_t bytes=iio_buffer_refill(buffer);
        if (bytes==-EAGAIN) return 0;
        if (bytes!=64 || iio_buffer_step(buffer)!=64 ||
            (char *)iio_buffer_end(buffer)-(char *)iio_buffer_start(buffer)!=64) return -1;
        memcpy(w,iio_buffer_start(buffer),64);
        if (fwrite(w,1,64,stream)!=64) return -1;
        if (w[0]!=0x474c4131 || !w[1]) return -1;
        if (w[1]!=visit) { (*other)++;continue; }
        if (w[2]!=*events) return -1;
        (*events)++;
    }
    return -1;
}

/* Binary export through PPU's text SSH port, after reception. BusyBox on the
 * resident image need not provide base64 or compression. No IIO is opened. */
static int export_base64(void)
{
    static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    unsigned char in[12288];char out[17000];size_t n,total=0;
    if (puts("GLRTBASE64_BEGIN")<0) return 1;
    while ((n=fread(in,1,sizeof(in),stdin))>0) {
        size_t i,used=0,col=0;
        total+=n;
        if (total>60000000) return 1;
        for (i=0;i<n;i+=3) {
            uint32_t bits=(uint32_t)in[i]<<16;
            if (i+1<n) bits|=(uint32_t)in[i+1]<<8;
            if (i+2<n) bits|=in[i+2];
            out[used++]=alphabet[bits>>18];out[used++]=alphabet[(bits>>12)&63];
            out[used++]=i+1<n ? alphabet[(bits>>6)&63] : '=';
            out[used++]=i+2<n ? alphabet[bits&63] : '=';
            col+=4;
            if (col==64) { out[used++]='\n';col=0; }
        }
        if (col) out[used++]='\n';
        if (fwrite(out,1,used,stdout)!=used) return 1;
    }
    if (ferror(stdin) || puts("GLRTBASE64_END")<0 || fflush(stdout)) return 1;
    return 0;
}

int main(int argc, char **argv)
{
    struct iio_context *ctx=NULL;
    struct iio_device *iq=NULL,*events=NULL;
    struct iio_buffer *iq_buffer=NULL,*event_buffer=NULL;
    struct glrt_capture_snapshot baseline,final,current;
    struct glrt_capture_source cursor;
    struct glrt_tracking_iq_owner owner={0};
    struct glrt_tracking_iq_view view;
    int16_t *storage=NULL,*copied=NULL;
    FILE *iq_file=NULL,*event_file=NULL,*blocks_file=NULL,*snapshots_file=NULL;
    char wire[WIRE_SIZE],before[WIRE_SIZE],after[WIRE_SIZE];
    const char *stage="arguments",*failure=NULL;
    uint32_t visit,chunk,blocks,n=0;
    uint64_t limit=0,first=0,source_now=0,event_count=0,other_events=0,started=0,finished=0;
    int directory=-1,length,have_baseline=0,have_final=0,armed=0;
    unsigned i;
    uint16_t endian=1;
#define CHECK(condition, label) do { stage=label; if (!(condition)) { failure=stage; goto cleanup; } } while (0)
    if (argc==2 && !strcmp(argv[1],"--base64")) return export_base64();
    if (argc!=7 || strlen(argv[1])<1 || strlen(argv[1])>128 || strlen(argv[2])<1 || strlen(argv[2])>80 ||
        decimal(argv[3],UINT32_MAX,&visit) || decimal(argv[4],250000,&chunk) ||
        decimal(argv[5],MAX_SAMPLES,&blocks) || chunk%2 ||
        (uint64_t)chunk*blocks>MAX_SAMPLES || argv[6][0]!='/' ||
        strchr(argv[6],'\n') || strchr(argv[6],'\r')) {
        fprintf(stderr,"usage: %s SERIAL FIRMWARE VISIT EVEN_CHUNK BLOCKS /NEW_OUTPUT_DIR (maximum 5 seconds)\n",argv[0]);
        return 2;
    }
    for (i=0;argv[1][i];i++) if (!isalnum((unsigned char)argv[1][i]) &&
        !strchr("-._:",argv[1][i])) return 2;
    for (i=0;argv[2][i];i++) if (!isalnum((unsigned char)argv[2][i]) &&
        !strchr("-._",argv[2][i])) return 2;
    CHECK(*(unsigned char *)&endian==1,"little_endian_cpu");
    limit=(uint64_t)chunk*blocks;
    CHECK(mkdir(argv[6],0700)==0,"new_output_directory");
    CHECK((directory=open(argv[6],O_RDONLY|O_DIRECTORY|O_NOFOLLOW))>=0,"output_directory");
    CHECK((ctx=iio_create_local_context())!=NULL,"local_iio_context");
    CHECK(identity(ctx,argv[1],argv[2]),"pinned_identity");
    CHECK(iio_context_set_timeout(ctx,2000)==0,"iio_timeout");
    CHECK(rf_state(ctx,before)==0 && save_text(directory,"rf_before.txt",before)==0,"rf_before");
    iq=iio_context_find_device(ctx,"starlink-glrt-iq");
    events=iio_context_find_device(ctx,"starlink-glrt-events");
    CHECK(iq && events,"glrt_devices");
    CHECK(attr_is(iq,"capture_abi","GLA1-1.0-upper-only") &&
        attr_is(iq,"capture_extension_abi","GLA1-1.0") && attr_is(iq,"local_search_abi","GLA1-1.0"),"direct_gla1_abi");
    length=save_attr(directory,iq,"capture_snapshot","initial_snapshot.txt",wire);
    CHECK(length>0 && glrt_capture_snapshot_parse(wire,(size_t)length,&current)==0 &&
        !(current.words[19]&3) && current.words[20]!=visit,"idle_new_visit");
    CHECK(scan(iq,2,16,1)==0 && scan(events,16,32,0)==0,"scan_layout");
    CHECK((storage=malloc(4U*RATE)) && (copied=malloc(4U*chunk)),"ring_allocation");
    iq_file=new_file(directory,"iq.ci16");event_file=new_file(directory,"events.raw");
    blocks_file=new_file(directory,"blocks.csv");snapshots_file=new_file(directory,"block_snapshots.txt");
    CHECK(iq_file && event_file && blocks_file && snapshots_file,"evidence_files");
    CHECK(fputs("block,first,source_now,refill_begin_ns,refill_end_ns,snapshot_begin_ns,snapshot_end_ns,ring_end_ns,store_end_ns,event_end_ns\n",blocks_file)>=0,"block_header");
    CHECK(iio_device_set_kernel_buffers_count(events,1024)==0,"event_kernel_buffers");
    CHECK((event_buffer=iio_device_create_buffer(events,1,false))!=NULL,"event_buffer");
    CHECK(iio_buffer_set_blocking_mode(event_buffer,false)==0,"nonblocking_events");
    CHECK(iio_device_attr_write_longlong(iq,"capture_visit_id",visit)==0 &&
        iio_device_attr_write_longlong(iq,"capture_sample_limit",(long long)limit)==0,"finite_capture_settings");
    CHECK(iio_device_set_kernel_buffers_count(iq,4)==0,"iq_kernel_buffers");
    started=ns();
    CHECK(started && (iq_buffer=iio_device_create_buffer(iq,chunk,false))!=NULL,"iq_buffer_arm");
    armed=1;
    length=save_attr(directory,iq,"capture_baseline_snapshot","baseline_snapshot.txt",wire);
    CHECK(length>0 && glrt_capture_snapshot_parse(wire,(size_t)length,&baseline)==0 &&
        glrt_capture_source_begin(&cursor,visit,limit,&baseline)==0,"prearm_baseline");
    have_baseline=1;
    CHECK(save_attr(directory,iq,"capture_baseline_extension_snapshot","baseline_extension_snapshot.txt",wire)>0 &&
        save_attr(directory,iq,"local_search_baseline_snapshot","baseline_local_search_snapshot.txt",wire)>0,"prearm_extensions");
    for (n=0;n<blocks;n++) {
        uint64_t t0=ns(),t1,t2,t3,t4,t5,t6;
        ssize_t bytes;
        CHECK(t0>=started && t0-started<UINT64_C(20000000000),"capture_wall_deadline");
        bytes=iio_buffer_refill(iq_buffer);t1=ns();
        CHECK(bytes==(ssize_t)chunk*4 && iio_buffer_step(iq_buffer)==4 &&
            (char *)iio_buffer_end(iq_buffer)-(char *)iio_buffer_start(iq_buffer)==bytes,"whole_iq_block");
        t2=ns();length=read_attr(iq,"capture_snapshot",wire);t3=ns();
        CHECK(length>0 && glrt_capture_snapshot_parse(wire,(size_t)length,&current)==0 &&
            glrt_capture_source_take(&cursor,&current,chunk,&first,&source_now)==0,"block_source_binding");
        if (!n) CHECK(glrt_tracking_iq_owner_init(&owner,storage,RATE,visit,first)==0,"ring_reset");
        CHECK(glrt_tracking_iq_owner_publish(&owner,visit,first,iio_buffer_start(iq_buffer),chunk,source_now,t3)==0 &&
            glrt_tracking_iq_owner_copy(&owner,visit,first,copied,chunk,&view)==0 &&
            view.epoch==visit && view.valid && !view.closed && view.end==first+chunk &&
            view.source_now==source_now && view.observed_ns==t3 &&
            !memcmp(copied,iio_buffer_start(iq_buffer),4U*chunk),"ring_exact_copy");
        t4=ns();
        CHECK(fwrite(copied,4,chunk,iq_file)==chunk && fprintf(snapshots_file,"%s\n",wire)>0,"iq_evidence");
        t5=ns();
        CHECK(drain_events(event_buffer,event_file,visit,&event_count,&other_events)==0,"live_event_drain");
        t6=ns();
        CHECK(fprintf(blocks_file,"%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
            ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",n,first,source_now,t0,t1,t2,t3,t4,t5,t6)>0,"block_evidence");
    }
cleanup:
    if (iq_buffer) { iio_buffer_destroy(iq_buffer);iq_buffer=NULL; }
    if (owner.initialized && glrt_tracking_iq_owner_close(&owner,failure!=NULL) && !failure)
        failure="ring_close";
    finished=ns();
    if (armed) {
        length=save_attr(directory,iq,"capture_final_snapshot","final_snapshot.txt",wire);
        if (length>0 && glrt_capture_snapshot_parse(wire,(size_t)length,&final)==0 && final.words[20]==visit) have_final=1;
        else if (!failure) failure="final_snapshot";
        if (save_attr(directory,iq,"capture_final_extension_snapshot","final_extension_snapshot.txt",wire)<0 ||
            save_attr(directory,iq,"local_search_final_snapshot","final_local_search_snapshot.txt",wire)<0)
            if (!failure) failure="final_extensions";
    }
    if (have_baseline && have_final) {
        uint64_t deadline=ns()+UINT64_C(3000000000);
        struct timespec pause={0,1000000};
        if (final.cpu[1]<baseline.cpu[1]) { if (!failure) failure="event_counter_regression"; }
        else {
            uint64_t target=final.cpu[1]-baseline.cpu[1];
            while (event_count<target && ns()<deadline) {
                if (drain_events(event_buffer,event_file,visit,&event_count,&other_events)) {
                    if (!failure) failure="final_event_drain";
                    break;
                }
                if (event_count<target) nanosleep(&pause,NULL);
            }
            if (event_count!=target && !failure) failure="event_count";
        }
    }
    if (event_buffer) iio_buffer_destroy(event_buffer);
    if (ctx && armed) {
        if (rf_state(ctx,after) || save_text(directory,"rf_after.txt",after) || strcmp(before,after))
            if (!failure) failure="rf_after";
    }
    if (ctx) iio_context_destroy(ctx);
    if (iq_file && fclose(iq_file) && !failure) failure="iq_close";
    if (event_file && fclose(event_file) && !failure) failure="events_close";
    if (blocks_file && fclose(blocks_file) && !failure) failure="blocks_close";
    if (snapshots_file && fclose(snapshots_file) && !failure) failure="snapshots_close";
    if (owner.initialized && glrt_tracking_iq_owner_destroy(&owner) && !failure) failure="ring_destroy";
    free(copied);free(storage);
    if (directory>=0) close(directory);
    printf("{\"status\":\"%s\",\"failed_stage\":\"%s\",\"visit\":%u,\"chunk_samples\":%u,"
        "\"requested_samples\":%" PRIu64 ",\"completed_blocks\":%u,\"events\":%" PRIu64
        ",\"other_visit_events\":%" PRIu64 ",\"capture_begin_ns\":%" PRIu64 ",\"capture_closed_ns\":%" PRIu64
        ",\"independent_attestation_required\":true,\"tracking_feedback_exercised\":false}\n",
        failure ? "failed" : "captured",failure ? failure : "",visit,chunk,limit,n,event_count,other_events,started,finished);
    return failure ? 1 : 0;
}
