"""Closed native publication, including failure and interrupted-write behavior."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tests.starlink_glrt.test_native_binding import evidence
from tests.starlink_glrt.test_native_controller import controller, pilot_words
from tools import starlink_glrt_native_publication as p


def inputs(tmp_path, controller, pilot_words):
    values = evidence(controller, pilot_words)
    paths = {}
    for name in ('journal','owner','protocol','summary','final_snapshot'):
        path=tmp_path/name;path.write_bytes(values[name]);paths[name]=path
    paths['iq']=tmp_path/'iq.ci16';paths['iq'].write_bytes(bytes(values['iq_bytes']))
    return dict(**paths,episode_index=0,output=tmp_path/'published')


def test_publication_keeps_raw_inputs_and_failure_outcomes(tmp_path, controller, pilot_words):
    args=inputs(tmp_path,controller,pilot_words)
    owner=json.loads(args['owner'].read_text());owner['status']='failed'
    owner['episodes'][0]['runtime']['result']=-5;owner['episodes'][0]['process_exit']=1
    owner['episodes'][0]['journal_sha256']=p.sha(args['journal'].read_bytes())
    args['owner'].write_text(json.dumps(owner))
    manifest=p.publish_episode(**args)
    assert manifest['publication_status']=='complete' and manifest['runtime_result']==-5
    assert manifest['owner_status']=='failed' and not manifest['physical_precision_qualified']
    assert manifest['coarse_iq']['embedded'] is False
    assert json.loads((args['output']/'manifest.json').read_text())==manifest
    assert (args['output']/'journal.glrj').read_bytes()==args['journal'].read_bytes()
    assert (args['output']/'owner-receipt.json').read_bytes()==args['owner'].read_bytes()
    for name, artifact in manifest['artifacts'].items():
        data=(args['output']/name).read_bytes()
        assert len(data)==artifact['bytes'] and p.sha(data)==artifact['sha256']
    binding=json.loads((args['output']/'source-binding.json').read_text())
    assert binding['recording_export_sha256']==manifest['artifacts']['recording.json']['sha256']
    before=(args['output']/'manifest.json').read_bytes()
    with pytest.raises(FileExistsError):p.publish_episode(**args)
    assert (args['output']/'manifest.json').read_bytes()==before


def test_invalid_source_creates_no_publication(tmp_path, controller, pilot_words):
    args=inputs(tmp_path,controller,pilot_words)
    args['iq'].write_bytes(b'wrong')
    with pytest.raises(ValueError):p.publish_episode(**args)
    assert not args['output'].exists()


def test_payload_failure_leaves_no_complete_manifest_and_no_automatic_resume(
        tmp_path,controller,pilot_words,monkeypatch):
    args=inputs(tmp_path,controller,pilot_words)
    write=p.write_payload;count=0
    def fail(path,data):
        nonlocal count
        count+=1
        if count==2:raise OSError('retention failed')
        write(path,data)
    monkeypatch.setattr(p,'write_payload',fail)
    with pytest.raises(OSError,match='retention failed'):p.publish_episode(**args)
    assert (args['output']/'journal.glrj').exists()
    assert not (args['output']/'manifest.json').exists()
    monkeypatch.setattr(p,'write_payload',write)
    with pytest.raises(FileExistsError):p.publish_episode(**args)


def test_manifest_is_published_only_after_payloads_are_retained(
        tmp_path,controller,pilot_words,monkeypatch):
    args=inputs(tmp_path,controller,pilot_words)
    original_link=p.os.link;observed=[]
    def link(source,target):
        manifest=json.loads(Path(source).read_text())
        for name,artifact in manifest['artifacts'].items():
            assert p.sha((args['output']/name).read_bytes())==artifact['sha256']
        assert not Path(target).exists();observed.append(True)
        original_link(source,target)
    monkeypatch.setattr(p.os,'link',link)
    p.publish_episode(**args)
    assert observed==[True] and not list(args['output'].glob('.manifest-*'))


def test_publication_cli_reports_manifest_digest(tmp_path,controller,pilot_words):
    args=inputs(tmp_path,controller,pilot_words)
    command=[sys.executable,'-m','tools.starlink_glrt_native_publication']
    for name,value in args.items():command+=['--'+name.replace('_','-'),str(value)]
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(command,cwd=root,check=True,text=True,capture_output=True)
    report=json.loads(result.stdout)
    assert report['manifest_sha256']==p.sha(Path(report['manifest']).read_bytes())
    assert report['head_count']==16 and report['publication_status']=='complete'
