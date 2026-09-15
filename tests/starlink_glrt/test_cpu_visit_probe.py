"""Actual fork/wait and evidence isolation; mock child performs no IIO calls."""
import ctypes as c
import json
import os
from pathlib import Path
import subprocess

import pytest

from .test_tracking_seed import SOURCES

pytestmark=pytest.mark.fftw

WRAPPER=r'''
#include "glrt_cpu_visit_probe.c"
int inspect_idle_words(const uint32_t w[24],uint32_t rate) { return visit_idle_snapshot(w,rate); }
int classify_activity(const char *path) { double score;return visit_activity_score(path,&score); }
double classify_retained_activity_score(const char *path) {
    double score=0;int rc=visit_activity_score(path,&score);return rc==1 ? score : rc ? -2 : -1;
}
int classify_activity_scores(const double *scores,unsigned count) { return isolated_activity(scores,count); }
int loss_disposition(unsigned fault) {
    struct live s={0};s.done=1;s.result=GLRT_NATIVE_ACQUISITION_LOST;s.native_clean_loss=1;
    interrupted=fault==1;
    if(fault==2) s.done=0;
    if(fault==3) s.started=1;
    if(fault==4) s.observer_started=1;
    if(fault==5) s.result=GLRT_NATIVE_RETENTION_ERROR;
    if(fault==6) s.native_clean_loss=0;
    if(fault==9) s.stop=1;
    return live_visit_clean_loss(fault==8 ? NULL : &s,fault!=7);
}
const char *iio_device_get_id(const struct iio_device *d) { (void)d;return "iio:device0"; }
int iio_channel_attr_read_longlong(const struct iio_channel *c,const char *n,long long *out)
{ (void)c;(void)n;(void)out;return -1; }
int iio_channel_attr_write_longlong(const struct iio_channel *c,const char *n,long long out)
{ (void)c;(void)n;(void)out;return -1; }
static int simulated_child(int argc,char **argv) {
    if(!strcmp(argv[1],"scan64")) {
        if(argc!=7 || strcmp(argv[6],"1536-selected-observer3-scan64")) return 9;
    } else if(!strcmp(argv[1],"selected")) {
        if(argc!=7 || strcmp(argv[6],"1536-selected")) return 9;
    } else if(!strncmp(argv[1],"scout_",6)) {
        if(argc!=7 || strcmp(argv[6],SCOUT_PROFILE)) return 9;
    } else if(!strncmp(argv[1],"sparse_",7)) {
        if(argc!=7 || strcmp(argv[6],SPARSE_PROFILE)) return 9;
    } else if(argc!=6) return 9;
    if(!strncmp(argv[1],"scout_",6) || !strncmp(argv[1],"sparse_",7)) {
        unsigned scout=!strncmp(argv[1],"scout_",6),signal=strstr(argv[1],"signal")!=NULL;
        unsigned complete=strstr(argv[1],"complete")!=NULL || signal;
        unsigned handoffs=complete,results=complete ? (scout ? 16 : 751) : 0;
        if(strstr(argv[1],"partial")) { handoffs=1;results=8;complete=0; }
        printf("{\"scope\":\"bounded_live_cpu_acquisition_native_feedback\",\"rate\":0,"
            "\"status\":0,\"blocks\":%u,\"attempts\":1,\"handoffs\":%u,"
            "\"native_results\":%u,\"native_completed_runs\":%u,\"worker_complete\":1}\n",
            scout ? 1536U : 45000U,handoffs,results,complete);
        if(scout) {
            char path[4096];snprintf(path,sizeof(path),"%s/worker.jsonl",argv[5]);FILE *f=fopen(path,"wx");
            unsigned strong=!strcmp(argv[1],"scout_activity") ? 2U : !strcmp(argv[1],"scout_weak") ? 1U : 0U;
            if(!f) return 8;
            for(unsigned n=1;n<=6;n++)
                fprintf(f,"{\"kind\":\"candidate_order\",\"attempt\":%u,\"single_pilot_power\":[%.3f,0.003,0.003]}\n",
                    n,n<=strong ? .05 : .01);
            if(fclose(f)) return 8;
        }
        return 0;
    }
    printf("retained child output\n");fprintf(stderr,"retained child diagnostics\n");
    if(!strcmp(argv[1],"fail")) return 1;
    if(!strcmp(argv[1],"clean_loss")) return LIVE_VISIT_CLEAN_LOSS_EXIT;
    if(!strcmp(argv[1],"unknown")) return 4;
    if(!strcmp(argv[1],"signal")) { raise(SIGKILL);return 0; }
    if(!strcmp(argv[1],"hang")) {
        signal(SIGTERM,SIG_IGN);
        while(1) pause();
    }
    return 0;
}
static int simulated_followup_child(int argc,char **argv) {
    if(argc!=7 || (strcmp(argv[6],SPARSE_PROFILE) && strcmp(argv[6],SPARSE30_PROFILE) &&
        strcmp(argv[6],SPARSE100_PROFILE) && strcmp(argv[6],SEGMENT30_PROFILE))) return 9;
    unsigned results=!strcmp(argv[6],SPARSE_PROFILE) ? 751U :
        !strcmp(argv[6],SPARSE100_PROFILE) ? 8335U : 2501U;
    unsigned blocks=!strcmp(argv[6],SEGMENT30_PROFILE) ? 7500U : 45000U;
    printf("{\"scope\":\"bounded_live_cpu_acquisition_native_feedback\",\"rate\":0,"
        "\"status\":0,\"blocks\":%u,\"attempts\":2,\"handoffs\":1,"
        "\"native_results\":%u,\"native_completed_runs\":1,\"worker_complete\":1}\n",blocks,results);
    return 0;
}
int exercise_child(const char *directory,const char *mode) {
    char *args[]={"probe",(char *)mode,"serial","bank","refs",(char *)directory};
    struct visit_context context={.args=args,.probe_main=simulated_child};
    context.visit_count=!strcmp(mode,"selected") ? 4 : 2;
    if(!strcmp(mode,"scan64")) context.profile="1536-selected-observer3-scan64";
    if(!strncmp(mode,"scout_",6)) { context.profile=SCOUT_PROFILE;context.followup_sparse=1; }
    if(!strncmp(mode,"sparse_",7)) { context.profile=SPARSE_PROFILE;context.followup_sparse=1; }
    uint64_t budget=!strcmp(mode,"hang") ? UINT64_C(100000000) : UINT64_C(2000000000);
    interrupted=0;
    int rc=visit_child(&context,0,clock_ns(NULL)+budget),status;
    if(waitpid(-1,&status,WNOHANG)!=-1 || errno!=ECHILD) return 99;
    return rc;
}
int invalid_plan(const char *directory,unsigned count,int adjacent) {
    char *args[]={"probe","30000000","1040005e0b100007100010000bf33a5d4d","bank","refs",
        (char *)directory,"1190312500","1440312500","1690312500","1940312500",NULL};
    args[5+count]=adjacent ? args[4+count] : "123";
    return main((int)count+6,args);
}
int exercise_four_children(const char *directory) {
    char *args[]={"probe","selected","serial","bank","refs",(char *)directory};
    struct visit_context context={.args=args,.probe_main=simulated_child,.visit_count=4};
    interrupted=0;
    for(unsigned n=0;n<4;n++) if(visit_child(&context,n,clock_ns(NULL)+UINT64_C(2000000000))) return -1;
    int status;return waitpid(-1,&status,WNOHANG)==-1 && errno==ECHILD ? 0 : -1;
}
int exercise_followup_child(const char *directory,const char *profile) {
    char *args[]={"probe","sparse_complete","serial","bank","refs",(char *)directory};
    struct visit_context context={.args=args,.probe_main=simulated_child,
        .followup_probe_main=simulated_followup_child,.visit_count=4,
        .profile=profile,.followup_sparse=1};
    interrupted=0;
    return visit_child(&context,4,clock_ns(NULL)+UINT64_C(2000000000));
}
int parse_plan(unsigned rate,unsigned count,const char *profile) {
    char raw_rate[32];snprintf(raw_rate,sizeof(raw_rate),"%u",rate);
    char *args[]={"probe",raw_rate,"1040005e0b100007100010000bf33a5d4d","bank","refs","out",
        "1190312500","1440312500","1690312500","1940312500",NULL,NULL};
    struct visit_context context={0};uint64_t lo[4];
    if(count>5) return -1;
    if(profile) args[6+count]=(char *)profile;
    if(visit_arguments(6+(int)count+(profile!=NULL),args,&context,lo)) return -1;
    const char *selected=visit_profile(&context);
    if(context.visit_count!=count || context.rate!=rate) return -2;
    if(context.followup_sparse) return selected && !strcmp(selected,SCOUT_PROFILE) ? 16 : -3;
    return selected && !strcmp(selected,"1536-selected-observer3-scan64") ? 64 : 8;
}
struct continuity_fake {
    struct glrt_visit_state state;
    uint64_t now;
    unsigned call,numbers[16];
    int mode;
    struct visit_context *visit;
};
static uint64_t continuity_clock(void *pointer) { return ((struct continuity_fake *)pointer)->now; }
static int continuity_cancelled(void *pointer) { (void)pointer;return 0; }
static int continuity_inspect(void *pointer,struct glrt_visit_state *state)
{ *state=((struct continuity_fake *)pointer)->state;return 0; }
static int continuity_tune(void *pointer,uint64_t hz)
{ struct continuity_fake *f=pointer;f->state.lo_hz=hz-4;f->now+=1000;return 0; }
static int continuity_run_child(void *pointer,unsigned number,uint64_t deadline) {
    struct continuity_fake *f=pointer;int outcome=0;(void)deadline;
    f->numbers[f->call]=number;f->state.epoch++;f->state.native_latest+=100000;f->now+=1000;
    if(f->mode==0) outcome=(f->call==0 || f->call==2) ? GLRT_VISIT_SIGNAL :
        f->call==1 ? GLRT_VISIT_CLEAN_LOSS : 0;
    else if(f->mode==2) outcome=(f->call%2)==0 ? GLRT_VISIT_SIGNAL : GLRT_VISIT_CLEAN_LOSS;
    else if(f->mode==3 && !strcmp(visit_profile(f->visit),SCOUT_PROFILE) && number<2) {
        double score=number ? .07 : .04;
        if(f->visit->activity_number==UINT_MAX || score>f->visit->activity_score) {
            f->visit->activity_number=number;f->visit->activity_score=score;
        }
    } else if(f->mode==3 && !strcmp(visit_profile(f->visit),SEGMENT30_PROFILE))
        outcome=GLRT_VISIT_CLEAN_LOSS;
    f->call++;return outcome;
}
static int continuity_retain(void *pointer,const char *kind,unsigned number,int outcome,
    const struct glrt_visit_state *state)
{ (void)pointer;(void)kind;(void)number;(void)outcome;(void)state;return 0; }
int exercise_continuity(int mode,unsigned out[7],unsigned numbers[16]) {
    struct continuity_fake fake={.state={1190312496,1000,30000000,1,1,1},.now=1000,.mode=mode};
    struct glrt_visit_ports ports={&fake,continuity_clock,continuity_cancelled,continuity_inspect,
        continuity_tune,continuity_run_child,continuity_retain};
    struct visit_context context={.journal=tmpfile(),.rate=30000000,.visit_count=4,
        .profile=SCOUT_PROFILE,.followup_profile=SEGMENT30_PROFILE,.followup_sparse=1,.continuity=1};
    fake.visit=&context;if(mode==3) context.ranked_continuity=1;
    struct continuity_result result;uint64_t lo[4]={1190312500,1440312500,1690312500,1940312500};
    if(!context.journal) return -99;
    int rc=continuity_run(&context,&ports,lo,&result);fclose(context.journal);
    out[0]=result.selected;out[1]=result.visits_executed;out[2]=result.scan_rounds;
    out[3]=result.segments_started;out[4]=(unsigned)result.track_complete;
    out[5]=fake.call;out[6]=(unsigned)rc;
    memcpy(numbers,fake.numbers,sizeof(fake.numbers));return rc;
}
'''


@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    root=Path(__file__).resolve().parents[2];out=tmp_path_factory.mktemp('visit-child')
    fixture=root/'tests/starlink_glrt/iio_probe_fixture'
    (out/'iio.h').write_text((fixture/'iio.h').read_text()+
        '\nconst char *iio_device_get_id(const struct iio_device *);\n'
        'int iio_channel_attr_read_longlong(const struct iio_channel *,const char *,long long *);\n'
        'int iio_channel_attr_write_longlong(const struct iio_channel *,const char *,long long);\n')
    (out/'wrapper.c').write_text(WRAPPER)
    prefix=os.environ.get('GLRT_FFTW_PREFIX')
    include=['-I',str(Path(prefix)/'include')] if prefix else []
    libraries=['-L',str(Path(prefix)/'lib'),'-Wl,-rpath,'+str(Path(prefix)/'lib')] if prefix else []
    names=['glrt_tracking_visit.c','glrt_cpu_coarse.c','glrt_cpu_seed.c','glrt_tracking_worker.c',
        'glrt_tracking_live_bootstrap.c','glrt_tracking_observer.c','glrt_tracking_iq.c',
        'glrt_iq_tracking_source.c','glrt_capture_source.c','glrt_tracking_transport.c',
        'glrt_native_controller.c','glrt_native_posix.c',*SOURCES]
    subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-pthread','-shared','-fPIC',
        '-I',str(out),'-I',str(root/'tools'),*include,str(out/'wrapper.c'),str(fixture/'backend.c'),
        *(str(root/'tools'/name) for name in names),*libraries,'-lfftw3','-lm','-o',str(out/'visit.so')],check=True)
    lib=c.CDLL(str(out/'visit.so'));lib.exercise_child.argtypes=[c.c_char_p,c.c_char_p]
    lib.inspect_idle_words.argtypes=[c.POINTER(c.c_uint32),c.c_uint32]
    lib.classify_activity.argtypes=[c.c_char_p]
    lib.classify_retained_activity_score.argtypes=[c.c_char_p]
    lib.classify_retained_activity_score.restype=c.c_double
    lib.classify_activity_scores.argtypes=[c.c_void_p,c.c_uint]
    lib.invalid_plan.argtypes=[c.c_char_p,c.c_uint,c.c_int]
    lib.exercise_four_children.argtypes=[c.c_char_p]
    lib.exercise_followup_child.argtypes=[c.c_char_p,c.c_char_p]
    lib.parse_plan.argtypes=[c.c_uint,c.c_uint,c.c_char_p]
    lib.exercise_continuity.argtypes=[c.c_int,c.c_void_p,c.c_void_p]
    return lib


@pytest.mark.parametrize('mode',['pass','fail','hang','existing','clean_loss','unknown','signal','selected','scan64',
    'scout_signal','scout_activity','scout_weak','scout_empty','scout_partial',
    'sparse_complete','sparse_empty','sparse_partial'])
def test_child_is_reaped_before_return_and_evidence_is_never_overwritten(probe,tmp_path,mode):
    if mode=='existing':
        (tmp_path/'visit-0').mkdir();(tmp_path/'visit-0/stdout.json').write_text('preserved')
    expected={'pass':0,'selected':0,'scan64':0,'clean_loss':1,'scout_signal':2,'scout_activity':2,
        'scout_weak':2,'scout_empty':0,
        'sparse_complete':0,'sparse_empty':3}.get(mode,-1)
    assert probe.exercise_child(os.fsencode(tmp_path),mode.encode())==expected
    if mode=='existing': assert (tmp_path/'visit-0/stdout.json').read_text()=='preserved'
    elif mode.startswith(('scout_','sparse_')):
        assert json.loads((tmp_path/'visit-0/stdout.json').read_text())['scope']=='bounded_live_cpu_acquisition_native_feedback'
    elif mode not in ('hang','signal'):
        assert (tmp_path/'visit-0/stdout.json').read_text()=='retained child output\n'
        assert (tmp_path/'visit-0/stderr.txt').read_text()=='retained child diagnostics\n'


@pytest.mark.parametrize('fault',range(10))
def test_clean_loss_requires_terminal_joined_native_provenance(probe,fault):
    assert probe.loss_disposition(fault)==int(fault==0)


@pytest.mark.parametrize('count',[2,3,4])
@pytest.mark.parametrize('adjacent',[0,1])
def test_entire_plan_is_checked_before_creating_evidence(probe,tmp_path,count,adjacent):
    assert probe.invalid_plan(os.fsencode(tmp_path),count,adjacent)==2
    assert not list(tmp_path.iterdir())


def test_four_selected_children_have_separate_evidence_and_are_all_reaped(probe,tmp_path):
    assert probe.exercise_four_children(os.fsencode(tmp_path))==0
    assert sorted(p.name for p in tmp_path.iterdir())==[f'visit-{n}' for n in range(4)]
    for n in range(4):
        assert (tmp_path/f'visit-{n}/stdout.json').read_text()=='retained child output\n'


@pytest.mark.parametrize('profile',[SPARSE_PROFILE := b'45000-selected-observer9-scan80-local2-track10-sparse10-authority',
    b'45000-selected-observer9-scan80-local2-track30-sparse10-authority',
    b'45000-selected-observer9-scan80-local2-track100-sparse10-authority',
    b'7500-selected-observer9-scan80-local2-track30-sparse10-authority-segment'])
def test_sparse_followup_uses_reacquiring_probe(probe,tmp_path,profile):
    assert probe.exercise_followup_child(os.fsencode(tmp_path),profile)==0
    status=json.loads((tmp_path/'visit-4/stdout.json').read_text())
    assert status['attempts']==2
    assert status['native_completed_runs']==1


@pytest.mark.parametrize('damage,expected',[
    ('none',1),('one_hit',1),('zero_hit',0),('missing_attempt',-1),('duplicate_attempt',-1),
    ('short',-1),('too_many',-1),('nan',-1),('duplicate_power',-1),
])
def test_retained_activity_requires_one_strong_bounded_attempt(probe,tmp_path,damage,expected):
    rows=[]
    for attempt in range(1,7):
        power=.05 if attempt<=2 else .01
        if damage=='one_hit' and attempt==2: power=.014
        if damage=='zero_hit': power=.014
        row={'kind':'candidate_order','attempt':attempt,'single_pilot_power':[power,.003,.003]}
        rows.append(json.dumps(row,separators=(',',':')))
    if damage=='missing_attempt': rows[2]=rows[2].replace('"attempt":3','"attempt":4')
    if damage=='duplicate_attempt': rows[1]=rows[1].replace('"attempt":2','"attempt":1')
    if damage=='short': rows.clear()
    if damage=='too_many': rows[0]=rows[0].replace('[0.05,0.003,0.003]', '['+','.join(['0.05']*65)+']')
    if damage=='nan': rows[0]=rows[0].replace('0.05','NaN')
    if damage=='duplicate_power': rows[0]=rows[0].replace('}',',"single_pilot_power":[0.05]}')
    path=tmp_path/'worker.jsonl';path.write_text('\n'.join(rows)+'\n')
    assert probe.classify_activity(os.fsencode(path))==expected


@pytest.mark.parametrize('power,floor,expected',[
    (.014,.002,0),
    (.018,.003,1),
    (.018,.0031,0),
    (.029,.0027,1),
])
def test_retained_activity_uses_absolute_and_local_floor_gates(probe,tmp_path,power,floor,expected):
    rows=[json.dumps({'kind':'candidate_order','attempt':attempt,
        'single_pilot_power':[power,floor,floor]},separators=(',',':'))
        for attempt in range(1,7)]
    path=tmp_path/'worker.jsonl';path.write_text('\n'.join(rows)+'\n')
    assert probe.classify_activity(os.fsencode(path))==expected


@pytest.mark.parametrize('power,floor,expected',[
    (.014,.002,0),(.018,.003,1),(.018,.0031,0),(.029,.0027,1),
])
def test_live_scout_and_retained_reviewer_share_activity_gate(probe,power,floor,expected):
    scores=(c.c_double*3)(power,floor,floor)
    assert probe.classify_activity_scores(scores,len(scores))==expected


def test_retained_activity_can_end_after_first_detected_attempt(probe,tmp_path):
    row={'kind':'candidate_order','attempt':1,'single_pilot_power':[.018,.003,.003]}
    path=tmp_path/'worker.jsonl';path.write_text(json.dumps(row,separators=(',',':'))+'\n')
    assert probe.classify_activity(os.fsencode(path))==1


def test_retained_activity_score_is_strongest_candidate_not_array_position(probe,tmp_path):
    row={'kind':'candidate_order','attempt':1,'single_pilot_power':[.003,.052,.004]}
    path=tmp_path/'worker.jsonl';path.write_text(json.dumps(row,separators=(',',':'))+'\n')
    assert probe.classify_retained_activity_score(os.fsencode(path))==pytest.approx(.052)


@pytest.mark.parametrize('rate',[30000000,60000000,2500000])
@pytest.mark.parametrize('count',[1,2,3,4])
@pytest.mark.parametrize('profile',[None,b'1536-selected-observer3-scan64',b'sparse10-after-scout16',
    b'sparse30-after-scout16',b'sparse100-after-scout16',b'continuity30-after-scout16',
    b'continuity30-ranked-after-scout16',b'unknown'])
def test_explicit_scan64_plan_preserves_legacy_and_rejects_invalid_arguments(probe,rate,count,profile):
    valid=rate in (30000000,60000000) and count in (2,3,4) and profile!=b'unknown'
    expected=16 if profile in (b'sparse10-after-scout16',b'sparse30-after-scout16',b'sparse100-after-scout16',
        b'continuity30-after-scout16',b'continuity30-ranked-after-scout16') else 64 if profile else 8
    assert probe.parse_plan(rate,count,profile)==(expected if valid else -1)


@pytest.mark.parametrize('mode,expected,numbers',[
    (0,[0,4,2,2,1,4,0],[0,1,2,3]),
    (1,[2**32-1,12,3,0,0,12,0],list(range(12))),
    (2,[0,6,3,3,0,6,1],list(range(6))),
    (3,[1,13,3,1,0,13,0],list(range(13))),
])
def test_continuity_rescans_with_contiguous_evidence_and_stops_on_complete(probe,mode,expected,numbers):
    out=(c.c_uint*7)();seen=(c.c_uint*16)()
    rc=probe.exercise_continuity(mode,out,seen)
    assert list(out)==expected and rc==expected[-1]
    assert list(seen)[:len(numbers)]==numbers


@pytest.mark.parametrize('rate',[30000000,60000000])
@pytest.mark.parametrize('epoch',[0,1,7])
@pytest.mark.parametrize('mode',['idle','boot_drops','active','fault','configured','wrong_rate','unread'])
def test_only_epoch_zero_can_have_pre_acquisition_drop_counters(probe,rate,epoch,mode):
    words=(c.c_uint32*24)();words[2]=epoch;words[20]=rate
    words[0]=0x474c5431;words[1]=1;words[21]=rate*33//25000;words[22]=0xb04a2fab;words[23]=1
    if mode=='boot_drops': words[18]=4;words[19]=5413144
    if mode=='active': words[5]=16
    if mode=='fault': words[6]=1
    if mode=='configured': words[7]=1
    if mode=='wrong_rate': words[20]=2500000
    if mode=='unread': words[9]=1
    assert probe.inspect_idle_words(words,rate)==int(mode=='idle' or (mode=='boot_drops' and epoch==0))
