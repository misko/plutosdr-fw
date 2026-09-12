"""Actual pthread publication/copy boundary with independent index-coded IQ."""
from pathlib import Path
import subprocess

import pytest


BENCH = r'''
#define _POSIX_C_SOURCE 200809L
#include "glrt_tracking_iq_owner.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void fill(int16_t *iq,uint64_t first,size_t count)
{
    size_t n;
    for(n=0;n<count;n++) { iq[2*n]=(int16_t)(first+n);iq[2*n+1]=(int16_t)~(first+n); }
}
static void check(const int16_t *iq,uint64_t first,size_t count)
{
    size_t n;
    for(n=0;n<count;n++) {
        assert(iq[2*n]==(int16_t)(first+n));assert(iq[2*n+1]==(int16_t)~(first+n));
    }
}
static void barrier(pthread_barrier_t *b)
{ int rc=pthread_barrier_wait(b);assert(rc==0 || rc==PTHREAD_BARRIER_SERIAL_THREAD); }

struct concurrent {
    struct glrt_tracking_iq_owner owner;
    pthread_barrier_t ready,finished;
    unsigned copies;
};
static void *retained_worker(void *arg)
{
    struct concurrent *s=arg;
    struct glrt_tracking_iq_view before,after;
    int16_t copied[16],stale[16];
    assert(!glrt_tracking_iq_owner_copy(&s->owner,7,1000,copied,8,&before));
    assert(before.end==1008 && before.source_now==1020 && before.generation==2);
    barrier(&s->ready);
    // Simulate expensive numerical work outside the lock. The producer must
    // finish many ring wraps before this worker is allowed to resume.
    barrier(&s->finished);
    check(copied,1000,8);
    memset(stale,0x55,sizeof(stale));
    assert(glrt_tracking_iq_owner_copy(&s->owner,7,1000,stale,8,&after)==GLRT_RECENT_IQ_OVERWRITTEN);
    for(unsigned n=0;n<16;n++) assert(stale[n]==0x5555);
    assert(after.closed && after.valid && after.generation>before.generation);
    assert(before.end==1008 && before.source_now==1020);
    return NULL;
}
static void *copy_worker(void *arg)
{
    struct concurrent *s=arg;
    struct glrt_tracking_iq_view seen,copied;
    int16_t iq[8];
    int rc;
    // This first real copy makes test progress independent of thread startup.
    assert(!glrt_tracking_iq_owner_copy(&s->owner,7,1000,iq,4,&seen));
    check(iq,1000,4);s->copies++;
    barrier(&s->ready);
    for(;;) {
        assert(!glrt_tracking_iq_owner_copy(&s->owner,7,0,NULL,0,&seen));
        assert(seen.valid && seen.source_now>=seen.end && seen.observed_ns);
        if(seen.closed) break;
        uint64_t first=seen.end-4;
        memset(iq,0x55,sizeof(iq));
        rc=glrt_tracking_iq_owner_copy(&s->owner,7,first,iq,4,&copied);
        assert(copied.generation>=seen.generation && copied.source_now>=copied.end);
        if(rc==GLRT_RECENT_IQ_OVERWRITTEN) {
            for(unsigned n=0;n<8;n++) assert(iq[n]==0x5555);
        } else {
            assert(!rc && first>=copied.first && first+4<=copied.end);
            check(iq,first,4);s->copies++;
        }
    }
    return NULL;
}
int main(int argc,char **argv)
{
    struct glrt_tracking_iq_owner owner={0};
    struct glrt_tracking_iq_view view;
    int16_t storage[64],incoming[64],out[32];
    uint64_t first=UINT64_C(0x1000000000000000)+1000;
    assert(argc==2);
    if(!strcmp(argv[1],"concurrent") || !strcmp(argv[1],"retained")) {
        struct concurrent s={0};pthread_t worker;
        assert(!pthread_barrier_init(&s.ready,NULL,2));
        assert(!pthread_barrier_init(&s.finished,NULL,2));
        assert(!glrt_tracking_iq_owner_init(&s.owner,storage,32,7,1000));
        fill(incoming,1000,8);
        assert(!glrt_tracking_iq_owner_publish(&s.owner,7,1000,incoming,8,1020,42));
        int retained=!strcmp(argv[1],"retained");
        assert(!pthread_create(&worker,NULL,retained ? retained_worker : copy_worker,&s));
        barrier(&s.ready);
        for(unsigned n=0;n<3000;n++) {
            uint64_t start=1008+8*n;
            fill(incoming,start,8);
            assert(!glrt_tracking_iq_owner_publish(&s.owner,7,start,incoming,8,start+20,43+n));
        }
        assert(!glrt_tracking_iq_owner_close(&s.owner,0));
        if(retained) barrier(&s.finished);
        assert(!pthread_join(worker,NULL));
        if(!retained) assert(s.copies>0);
        assert(!glrt_tracking_iq_owner_destroy(&s.owner));
        assert(!pthread_barrier_destroy(&s.ready));assert(!pthread_barrier_destroy(&s.finished));
    } else {
        if(!strcmp(argv[1],"wrap")) first=UINT64_MAX-10;
        assert(!glrt_tracking_iq_owner_init(&owner,storage,32,7,first));
        assert(glrt_tracking_iq_owner_init(&owner,storage,32,7,first)==-1);
        assert(glrt_tracking_iq_owner_destroy(&owner)==-1);
        assert(!glrt_tracking_iq_owner_copy(&owner,7,0,NULL,0,&view));
        assert(view.first==first && view.end==first && view.source_now==first &&
               !view.observed_ns && view.valid && !view.closed && view.generation==1);
        fill(incoming,first,8);
        uint64_t initial_source=first+(!strcmp(argv[1],"wrap") ? 9 : 20);
        assert(!glrt_tracking_iq_owner_publish(&owner,7,first,incoming,8,initial_source,42));
        assert(!glrt_tracking_iq_owner_copy(&owner,7,first+2,out,4,&view));
        check(out,first+2,4);
        assert(view.end==first+8 && view.source_now==initial_source && view.observed_ns==42 && view.generation==2);
        if(!strcmp(argv[1],"lifecycle")) {
            assert(glrt_tracking_iq_owner_publish(&owner,6,first+8,incoming,8,0,0)==-2);
            memset(out,0x55,sizeof(out));
            assert(glrt_tracking_iq_owner_copy(&owner,6,first,out,8,&view)==-2);
            assert(view.epoch==7 && view.valid && view.generation==2);
            for(unsigned n=0;n<32;n++) assert(out[n]==0x5555);
            assert(!glrt_tracking_iq_owner_close(&owner,0));
            assert(glrt_tracking_iq_owner_publish(&owner,7,first+8,incoming,8,first+20,43)==GLRT_IQ_OWNER_CLOSED);
            assert(!glrt_tracking_iq_owner_copy(&owner,7,first,out,8,&view));
            check(out,first,8);assert(view.closed && view.valid);
        } else {
            uint64_t position=first+8,now=first+20,time=43;
            if(!strcmp(argv[1],"gap")) position++;
            else if(!strcmp(argv[1],"overlap")) position--;
            else if(!strcmp(argv[1],"future")) now=first+15;
            else if(!strcmp(argv[1],"source_regression")) now=first+19;
            else if(!strcmp(argv[1],"time_regression")) time=41;
            else if(!strcmp(argv[1],"zero_time")) time=0;
            else if(!strcmp(argv[1],"generation")) owner.generation=UINT64_MAX;
            else assert(!strcmp(argv[1],"wrap") || !strcmp(argv[1],"lost_close"));
            if(!strcmp(argv[1],"lost_close")) assert(!glrt_tracking_iq_owner_close(&owner,1));
            else assert(glrt_tracking_iq_owner_publish(&owner,7,position,incoming,8,now,time)==-3);
            memset(out,0x55,sizeof(out));
            assert(glrt_tracking_iq_owner_copy(&owner,7,first,out,8,&view)==-3);
            assert(!view.valid);
            for(unsigned n=0;n<32;n++) assert(out[n]==0x5555);
            assert(!glrt_tracking_iq_owner_close(&owner,1));
        }
        assert(!glrt_tracking_iq_owner_destroy(&owner));
        assert(!glrt_tracking_iq_owner_init(&owner,storage,32,8,500));
        assert(glrt_tracking_iq_owner_publish(&owner,7,0,incoming,8,0,0)==-2);
        assert(!glrt_tracking_iq_owner_copy(&owner,8,0,NULL,0,&view));
        assert(view.valid && view.epoch==8 && view.first==500 && view.generation==1);
        assert(!glrt_tracking_iq_owner_close(&owner,0));
        assert(!glrt_tracking_iq_owner_destroy(&owner));
    }
    puts("PASS");return 0;
}
'''


@pytest.fixture(scope="module")
def owner_binary(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("iq-owner")
    (out/"test.c").write_text(BENCH)
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
        "-I", str(root/"tools"), str(out/"test.c"), str(root/"tools/glrt_tracking_iq_owner.c"),
        str(root/"tools/glrt_tracking_recent_iq.c"), "-o", str(out/"test")], check=True)
    return out/"test"


@pytest.mark.parametrize("mode", ["lifecycle", "gap", "overlap", "future", "source_regression",
    "time_regression", "zero_time", "generation", "wrap", "lost_close", "retained", "concurrent"])
def test_copies_remain_bound_to_source_and_survive_concurrent_publication(owner_binary, mode):
    result = subprocess.run([str(owner_binary), mode], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout.strip() == "PASS", result.stdout+result.stderr
