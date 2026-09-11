"""Ethernet source hooks for PPU's bounded native supervisor.

The owner supplies the public station lease and numerical seed builder. Capture
and companion programs run through their public CLIs. No firmware writes, radio
discovery fallback, private application imports or automatic fault retries.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import signal
import subprocess
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path

from pluto_plus import glrt_canary as g
from pluto_plus.native_journal_export import export_stopped_journal
from pluto_plus.native_supervisor import NativeCandidate, NativeEpisode
from pluto_plus.radio_lock import acquire_radio_lock

from .starlink_glrt_iio import Context, Library
from .starlink_glrt_lean_abi import LeanSnapshot
from .starlink_glrt_native_journal import recover, review
from .starlink_glrt_native_restart import restart_fence
from .starlink_glrt_schedule_abi import ScheduleBatch, ScheduleSnapshot


def save(path, value):
    data = value if isinstance(value, bytes) else (json.dumps(value, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def one_line(text, prefix):
    rows = [row for row in text.splitlines() if row.startswith(prefix)]
    if len(rows) != 1:
        raise ValueError('missing or ambiguous ' + prefix)
    return rows[0]


def read_publication(path):
    try:
        with path.open('rb') as stream:
            data = stream.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            raise ValueError('oversized companion publication')
        return json.loads(data)
    except FileNotFoundError:
        return None


@dataclass(frozen=True)
class CapturePrograms:
    """Executable locations, passed explicitly rather than importing a host app."""
    host_python: Path
    host_cwd: Path
    follower: Path
    capture_python: Path
    firmware_cwd: Path
    bank: Path
    ddc_manifest: Path

    def commands(self, root, identity, host, visit, samples):
        capture, live, work = (root / name for name in ('capture', 'live', 'work'))
        precision = [str(self.host_python), '-m', 'leo.cli.glrt_precision',
            '--iq', str(capture/'iq.ci16'), '--samples', str(samples), '--serial', identity.serial,
            '--collector-protocol', str(capture/'protocol.json'),
            '--collector-summary', str(capture/'summary.json'),
            '--collector-final-snapshot', str(capture/'final_snapshot.txt'),
            '--output', str(live), '--follow']
        follower = [str(self.host_python), str(self.follower), '--capture', str(capture),
            '--records', str(live/'records.jsonl'), '--precision-summary', str(live/'summary.json'),
            '--bank', str(self.bank), '--ddc-manifest', str(self.ddc_manifest),
            '--output', str(work), '--samples', str(samples), '--serial', identity.serial,
            '--timeout', '300', '--follow', '--template-relative', '--bridge-one-rejected-frame']
        collector = [str(self.capture_python), '-m', 'tools.starlink_glrt_lean_capture',
            '--uri', 'ip:'+host, '--serial', identity.serial, '--firmware-version', identity.firmware,
            '--visit', str(visit), '--samples', str(samples), '--lo-hz', '1690312496',
            '--bandwidth-hz', '2500000', '--chunk-samples', '250000', '--output', str(capture)]
        return [('precision', precision, self.host_cwd), ('companion', follower, self.host_cwd),
                ('coarse', collector, self.firmware_cwd)]


class CapturePipeline:
    """Retain the bounded corpus in place, including partial/failed source evidence."""
    def __init__(self, programs, root, *, popen=subprocess.Popen, clock=time.monotonic,
                 sleep=time.sleep):
        self.programs, self.root = programs, root
        self.popen, self.clock, self.sleep = popen, clock, sleep
        self.children = []
        self.source_end = None

    def require_running(self):
        if any(child.poll() is not None for _, child, _ in self.children):
            raise RuntimeError('a native source pipeline exited')

    def start(self, identity, host, visit, samples, deadline, cancel):
        self.root.mkdir(parents=True, exist_ok=False)
        commands = self.programs.commands(self.root, identity, host, visit, samples)
        save(self.root/'commands.json', [(name, argv, str(cwd)) for name, argv, cwd in commands])
        for name, argv, cwd in commands:
            if name == 'coarse':
                while True:
                    self.require_running()
                    if cancel.is_set() or self.clock() >= deadline:
                        raise TimeoutError('capture startup cancelled or expired')
                    try:
                        precision = read_publication(self.root/'live/protocol.json')
                        companion = read_publication(self.root/'work/protocol.json')
                    except json.JSONDecodeError:
                        self.sleep(.005)
                        continue
                    if precision is not None and companion is not None:
                        if (precision.get('schema') != 'glrt-precision-stream/v1'
                                or companion.get('scope') != 'coarse_native_bootstrap_companion'
                                or companion.get('arguments', {}).get('template_relative') is not True):
                            raise ValueError('companion protocol differs')
                        break
                    self.sleep(.005)
            log = (self.root/(name+'.log')).open('x')
            try:
                if name == 'coarse':
                    self.source_end = self.clock()+samples/2_500_000
                child = self.popen(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            except BaseException:
                log.close()
                raise
            self.children.append((name, child, log))
        while True:
            self.require_running()
            if cancel.is_set() or self.clock() >= deadline:
                raise TimeoutError('live source startup cancelled or expired')
            live = read_publication(self.root/'capture/live_source.json')
            if live is not None:
                if (live.get('schema') != 'glrt-lean-live-source/v1'
                        or live.get('serial') != identity.serial or live.get('visit') != visit
                        or live.get('provisional') is not True
                        or live.get('source_rate_hz') != 60000000
                        or live.get('output_rate_hz') != 2500000
                        or live.get('native_samples_per_output_sample') != 24):
                    raise ValueError('live capture source differs')
                return
            self.sleep(.005)

    def close(self, deadline):
        """Native writer must already be stopped. Never erase a partial corpus."""
        outcomes = []
        for name, child, log in reversed(self.children):
            try:
                # Let a nearly completed finite collector retain complete source
                # evidence when its natural end fits the existing cleanup bound.
                if (name == 'coarse' and child.poll() is None and self.source_end is not None
                        and self.source_end+3 < deadline):
                    try:
                        child.wait(timeout=max(.001, self.source_end+3-self.clock()))
                    except subprocess.TimeoutExpired:
                        pass
                if child.poll() is None:
                    child.send_signal(signal.SIGINT)
                    child.wait(timeout=max(.001, min(8, deadline-self.clock())))
                outcomes.append({'name': name, 'exit_code': child.poll()})
            except (OSError, subprocess.TimeoutExpired) as error:
                outcomes.append({'name': name, 'error': str(error), 'pid': child.pid})
            finally:
                log.close()
        save(self.root/'pipeline-close.json', outcomes)
        return all(child.poll() is not None for _, child, _ in self.children)


class DeadlineTransport:
    """Apply one absolute deadline to every bounded journal-export SSH chunk."""
    def __init__(self, transport, deadline, clock=time.monotonic):
        self.transport, self.deadline, self.clock = transport, deadline, clock

    def run(self, command, *, timeout_s=15, **kwargs):
        remaining = self.deadline-self.clock()
        if not math.isfinite(remaining) or remaining <= 0:
            raise TimeoutError('native source operation deadline expired')
        result = self.transport.run(command, timeout_s=min(timeout_s, remaining), **kwargs)
        if self.clock() > self.deadline:
            raise TimeoutError('native source transport exceeded its deadline')
        return result


class EthernetNativeSource:
    """Concrete source hooks; compose with PreparedNativeSession and supervise_native.

    ``station_lease(identity, deadline)`` returns the application's public lease
    context manager. ``predict(history, snapshot, origin)`` returns a validated
    ScheduleBatch from the established numerical predictor. Neither port may
    discover another radio or weaken the full-pilot acceptance gates.
    """
    def __init__(self, *, transport, deployment, controller_sha256, host, visit,
                 pipeline, evidence, station_lease, predict, samples=450_000_000,
                 clock=time.monotonic, sleep=time.sleep):
        if (host != '192.168.1.20' or type(visit) is not int or not 0 < visit < 2**32
                or type(samples) is not int or not 0 < samples <= 600_000_000
                or samples % 250000 or re.fullmatch('[0-9a-f]{64}', controller_sha256) is None):
            raise ValueError('requires the current bounded .20 deployment target')
        self.transport, self.deployment, self.controller_sha256 = transport, deployment, controller_sha256
        self.host, self.visit, self.samples = host, visit, samples
        self.pipeline, self.evidence = pipeline, evidence
        self.station_lease, self.predict = station_lease, predict
        self.clock, self.sleep = clock, sleep
        self.stack = ExitStack()
        self.context = self.device = self.identity = self.remote = None
        self.state = self.fence = self.pending = None
        self.index, self.counter = 0, 0
        self.rebased = self.prepared = False
        self.used = False

    def retain(self, kind, data):
        save(self.evidence/f'evidence-{self.counter:05d}-{kind}', data)
        self.counter += 1

    def _attest(self, deadline):
        transport = DeadlineTransport(self.transport, deadline, self.clock)
        result = g.attest_tx_safe_idle(transport, self.plan, serial=self.identity.serial,
            host=self.host, layout=self.profile.return_iio_layout)
        fields = result['remote']
        if any(fields[key] != getattr(self.identity, key) for key in
               ('serial', 'firmware', 'boot_id', 'fit_sha256')):
            raise ValueError('native source identity changed')
        return result

    def _configure(self):
        self.retain('rf-configuration', g.configure_native_source(host=self.host,
            serial=self.identity.serial, firmware=self.identity.firmware))

    def open(self, identity, deadline, cancel):
        if self.used or identity.serial != '1040005e0b100007100010000bf33a5d4d':
            raise ValueError('source is single-use and restricted to the commissioned .20 serial')
        self.used, self.identity = True, identity
        self.evidence.mkdir(parents=True, exist_ok=False)
        self.stack.enter_context(self.station_lease(identity, deadline))
        self.stack.enter_context(acquire_radio_lock(identity.serial))
        self.plan, self.profile = g.deployment_identity(self.deployment, serial=identity.serial, host=self.host)
        self.retain('before', self._attest(deadline))
        if cancel.is_set() or self.clock() >= deadline:
            raise TimeoutError('cancelled or expired before RX configuration')
        self._configure()
        transport = DeadlineTransport(self.transport, deadline, self.clock)
        discovery = transport.run('sh -s', stdin=b'for d in /sys/bus/iio/devices/iio:device*; do\n'
            b'if test -f "$d/native_schedule_abi"; then readlink -f "$d"; fi\ndone', timeout_s=5)
        self.directory = one_line(discovery, '/sys/devices/')
        if not re.fullmatch(r'/sys/devices/[A-Za-z0-9_./:@+-]+', self.directory):
            raise ValueError('invalid attested sysfs directory')
        self.context = Context(Library(), 'ip:'+self.host, identity.serial, identity.firmware, timeout_ms=2000)
        self.device = self.context.device('starlink-glrt-iq')
        for name, expected in [('capture_abi', 'GLF1-1.0-upper-only'),
                               ('native_schedule_abi', 'GLS1-1.0'), ('native_capture_enable', '0')]:
            if self.device.read(name) != expected:
                raise ValueError('native interface differs')
        self.state = ScheduleSnapshot.from_sysfs(self.device.read('native_schedule_snapshot'))
        self.state.require_drained()
        if self.state.configured or self.state.faults or self.state.status & 16:
            raise ValueError('source not initially clear')
        if self.samples/2_500_000+30 > deadline-self.clock():
            raise TimeoutError('finite source plus its I/O margin exceeds the session deadline')
        self.pipeline.start(identity, self.host, self.visit, self.samples, min(deadline, self.clock()+30), cancel)
        self.native_runtime_seconds = min(45, max(1, int(self.samples/2_500_000)-10))
        # Reserve the 45 s controller bound, measured ~29 s journal export and
        # remaining bookkeeping. SSH chunks still enforce the absolute deadline.
        self.launch_deadline = min(deadline-90, self.clock()+180,
            self.pipeline.source_end-self.native_runtime_seconds-5)

    def _stage(self, deadline):
        transport = DeadlineTransport(self.transport, deadline, self.clock)
        remote = one_line(transport.run('mktemp -d /tmp/glrt-acquired.XXXXXX', timeout_s=5), '/tmp/glrt-acquired.')
        if not re.fullmatch(r'/tmp/glrt-acquired\.[A-Za-z0-9]{6}', remote):
            raise ValueError('invalid owned native scratch directory')
        self.remote = remote  # Retain even if staging later fails.
        self.retain('remote', remote.encode())
        installed = '/usr/sbin/glrt_native_radio'
        output = transport.run('set -eu; test -f '+installed+'; test ! -L '+installed+
            '; test "$(ls -ld '+installed+' | cut -c1-10)" = -rwxr-xr-x; sha256sum '+installed, timeout_s=5)
        if one_line(output, self.controller_sha256) != self.controller_sha256+'  '+installed:
            raise ValueError('installed controller differs')
        transport.run('cp '+installed+' '+remote+'/controller', timeout_s=5)
        transport.run('sha256sum -c', stdin=(self.controller_sha256+'  '+remote+'/controller\n').encode(), timeout_s=5)

    def prepare_launch(self, deadline, cancel):
        if self.pending is not None or self.prepared or self.rebased:
            raise ValueError('prior source execution has not been reconciled')
        self.pipeline.require_running()
        if cancel.is_set() or self.clock() >= min(deadline, self.launch_deadline):
            return None
        self._stage(deadline)
        self.rebased = True  # A failed command is uncertain, never retry it.
        self.device.command('native_schedule_command', 16)
        while not cancel.is_set() and self.clock() < min(deadline, self.launch_deadline):
            self.pipeline.require_running()
            history = read_publication(self.pipeline.root/'work/ready.json')
            if history is None:
                self.sleep(.005)
                continue
            if (history.get('schema') != 'glrt-coarse-bootstrap-history/v2'
                    or history.get('epoch_reference') != 'acquired_full_pilot_template'
                    or history.get('physical_frame_epoch_qualified') is not False
                    or history.get('provisional') is not True or history.get('serial') != self.identity.serial
                    or history.get('visit') != self.visit or len(history.get('history', [])) != 24):
                raise ValueError('bootstrap history identity differs')
            raw = self.device.read('capture_snapshot')
            current = ScheduleSnapshot.from_sysfs(self.device.read('native_schedule_snapshot'))
            origin = LeanSnapshot.decode(raw).require_live_prefix(expected_visit=self.visit,
                received_samples=history['history'][-1]['available_through_sample'])
            if (current.epoch != self.state.epoch+1 or history.get('native_origin') != origin
                    or current.configured or current.faults or current.cdc_drops or current.pacer_drops
                    or current.status & 0x30 != 0x30):
                raise ValueError('bootstrap source no longer matches the rebased capture')
            current.require_drained()
            starts = tuple(origin+24*(row['sample_start']-80)-1272 for row in history['history'])
            if self.fence is not None:
                try:
                    self.fence.require_fresh_observations(starts)
                except ValueError:
                    self.sleep(.005)
                    continue
            try:
                seed = self.predict(history, current, origin)
            except ValueError:
                self.sleep(.005)
                continue
            if (not isinstance(seed, ScheduleBatch) or seed.epoch != current.epoch
                    or seed.tag != self.visit or seed.repeats != 64
                    or seed.start < current.latest_index+3_000_000
                    or seed.prediction(seed.repeats-1)[0]+79199 > seed.expires):
                raise ValueError('numerical seed binding or lead differs')
            latest = read_publication(self.pipeline.root/'work/ready.json')
            keys = ('schema', 'epoch_reference', 'physical_frame_epoch_qualified', 'provisional',
                    'serial', 'visit', 'native_origin')
            if (latest is None or any(history.get(k) != latest.get(k) for k in keys)
                    or len(latest.get('history', [])) != 24 or history['history'][-1] not in latest['history']):
                continue
            text = seed.encode().strip()
            if not re.fullmatch(r'[0-9a-f]+(?: [0-9a-f]+){9}', text):
                raise ValueError('noncanonical native bootstrap')
            self.retain('history', history)
            self.retain('seed', asdict(seed))
            script = "trap '' HUP\nd="+shlex.quote(self.remote)+'\n'
            script += 'printf \'%s\\n\' '+shlex.quote(text)+' > "$d/bootstrap"\n'
            script += '"$d/controller" '+shlex.quote(self.directory)+' "$d/journal" "$d/bootstrap" 32768 '+str(self.native_runtime_seconds)+' --bootstrap-slices > "$d/runtime-output" 2>&1 &\n'
            script += 'pid=$!\nprintf "%s\\n" "$pid" > "$d/pid"\nwait "$pid"\n'
            script += 'code=$?\nprintf "%s\\n" "$code" > "$d/exit"\ncat "$d/runtime-output"\nprintf "GLRT_RUNTIME_EXIT %s\\n" "$code"\n'
            self.prepared = True
            return NativeCandidate(self.identity, seed.epoch, starts, seed.start), script.encode()
        return None

    def _stopped(self, deadline):
        output = DeadlineTransport(self.transport, deadline, self.clock).run(
            'set -eu; if test -s '+self.remote+'/exit; then cat '+self.remote+
            '/exit; else printf "RUNNING\\n"; fi', timeout_s=5)
        values = [line for line in output.splitlines() if re.fullmatch('[0-9]{1,3}', line)]
        return len(values) == 1 and int(values[0]) <= 255

    def _stop_owned_writer(self, deadline):
        """Signal only the controller executable in this session's unique scratch."""
        if self._stopped(deadline):
            return
        script = 'set -eu\nd='+shlex.quote(self.remote)+'\n'
        script += '''test -f "$d/pid"
test ! -L "$d/pid"
pid=$(cat "$d/pid")
case "$pid" in ''|*[!0-9]*) exit 2;; esac
test "$pid" -gt 1
test "$(readlink "/proc/$pid/exe")" = "$d/controller"
kill -INT "$pid"
printf 'OWNED_STOP_SENT\\n'
'''
        output = DeadlineTransport(self.transport, deadline, self.clock).run(
            'sh -s', stdin=script.encode(), timeout_s=5)
        if one_line(output, 'OWNED_STOP_SENT') != 'OWNED_STOP_SENT':
            raise ValueError('owned controller stop is uncertain')
        while self.clock() < deadline:
            if self._stopped(deadline):
                return
            self.sleep(.05)
        raise TimeoutError('owned controller did not stop within cleanup bound')

    def _retain_remote_inventory(self, deadline):
        """Keep stopped interrupted evidence remotely; never treat it as an export."""
        command = 'set -eu; test -s '+self.remote+'/exit; '
        command += 'test -f '+self.remote+'/journal; test ! -L '+self.remote+'/journal; '
        command += 'printf "PPU_SIZE="; wc -c < '+self.remote+'/journal; sha256sum '+self.remote+'/journal'
        output = DeadlineTransport(self.transport, deadline, self.clock).run(command, timeout_s=5)
        sizes = re.findall(r'(?m)^PPU_SIZE=\s*([0-9]+)\s*$', output)
        hashes = re.findall(r'(?m)^([0-9a-f]{64})\s+'+re.escape(self.remote+'/journal')+r'\s*$', output)
        if len(sizes) != 1 or not 6 < int(sizes[0]) <= 16*1024*1024 or len(hashes) != 1:
            raise ValueError('stopped interrupted journal inventory differs')
        self.retain('interrupted-remote-journal', {'directory': self.remote, 'bytes': int(sizes[0]),
            'sha256': hashes[0], 'exported': False, 'reviewed': False})

    def finish_execution(self, output, candidate, deadline):
        self.retain('runtime-output', output.encode())
        result = json.loads(one_line(output, '{"scope":'))
        exit_code = int(one_line(output, 'GLRT_RUNTIME_EXIT ').split()[1])
        if (result.get('scope') != 'finite_radio_local_feedback'
                or exit_code != (0 if result.get('result') == 0 else 1) or not self._stopped(deadline)):
            raise ValueError('native writer return is not verified')
        data, transfer = export_stopped_journal(DeadlineTransport(self.transport, deadline, self.clock),
            self.remote, expected_bytes=result['journal_bytes'])
        self.index += 1
        save(self.evidence/f'episode-{self.index}.glrj', data)  # Preserve before any parser can reject it.
        self.retain('export', transfer)
        checked = review(data, epoch=candidate.epoch)
        current = ScheduleSnapshot.from_sysfs(self.device.read('native_schedule_snapshot'))
        self.fence = restart_fence(data, epoch=candidate.epoch, result=result['result'],
            configured=result['configured'], retained_popped=result['retained_popped'],
            writer_stopped=True, current=current)
        drained = checked['drained']
        episode = NativeEpisode(self.identity, candidate.epoch, result['result'], drained.configured,
            drained.admitted, drained.committed, drained.popped, checked['supported'],
            current.latest_index, hashlib.sha256(data).hexdigest(), True,
            drained.faults, drained.cdc_drops+drained.pacer_drops)
        self.pending, self.state = episode, current
        return episode

    def retain_episode(self, episode, deadline):
        if episode != self.pending or self.clock() >= deadline:
            raise ValueError('pending journal identity or retention deadline differs')
        path = self.evidence/f'episode-{self.index}.glrj'
        if hashlib.sha256(path.read_bytes()).hexdigest() != episode.journal_sha256:
            raise ValueError('retained journal changed')
        self.retain('episode', asdict(episode))
        # Only a durable, reviewed, cleared episode permits removing its scratch.
        transport = DeadlineTransport(self.transport, deadline, self.clock)
        transport.run('rm -f '+' '.join(self.remote+'/'+name for name in
            ('controller', 'bootstrap', 'journal', 'pid', 'exit', 'runtime-output')), timeout_s=5)
        transport.run('rmdir '+self.remote, timeout_s=5)
        self.pending = None
        self.remote = None
        self.prepared = self.rebased = False

    def close(self, deadline):
        errors = []
        try:
            if self.device is not None and self.rebased:
                try:
                    if self.prepared:
                        self._stop_owned_writer(min(deadline-10, self.clock()+5))
                        self._retain_remote_inventory(deadline)
                    current = ScheduleSnapshot.from_sysfs(self.device.read('native_schedule_snapshot'))
                    if current.epoch not in (self.state.epoch, self.state.epoch+1):
                        raise ValueError('cleanup source epoch changed')
                    if not self.prepared:
                        recover(self.device, b'GLRJ1\n', epoch=current.epoch, writer_stopped=True,
                            retain=self.retain, deadline=deadline, clock=self.clock, sleep=self.sleep)
                    else:
                        current.require_drained()
                        if current.configured or current.faults or current.status & 16:
                            raise ValueError('native controller did not clear ownership')
                except BaseException as error:  # noqa: BLE001 -- cleanup must survive interruption
                    errors.append('native: '+str(error))
            try:
                if self.pipeline.children and not self.pipeline.close(deadline-10):
                    errors.append('source children did not close')
            except BaseException as error:  # noqa: BLE001 -- continue independent cleanup attempts
                errors.append('pipeline: '+str(error))
            if self.context is not None:
                try:
                    final = ScheduleSnapshot.from_sysfs(self.device.read('native_schedule_snapshot'))
                    final.require_drained()
                    if final.configured or final.faults or final.status & 16:
                        raise ValueError('final scheduler ownership is not clear')
                    self.retain('final-schedule', asdict(final))
                except BaseException as error:  # noqa: BLE001 -- still close the metadata connection
                    errors.append('scheduler: '+str(error))
                try:
                    self.context.close()
                except BaseException as error:  # noqa: BLE001 -- still attempt final attestation
                    errors.append('metadata close: '+str(error))
            if hasattr(self, 'plan'):
                try:
                    self.retain('after', self._attest(deadline))
                except BaseException as error:  # noqa: BLE001 -- retain failure before releasing leases
                    errors.append('attestation: '+str(error))
            self.retain('cleanup', {'errors': errors, 'physical_precision_qualified': False,
                'autonomous_service_deployed': False})
            return not errors and hasattr(self, 'plan') and self.clock() <= deadline
        finally:
            self.stack.close()
