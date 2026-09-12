"""Live-owner IQ reaches real bootstrap arithmetic before a future handoff."""
from pathlib import Path
import subprocess

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows


BENCH = r'''
#include "glrt_tracking_live_bootstrap.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc,char **argv)
{
    struct glrt_tracking_iq_owner owner={0};
    struct glrt_tracking_bootstrap_live live;
    struct glrt_tracking_bootstrap_trace trace;
    int16_t refs[52800],scratch[6600];
    size_t count=213300;
    uint64_t anchor=1000000;
    int rc;
    assert(argc==3);
    FILE *f=fopen(argv[2],"rb");assert(f);
    assert(fread(refs,sizeof(refs),1,f)==1 && fgetc(f)==EOF);assert(!fclose(f));
    if(!strcmp(argv[1],"positive_large")) anchor=UINT64_C(0x1000000000000000)+1000;
    size_t capacity=!strcmp(argv[1],"overwrite") ? 3300 : 250000;
    int16_t *storage=calloc(2*capacity,sizeof(*storage)),*iq=calloc(2*count,sizeof(*iq));
    assert(storage && iq);
    assert(!glrt_tracking_iq_owner_init(&owner,storage,capacity,3,anchor));
    assert(!glrt_tracking_bootstrap_live_init(&live,3,anchor,0,0,anchor+5000000));
    if(strcmp(argv[1],"negative"))
        for(unsigned frame=0;frame<8;frame++)
            for(unsigned n=0;n<3300;n++) {
                iq[2*(frame*30000+n)]=refs[4*n];iq[2*(frame*30000+n)+1]=refs[4*n+1];
            }
    memset(&trace,0x55,sizeof(trace));
    assert(glrt_tracking_live_bootstrap_step(&live,&owner,refs,scratch,2500,&trace)==GLRT_BOOTSTRAP_WAIT);
    assert(!trace.handoff.rate && !trace.job.start && !trace.moments.count && !live.core.jobs);
    if(!strcmp(argv[1],"waiting")) {
        assert(!glrt_tracking_iq_owner_publish(&owner,3,anchor,iq,3299,anchor+3300,42));
        for(unsigned n=0;n<3;n++) {
            assert(glrt_tracking_live_bootstrap_step(&live,&owner,refs,scratch,2500,&trace)==GLRT_BOOTSTRAP_WAIT);
            assert(!trace.job.start && !trace.handoff.rate && !live.core.pending && !live.core.jobs);
        }
    } else {
        assert(!glrt_tracking_iq_owner_publish(&owner,3,anchor,iq,count,anchor+count+1000,42));
        if(!strcmp(argv[1],"closed")) assert(!glrt_tracking_iq_owner_close(&owner,0));
        if(!strcmp(argv[1],"lost")) assert(!glrt_tracking_iq_owner_close(&owner,1));
        if(!strcmp(argv[1],"stale")) live.core.trend.history.epoch=4;
        if(!strcmp(argv[1],"deadline")) live.source_deadline=anchor+count;
        if(!strcmp(argv[1],"bad_rate")) live.core.trend.rate=5000000;
        if(!strncmp(argv[1],"positive",8) || !strcmp(argv[1],"negative")) {
            for(unsigned n=0;n<8;n++) {
                rc=glrt_tracking_live_bootstrap_step(&live,&owner,refs,scratch,2500,&trace);
                assert(rc==GLRT_BOOTSTRAP_PAST && trace.frame==n*9 && trace.job.start==anchor+n*30000);
                assert(trace.source.end==anchor+count && trace.source.source_now==anchor+count+1000);
                assert(trace.source.observed_ns==42 && trace.source.epoch==3 && trace.source.valid && !trace.source.closed);
                assert(trace.job.start+3300<=trace.source.end && trace.moments.start==trace.job.start && trace.moments.count==3300);
                assert(live.core.jobs==n+1 && !live.core.pending && !trace.handoff.rate);
                assert(!memcmp(scratch,iq+2*n*30000,sizeof(scratch)));
                if(!strcmp(argv[1],"negative")) assert(!trace.accepted && trace.estimate.rejection);
                else assert(trace.accepted==1 && !trace.estimate.rejection && trace.estimate.coherence>.99 &&
                            fabs(trace.estimate.cfo_hz)<5 && fabs(trace.estimate.delay_correction_s)<1e-8);
            }
            rc=glrt_tracking_live_bootstrap_step(&live,&owner,refs,scratch,2500,&trace);
            if(!strcmp(argv[1],"negative"))
                assert(rc==GLRT_BOOTSTRAP_ERROR && live.core.failure==GLRT_BOOTSTRAP_HISTORY && !trace.handoff.rate);
            else {
                assert(rc==GLRT_BOOTSTRAP_READY && trace.handoff.rate==2500000 && trace.handoff.prediction.repeats==8);
                assert(trace.job.start>=trace.source.source_now+2500 && !trace.moments.count);
                assert(trace.frame+7-live.core.trend.history.last_supported<=32);
                // READY is a finite handoff, never a reusable permission to
                // submit repeatedly or consume an old copied trace.
                assert(glrt_tracking_live_bootstrap_step(&live,&owner,refs,scratch,2500,&trace)==GLRT_BOOTSTRAP_ERROR);
                assert(!trace.handoff.rate && !trace.job.start);
            }
        } else {
            assert(glrt_tracking_live_bootstrap_step(&live,&owner,refs,scratch,2500,&trace)==GLRT_BOOTSTRAP_ERROR);
            assert(!live.core.valid && !live.core.pending && !trace.handoff.rate && !trace.job.start);
            assert(live.core.failure==(!strcmp(argv[1],"deadline") ? GLRT_BOOTSTRAP_BUDGET :
                   !strcmp(argv[1],"bad_rate") ? GLRT_BOOTSTRAP_INVALID : GLRT_BOOTSTRAP_SOURCE_LOSS));
        }
    }
    assert(!glrt_tracking_iq_owner_close(&owner,0));
    assert(!glrt_tracking_iq_owner_destroy(&owner));
    free(iq);free(storage);puts("PASS");return 0;
}
'''


@pytest.fixture(scope="module")
def live_binary(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("live-bootstrap")
    (out/"test.c").write_text(BENCH)
    files = ["glrt_tracking_live_bootstrap.c", "glrt_tracking_iq_owner.c", "glrt_tracking_recent_iq.c",
        "glrt_tracking_bootstrap.c", "glrt_tracking_iq.c", "glrt_native_trend.c", "glrt_native_schedule.c",
        "glrt_tracking_schedule.c", "glrt_native_solver.c"]
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
        "-I", str(root/"tools"), str(out/"test.c"), *(str(root/"tools"/name) for name in files),
        "-lm", "-o", str(out/"test")], check=True)
    bank = root/"hdl/library/starlink_glrt"
    cubic = (bank/"native_cubic_60000000_upper.mem").read_bytes()
    direct = (bank/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes()
    np.asarray([reference_rows(cubic, direct, 2500000, phase) for phase in range(4)], dtype="<i2").tofile(out/"references")
    return out/"test", out/"references"


@pytest.mark.parametrize("mode", ["positive", "positive_large", "negative", "waiting", "closed",
    "lost", "stale", "deadline", "overwrite", "bad_rate"])
def test_actual_copied_pilots_build_only_causal_bounded_handoff(live_binary, mode):
    binary, references = live_binary
    result = subprocess.run([str(binary), mode, str(references)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout.strip() == "PASS", result.stdout+result.stderr
