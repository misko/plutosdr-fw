"""Actual mailbox equivalence for a conservative writer-phase authorization."""
import argparse,json,subprocess,time
from pathlib import Path
from staged_fft_experiment import fresh,require,sha
ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
def run(output):
    sources=[RTL/'tb_product_publication_ownership.sv',RTL/'starlink_pss_product_mailbox_staged_identity.v',Path(__file__).resolve()]
    before={str(p):sha(p) for p in sources};fresh(output);started=time.time();results=[]
    for aw in [2,9]:
        for name,auth in [('candidate','candidate_auth'),('missing_veto','committed && (ov === 1\'b0)')]:
            folder=output/(str(aw)+'-'+name);folder.mkdir()
            bench=folder/'tb.sv';bench.write_text(sources[0].read_text().replace('__AUTH__',auth))
            build=subprocess.run(['iverilog','-g2012','-s','tb','-Ptb.AW='+str(aw),'-o',str(folder/'sim'),str(bench),str(sources[1])],capture_output=True,text=True,timeout=30)
            (folder/'compile.log').write_text(build.stdout+build.stderr)
            require(build.returncode==0,'actual bank comparison compiles')
            result=subprocess.run(['vvp',str(folder/'sim')],capture_output=True,text=True,timeout=60)
            (folder/'simulate.log').write_text(result.stdout+result.stderr)
            if name=='candidate':require(result.returncode==0 and 'PRODUCT_OWNERSHIP_PASS' in result.stdout,'ownership and exact original bank')
            else:require(result.returncode!=0 and 'bank state mismatch' in result.stdout,'current veto mutant rejected')
            results.append(dict(aw=aw,name=name,returncode=result.returncode,log=result.stdout,sha256=sha(folder/'simulate.log')))
    require(before=={p:sha(Path(p)) for p in before},'proof source stability')
    result=dict(passed=True,before=before,results=results,elapsed=time.time()-started,deployment_eligible=False)
    (output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    print(json.dumps(run(p.parse_args().output),indent=2))

