import csv
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import nibabel as nib
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
WRAPPER=ROOT/'shell/spinoza_featextract'
CORE=ROOT/'bin/_featextract.py'
loader=SourceFileLoader('extract_wrapper',str(WRAPPER))
spec=importlib.util.spec_from_loader(loader.name,loader);w=importlib.util.module_from_spec(spec);loader.exec_module(w)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project=self.root/'study';self.project.mkdir()
        self.manifest=self.root/'manifest.tsv';self.output=self.root/'result.tsv';self.serial=self.root/'serial.tsv'
        self.roi=self.root/'{subject}'/'labels.nii.gz'
        rows=[]
        for subject in ['01','02']:
            roi=self.root/('sub-'+subject)/'labels.nii.gz';roi.parent.mkdir()
            values=np.full((4,4,4),465,dtype=np.int16);values[2:]=435
            nib.save(nib.Nifti1Image(values,np.eye(4)),roi)
            for contrast,ref,value in [('US', '4354bdf9d9510816',.1),('CS','a827d50fdb86133a',1.2)]:
                folder=self.root/subject/contrast;folder.mkdir(parents=True)
                stat=folder/'cope1.nii.gz';mask=folder/'mask.nii.gz'
                affine=np.diag([2.,2.,2.,1.])
                nib.save(nib.Nifti1Image(np.full((2,2,2),value,dtype=np.float32),affine),stat)
                nib.save(nib.Nifti1Image(np.ones((2,2,2),dtype=np.uint8),affine),mask)
                rows.append(dict(subject=subject,task='faces',canonical_name=contrast,second_level_dir=str(folder),
                    cope_file=str(stat),mask_file=str(mask),effect_units='psc',psc_reference_id=ref,space='T1w',desc='masked'))
        self.rows=rows;self.write_manifest()
        self.native=['--manifest',str(self.manifest),'--input-units','psc','--roi',str(self.roi),
                     '--roi-type','labels','--areas','465','435','--stat','cope','--output',str(self.output),'--strict']

    def write_manifest(self):
        with self.manifest.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(self.rows[0]),delimiter='\t');writer.writeheader();writer.writerows(self.rows)

    def invoke(self,extra=(),native=None,timeout=40):
        return subprocess.run([sys.executable,str(WRAPPER),'-l','2',*extra,str(self.project),'--',*(self.native if native is None else native)],
                              text=True,capture_output=True,timeout=timeout)

    def plan(self):
        return next(self.project.glob('code/logs/*/extraction_plan.json'))

    def test_local_parallel_output_is_identical_to_serial_and_reusable(self):
        argv=w.replace_option(self.native,'--output',self.serial)
        result=subprocess.run([sys.executable,str(CORE),*argv],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=self.invoke(['--local','-m','2'])
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(self.output.read_bytes(),self.serial.read_bytes())
        plan_path=self.plan();plan=json.loads(plan_path.read_text())
        self.assertEqual(len(plan['jobs']),2)
        self.assertEqual(len(plan['expected']),8)
        self.assertFalse(Path(str(self.output)+'.extract-claim.json').exists())
        before=self.output.stat().st_mtime_ns
        result=self.invoke(['--local','-m','2'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(before,self.output.stat().st_mtime_ns)

    def test_global_reference_guard_precedes_subject_partitioning(self):
        self.rows[2]['psc_reference_id']='different';self.write_manifest()
        result=self.invoke(['--local'])
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Multiple PSC references',result.stderr)
        self.assertFalse(self.output.exists())

    def test_dry_run_never_claims_or_writes_final_output(self):
        result=self.invoke(['--local','--dry-run'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(Path(str(self.output)+'.extract-claim.json').exists())
        self.assertTrue(json.loads(self.plan().read_text())['preview'])

    def test_existing_output_requires_explicit_overwrite(self):
        self.output.write_text('previous result\n')
        result=self.invoke(['--local'])
        self.assertNotEqual(result.returncode,0)
        self.assertIn('--overwrite',result.stderr)
        self.assertEqual(self.output.read_text(),'previous result\n')
        result=self.invoke(['--local','--overwrite'])
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('mean_estimate',self.output.read_text())

    def test_failed_strict_worker_does_not_replace_final_output(self):
        self.output.write_text('previous result\n')
        native=list(self.native);native[native.index('435')]='999'
        result=self.invoke(['--local','--overwrite'],native=native)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('workers failed',result.stderr)
        self.assertEqual(self.output.read_text(),'previous result\n')
        self.assertTrue(Path(str(self.output)+'.extract-claim.json').exists())

    def test_changed_inputs_are_rejected_on_resume(self):
        native=list(self.native);native[native.index('435')]='999'
        result=self.invoke(['--local'],native=native)
        self.assertNotEqual(result.returncode,0)
        self.manifest.write_text(self.manifest.read_text()+'\n')
        result=subprocess.run([sys.executable,str(WRAPPER),'--resume-submission',str(self.plan().parent)],text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Input changed',result.stderr)

    def test_fragment_duplicate_or_missing_rows_prevent_merge(self):
        result=self.invoke(['--local'])
        self.assertEqual(result.returncode,0,result.stderr)
        plan_path=self.plan();plan=w.load_plan(plan_path)
        job=plan['jobs'][0];folder=plan_path.parent/job['folder'];fragment=folder/'results.tsv'
        with fragment.open() as f:
            reader=csv.DictReader(f,delimiter='\t');fields=reader.fieldnames;rows=list(reader)
        rows[1]=rows[0]
        with fragment.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields,delimiter='\t');writer.writeheader();writer.writerows(rows)
        with self.assertRaisesRegex(RuntimeError,'duplicate'):
            w.read_fragment(plan,job,fragment)

    def test_stat_mask_is_not_cached_across_contrasts(self):
        # Geometry matches but the second contrast uses a different validity mask.
        second=Path(self.rows[1]['mask_file']);image=nib.load(second)
        data=np.ones(image.shape,dtype=np.uint8);data[0]=0
        nib.save(nib.Nifti1Image(data,image.affine),second)
        native=[v for v in self.native if v!='--strict']
        result=self.invoke(['--local'],native=native)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        with self.output.open() as f:
            rows=list(csv.DictReader(f,delimiter='\t'))
        counts={(r['subject'],r['canonical_name'],r['roi_id']):r['n_valid_voxels'] for r in rows}
        self.assertNotEqual(counts['01','US','465'],counts['01','CS','465'])

    def test_symlink_retargeting_changes_identity(self):
        first=self.root/'first';second=self.root/'second';link=self.root/'link'
        first.write_text('first');second.write_text('second');link.symlink_to(first)
        saved=w.identity(link);link.unlink();link.symlink_to(second)
        with self.assertRaisesRegex(RuntimeError,'Input changed'):
            w.check_inputs([saved])

    def test_resume_existing_plan_does_not_hold_output_lock(self):
        # Simulate interruption before worker execution by planning Slurm through mocks.
        def submit(*args,**kwargs):
            pass
        with patch.object(w,'slurm_limits',return_value=(99,300)),patch.object(w.scheduler,'dispatch',side_effect=RuntimeError('planned stop')):
            status=w.main(['-l','2',str(self.project),'--',*self.native])
        self.assertEqual(status,1)
        plan_path=self.plan();plan=json.loads(plan_path.read_text());plan['mode']='local'
        plan_path.write_text(json.dumps(plan))
        # The plan identity is unchanged: execution location is not a numerical setting.
        result=self.invoke(['--local'],timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(self.output.is_file())


    def test_generated_slurm_runners_and_merge_match_serial(self):
        calls=[]
        def submit(argv, env=None):
            if argv[0] != 'sbatch':
                return ''
            calls.append(argv)
            return str(500+len(calls))+'\n'
        with patch.object(w,'slurm_limits',return_value=(99,300)), \
             patch.object(w.scheduler,'queue_snapshot',return_value={}), \
             patch.object(w.scheduler,'command',side_effect=submit), \
             patch.dict(os.environ,{'FMRIPROC_FEAT_STATE_DIR':str(self.root/'cache')}):
            status=w.main(['-l','2','-m','8',str(self.project),'--',*self.native])
        self.assertEqual(status,0)
        self.assertEqual(len(calls),2)
        self.assertIn('--array=1-2%2',calls[0])
        self.assertTrue(any('afterok:501' in item for item in calls[1]))
        folder=self.plan().parent
        for index in (1,2):
            env=dict(os.environ,SLURM_ARRAY_TASK_ID=str(index),FEAT_BATCH_OFFSET='0')
            result=subprocess.run(['bash',str(folder/'runner.sh')],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run(['bash',str(folder/'merge.sh')],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        core_argv=w.replace_option(self.native,'--output',self.serial)
        w.core.main(core_argv)
        self.assertEqual(self.output.read_bytes(),self.serial.read_bytes())


class Resampling(unittest.TestCase):
    def test_resample_once_for_multiple_labels_and_same_grid(self):
        core=w.core
        roi=nib.Nifti1Image(np.ones((4,4,4),dtype=np.int16),np.eye(4))
        stat=nib.Nifti1Image(np.ones((2,2,2)),np.diag([2.,2.,2.,1.]))
        args=type('Args',(),dict(roi_type='labels',threshold=0.,weighted=False,min_voxels=1))()
        cache=w.OrderedDict();definitions=[('1',[1],None),('2',[2],None)]
        original=core.resample_from_to
        with patch.object(core,'resample_from_to',wraps=original) as sample:
            core.extract(roi,stat,args,definitions,sampled_cache=cache)
            core.extract(roi,stat,args,definitions,sampled_cache=cache)
        self.assertEqual(sample.call_count,1)

    def test_identical_grid_skips_resampling(self):
        core=w.core
        roi=nib.Nifti1Image(np.ones((2,2,2),dtype=np.int16),np.eye(4))
        stat=nib.Nifti1Image(np.ones((2,2,2)),np.eye(4))
        args=type('Args',(),dict(roi_type='labels',threshold=0.,weighted=False,min_voxels=1))()
        with patch.object(core,'resample_from_to',side_effect=AssertionError('unnecessary resample')):
            core.extract(roi,stat,args,[('1',[1],None)],sampled_cache=w.OrderedDict())



class MasterRouting(unittest.TestCase):
    def test_module28_extract_and_glm_argument_routing(self):
        master=(WRAPPER.parent/'master').read_text()
        block=master[master.index('# STEP 28: FEAT'):master.index('# STEP 29: Single-trial')]
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            binary=folder/'capture'
            binary.write_text('#!'+sys.executable+'\nimport json,os,sys\nopen(os.environ["CAPTURE"],"w").write(json.dumps(sys.argv))\n')
            binary.chmod(0o755)
            for name in ['spinoza_feat','spinoza_featextract']:
                (folder/name).symlink_to(binary)
            for extraction in ['0','1']:
                env=dict(os.environ,PATH=str(folder)+os.pathsep+os.environ['PATH'],CAPTURE=str(folder/'args.json'),
                         FLAG_executeModule='28',HELP='0',feat_extract=extraction,WHICH_MOD='2',
                         DIR_DATA_HOME='/study',SUB='01',jobs_flag='-j 8',SGE_QUEUE='-q short',OW='1',
                         X_KWARGS='--manifest /study/manifest.tsv --roi "/study/{subject}/atlas.nii.gz"')
                result=subprocess.run(['bash','-c',
                    'print_module_start() { :; }; print_module_end() { :; }; print_cmd() { :; };\n'+block],
                    env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                argv=json.loads((folder/'args.json').read_text())
                self.assertEqual(Path(argv[0]).name,'spinoza_featextract' if extraction=='1' else 'spinoza_feat')
                self.assertIn('-m',argv);self.assertEqual(argv[argv.index('-m')+1],'8')
                self.assertEqual(argv.index('--overwrite') < argv.index('--'),extraction=='1')
                self.assertIn('/study/{subject}/atlas.nii.gz',argv)

if __name__=='__main__':
    unittest.main()
