"""Scheduler simulation: no cluster or neuroimaging dependencies required."""
import importlib.util
import json
import os
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('feat_dispatch', Path(__file__).parents[1] / 'shell' / 'spinoza_feat_dispatch.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class Scheduler:
    def __init__(self, partial=False):
        self.jobs = {}
        self.commands = []
        self.round = 0
        self.partial = partial

    def queue(self):
        self.round += 1
        if self.partial and self.round >= 3:
            for job in ['100_1', '100_2']:
                self.jobs[job] = 'COMPLETED'
        return {k: v for k, v in self.jobs.items() if v not in d.TERMINAL}

    def command(self, argv, env=None):
        if argv[0] == 'sacct':
            return '\n'.join(k + '|' + v + '|' for k, v in self.jobs.items() if v in d.TERMINAL)
        assert argv[0] == 'sbatch', argv
        self.commands.append(argv)
        jid = str(99 + len(self.commands))
        array = next((a for a in argv if a.startswith('--array=')), None)
        if array:
            size = int(array.split('%')[0].split('-')[-1])
            self.jobs.update({f'{jid}_{i}': 'PENDING' for i in range(1, size + 1)})
        else:
            self.jobs[jid] = 'PENDING'
        return jid + '\n'


class TestDispatch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.folder = self.root / 'submission'
        self.folder.mkdir()
        self.state_path = self.folder / 'dispatch_state.json'

    def create(self, count=300, running=300, cap=99, merge=False):
        config = dict(count=count, max_running=running, max_submitted=running + int(merge),
                      max_queued=running, array_cap=cap, queue='test', cpus=1, job_name='featL1')
        for name in ['runner', 'jobs_file'] + (['merge_runner'] if merge else []):
            path = self.folder / name
            path.write_text('echo test\n')
            config[name] = str(path)
        state = dict(config=config, fingerprints=d.fingerprints(config), offset=0,
                     waves=[], status='dispatching')
        d.write_json(self.state_path, state)
        return state

    def run_dispatch(self, scheduler):
        with patch.object(d, 'queue_snapshot', scheduler.queue), patch.object(d, 'command', scheduler.command):
            d.dispatch(self.state_path, self.cache, poll=0)
        return json.loads(self.state_path.read_text())

    def test_300_slots_use_multiple_active_arrays(self):
        self.create()
        scheduler = Scheduler()
        state = self.run_dispatch(scheduler)
        self.assertEqual([w['count'] for w in state['waves']], [99, 99, 99, 3])
        self.assertEqual([w['offset'] for w in state['waves']], [0, 99, 198, 297])
        self.assertEqual(len(scheduler.jobs), 300)
        self.assertEqual(state['status'], 'submitted')

    def test_refills_before_first_wave_finishes(self):
        self.create(count=6, running=4, cap=3)
        scheduler = Scheduler(partial=True)
        state = self.run_dispatch(scheduler)
        self.assertEqual([w['count'] for w in state['waves']], [3, 1, 2])
        self.assertEqual(state['waves'][0]['terminal'], {'1': 'COMPLETED', '2': 'COMPLETED'})
        self.assertEqual(scheduler.jobs['100_3'], 'PENDING')

    def test_merge_depends_on_all_active_arrays(self):
        self.create(count=6, running=6, cap=3, merge=True)
        scheduler = Scheduler()
        state = self.run_dispatch(scheduler)
        self.assertIn('--dependency=afterok:100:101', scheduler.commands[-1])
        self.assertEqual(state['merge_id'], '102')

    def test_resume_does_not_resubmit(self):
        self.create(count=4, running=4, cap=2)
        scheduler = Scheduler()
        self.run_dispatch(scheduler)
        self.run_dispatch(scheduler)
        self.assertEqual(len(scheduler.commands), 2)

    def test_interrupted_dispatch_resumes_offset(self):
        self.create(count=6, running=6, cap=3)
        scheduler = Scheduler()
        original = scheduler.command
        # Interrupt before querying next wave, outside the sbatch journal gap.
        original_queue = scheduler.queue
        def queue():
            if scheduler.round == 1:
                raise KeyboardInterrupt()
            return original_queue()
        with patch.object(d, 'queue_snapshot', queue), patch.object(d, 'command', original):
            with self.assertRaises(KeyboardInterrupt):
                d.dispatch(self.state_path, self.cache, poll=0)
        state = self.run_dispatch(scheduler)
        self.assertEqual([w['offset'] for w in state['waves']], [0, 3])

    def test_uncertain_submission_blocks_duplicate(self):
        state = self.create(count=4, running=4, cap=2)
        state['pending_submission'] = {'kind': 'wave'}
        d.write_json(self.state_path, state)
        with self.assertRaisesRegex(RuntimeError, 'Uncertain sbatch'):
            self.run_dispatch(Scheduler())

    def test_changed_inputs_block_resume(self):
        state = self.create()
        Path(state['config']['runner']).write_text('changed')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.run_dispatch(Scheduler())

    def test_unseen_reservations_and_other_pending_jobs_count(self):
        state = self.create(count=6, running=6, cap=3)
        state['waves'] = [dict(id='10', count=3, terminal={})]
        self.assertEqual(d.capacity([state], {'20': 'PENDING'}, state['config']), 2)
        self.assertEqual(d.capacity([state], {}, state['config']), 3)

    def test_missing_queue_rows_are_not_assumed_complete(self):
        state = self.create()
        state['waves'] = [dict(id='10', count=3, terminal={})]
        with patch.object(d, 'command', return_value=''):
            d.refresh([state], {})
        self.assertEqual(state['waves'][0]['terminal'], {})

    def test_failed_task_stops_later_waves(self):
        state = self.create(count=6, running=6, cap=3)
        state['waves'] = [dict(id='10', count=3, offset=0, terminal={'1': 'FAILED'})]
        state['offset'] = 3
        d.write_json(self.state_path, state)
        scheduler = Scheduler()
        with self.assertRaisesRegex(RuntimeError, 'FEAT tasks failed'):
            self.run_dispatch(scheduler)
        self.assertEqual(scheduler.commands, [])

    def test_scheduler_query_failure_aborts(self):
        self.create()
        with patch.object(d, 'queue_snapshot', side_effect=RuntimeError('squeue failed')):
            with self.assertRaisesRegex(RuntimeError, 'squeue failed'):
                d.dispatch(self.state_path, self.cache, poll=0)

    def test_pending_limit_applies(self):
        state = self.create(count=300, running=300)
        state['config']['max_queued'] = 20
        self.assertEqual(d.capacity([state], {}, state['config']), 20)

    def test_other_submission_keeps_its_reservation(self):
        state = self.create(count=6, running=6, cap=3)
        prior = dict(waves=[dict(id='20', count=4, terminal={'1': 'COMPLETED'})],
                     merge_id='21')
        self.assertEqual(d.capacity([prior, state], {}, state['config']), 2)
        prior['merge_terminal'] = 'COMPLETED'
        self.assertEqual(d.capacity([prior, state], {}, state['config']), 3)

    def test_sbatch_failure_preserves_uncertain_journal(self):
        state = self.create(count=4, running=4, cap=2)
        with patch.object(d, 'command', side_effect=subprocess.CalledProcessError(1, ['sbatch'], output='', stderr='sbatch: quota rejected')):
            with self.assertRaises(subprocess.CalledProcessError):
                d.submit(state, self.state_path, ['sbatch'], 'wave', count=2, offset=0)
        saved = json.loads(self.state_path.read_text())
        self.assertEqual(saved['pending_submission']['count'], 2)
        self.assertEqual(saved['pending_submission']['stderr'], 'sbatch: quota rejected')
        self.assertEqual(saved['pending_submission']['returncode'], 1)
        self.assertEqual(saved['offset'], 0)

    def test_retry_six_purged_node_failures_preserves_row_mapping(self):
        state = self.create(count=785, running=300, cap=99, merge=True)
        sizes = [99, 99, 99, 2, 99, 83, 35]
        offset = 0
        for number, size in enumerate(sizes):
            terminal = {str(i): 'COMPLETED' for i in range(1, size + 1)}
            if number == 2:
                terminal.update({str(i): 'NODE_FAIL' for i in range(45, 51)})
            state['waves'].append(dict(id=str(10+number), count=size, offset=offset, terminal=terminal))
            offset += size
        state['offset'] = offset
        d.write_json(self.state_path, state)
        scheduler = Scheduler()
        with patch.object(d, 'queue_snapshot', scheduler.queue), patch.object(d, 'command', scheduler.command):
            d.dispatch(self.state_path, self.cache, poll=0, retry_failed=True)
        result = json.loads(self.state_path.read_text())
        retry = result['waves'][7]
        self.assertEqual((retry['offset'], retry['count'], retry['kind']), (242, 6, 'retry'))
        self.assertIn('--export=ALL,FEAT_BATCH_OFFSET=242', scheduler.commands[0])
        self.assertEqual(result['offset'], 785)
        self.assertEqual(d.failed_tasks(result), [])
        self.assertEqual(result['waves'][2]['replacements']['45'], '100_1')
        self.assertEqual(result['waves'][2]['replacements']['50'], '100_6')
        self.assertIn('--dependency=afterok:100:101:102:103', scheduler.commands[-1])

    def test_retry_dependency_avoids_failed_parent_array(self):
        state = self.create(count=3, running=5, cap=3, merge=True)
        state['waves'] = [dict(id='10', count=3, offset=0,
                              terminal={'1': 'NODE_FAIL', '3': 'COMPLETED'})]
        state['offset'] = 3
        d.write_json(self.state_path, state)
        scheduler = Scheduler()
        scheduler.jobs['10_2'] = 'PENDING'
        with patch.object(d, 'queue_snapshot', scheduler.queue), patch.object(d, 'command', scheduler.command):
            d.dispatch(self.state_path, self.cache, poll=0, retry_failed=True)
        self.assertIn('--dependency=afterok:10_2:100', scheduler.commands[-1])

    def test_retry_pending_queue_survives_interruption_without_flag(self):
        state = self.create(count=3, running=4, cap=3)
        state['waves'] = [dict(id='10', count=3, offset=0,
                              terminal={'1': 'NODE_FAIL', '2': 'COMPLETED', '3': 'COMPLETED'})]
        state['offset'] = 3
        state['retry_queue'] = [dict(wave='10', task='1', row=1, status='NODE_FAIL')]
        d.write_json(self.state_path, state)
        scheduler = Scheduler()
        result = self.run_dispatch(scheduler)
        self.assertEqual(result['retry_queue'], [])
        self.assertEqual(result['waves'][1]['offset'], 0)
        self.assertEqual(len(scheduler.commands), 1)

    def test_retry_does_not_reissue_live_requeued_tasks(self):
        state = self.create(count=3, running=4, cap=3)
        state['waves'] = [dict(id='10', count=3, offset=0,
                              terminal={'1': 'NODE_FAIL', '2': 'COMPLETED', '3': 'COMPLETED'})]
        state['offset'] = 3
        d.write_json(self.state_path, state)
        scheduler = Scheduler()
        scheduler.jobs['10_1'] = 'PENDING'
        with patch.object(d, 'queue_snapshot', scheduler.queue), patch.object(d, 'command', scheduler.command):
            d.dispatch(self.state_path, self.cache, poll=0, retry_failed=True)
        self.assertEqual(scheduler.commands, [])

    def test_explicit_quota_rejection_clears_intent_without_advancing(self):
        state = self.create(count=4, running=4, cap=4)
        error = subprocess.CalledProcessError(1, ['sbatch'], output='',
            stderr='sbatch: error: AssocMaxSubmitJobLimit\nallocation failure: Job violates accounting/QOS policy')
        with patch.object(d, 'command', side_effect=error):
            with self.assertRaises(d.SubmissionQuotaError):
                d.submit(state, self.state_path, ['sbatch'], 'wave', count=4, offset=0)
        saved = json.loads(self.state_path.read_text())
        self.assertNotIn('pending_submission', saved)
        self.assertEqual(saved['offset'], 0)
        self.assertEqual(saved['rejected_submissions'][0]['count'], 4)

    def test_quota_waits_then_submits_smaller_wave(self):
        self.create(count=4, running=4, cap=4)
        scheduler = Scheduler()
        attempts = []
        def submit(argv, env=None):
            if argv[0] == 'sbatch':
                attempts.append(argv)
                if len(attempts) == 1:
                    raise subprocess.CalledProcessError(1, argv, output='', stderr='sbatch: error: AssocMaxSubmitJobLimit')
            return scheduler.command(argv, env)
        with patch.object(d, 'queue_snapshot', scheduler.queue), patch.object(d, 'command', submit), patch.object(d.time, 'sleep') as sleep:
            d.dispatch(self.state_path, self.cache, poll=30)
        saved = json.loads(self.state_path.read_text())
        self.assertEqual([w['count'] for w in saved['waves']], [2, 2])
        self.assertEqual([w['offset'] for w in saved['waves']], [0, 2])
        self.assertEqual(saved['offset'], 4)
        sleep.assert_called_once_with(30)

    def test_receipt_with_error_is_not_assumed_rejected(self):
        state = self.create(count=4, running=4, cap=4)
        error = subprocess.CalledProcessError(1, ['sbatch'], output='12345\n', stderr='AssocMaxSubmitJobLimit')
        with patch.object(d, 'command', side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                d.submit(state, self.state_path, ['sbatch'], 'wave', count=4, offset=0)
        self.assertIn('pending_submission', json.loads(self.state_path.read_text()))

    def test_confirm_old_rejected_submission_resumes_tail(self):
        state = self.create(count=4, running=4, cap=4)
        state['offset'] = 2
        state['waves'] = [dict(id='10', count=2, offset=0, terminal={'1':'COMPLETED','2':'COMPLETED'})]
        state['pending_submission'] = dict(kind='wave', count=2, offset=2, command=['sbatch'])
        d.write_json(self.state_path, state)
        scheduler = Scheduler()
        with patch.object(d, 'queue_snapshot', scheduler.queue), patch.object(d, 'command', scheduler.command):
            d.dispatch(self.state_path, self.cache, poll=0, retry_rejected=True)
        saved = json.loads(self.state_path.read_text())
        self.assertEqual(saved['offset'], 4)
        self.assertEqual(saved['waves'][-1]['offset'], 2)
        self.assertEqual(len(scheduler.commands), 1)
        self.assertNotIn('pending_submission', saved)
        self.assertEqual(saved['rejected_submissions'][0]['resolution'], 'explicitly-confirmed-rejected-on-resume')

    def test_merge_quota_retry_does_not_resubmit_waves(self):
        self.create(count=2, running=3, cap=2, merge=True)
        scheduler = Scheduler()
        merge_attempts = []
        def submit(argv, env=None):
            if argv[0]=='sbatch' and not any(a.startswith('--array=') for a in argv):
                merge_attempts.append(argv)
                if len(merge_attempts) == 1:
                    raise subprocess.CalledProcessError(1, argv, output='', stderr='QOSMaxSubmitJobPerUserLimit')
            return scheduler.command(argv, env)
        with patch.object(d, 'queue_snapshot', scheduler.queue), patch.object(d, 'command', submit), patch.object(d.time, 'sleep'):
            d.dispatch(self.state_path, self.cache, poll=0)
        saved = json.loads(self.state_path.read_text())
        self.assertEqual(len(saved['waves']),1)
        self.assertEqual(len(scheduler.commands),2)
        self.assertEqual(saved['merge_id'],'101')


    def test_extraction_retry_replaces_only_failed_worker_and_blocked_merge(self):
        state=self.create(count=2,running=4,merge=True)
        state['config']['allow_merge_retry']=True
        d.write_json(self.state_path,state)
        scheduler=Scheduler()
        state=self.run_dispatch(scheduler)
        scheduler.jobs['100_1']='COMPLETED'
        scheduler.jobs['100_2']='FAILED'
        original_command=scheduler.command
        canceled=[]
        def command(argv,env=None):
            if argv[0]=='scancel':
                canceled.append(argv[1]);scheduler.jobs[argv[1]]='CANCELLED';return ''
            return original_command(argv,env)
        with patch.object(d,'queue_snapshot',scheduler.queue),patch.object(d,'command',command):
            d.dispatch(self.state_path,self.cache,poll=0,retry_failed=True,queue_override='short')
        saved=json.loads(self.state_path.read_text())
        self.assertEqual(canceled,['101'])
        self.assertEqual(saved['config']['queue'],'short')
        self.assertEqual(len(saved['waves']),2)
        self.assertEqual(saved['waves'][-1]['count'],1)
        self.assertEqual(saved['previous_merges'][0]['id'],'101')
        self.assertNotEqual(saved['merge_id'],'101')


class TestWrapperIntegration(unittest.TestCase):
    def test_shell_detects_task_cap_and_resumes_same_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / 'bin'
            binary.mkdir()
            scheduler = binary / 'scheduler'
            scheduler.write_text("#!" + sys.executable + "\n" + r'''import json, os, sys
from pathlib import Path
name=Path(sys.argv[0]).name
store=Path(os.environ['FAKE_SLURM_STATE'])
s=json.loads(store.read_text()) if store.exists() else {'calls':[], 'jobs':{}}
if name=='scontrol':
    print('MaxArraySize = 100\nSchedulerParameters = max_array_tasks=40')
elif name=='sacctmgr':
    print('300|')
elif name=='squeue':
    for job in s['jobs']: print(job+'|PENDING')
elif name=='sacct':
    pass
elif name=='sbatch':
    s['calls'].append(sys.argv[1:])
    jid=str(100+len(s['calls']))
    array=next((x for x in sys.argv if x.startswith('--array=')),None)
    if array:
        count=int(array.split('%')[0].split('-')[-1])
        s['jobs'].update({jid+'_'+str(i):'PENDING' for i in range(1,count+1)})
    store.write_text(json.dumps(s))
    print(jid)
''')
            scheduler.chmod(0o755)
            for name in ['scontrol','sacctmgr','squeue','sacct','sbatch']:
                (binary / name).symlink_to(scheduler)
            project = root / 'project'
            func = project / 'derivatives' / 'fmriprep' / 'sub-01' / 'func'
            func.mkdir(parents=True)
            for run in range(1, 121):
                (func / f'sub-01_task-test_run-{run:03}_desc-preproc_bold.nii.gz').touch()
            setup = root / 'setup.sh'
            setup.write_text('start_timer() { :; }\nend_timer() { :; }\n')
            env = dict(os.environ, USER='testuser', PATH=str(binary)+os.pathsep+os.environ['PATH'],
                       FAKE_SLURM_STATE=str(root/'scheduler.json'), SETUP_FILE=str(setup),
                       FMRIPROC_FEAT_STATE_DIR=str(root/'cache'))
            wrapper=Path(__file__).parents[1]/'shell'/'spinoza_feat'
            result=subprocess.run(['bash',str(wrapper),'-m','300',str(project),'--',
                                   '--task','test','--desc','preproc'],env=env,
                                  text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            state_path=next(project.glob('code/logs/*/dispatch_state.json'))
            state=json.loads(state_path.read_text())
            self.assertEqual([w['count'] for w in state['waves']],[40,40,40])
            self.assertEqual(state['offset'],120)
            result=subprocess.run(['bash',str(wrapper),'--resume-submission',str(state_path.parent)],
                                  env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len(json.loads((root/'scheduler.json').read_text())['calls']),3)


if __name__ == '__main__':
    unittest.main()
