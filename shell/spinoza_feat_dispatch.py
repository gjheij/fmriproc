#!/usr/bin/env python3
"""Bounded, resumable Slurm wave submission for spinoza_feat (stdlib only)."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY',
            'NODE_FAIL', 'PREEMPTED', 'BOOT_FAIL', 'DEADLINE', 'REVOKED'}


class SubmissionQuotaError(RuntimeError):
    """Slurm explicitly rejected a submission because its submit quota is full."""


def has_receipt(stdout):
    return any(line.strip().split(';', 1)[0].isdigit() for line in (stdout or '').splitlines())


def quota_rejection(error):
    codes = ('AssocMaxSubmitJobLimit', 'AssocGrpSubmitJobsLimit',
             'QOSMaxSubmitJobPerUserLimit', 'QOSMaxSubmitJobPerAccountLimit',
             'QOSGrpSubmitJobsLimit')
    return error.returncode > 0 and not has_receipt(error.stdout) and any(
        code in (error.stderr or '') for code in codes)


def write_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def command(argv, env=None):
    return subprocess.run(argv, check=True, capture_output=True, text=True, env=env).stdout


def log(folder, message):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + message
    print(line, flush=True)
    with (Path(folder) / 'submission.log').open('a') as stream:
        stream.write(line + '\n')


def fingerprints(config):
    return {name: hashlib.sha256(Path(config[name]).read_bytes()).hexdigest()
            for name in ('runner', 'jobs_file', 'merge_runner') if config.get(name)}


def queue_snapshot():
    output = command(['squeue', '-r', '-h', '-u', os.environ['USER'],
                      '--states=all', '-o', '%i|%T'])
    rows = {}
    for line in output.splitlines():
        fields = line.strip().split('|')
        if len(fields) != 2:
            raise RuntimeError('Unexpected squeue output; refusing to guess available capacity')
        job, state = fields
        state = state.split()[0].rstrip('+')
        if state not in TERMINAL:
            rows[job] = state
    return rows


def refresh(states, queue):
    """Missing queue rows keep reservations until accounting proves termination."""
    missing_arrays = []
    for state in states:
        for wave in state['waves']:
            if any(f"{wave['id']}_{i}" not in queue and str(i) not in wave['terminal']
                   for i in range(1, wave['count'] + 1)):
                missing_arrays.append(wave['id'])
    for state in states:
        if state.get('merge_id') and not state.get('merge_terminal') and state['merge_id'] not in queue:
            missing_arrays.append(state['merge_id'])
    records = {}
    if missing_arrays:
        output = command(['sacct', '-n', '-X', '-P', '--array', '--starttime=1970-01-01',
                          '-j', ','.join(missing_arrays), '--format=JobID%64,State%40'])
        for line in output.splitlines():
            fields = line.strip().split('|')
            if len(fields) >= 2:
                status = fields[1].split()[0].rstrip('+') if fields[1].strip() else ''
                if status in TERMINAL:
                    records[fields[0]] = status
    for state in states:
        if state.get('merge_id') in records:
            state['merge_terminal'] = records[state['merge_id']]
        for wave in state['waves']:
            for i in range(1, wave['count'] + 1):
                job = f"{wave['id']}_{i}"
                if job in queue:
                    wave['terminal'].pop(str(i), None)
                elif job in records:
                    wave['terminal'][str(i)] = records[job]


def capacity(states, queue, config):
    # Each wave has count == throttle, so every outstanding task reserves a
    # potential running slot, including tasks not yet visible in squeue.
    reserved = set()
    for state in states:
        for wave in state['waves']:
            reserved.update(f"{wave['id']}_{i}" for i in range(1, wave['count'] + 1)
                            if str(i) not in wave['terminal'])
        if state.get('merge_id') and not state.get('merge_terminal'):
            reserved.add(state['merge_id'])
    external = set(queue) - reserved
    used = len(reserved) + len(external)
    pending = sum(status == 'PENDING' for status in queue.values())
    pending += len(reserved - set(queue))
    merge_slot = int(bool(config.get('merge_runner')))
    return max(0, min(config['max_running'] - used,
                      config['max_submitted'] - used - merge_slot,
                      config['max_queued'] - pending))


def failed_entries(state):
    queued = {(entry['wave'], entry['task']) for entry in state.get('retry_queue', [])}
    return [dict(wave=wave['id'], task=i, row=wave['offset'] + int(i), status=status)
            for wave in state['waves'] for i, status in wave['terminal'].items()
            if status != 'COMPLETED' and i not in wave.get('replacements', {})
            and (wave['id'], i) not in queued]


def failed_tasks(state):
    return [f"{entry['wave']}_{entry['task']}: {entry['status']}" for entry in failed_entries(state)]


def merge_dependencies(state):
    dependencies = []
    for wave in state['waves']:
        pending = [i for i in range(1, wave['count'] + 1) if str(i) not in wave['terminal']]
        if not pending:
            continue
        if any(status != 'COMPLETED' for status in wave['terminal'].values()):
            # A failed parent array cannot become successful through replacement
            # jobs. Depend only on its remaining good task IDs, plus retry arrays.
            dependencies.extend(f"{wave['id']}_{i}" for i in pending)
        else:
            dependencies.append(wave['id'])
    return dependencies


def submit(state, state_path, argv, kind, **details):
    # Journal before sbatch. If acceptance succeeds but receipt persistence is
    # interrupted, resume refuses to submit duplicates and names the journal.
    state['pending_submission'] = dict(kind=kind, command=argv, **details)
    write_json(state_path, state)
    env = os.environ.copy()
    env.update(state['config'].get('sbatch_environment', {}))
    try:
        receipt = command(argv, env=env).strip().split(';', 1)[0]
    except subprocess.CalledProcessError as error:
        state['pending_submission'].update(
            returncode=error.returncode, stdout=error.stdout or '', stderr=error.stderr or '')
        if quota_rejection(error):
            rejected = state.pop('pending_submission')
            rejected['resolution'] = 'explicit-slurm-quota-rejection'
            state.setdefault('rejected_submissions', []).append(rejected)
            write_json(state_path, state)
            raise SubmissionQuotaError((error.stderr or '').strip()) from error
        write_json(state_path, state)
        raise
    if not receipt.isdigit():
        raise RuntimeError('Unrecognized sbatch receipt; inspect pending_submission in ' + str(state_path))
    if kind in ('wave', 'retry'):
        state['waves'].append(dict(id=receipt, count=details['count'],
                                   offset=details['offset'], terminal={}, kind=kind))
        if kind == 'wave':
            state['offset'] += details['count']
        else:
            for index, entry in enumerate(details['replaces'], 1):
                source = next(w for w in state['waves'] if w['id'] == entry['wave'])
                source.setdefault('replacements', {})[entry['task']] = f'{receipt}_{index}'
                state['retry_queue'].remove(entry)
    else:
        state['merge_id'] = receipt
    state.pop('pending_submission')
    write_json(state_path, state)
    return receipt


def dispatch(state_path, cache_dir, poll=30, retry_failed=False, retry_rejected=False):
    state_path = Path(state_path).resolve()
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (cache_dir / 'dispatcher.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another FEAT dispatcher is active for this user; resume after it exits')
        ledger = cache_dir / 'submissions.json'
        paths = json.loads(ledger.read_text()) if ledger.exists() else []
        if str(state_path) not in paths:
            paths.append(str(state_path))
            write_json(ledger, paths)
        states = []
        for path in paths:
            if not Path(path).is_file():
                raise RuntimeError('Reservation state is missing; inspect ' + str(ledger) + ': ' + path)
            state = json.loads(Path(path).read_text())
            if state.get('pending_submission'):
                if retry_rejected and str(Path(path).resolve()) == str(state_path):
                    if has_receipt(state['pending_submission'].get('stdout')):
                        raise RuntimeError('Submission has a possible job receipt; reconcile it before retrying')
                    rejected = state.pop('pending_submission')
                    rejected['resolution'] = 'explicitly-confirmed-rejected-on-resume'
                    state.setdefault('rejected_submissions', []).append(rejected)
                    state['status'] = 'dispatching'
                    write_json(path, state)
                else:
                    raise RuntimeError('Uncertain sbatch submission; inspect squeue and pending_submission in ' + path)
            state['_path'] = path
            states.append(state)
        current = next(s for s in states if s['_path'] == str(state_path))
        config = current['config']
        if fingerprints(config) != current['fingerprints']:
            raise RuntimeError('Runner, job list or merge script changed; refusing to resume')
        folder = state_path.parent
        if retry_failed and current.get('merge_id'):
            raise RuntimeError('A manifest merge was already submitted; inspect its state before retrying')
        if current.get('status') == 'submitted' and not retry_failed and not current.get('retry_queue'):
            log(folder, 'All tasks already submitted; no new jobs queued')
            return
        log(folder, f"Dispatching {config['count']} FEAT tasks; concurrency={config['max_running']}; "
                    f"array cap={config['array_cap']}; MaxSubmitJobs={config['max_submitted']}")
        log(folder, 'Log directory: ' + str(folder))
        log(folder, 'Resume command: spinoza_feat --resume-submission ' + str(folder))
        last_wait = None
        retry_initialized = False
        submission_cap = config['array_cap']
        while True:
            queue = queue_snapshot()
            refresh(states, queue)
            for state in states:
                write_json(state['_path'], state)
            if retry_failed and not retry_initialized:
                current.setdefault('retry_queue', []).extend(failed_entries(current))
                current['status'] = 'dispatching'
                write_json(state_path, current)
                log(folder, f"Retry requested for {len(current['retry_queue'])} failed task(s); original jobs are retained in history")
                retry_initialized = True
            failures = failed_tasks(current)
            if failures:
                raise RuntimeError('FEAT tasks failed; stopping further submissions: ' + '; '.join(failures))
            retries = sorted(current.get('retry_queue', []), key=lambda entry: entry['row'])
            if current['offset'] == config['count'] and not retries:
                break
            if retries:
                # A contiguous slice can use the unchanged snapshot runner.
                contiguous = [retries[0]]
                for entry in retries[1:]:
                    if entry['row'] != contiguous[-1]['row'] + 1:
                        break
                    contiguous.append(entry)
                remaining = len(contiguous)
            else:
                remaining = config['count'] - current['offset']
            count = min(remaining, config['array_cap'], submission_cap,
                        capacity(states, queue, config))
            if not count:
                summary = (current['offset'], len(queue))
                if summary != last_wait:
                    log(folder, f"Waiting for capacity; {current['offset']}/{config['count']} tasks submitted")
                    last_wait = summary
                time.sleep(poll)
                continue
            offset = retries[0]['row'] - 1 if retries else current['offset']
            argv = ['sbatch', '--parsable', '--partition=' + config['queue'],
                    f'--array=1-{count}%{count}', f'--export=ALL,FEAT_BATCH_OFFSET={offset}',
                    '--cpus-per-task=' + str(config['cpus']), '--job-name=' + config['job_name'],
                    '--output=' + str(folder / (config['job_name'] + '_%A_%a.out')), config['runner']]
            kind = 'retry' if retries else 'wave'
            details = dict(count=count, offset=offset)
            if retries:
                details['replaces'] = contiguous[:count]
            try:
                jid = submit(current, state_path, argv, kind, **details)
            except SubmissionQuotaError as error:
                submission_cap = max(1, count // 2)
                summary = ('quota', count, str(error))
                if summary != last_wait:
                    log(folder, f'Slurm submission quota rejected {count} tasks; waiting {poll} s, '
                                f'then trying at most {submission_cap}. No rows were assigned. {error}')
                    last_wait = summary
                time.sleep(poll)
                continue
            label = "retry wave" if kind == "retry" else "wave"
            log(folder, f"Submitted {label} {len(current['waves'])}: rows {offset+1}-{offset+count}, "
                        f"array 1-{count}%{count}, Slurm job {jid}")
            last_wait = None
        if config.get('merge_runner') and not current.get('merge_id'):
            last_merge_error = None
            while True:
                queue = queue_snapshot()
                refresh(states, queue)
                for state in states:
                    write_json(state['_path'], state)
                failures = failed_tasks(current)
                if failures:
                    raise RuntimeError('FEAT tasks failed before manifest merge: ' + '; '.join(failures))
                # Failed originals replaced by retries require task-specific dependencies.
                dependencies = merge_dependencies(current)
                argv = ['sbatch', '--parsable', '--partition=' + config['queue'],
                        '--cpus-per-task=1', '--job-name=' + config['job_name'] + 'Merge',
                        '--output=' + str(folder / (config['job_name'] + '_merge_%j.out'))]
                if dependencies:
                    argv.append('--dependency=afterok:' + ':'.join(dependencies))
                try:
                    jid = submit(current, state_path, argv + [config['merge_runner']], 'merge')
                except SubmissionQuotaError as error:
                    if str(error) != last_merge_error:
                        log(folder, f'Slurm submission quota full; waiting {poll} s before manifest merge. {error}')
                        last_merge_error = str(error)
                    time.sleep(poll)
                    continue
                log(folder, f'Submitted manifest merge job {jid}; dependencies={dependencies}')
                break
        current['status'] = 'submitted'
        write_json(state_path, current)
        log(folder, f"All {config['count']} tasks submitted across {len(current['waves'])} waves; "
                    'Slurm jobs continue independently')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--retry-failed', action='store_true', help='On resume, submit fresh replacements for recorded failed tasks')
    parser.add_argument('--retry-rejected', action='store_true', help='On resume, acknowledge that the saved uncertain submission was rejected, not accepted')
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--runner')
    parser.add_argument('--jobs-file')
    parser.add_argument('--merge-runner')
    parser.add_argument('--max-running', type=int)
    parser.add_argument('--max-submitted', type=int)
    parser.add_argument('--max-queued', type=int)
    parser.add_argument('--array-cap', type=int)
    parser.add_argument('--queue')
    parser.add_argument('--cpus', type=int)
    parser.add_argument('--job-name')
    args = parser.parse_args(argv)
    cache = Path(os.environ.get('FMRIPROC_FEAT_STATE_DIR',
                                str(Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'fmriproc' / 'feat')))
    try:
        if (args.retry_failed or args.retry_rejected) and not args.resume:
            raise ValueError('--retry-failed and --retry-rejected require --resume')
        if args.resume:
            state_path = args.resume.resolve() / 'dispatch_state.json'
        else:
            config = vars(args).copy()
            config.pop('resume')
            config.pop('retry_failed')
            config.pop('retry_rejected')
            folder = config.pop('work_dir').resolve()
            config['jobs_file'] = str(Path(config['jobs_file']).resolve())
            config['runner'] = str(Path(config['runner']).resolve())
            if config.get('merge_runner'):
                config['merge_runner'] = str(Path(config['merge_runner']).resolve())
            config['max_queued'] = config['max_queued'] or config['max_submitted']
            for key in ('max_running', 'max_submitted', 'max_queued', 'array_cap', 'cpus'):
                if not isinstance(config[key], int) or config[key] < 1:
                    raise ValueError(key + ' must be a positive integer')
            if config.get('merge_runner') and config['max_submitted'] < 2:
                raise ValueError('Manifest merge dispatch requires at least two submitted-job slots')
            config['count'] = len(Path(config['jobs_file']).read_text().splitlines())
            config['sbatch_environment'] = {k: v for k, v in os.environ.items() if k.startswith('SBATCH_')}
            state_path = folder / 'dispatch_state.json'
            if state_path.exists():
                raise RuntimeError('Submission already initialized; use --resume')
            write_json(state_path, dict(config=config, fingerprints=fingerprints(config),
                                       offset=0, waves=[], status='dispatching'))
        dispatch(state_path, cache, retry_failed=args.retry_failed, retry_rejected=args.retry_rejected)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            if error.stdout:
                print(error.stdout.strip(), file=sys.stderr)
            if error.stderr:
                print(error.stderr.strip(), file=sys.stderr)
        print('Already submitted Slurm jobs have not been canceled.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
