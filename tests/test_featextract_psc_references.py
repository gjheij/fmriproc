import argparse
import csv
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import nibabel as nib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'bin'))
loader=SourceFileLoader('featextract',str(Path(__file__).resolve().parents[1]/'bin/call_featextract'))
spec=spec_from_loader(loader.name,loader)
module=module_from_spec(spec)
loader.exec_module(module)

REF_US='4354bdf9d9510816'
REF_CS='a827d50fdb86133a'


def args(**overrides):
    values={name:[] for name in ('subject','session','task','run','desc','space','acquisition',
        'direction','echo','reconstruction','part','resolution','density','group_contrast')}
    values.update(where=[],psc_reference_id=[],conditions=None,input_units='psc')
    values.update(overrides)
    return argparse.Namespace(**values)


def row(subject='01',contrast='CS_50%_1',reference=REF_CS,**overrides):
    result=dict(subject=subject,canonical_name=contrast,effect_units='psc',psc_reference_id=reference,
                second_level_dir='/study/level2/sub-'+subject+'/contrast.feat',task='aversivechoice',
                desc='masked',space='T1w')
    result.update(overrides)
    return result


def select(rows,**overrides):
    fields=set().union(*(r.keys() for r in rows))
    return module.select_manifest_rows(rows,fields,args(**overrides))


class ReferenceSelection(unittest.TestCase):
    def test_different_contrasts_keep_their_references(self):
        rows=[row(),row(contrast='US_0%',reference=REF_US),row('02'),row('02','US_0%',REF_US)]
        selected=select(rows)
        self.assertEqual(selected,rows)

    def test_same_contrast_across_subjects_cannot_mix_references(self):
        with self.assertRaisesRegex(ValueError,'within one contrast/analysis stream'):
            select([row(),row('02',reference=REF_US)])

    def test_same_contrast_across_runs_cannot_mix_references(self):
        with self.assertRaisesRegex(ValueError,'canonical_name=CS_50%_1'):
            select([row(run='01'),row(run='02',reference=REF_US)])

    def test_explicit_multiple_references_do_not_bypass_guard(self):
        with self.assertRaisesRegex(ValueError,'Multiple PSC references'):
            select([row(),row('02',reference=REF_US)],psc_reference_id=[REF_CS,REF_US])

    def test_explicit_single_reference_still_filters(self):
        selected=select([row(),row('02',reference=REF_US)],psc_reference_id=[REF_CS])
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['subject'],'01')

    def test_distinct_streams_can_have_distinct_references(self):
        self.assertEqual(len(select([row(),row('02',reference=REF_US,desc='preproc')])),2)

    def test_group_contrasts_are_separate_streams(self):
        rows=[row(group_dir='/group/mean',group_contrast='GroupMean'),
              row(reference=REF_US,group_dir='/group/age',group_contrast='Age')]
        self.assertEqual(len(select(rows)),2)

    def test_missing_psc_reference_remains_an_error(self):
        with self.assertRaisesRegex(ValueError,'require a psc_reference_id'):
            select([row(reference='')])

    def test_mixed_units_still_require_selection(self):
        with self.assertRaisesRegex(ValueError,'mix raw and PSC'):
            select([row(),row(effect_units='raw',reference='')],input_units=None)

    def test_condition_selection_runs_before_consistency_check(self):
        rows=[row(),row('02',reference=REF_US),row(contrast='US_0%',reference=REF_US)]
        selected=select(rows,conditions=['US_0%'])
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['canonical_name'],'US_0%')

    def test_first_level_psc_paths_remain_selected(self):
        first=row(second_level_dir='',feat_dir='/first.feat',effect_units='raw',
                  psc_cope_file='/first.feat/psc/cope1.nii.gz',
                  psc_varcope_file='/first.feat/psc/varcope1.nii.gz',
                  psc_mask_file='/first.feat/psc/mask.nii.gz')
        selected=select([first])[0]
        self.assertEqual(selected['cope_file'],first['psc_cope_file'])
        self.assertEqual(selected['effect_units'],'psc')


class ExtractionIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.manifest=self.root/'manifest.tsv'
        self.output=self.root/'roi.tsv'
        self.roi=self.root/'labels.nii.gz'
        self.save(self.roi,465)
        self.rows=[]
        for subject in ['01','02']:
            for contrast,reference,value in [('CS_50%_1',REF_CS,1.2),('US_0%',REF_US,.05)]:
                directory=self.root/subject/contrast
                directory.mkdir(parents=True)
                self.save(directory/'mask.nii.gz',1)
                self.save(directory/'cope1.nii.gz',value)
                self.rows.append(row(subject,contrast,reference,second_level_dir=str(directory),
                                     cope_file=str(directory/'cope1.nii.gz')))
        self.write_manifest()

    def save(self,path,value):
        nib.save(nib.Nifti1Image(np.full((2,2,2),value,dtype=np.float32),np.eye(4)),path)

    def write_manifest(self):
        with self.manifest.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(self.rows[0]),delimiter='\t')
            writer.writeheader();writer.writerows(self.rows)

    def invoke(self):
        with patch.object(sys,'argv',['call_featextract','--manifest',str(self.manifest),
            '--input-units','psc','--desc','masked','--space','T1w','--roi',str(self.roi),
            '--roi-type','labels','--areas','465','--stat','cope','--output',str(self.output),'--strict']),\
             patch('sys.stderr',new_callable=io.StringIO):
            module.main()

    def test_both_reference_families_extract_in_one_command(self):
        self.invoke()
        with self.output.open() as stream:
            rows=list(csv.DictReader(stream,delimiter='\t'))
        self.assertEqual(len(rows),4)
        self.assertEqual({r['psc_reference_id'] for r in rows},{REF_US,REF_CS})
        self.assertTrue(all(r['status']=='ok' and r['estimate_units']=='percent' for r in rows))
        for record in rows:
            self.assertAlmostEqual(float(record['mean_estimate']),1.2 if record['canonical_name'].startswith('CS') else .05,places=6)
            self.assertEqual(record['n_valid_voxels'],'8')
        self.assertEqual({r['subject'] for r in rows},{'01','02'})

    def test_inconsistent_manifest_fails_before_output_is_replaced(self):
        self.rows[2]['psc_reference_id']=REF_US
        self.write_manifest()
        self.output.write_text('existing results\n')
        with self.assertRaisesRegex(SystemExit,'Multiple PSC references'):
            self.invoke()
        self.assertEqual(self.output.read_text(),'existing results\n')


if __name__=='__main__':
    unittest.main()
