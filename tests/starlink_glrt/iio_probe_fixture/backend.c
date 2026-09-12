/* Finite conserved IQ and one empty coarse decision. Faults exercise the
 * owner's lifecycle; numerical/source attestation uses independent Python. */
#define _POSIX_C_SOURCE 200809L
#include "iio.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
struct iio_context { int unused; };
struct iio_device { int kind; };
struct iio_channel { int kind,index; };
struct iio_buffer { int kind;size_t samples,bytes;void *data; };
static struct iio_context context;
static struct iio_device devices[3]={{0},{1},{2}};
static struct iio_channel channels[3][16];
static uint32_t visit,limit,received,generation=1;
static int armed,closed,event_closed,event_sent;
static int bootstrap_signal;
static int16_t references[52800];
static int fault(const char *name) { const char *s=getenv("PROBE_FAULT");return s && !strcmp(s,name); }
struct iio_context *iio_create_local_context(void)
{
    bootstrap_signal=getenv("PROBE_SIGNAL")!=NULL;
    if(bootstrap_signal) {
        const char *name=getenv("PROBE_REFERENCE");FILE *f=name ? fopen(name,"rb") : NULL;
        if(!f) return NULL;
        int valid=fread(references,sizeof(references),1,f)==1 && fgetc(f)==EOF;
        if(fclose(f) || !valid) return NULL;
    }
    return &context;
}
void iio_context_destroy(struct iio_context *c)
{
    FILE *f=fopen(getenv("PROBE_TRACE"),"w");(void)c;
    if (f) { fprintf(f,"%d %d %d\n",armed,closed,event_closed);fclose(f); }
}
const char *iio_context_get_attr_value(const struct iio_context *c,const char *name)
{
    (void)c;
    return !strcmp(name,"hw_serial") ? fault("identity") ? "wrong" : "10400056f695001322002d0010ad1719f2" : "test-fw";
}
int iio_context_set_timeout(struct iio_context *c,unsigned n) { (void)c;(void)n;return 0; }
struct iio_device *iio_context_find_device(const struct iio_context *c,const char *name)
{
    (void)c;return devices+(!strcmp(name,"ad9361-phy") ? 2 : !strcmp(name,"starlink-glrt-events"));
}
struct iio_channel *iio_device_get_channel(const struct iio_device *d,unsigned n)
{ channels[d->kind][n].kind=d->kind;channels[d->kind][n].index=(int)n;return &channels[d->kind][n]; }
struct iio_channel *iio_device_find_channel(const struct iio_device *d,const char *name,bool output)
{ (void)name;(void)output;return iio_device_get_channel(d,0); }
unsigned iio_device_get_channels_count(const struct iio_device *d) { return d->kind==1 ? 16 : 2; }
ssize_t iio_device_get_sample_size(const struct iio_device *d) { return d->kind==1 ? 64 : 4; }
void iio_channel_disable(struct iio_channel *c) { (void)c; }
void iio_channel_enable(struct iio_channel *c) { (void)c; }
bool iio_channel_is_scan_element(const struct iio_channel *c) { (void)c;return true; }
bool iio_channel_is_output(const struct iio_channel *c) { (void)c;return false; }
long iio_channel_get_index(const struct iio_channel *c) { return c->index; }
const struct iio_data_format *iio_channel_get_data_format(const struct iio_channel *c)
{
    static struct iio_data_format f;
    memset(&f,0,sizeof(f));f.length=f.bits=c->kind==1 ? 32 : 16;f.is_signed=c->kind!=1;f.repeat=1;
    if (fault("layout")) f.shift=1;
    return &f;
}
ssize_t iio_channel_attr_read(const struct iio_channel *c,const char *name,char *out,size_t size)
{
    const char *value="30";(void)c;
    if (!strcmp(name,"sampling_frequency")) value=fault("rate") ? "5000000" : "2500000";
    if (!strcmp(name,"rf_bandwidth")) value="2500000";
    if (!strcmp(name,"gain_control_mode")) value="manual";
    if (!strcmp(name,"rf_port_select")) value="A_BALANCED";
    if (!strcmp(name,"frequency")) value=closed && fault("rf_change") ? "1690312497" : "1690312496";
    if (!strcmp(name,"powerdown")) value=fault("tx_enabled") ? "0" : "1";
    {
        int n=snprintf(out,size,"%s\n",value);
        if (!fault("newline_attrs")) out[n-1]=0;
        if (fault("embedded_nul")) out[1]=0;
        return n;
    }
}
ssize_t iio_device_attr_read(const struct iio_device *d,const char *name,char *out,size_t size)
{
    uint32_t w[64]={0};unsigned count=64,i;int n,base=strstr(name,"baseline")!=NULL;
    int final=strstr(name,"final")!=NULL,search=strstr(name,"local_search")!=NULL;
    uint32_t amount=base || !armed ? 0 : received;
    uint32_t g=base ? 2 : final ? 999 : ++generation;
    (void)d;
    if (strstr(name,"abi")) {
        n=snprintf(out,size,"%s\n",!strcmp(name,"capture_abi") ? "GLA1-1.0-upper-only" : "GLA1-1.0");
        if (!fault("newline_attrs")) out[n-1]=0;
        return n;
    }
    if (strstr(name,"extension")) {
        count=16;
        if (!base) { w[0]=7;w[2]=100+amount-1; }
        n=snprintf(out,size,"GLA1 00010000 %u %u 2500000",g,visit);
    } else if (search) {
        count=16;w[13]=visit;
        if (!base) {
            w[0]=0x113;w[3]=1;w[4]=w[5]=1;w[6]=w[7]=w[9]=1;w[14]=100;
            if(bootstrap_signal) {
                unsigned complete=amount>=458752;
                w[0]|=complete ? 0 : 128;w[3]=2;w[4]=2*complete;w[5]=(unsigned)event_sent;
                w[6]=(amount+249999)/250000;w[7]=amount ? 1 : 0;w[8]=w[6]-w[7];
                w[9]=w[10]=complete;w[11]=w[7]-complete;
            }
        }
        n=snprintf(out,size,"GLA1 00010000 %u 2500000 250000 14000",g);
    } else {
        if (amount) {
            w[0]=100;w[2]=100+amount-1;w[4]=w[6]=amount;w[12]=w[14]=amount;
            w[19]=final ? 24 : 25;w[21]=16;w[42]=100+amount+123;
        }
        w[20]=visit;w[62]=2500000;
        if (!base && !final && amount && fault("source_gap")) w[44]=1;
        if (!base && !final && amount && fault("stale_snapshot")) g=2;
        n=snprintf(out,size,"GLA1 00010000 2500000 2500000 %u 0 2500000 0 %u %u 0 0 0 0",g,
            bootstrap_signal ? 2*(amount>=458752) : amount==limit && armed,
            bootstrap_signal ? 2*(amount>=458752) : amount==limit && armed);
    }
    for (i=0;i<count;i++) n+=snprintf(out+n,size-(size_t)n," %08x",w[i]);
    n+=snprintf(out+n,size-(size_t)n,"\n");
    if (!fault("newline_attrs")) out[n-1]=0;
    return n;
}
int iio_device_attr_write_longlong(const struct iio_device *d,const char *name,long long value)
{ (void)d;if (!strcmp(name,"capture_visit_id")) visit=(uint32_t)value;else limit=(uint32_t)value;return 0; }
int iio_device_set_kernel_buffers_count(const struct iio_device *d,unsigned n) { (void)d;(void)n;return 0; }
struct iio_buffer *iio_device_create_buffer(const struct iio_device *d,size_t n,bool cyclic)
{
    struct iio_buffer *b=calloc(1,sizeof(*b));(void)cyclic;
    b->kind=d->kind;b->samples=n;b->bytes=n*(d->kind ? 64 : 4);b->data=calloc(1,b->bytes);
    if (!d->kind) { armed=1;generation=2; }
    return b;
}
void iio_buffer_destroy(struct iio_buffer *b) { if (b->kind) event_closed++;else closed++;free(b->data);free(b); }
int iio_buffer_set_blocking_mode(struct iio_buffer *b,bool blocking)
{ (void)b;(void)blocking;return fault("nonblocking") ? -ENOSYS : 0; }
ssize_t iio_buffer_refill(struct iio_buffer *b)
{
    if (b->kind) {
        uint32_t *w=b->data;
        if(bootstrap_signal) {
            if(received<458752 || event_sent>=2) return -EAGAIN;
            memset(w,0,64);w[0]=0x474c4131;w[1]=visit;w[2]=(unsigned)event_sent;w[3]=100;
            w[5]=(4U<<6)|(event_sent==1);w[7]=23000;w[8]=w[9]=w[10]=w[11]=65536;w[12]=14000;
            event_sent++;return 64;
        }
        if (received!=limit || event_sent) return -EAGAIN;
        w[0]=0x474c4131;w[1]=visit;w[2]=fault("event_sequence") ? 1 : 0;w[3]=100;w[5]=3;w[12]=14000;
        event_sent=1;return 64;
    } else {
        size_t i;int16_t *w=b->data;
        if (fault("refill")) return -EIO;
        for (i=0;i<2*b->samples;i++) {
            if(bootstrap_signal) {
                uint64_t offset=received+i/2;unsigned phase=0,position=3300;
                if(offset>=22) {
                    uint64_t frame=(3*(offset-22)+2)/10000;
                    position=(unsigned)(offset-22-frame*10000/3);
                    phase=frame%3==0 ? 0 : frame%3==1 ? 1 : 3;
                }
                w[i]=position<3300 ? references[(phase*3300+position)*4+i%2] : 0;
            } else w[i]=(int16_t)((2*received+i)%65536-32768);
        }
        if(bootstrap_signal) {
            struct timespec pause={0,(long)(b->samples*400)};
            while(nanosleep(&pause,&pause) && errno==EINTR) {}
        }
        received+=(uint32_t)b->samples;
        return fault("partial") ? (ssize_t)b->bytes-4 : (ssize_t)b->bytes;
    }
}
ptrdiff_t iio_buffer_step(const struct iio_buffer *b) { return b->kind ? 64 : 4; }
void *iio_buffer_start(const struct iio_buffer *b) { return b->data; }
void *iio_buffer_end(const struct iio_buffer *b) { return (char *)b->data+b->bytes; }
