import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WrapperRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        setup = self.root / 'setup.sh'
        setup.write_text('')
        helper = self.root / 'call_bashhelper'
        helper.write_text('''
print_subject_header() { :; }
print_line() { :; }
print_error_msg() { echo "$*" >&2; }
print_directory_not_exist() { echo "$*" >&2; }
decide_job_type() { echo stglm; }
print_cmd() { printf '%q ' "$@"; printf '\\n'; }
''')
        self.env = dict(os.environ, SETUP_FILE=str(setup), PATH=str(self.root) + os.pathsep + os.environ['PATH'])

    def invoke(self, values):
        return subprocess.run(['bash', str(ROOT / 'bin/call_stglm'), '-p', str(self.project),
            '-u', '29', '--glm-single', '--local', '--dry-run', *values], env=self.env, text=True, capture_output=True)

    def test_space_and_comma_forms_reach_native_stglm(self):
        for values in (['--run', '01', '03', '04'], ['--runs', '01,03,04']):
            result = self.invoke(values)
            self.assertEqual(result.returncode, 0, result.stderr)
            argv = shlex.split(result.stdout.strip().splitlines()[-1])
            start = argv.index('--run')
            self.assertEqual(argv[start+1:start+4], ['01', '03', '04'])

    def test_invalid_or_empty_selection_fails(self):
        for values in (['--run'], ['--run', 'abc'], ['--run', '0']):
            self.assertNotEqual(self.invoke(values).returncode, 0)


if __name__ == '__main__':
    unittest.main()
