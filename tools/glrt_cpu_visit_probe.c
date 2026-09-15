/* SPDX-License-Identifier: GPL-2.0 */
/* Radio-local qualification composition. A forked child runs the component's
 * existing finite probe; the parent owns LO changes and checks cleanup. */
#define main glrt_cpu_probe_main
#include "glrt_cpu_live_probe.c"
#undef main
#include "glrt_tracking_visit.h"
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/wait.h>

#define SCOUT_PROFILE "1536-selected-observer3-scan64-scout16"
#define SPARSE_PROFILE "45000-selected-observer9-scan80-local2-track10-sparse10-authority"
#define SPARSE30_PROFILE "45000-selected-observer9-scan80-local2-track30-sparse10-authority"
#define SPARSE100_PROFILE "45000-selected-observer9-scan80-local2-track100-sparse10-authority"
#define FOLLOWUP_PLAN "sparse10-after-scout16"
#define FOLLOWUP30_PLAN "sparse30-after-scout16"
#define FOLLOWUP100_PLAN "sparse100-after-scout16"
#define SCOUT_ACTIVITY_POWER 0.04
#define SCOUT_ACTIVITY_HITS 1U

struct visit_context {
    char **args;
    FILE *journal;
    uint32_t rate;
    unsigned visit_count;
    const char *profile;
    const char *followup_profile;
    const char *followup_plan;
    int followup_sparse;
    int activity_selected;
    int (*probe_main)(int,char **);
    int (*followup_probe_main)(int,char **);
};
static const char *visit_profile(const struct visit_context *v)
{
    return v->profile ? v->profile : v->visit_count>2 ? "1536-selected" : NULL;
}
/* The optional trailing profile is opt-in; existing visit invocations retain
 * their exact child profile. Validate the full plan before any IIO contact. */
static int visit_arguments(int argc,char **argv,struct visit_context *v,uint64_t lo[4])
{
    char *end;int count=argc-6;
    if(argc<8 || argc>11 || (strcmp(argv[1],"30000000") && strcmp(argv[1],"60000000")) ||
       strcmp(argv[2],"1040005e0b100007100010000bf33a5d4d")) return -1;
    v->profile=NULL;
    if(!strcmp(argv[argc-1],"1536-selected-observer3-scan64")) {
        v->profile=argv[argc-1];count--;
    } else if(!strcmp(argv[argc-1],FOLLOWUP_PLAN) ||
              !strcmp(argv[argc-1],FOLLOWUP30_PLAN) ||
              !strcmp(argv[argc-1],FOLLOWUP100_PLAN)) {
        v->profile=SCOUT_PROFILE;v->followup_sparse=1;v->followup_plan=argv[argc-1];
        v->followup_profile=!strcmp(v->followup_plan,FOLLOWUP_PLAN) ? SPARSE_PROFILE :
            !strcmp(v->followup_plan,FOLLOWUP30_PLAN) ? SPARSE30_PROFILE : SPARSE100_PROFILE;
        count--;
    }
    if(count<2 || count>4) return -1;
    for(int n=0;n<count;n++) {
        errno=0;lo[n]=strtoull(argv[6+n],&end,10);
        if(errno || *end || !*argv[6+n]) return -1;
        if((lo[n]!=1190312500 && lo[n]!=1440312500 && lo[n]!=1690312500 && lo[n]!=1940312500) ||
           (n && lo[n]==lo[n-1])) return -1;
    }
    v->args=argv;v->rate=(uint32_t)strtoul(argv[1],NULL,10);v->visit_count=(unsigned)count;
    return 0;
}
static int visit_cancelled(void *unused) { (void)unused;return interrupted!=0; }
static int visit_probe_main(int argc,char **argv) { return live_probe_run(argc,argv,1); }
static int followup_probe_main(int argc,char **argv) { return live_probe_run(argc,argv,0); }
static int channel_is(struct iio_channel *channel,const char *name,const char *expected)
{
    char raw[128];ssize_t n;
    if(!channel || (n=iio_channel_attr_read(channel,name,raw,sizeof(raw)))<=0 || n>=128) return 0;
    while(n && (raw[n-1]==0 || raw[n-1]=='\n' || raw[n-1]=='\r')) n--;
    raw[n]=0;return !strcmp(raw,expected);
}
static int channel_number(struct iio_channel *channel,const char *name,long long *out)
{
    return !channel || iio_channel_attr_read_longlong(channel,name,out) ? -1 : 0;
}
static int visit_idle_snapshot(const uint32_t w[24],uint32_t rate)
{
    /* Epoch zero precedes the first real-refill REBASE. Calibration/boot
     * counters are retained but are not losses from a tracking acquisition.
     * Every nonzero acquisition epoch must still have zero source drops. */
    return glrt_tracking_snapshot_drained(w) && !(w[5]&16) && !w[6] && !w[7] &&
        w[20]==rate && (!w[2] || (!w[18] && !w[19]));
}
static int visit_inspect(void *pointer,struct glrt_visit_state *state)
{
    struct visit_context *v=pointer;struct iio_context *ctx=iio_create_local_context();
    struct iio_device *iq,*phy;struct iio_channel *rx,*lo,*txlo,*tx;
    char label[80],path[PATH_MAX],raw[4096];uint32_t w[24];long long hz,rate,bw,power;
    FILE *file=NULL;int rc=-1,enabled;
    if(!ctx) return -1;
    snprintf(label,sizeof(label),"glrt-iq-tracking-r%u-v1",v->rate);
    if(iio_context_set_timeout(ctx,2000) || !iio_context_get_attr_value(ctx,"hw_serial") ||
       strcmp(iio_context_get_attr_value(ctx,"hw_serial"),v->args[2]) ||
       !iio_context_get_attr_value(ctx,"fw_version") || strcmp(iio_context_get_attr_value(ctx,"fw_version"),label)) goto done;
    iq=iio_context_find_device(ctx,"starlink-glrt-iq");phy=iio_context_find_device(ctx,"ad9361-phy");
    if(!iq || !phy || iio_context_find_device(ctx,"cf-ad9361-dds-core-lpc") ||
       !is_attr(iq,"capture_abi","GLI1-1.0-upper-only") || !is_attr(iq,"tracking_abi","GLT1-1.0")) goto done;
    rx=iio_device_find_channel(phy,"voltage0",false);tx=iio_device_find_channel(phy,"voltage0",true);
    lo=iio_device_find_channel(phy,"altvoltage0",true);txlo=iio_device_find_channel(phy,"altvoltage1",true);
    if(channel_number(lo,"frequency",&hz) || channel_number(rx,"sampling_frequency",&rate) ||
       channel_number(rx,"rf_bandwidth",&bw) || channel_number(txlo,"powerdown",&power) ||
       rate!=v->rate || bw!=2500000 || power!=1 ||
       !channel_is(rx,"gain_control_mode","manual") || !channel_is(rx,"hardwaregain","30.000000 dB") ||
       !channel_is(rx,"rf_port_select","A_BALANCED") || !channel_is(tx,"hardwaregain","-80.000000 dB") ||
       !is_attr(phy,"ensm_mode","rx")) goto done;
    if(!iio_device_get_id(iq) || snprintf(path,sizeof(path),"/sys/bus/iio/devices/%s/buffer/enable",iio_device_get_id(iq))<=0 ||
       !(file=fopen(path,"r")) || fscanf(file,"%d",&enabled)!=1 || enabled) goto done;
    {
        int length=attr(iq,"tracking_snapshot",raw,NULL);
        if(length<=0 || glrt_tracking_snapshot_parse(raw,(size_t)length,w) ||
           !visit_idle_snapshot(w,v->rate))
            goto done;
        /* Retain the exact snapshot that passed validation. A second read
         * advances the hardware counter and cannot prove this inspection. */
        if(fprintf(v->journal,"snapshot %s\n",raw)<0 || fflush(v->journal)) goto done;
    }
    *state=(struct glrt_visit_state){(uint64_t)hz,wide(w+3),v->rate,w[2],1,1};rc=0;
done:
    if(file && fclose(file)) rc=-1;
    iio_context_destroy(ctx);return rc;
}
static int visit_tune(void *pointer,uint64_t hz)
{
    struct visit_context *v=pointer;struct glrt_visit_state state;
    struct iio_context *ctx;struct iio_device *phy;struct iio_channel *lo;int rc=-1;
    /* Recheck immediately before the only RF mutation, under the caller's
     * serial/global leases. Fixed receive clock and PN calibration persist. */
    if(visit_inspect(v,&state) || interrupted) return -1;
    ctx=iio_create_local_context();if(!ctx) return -1;
    phy=iio_context_find_device(ctx,"ad9361-phy");lo=phy ? iio_device_find_channel(phy,"altvoltage0",true) : NULL;
    if(lo && !iio_context_set_timeout(ctx,2000) && iio_channel_attr_write_longlong(lo,"frequency",(long long)hz)>=0) rc=0;
    iio_context_destroy(ctx);return rc;
}
static int visit_retain(void *pointer,const char *kind,unsigned number,int result,const struct glrt_visit_state *s)
{
    struct visit_context *v=pointer;
    return fprintf(v->journal,"visit %s %u %d %" PRIu64 " %u %u %" PRIu64 " %d %d\n",
        kind,number,result,s->lo_hz,s->rate,s->epoch,s->native_latest,s->idle,s->fixed_rf_valid)<0 || fflush(v->journal) ? -1 : 0;
}
static int status_number(const char *raw,const char *key,uint32_t *out)
{
    char token[80],*at,*end;unsigned long value;
    if(snprintf(token,sizeof(token),"\"%s\":",key)<=0 || !(at=strstr(raw,token)) ||
       strstr(at+strlen(token),token)) return -1;
    at+=strlen(token);
    if(*at<'0' || *at>'9') return -1;
    errno=0;value=strtoul(at,&end,10);
    if(errno || end==at || value>UINT32_MAX || (*end!=',' && *end!='}')) return -1;
    *out=(uint32_t)value;return 0;
}
/* A successful child exit is only a transport fact. Promote it to a scout
 * signal or completed follow-up from the child's single retained status line. */
static int visit_status(const char *path,uint32_t rate,const char *profile)
{
    char raw[2048],*newline;FILE *file=fopen(path,"r");size_t length;
    uint32_t actual_rate,status,blocks,attempts,handoffs,results,completed,worker;
    if(!file) return -1;
    length=fread(raw,1,sizeof(raw)-1,file);
    int invalid=ferror(file) || !feof(file) || !length;
    if(fclose(file) || invalid) return -1;
    raw[length]=0;newline=strchr(raw,'\n');
    if(!newline || newline!=raw+length-1 || strchr(newline+1,'\n') ||
       !strstr(raw,"\"scope\":\"bounded_live_cpu_acquisition_native_feedback\"")) return -1;
    if(status_number(raw,"rate",&actual_rate) || status_number(raw,"status",&status) ||
       status_number(raw,"blocks",&blocks) || status_number(raw,"attempts",&attempts) ||
       status_number(raw,"handoffs",&handoffs) || status_number(raw,"native_results",&results) ||
       status_number(raw,"native_completed_runs",&completed) ||
       status_number(raw,"worker_complete",&worker) || actual_rate!=rate || status || !worker) return -1;
    if(!strcmp(profile,SCOUT_PROFILE)) {
        if(blocks>BLOCKS || attempts>ATTEMPTS || completed>1) return -1;
        if(handoffs>=1 && completed==1 && results>=SCOUT_NATIVE_RESULTS) return GLRT_VISIT_SIGNAL;
        return !handoffs && !completed && !results ? GLRT_VISIT_DONE : -1;
    }
    if(!strcmp(profile,SPARSE_PROFILE) || !strcmp(profile,SPARSE30_PROFILE) ||
       !strcmp(profile,SPARSE100_PROFILE)) {
        uint32_t required=!strcmp(profile,SPARSE_PROFILE) ? SPARSE_NATIVE_RESULTS :
            !strcmp(profile,SPARSE30_PROFILE) ? SPARSE30_NATIVE_RESULTS : SPARSE100_NATIVE_RESULTS;
        if(blocks>45000 || attempts>256 || completed>1) return -1;
        if(handoffs>=1 && completed==1 && results>=required) return GLRT_VISIT_DONE;
        return !handoffs && !completed && !results ? GLRT_VISIT_NO_TRACK : -1;
    }
    return -1;
}
/* A short scan64 child can retain strong activity without satisfying the full
 * native handoff. One attempt above the corpus-derived floor selects the LO
 * for stricter scan80/local refinement; this never claims tracking success. */
static int visit_activity(const char *path)
{
    FILE *file=fopen(path,"r");char *line=NULL;size_t capacity=0;ssize_t length;
    unsigned expected_attempt=1,hits=0;int rc=-1;
    if(!file) return -1;
    while((length=getline(&line,&capacity,file))>=0) {
        static const char token[]="\"single_pilot_power\":[";
        char *at,*end;uint32_t attempt;unsigned count=0;double peak=0;
        if((size_t)length>65536) goto done;
        if(!strstr(line,"\"kind\":\"candidate_order\"")) continue;
        if(status_number(line,"attempt",&attempt) || attempt!=expected_attempt++ ||
           !(at=strstr(line,token)) || strstr(at+sizeof(token)-1,token)) goto done;
        at+=sizeof(token)-1;
        for(;;) {
            double value;
            if(*at<'0' || *at>'9') goto done;
            errno=0;value=strtod(at,&end);
            if(errno || end==at || !isfinite(value) || value<0 || value>1 || ++count>64) goto done;
            if(value>peak) peak=value;
            if(*end==']') { at=end+1;break; }
            if(*end!=',') goto done;
            at=end+1;
        }
        if(!count || (*at!=',' && *at!='}')) goto done;
        if(peak>=SCOUT_ACTIVITY_POWER) hits++;
    }
    if(ferror(file) || expected_attempt!=ATTEMPTS+1) goto done;
    rc=hits>=SCOUT_ACTIVITY_HITS;
done:
    free(line);if(fclose(file)) rc=-1;return rc;
}
static int visit_child(void *pointer,unsigned number,uint64_t deadline)
{
    struct visit_context *v=pointer;char directory[PATH_MAX],out[PATH_MAX],err[PATH_MAX],worker[PATH_MAX];
    char *args[]={v->args[0],v->args[1],v->args[2],v->args[3],v->args[4],directory,
        (char *)visit_profile(v),NULL};
    int stdout_fd=-1,stderr_fd=-1,status=0,stopping=0;pid_t pid,waited;uint64_t stop_at=0,now=clock_ns(NULL);
    if(snprintf(directory,sizeof(directory),"%s/visit-%u",v->args[5],number)<=0 || mkdir(directory,0700) ||
       snprintf(out,sizeof(out),"%s/stdout.json",directory)<=0 || snprintf(err,sizeof(err),"%s/stderr.txt",directory)<=0 ||
       snprintf(worker,sizeof(worker),"%s/worker.jsonl",directory)<=0) return -1;
    stdout_fd=open(out,O_WRONLY|O_CREAT|O_EXCL,0600);stderr_fd=open(err,O_WRONLY|O_CREAT|O_EXCL,0600);
    if(stdout_fd<0 || stderr_fd<0 || !now || now>=deadline) goto fail;
    pid=fork();
    if(pid<0) goto fail;
    if(!pid) {
        int rc;
        if(dup2(stdout_fd,STDOUT_FILENO)<0 || dup2(stderr_fd,STDERR_FILENO)<0) _exit(2);
        close(stdout_fd);close(stderr_fd);
        rc=(v->followup_probe_main && (!strcmp(visit_profile(v),SPARSE_PROFILE) ||
            !strcmp(visit_profile(v),SPARSE30_PROFILE) || !strcmp(visit_profile(v),SPARSE100_PROFILE)) ?
            v->followup_probe_main : v->probe_main)(visit_profile(v) ? 7 : 6,args);
        if(fflush(stdout) || fflush(stderr)) rc=2;
        _exit(rc);
    }
    close(stdout_fd);close(stderr_fd);
    for(;;) {
        struct timespec pause={0,1000000};
        waited=waitpid(pid,&status,WNOHANG);
        if(waited==pid) break;
        if(waited<0 && errno!=EINTR) return -1; /* no second child */
        now=clock_ns(NULL);
        if(!stopping && (interrupted || !now || now>=deadline)) {
            kill(pid,SIGTERM);stopping=1;stop_at=now;
        }
        if(stopping && (!now || now<stop_at || now-stop_at>=UINT64_C(2000000000))) kill(pid,SIGKILL);
        nanosleep(&pause,NULL);
    }
    if(stopping || !WIFEXITED(status)) return -1;
    if(WEXITSTATUS(status)==LIVE_VISIT_CLEAN_LOSS_EXIT) return GLRT_VISIT_CLEAN_LOSS;
    if(WEXITSTATUS(status)) return -1;
    if(v->followup_sparse) {
        int outcome=visit_status(out,v->rate,visit_profile(v));
        if(outcome==GLRT_VISIT_DONE && !strcmp(visit_profile(v),SCOUT_PROFILE)) {
            int activity=visit_activity(worker);
            if(activity<0) return -1;
            if(activity) { v->activity_selected=1;return GLRT_VISIT_SIGNAL; }
        }
        return outcome;
    }
    return 0;
fail:
    if(stdout_fd>=0) close(stdout_fd);
    if(stderr_fd>=0) close(stderr_fd);
    return -1;
}
int main(int argc,char **argv)
{
    struct visit_context context={0};struct glrt_visit_ports ports;
    char path[PATH_MAX];uint64_t lo[4];struct sigaction action={0};int rc;
    unsigned selected=UINT_MAX;int followup_started=0;
    if(visit_arguments(argc,argv,&context,lo)) return 2;
    context.probe_main=visit_probe_main;
    context.followup_probe_main=followup_probe_main;
    if(snprintf(path,sizeof(path),"%s/visits.txt",argv[5])<=0 || !(context.journal=fopen(path,"wx"))) return 2;
    action.sa_handler=signal_stop;sigemptyset(&action.sa_mask);
    if(sigaction(SIGALRM,&action,NULL) || sigaction(SIGTERM,&action,NULL) || sigaction(SIGINT,&action,NULL)) return 2;
    alarm(context.followup_sparse ? 400 : 60);
    ports=(struct glrt_visit_ports){&context,clock_ns,visit_cancelled,visit_inspect,visit_tune,visit_child,visit_retain};
    rc=fprintf(context.journal,"plan %u %s",context.rate,argv[2])<0 ? GLRT_VISIT_RETENTION : 0;
    for(unsigned n=0;n<context.visit_count;n++)
        if(fprintf(context.journal," %" PRIu64,lo[n])<0) rc=GLRT_VISIT_RETENTION;
    if(fprintf(context.journal," %s %u %" PRIu64 "\n",
       context.followup_sparse ? context.followup_plan : visit_profile(&context) ? visit_profile(&context) : "1536",
       context.visit_count,context.followup_sparse ? UINT64_C(400000000000) : UINT64_C(60000000000))<0 ||
       fflush(context.journal)) rc=GLRT_VISIT_RETENTION;
    if(!rc && context.followup_sparse) {
        rc=glrt_tracking_visit_until_signal(&ports,context.rate,lo,context.visit_count,&selected);
        if(rc==GLRT_VISIT_SIGNAL) {
            followup_started=1;context.profile=context.followup_profile;
            rc=glrt_tracking_visit_followup_run(&ports,context.rate,lo[selected],context.visit_count);
        }
    } else if(!rc) rc=glrt_tracking_visit_plan_run(&ports,context.rate,lo,context.visit_count);
    if(fprintf(context.journal,"terminal %d\n",rc)<0 || fclose(context.journal)) rc=GLRT_VISIT_RETENTION;
    alarm(0);
    printf("{\"scope\":\"%s\",\"rate\":%u,\"result\":%d,\"rf_sample_limit\":%u",
        context.followup_sparse ? "bounded_arm_scout_sparse_followup" :
        context.visit_count==2 ? "bounded_arm_two_frequency_visits" : "bounded_arm_frequency_revisits",
        context.rate,rc,context.visit_count*25165824U+(followup_started ? 737280000U : 0U));
    if(context.followup_sparse) {
        printf(",\"followup_started\":%d,\"track_complete\":%d,\"selection\":\"%s\",\"selected_index\":",
            followup_started,followup_started && rc==GLRT_VISIT_DONE,
            !followup_started ? "none" : context.activity_selected ? "retained_activity" : "native_handoff");
        if(selected==UINT_MAX) printf("null"); else printf("%u",selected);
    }
    printf("}\n");
    return rc ? 1 : 0;
}
