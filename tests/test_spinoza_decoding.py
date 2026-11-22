import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / 'shell/spinoza_decoding'
TEMPLATE = ROOT / 'fmriproc/misc/panic_coglearn7t.yml'


class Decoding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'Cog Learn7T'
        self.beta = self.project / 'derivatives/glmsingle/impulse'
        for subject in ('sub-01', 'sub-02'):
            (self.beta / subject).mkdir(parents=True)
        self.config = self.root / 'panic.yml'
        self.cfg = yaml.safe_load(TEMPLATE.read_text())
        self.cfg['general_settings']['beta_dir'] = 'derivatives/glmsingle/impulse'
        self.cfg['general_settings']['save_dir'] = 'derivatives/panic'
        self.config.write_text(yaml.safe_dump(self.cfg))
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.capture = self.root / 'capture.json'
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'], CAPTURE=str(self.capture))
        self.stub('panic', 'import json,os,sys\nfrom pathlib import Path\nPath(os.environ["CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\n')
        self.stub('sbatch', 'import json,os,sys\nfrom pathlib import Path\nPath(os.environ["CAPTURE"]).write_text(json.dumps(dict(argv=sys.argv[1:],mem=os.getenv("SBATCH_MEM_PER_NODE"))))\nprint("123456")\n')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\n' + body)
        path.chmod(0o755)

    def run_wrapper(self, flags=(), extra=()):
        return subprocess.run([sys.executable, str(WRAPPER), *flags, str(self.project), '--',
                               '-f', str(self.config), *extra], env=self.env, text=True, capture_output=True)

    def plan(self):
        directory = next((self.project / 'code/logs').glob('spinoza_decoding_submission.*'))
        plan = json.loads((directory / 'submission.json').read_text())
        return directory, plan

    def test_yaml_and_subject_discovery_preserved(self):
        result = self.run_wrapper(['--dry-run', '-j', '2', '-m', '1'])
        self.assertEqual(result.returncode, 0, result.stderr)
        directory, plan = self.plan()
        self.assertIn('Log directory: ' + str(directory), result.stdout)
        self.assertEqual([job['subject'] for job in plan['jobs']], ['sub-01', 'sub-02'])
        cfg = yaml.safe_load(Path(plan['jobs'][0]['config']).read_text())
        self.assertEqual(cfg['roi_dict'], self.cfg['roi_dict'])
        self.assertEqual(cfg['general_settings']['source'], 'stglm')
        self.assertEqual(cfg['general_settings']['method'], 'GLMsingleTYPED')
        self.assertEqual(cfg['general_settings']['beta_dir'], str(self.beta))
        self.assertEqual(cfg['decoding_settings']['parallel']['n_jobs'], 2)
        self.assertIn('--array=1-2%1', result.stdout)
        self.assertFalse(self.capture.exists())
        subprocess.run(['bash', '-n', str(directory / 'panic_array_runner.sh')], check=True)

    def test_overrides_and_unsets_match_frozen_command(self):
        result = self.run_wrapper(['--dry-run', '-s', '01'], ['--set', 'general_settings.method=GLMsingleTYPEB',
            'label_dict={US_50%_1_neg: 0, US_0%: 1}', 'decoding_settings.n_permutations=5',
            '--unset', 'decoding_settings.inner_cv'])
        self.assertEqual(result.returncode, 0, result.stderr)
        _, plan = self.plan()
        cfg = yaml.safe_load(Path(plan['jobs'][0]['config']).read_text())
        self.assertEqual(cfg['label_dict'], {'US_50%_1_neg': 0, 'US_0%': 1})
        self.assertEqual(cfg['general_settings']['method'], 'GLMsingleTYPEB')
        self.assertEqual(cfg['decoding_settings']['n_permutations'], 5)
        self.assertNotIn('inner_cv', cfg['decoding_settings'])

    def test_local_and_slurm_runner_use_identical_command(self):
        result = self.run_wrapper(['--local', '-s', '01'])
        self.assertEqual(result.returncode, 0, result.stderr)
        directory, plan = self.plan()
        local = json.loads(self.capture.read_text())
        subprocess.run(['bash', str(directory / 'panic_array_runner.sh')], env=dict(self.env, SLURM_ARRAY_TASK_ID='1'), check=True)
        self.assertEqual(local, json.loads(self.capture.read_text()))
        self.assertEqual(local, plan['jobs'][0]['command'][1:])

    def test_unique_submission_and_slurm_resources(self):
        self.env['SBATCH_MEM_PER_NODE'] = '16G'
        for _ in range(2):
            result = self.run_wrapper(['-j', '2', '-m', '8', '-q', 'intelsr_short'])
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list((self.project / 'code/logs').glob('spinoza_decoding_submission.*'))), 2)
        submitted = json.loads(self.capture.read_text())
        self.assertEqual(submitted['mem'], '16G')
        self.assertIn('--cpus-per-task=2', submitted['argv'])
        self.assertIn('--array=1-2%2', submitted['argv'])

    def test_invalid_subject_or_cpu_fails_before_submission(self):
        for flags in (['-s', '99'], ['-j', '0']):
            result = self.run_wrapper(flags)
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_legacy_source_discovery_explicit_method_and_roi_fallback(self):
        legacy = self.project / 'derivatives/halfpipe/sub-01'
        legacy.mkdir(parents=True)
        self.cfg['general_settings'].pop('beta_dir')
        self.cfg['general_settings']['source'] = 'halfpipe'
        self.cfg.pop('roi_dict')
        self.config.write_text(yaml.safe_dump(self.cfg))
        result = self.run_wrapper(['--dry-run', '--lss', '--searchlight'])
        self.assertEqual(result.returncode, 0, result.stderr)
        _, plan = self.plan()
        cfg = yaml.safe_load(Path(plan['jobs'][0]['config']).read_text())
        self.assertEqual(cfg['general_settings']['method'], 'LSS')
        self.assertEqual(cfg['general_settings']['beta_dir'], str(legacy.parent))
        self.assertEqual(cfg['roi_dict'], str(self.project / 'derivatives/rois/sub-01/searchlight'))
        self.assertIn('--searchlight', plan['jobs'][0]['command'])

    def test_master_module_30_maps_cpus_concurrency_and_config(self):
        script = (ROOT / 'shell/master').read_text()
        section = script.split('module=30\n', 1)[1].split('# STEP 31:', 1)[0]
        harness = '''
print_module_start() { :; }
print_module_end() { :; }
print_cmd() { :; }
print_error_msg() { echo ERROR >&2; }
FLAG_executeModule=30
module=30
''' + section
        # The native wrapper is executable, just as it is after installation.
        launcher = self.bin / 'spinoza_decoding'
        launcher.symlink_to(WRAPPER)
        env = dict(self.env, DIR_DATA_HOME=str(self.project), SUB='01', jobs_flag='-j 2',
                   WHICH_MOD='3', SGE_QUEUE='-q intelsr_short',
                   X_KWARGS='-f ' + shlex.quote(str(self.config)) + ' --set decoding_settings.n_permutations=5')
        result = subprocess.run(['bash', '-c', harness], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(self.capture.exists(), result.stdout + result.stderr)
        submitted = json.loads(self.capture.read_text())
        self.assertIn('--cpus-per-task=2', submitted['argv'])
        self.assertIn('--array=1-1%1', submitted['argv'])
        _, plan = self.plan()
        cfg = yaml.safe_load(Path(plan['jobs'][0]['config']).read_text())
        self.assertEqual(cfg['decoding_settings']['n_permutations'], 5)


if __name__ == '__main__':
    unittest.main()
