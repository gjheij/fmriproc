"""PSC units, provenance, reference generation, and CLI/registration integration."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import types

os.environ.setdefault("NO_ET", "1")
os.environ.setdefault("NIPYPE_NO_ET", "1")

import nibabel as nib
import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fsl(monkeypatch):
    package = types.ModuleType("fmriproc")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, "fmriproc", package)
    spec = importlib.util.spec_from_file_location("fmriproc.fsl", ROOT / "fmriproc/fsl.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def image(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(np.array(values, dtype=np.float32).reshape(2, 2, 2), np.eye(4)), path)


@pytest.fixture
def run(tmp_path, fsl, monkeypatch):
    feat = tmp_path / "sub-01_task-test_run-01_desc-preproc.feat"
    feat.mkdir()
    settings = {
        "evs_orig": 3, "evs_real": 5, "ncon_real": 3, "ncon_orig": 3,
        "tr": 2.1, "npts": 335, "temphp_yn": 1, "paradigm_hp": 128,
        "convolve1": 3, "convolve2": 3, "convolve3": 0,
        "shape1": 3, "shape2": 3, "shape3": 2,
        "deriv_yn1": 1, "deriv_yn2": 1, "deriv_yn3": 0,
        "con_real1.1": 1, "con_real2.1": 1, "con_real2.3": -1,
        "con_real3.1": 2, "con_real3.3": -2,
    }
    (feat / "design.fsf").write_text("\n".join(f"set fmri({key}) {value}" for key, value in settings.items()))
    image(feat / "mean_func.nii.gz", [1000, 2000, 0, -1, np.nan, 1000, 1000, 1000])
    image(feat / "mask.nii.gz", [1] * 8)
    rows = []
    for number, name in enumerate(("A", "A-B", "2A-2B"), 1):
        for stem, value in (("cope", 20 * number), ("varcope", 4 * number)):
            image(feat / "stats" / f"{stem}{number}.nii.gz", [value] * 8)
        rows.append(dict(subject="01", session="", task="test", run="01", space="T1w", desc="preproc",
                         run_label=feat.stem, cope=str(number), contrast_name=name, canonical_name=name,
                         feat_dir=str(feat), cope_file=str(feat / "stats" / f"cope{number}.nii.gz"),
                         varcope_file=str(feat / "stats" / f"varcope{number}.nii.gz")))
    commands = []
    def fake_model(command, cwd):
        commands.append(command)
        assert command[0] == "feat_model"
        root = Path(command[1])
        fsf = fsl._psc_fsf_settings(root.with_suffix(".fsf"))
        assert fsf["temphp_yn"] == "0"
        assert fsf["tempfilt_yn1"] == "0"
        assert fsf["evs_real"] == "1"
        assert fsf["tr"] == "0.1"
        x = np.full((1200, 1), -0.2)
        x[250, 0] = 0.3
        root.with_suffix(".mat").write_text("/Matrix\n" + "\n".join(str(v) for v in x[:, 0]))
    monkeypatch.setattr(fsl, "run_logged_command", fake_model)
    return feat, pd.DataFrame(rows), tmp_path / "cache", commands


def test_scale_variance_mask_and_cache(fsl, run):
    feat, rows, cache, commands = run
    converted = fsl.convert_feat_to_psc(rows, cache, 1)
    assert len(commands) == 1
    cope = nib.load(feat / "psc/cope1.nii.gz").get_fdata().ravel()
    varcope = nib.load(feat / "psc/varcope1.nii.gz").get_fdata().ravel()
    np.testing.assert_allclose(cope[:2], [1, 0.5])
    np.testing.assert_allclose(varcope[:2], [0.01, 0.0025])
    np.testing.assert_allclose(cope[:2] / np.sqrt(varcope[:2]), 20 / np.sqrt(4))
    assert np.all(cope[2:5] == 0)
    assert nib.load(feat / "psc/mask.nii.gz").get_fdata().sum() == 5
    meta = json.loads((feat / "psc/normalization.json").read_text())
    assert meta["excluded_voxels"] == 3
    assert meta["contrasts"]["3"]["divisor"] == 2
    # Reuse is a true no-op for downstream file identities.
    before = (feat / "psc/cope1.nii.gz").stat().st_mtime_ns
    fsl.convert_feat_to_psc(rows, cache, 1)
    assert len(commands) == 1
    assert (feat / "psc/cope1.nii.gz").stat().st_mtime_ns == before
    selected = fsl.select_feat_units(converted, "psc", "1")
    assert selected.effect_units.eq("psc").all()
    assert selected.cope_file.str.contains("/psc/").all()
    assert fsl.select_feat_units(converted, "raw", "1").psc_reference_id.eq("").all()


def test_stale_inputs_require_psc_overwrite(fsl, run):
    feat, rows, cache, _ = run
    converted = fsl.convert_feat_to_psc(rows, cache, 1)
    image(feat / "stats/cope1.nii.gz", [100] * 8)
    with pytest.raises(Exception, match="stale"):
        fsl.convert_feat_to_psc(rows, cache, 1)
    with pytest.raises(Exception, match="stale"):
        fsl.select_feat_units(converted, "psc", "1")
    fsl.convert_feat_to_psc(rows, cache, 1, overwrite=True)
    assert nib.load(feat / "psc/cope1.nii.gz").get_fdata().ravel()[0] == 5


def test_stale_mean_and_rebuild(fsl, run):
    feat, rows, cache, _ = run
    fsl.convert_feat_to_psc(rows, cache, 1)
    recovered = fsl._normalize_contrast_manifest_table(rows)
    assert recovered.psc_cope_file.ne("").all()
    image(feat / "mean_func.nii.gz", [500] * 8)
    recovered = fsl._normalize_contrast_manifest_table(recovered)
    assert recovered.psc_cope_file.eq("").all()


@pytest.mark.parametrize("key,value,message", [
    ("con_real1.2", 1, "derivative"), ("con_real1.5", 1, "nuisance"),
    ("con_real2.3", -2, "unequal"), ("convolve2", 2, "common canonical"),
    ("ortho1.2", 1, "orthogonalized"),
])
def test_unsupported_contrasts(fsl, run, key, value, message):
    feat, rows, cache, _ = run
    with open(feat / "design.fsf", "a") as stream:
        stream.write(f"\nset fmri({key}) {value}\n")
    with pytest.raises(Exception, match=message):
        fsl.convert_feat_to_psc(rows, cache, 1)
    assert not (feat / "psc").exists()


def test_explicit_divisor_and_geometry(fsl, run):
    feat, rows, cache, _ = run
    with open(feat / "design.fsf", "a") as stream:
        stream.write("\nset fmri(con_real2.3) -2\n")
    fsl.convert_feat_to_psc(rows, cache, 1, divisors=["A-B=2"])
    bad = nib.Nifti1Image(np.zeros((3, 3, 3), dtype=np.float32), np.eye(4))
    nib.save(bad, feat / "stats/cope1.nii.gz")
    with pytest.raises(Exception, match="geometry|shape|dimensions",):
        fsl.convert_feat_to_psc(rows, cache, 1, divisors=["A-B=2"], overwrite=True)
    assert (feat / "psc/normalization.json").is_file()


def test_psc_only_cli_and_manifest_rebuild(fsl, run, monkeypatch):
    feat, rows, cache, _ = run
    deriv = feat.parent
    rows.to_csv(deriv / "contrast_manifest.tsv", sep="\t", index=False)
    work = deriv / "work" / feat.stem
    work.mkdir(parents=True)
    (work / "contrasts.json").write_text(rows.to_json(orient="records"))
    command = runpy.run_path(str(ROOT / "bin/call_feat"))["run_firstlevel"]
    # No BIDS directory or task is required; these inputs must not be prepared.
    result = CliRunner().invoke(command, ["--deriv-dir", str(deriv), "--space", "T1w", "--psc-only", "--subject", "1", "--run", "1"])
    assert result.exit_code == 0, result.output + repr(result.exception)
    saved = pd.read_csv(deriv / "contrast_manifest.tsv", sep="\t")
    assert saved.psc_cope_file.notna().all()
    fsl.rebuild_contrast_manifest(deriv)
    saved = pd.read_csv(deriv / "contrast_manifest.tsv", sep="\t")
    assert saved.psc_cope_file.notna().all()


def test_higher_level_unit_keys_and_missing_units(fsl, run):
    feat, rows, cache, _ = run
    converted = fsl.convert_feat_to_psc(rows, cache, 1)
    selected = fsl.select_feat_units(converted, "psc", "1")
    shared = fsl.shared_analysis_entities(selected)
    assert shared["effect_units"] == "psc"
    assert shared["psc_reference_id"]
    with pytest.raises(Exception, match="different effect_units"):
        fsl.shared_analysis_entities(pd.concat([selected, fsl.select_feat_units(rows, "raw", "1")]))
    with pytest.raises(Exception, match="No raw"):
        fsl.select_feat_units(selected, "raw", "2")
    with pytest.raises(Exception, match="missing"):
        fsl.select_feat_units(rows, "psc", "1")
    path = feat.parent / "level2.tsv"
    base = dict(subject="01", canonical_name="A", effect_units="raw", psc_reference_id="")
    fsl.merge_analysis_manifest(path, pd.DataFrame([base]), ["subject", "canonical_name", *fsl.FEAT_MEASURE_COLUMNS])
    base.update(effect_units="psc", psc_reference_id="abc")
    fsl.merge_analysis_manifest(path, pd.DataFrame([base]), ["subject", "canonical_name", *fsl.FEAT_MEASURE_COLUMNS])
    assert len(pd.read_csv(path, sep="\t")) == 2


def test_psc_registration_rejects_featregapply(fsl, run):
    feat, rows, cache, _ = run
    rows = fsl.select_feat_units(fsl.convert_feat_to_psc(rows, cache, 1), "psc", "1")
    with pytest.raises(Exception, match="featregapply cannot"):
        fsl.resolve_registered_input(row=rows.iloc[0], input_level="1", registration_mode="featregapply", registered_subdir="reg_standard", dry_run=True)
    a, b, mask, directory = fsl.resolve_registered_input(row=rows.iloc[0], input_level="1", registration_mode="prealigned", registered_subdir="reg_standard", dry_run=False)
    assert mask == feat / "psc/mask.nii.gz"
    assert a == feat / "psc/cope1.nii.gz"


def test_level2_level3_keep_unit_streams_and_reuse(fsl, run):
    feat, rows, cache, _ = run
    converted = fsl.convert_feat_to_psc(rows, cache, 1)
    other_run = converted.copy()
    other_run["run"] = "02"
    other_run["run_label"] += "_second"
    manifest = feat.parent / "contrast_manifest.tsv"
    pd.concat([converted, other_run]).to_csv(manifest, sep="\t", index=False)
    level2 = runpy.run_path(str(ROOT / "bin/call_feat2"))["main"]
    calls = []
    def fixed(rows, output, name, overwrite, dry_run):
        calls.append((rows.copy(), output))
        output.mkdir(parents=True)
        for stem in ("cope", "varcope", "tstat", "zstat"):
            image(output / "stats" / f"{stem}1.nii.gz", [1] * 8)
        image(output / "mask.nii.gz", [1] * 8)
        return dict(number_of_inputs=len(rows), second_level_dir=str(output), **{
            f"{stem}_file": str(output / "stats" / f"{stem}1.nii.gz")
            for stem in ("cope", "varcope", "tstat", "zstat")})
    level2.callback.__globals__["run_fixed_effects_group"] = fixed
    level2.callback.__globals__["_maybe_write_gfeat_report_index"] = lambda *a, **k: None
    out = feat.parent / "level2"
    args = ["--manifest", str(manifest), "--output-dir", str(out)]
    for units in ("raw", "psc", "psc", "raw"):
        result = CliRunner().invoke(level2, [*args, "--input-units", units])
        assert result.exit_code == 0, result.output + repr(result.exception)
    assert len(calls) == 6  # three contrasts per unit; repeated calls reuse.
    records = pd.read_csv(out / "contrast_manifest_level2.tsv", sep="\t", dtype=str, keep_default_na=False)
    assert len(records) == 6
    assert set(records.effect_units) == {"raw", "psc"}
    assert records.loc[records.effect_units == "psc", "second_level_dir"].str.contains("_units-psc_ref-").all()
    assert all(Path(value).parent.name == "psc" for value in calls[3][0].cope_file)
    second_subject = records.copy()
    second_subject["subject"] = "02"
    pd.concat([records, second_subject]).to_csv(out / "contrast_manifest_level2.tsv", sep="\t", index=False)
    level3 = runpy.run_path(str(ROOT / "bin/call_feat3"))["main"]
    group_calls = []
    def group(**kwargs):
        group_calls.append(kwargs)
        output = kwargs["output_dir"]
        output.mkdir(parents=True)
        for stem in ("cope", "varcope", "tstat", "zstat"):
            image(output / "stats" / f"{stem}1.nii.gz", [1] * 8)
        return [dict(group_dir=str(output), group_contrast="GroupMean", **{
            f"{stem}_file": str(output / "stats" / f"{stem}1.nii.gz")
            for stem in ("cope", "varcope", "tstat", "zstat")})]
    level3.callback.__globals__["run_cross_subject_analysis"] = group
    group_out = feat.parent / "level3"
    result = CliRunner().invoke(level3, ["--manifest", str(out / "contrast_manifest_level2.tsv"),
        "--output-dir", str(group_out), "--input-units", "psc", "--min-subjects", "2", "--no-report", "--registration-mode", "prealigned"])
    assert result.exit_code == 0, result.output + repr(result.exception)
    saved = pd.read_csv(group_out / "contrast_manifest_level3.tsv", sep="\t")
    assert saved.effect_units.eq("psc").all()
    assert len(group_calls) == 3
    assert all(call["rows"].effect_units.eq("psc").all() for call in group_calls)
    assert saved.group_dir.str.contains("_units-psc_ref-").all()


def test_registration_script_psc_alias_and_registered_resolver(fsl, run, tmp_path):
    feat, rows, cache, _ = run
    converted = fsl.convert_feat_to_psc(rows, cache, 1)
    reg = feat / "reg"
    reg.mkdir()
    for name in ("highres", "standard", "highres2standard", "highres2standard_warp", "example_func", "example_func2highres"):
        image(reg / f"{name}.nii.gz", [1] * 8)
    for name in ("highres2standard", "example_func2highres"):
        (reg / f"{name}.mat").write_text("identity")
    image(feat / "example_func.nii.gz", [1] * 8)
    h5 = tmp_path / "transform.h5"
    h5.write_text("transform")
    tools = tmp_path / "tools"
    tools.mkdir()
    scripts = {
        "call_loadsetup": "#!/bin/bash\ntrue\n",
        "call_bashhelper": "print_cmd() { printf '%q ' \"$@\"; printf '\\n'; }; print_line() { :; };\n",
        "call_antsapplytransforms": '#!/bin/bash\ncp "$3" "$4"\n',
    }
    for name in ("c3d_affine_tool", "wb_command", "convertwarp", "applywarp", "ConvertTransformFile", "CompositeTransformUtil", "updatefeatreg"):
        scripts[name] = "#!/bin/bash\nexit 0\n"
    for name, content in scripts.items():
        path = tools / name
        path.write_text(content)
        path.chmod(0o755)
    environment = {**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]}
    # This sandbox lacks /dev/fd; omit only the existing tee redirection.
    script = tmp_path / "call_ants2featreg"
    script.write_text((ROOT / "bin/call_ants2featreg").read_text().replace('exec > >(tee -a "$log_file") 2>&1', 'exec 2>&1'))
    cmd = ["bash", str(script), "--feat-dir", str(feat), "--t1w", str(reg / "highres.nii.gz"),
           "--boldref", str(feat / "example_func.nii.gz"), "--bold-to-t1w", str(reg / "example_func2highres.mat"),
           "--t1w-to-mni-h5", str(h5), "--template", str(reg / "standard.nii.gz"), "--apply-reg", "--stats-subdir", "psc"]
    result = subprocess.run(cmd, env=environment, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (feat / "reg_standard/psc/cope1.nii.gz").is_file()
    assert not (feat / "reg_standard/stats/cope1.nii.gz").exists()
    selected = fsl.select_feat_units(converted, "psc", "1")
    resolved = fsl.resolve_registered_input(row=selected.iloc[0], input_level="1", registration_mode="reg-standard", registered_subdir="reg_standard", dry_run=False)
    assert resolved[0] == feat / "reg_standard/psc/cope1.nii.gz"
    assert resolved[2] == feat / "reg_standard/psc/mask.nii.gz"
    h5.write_text("changed transform")
    with pytest.raises(Exception, match="changed"):
        fsl.resolve_registered_input(row=selected.iloc[0], input_level="1", registration_mode="reg-standard", registered_subdir="reg_standard", dry_run=False)


def test_psc_dry_run_does_not_create_outputs(fsl, run):
    feat, rows, cache, commands = run
    fsl.convert_feat_to_psc(rows, cache, 1, dry_run=True)
    assert not commands
    assert not (feat / "psc").exists()
    assert not cache.exists()


def test_array_fragment_merge_preserves_other_units(fsl, tmp_path):
    fragments = tmp_path / "parts"
    fragments.mkdir()
    output = tmp_path / "level2.tsv"
    row = dict(subject="01", session="", task="test", canonical_name="A", cope_file="raw", varcope_file="varraw")
    pd.DataFrame([row]).to_csv(output, sep="\t", index=False)
    row.update(effect_units="psc", psc_reference_id="abc", cope_file="psc", varcope_file="varpsc")
    pd.DataFrame([row]).to_csv(fragments / "job-1.tsv", sep="\t", index=False)
    fsl.merge_feat_manifest_fragments(fragments, output, 2)
    result = pd.read_csv(output, sep="\t")
    assert len(result) == 2
    assert set(result.effect_units) == {"raw", "psc"}
    fsl.merge_feat_manifest_fragments(fragments, output, 2)
    assert len(pd.read_csv(output, sep="\t")) == 2


def test_missing_sidecar_does_not_leave_stale_manifest_paths(fsl, run):
    feat, rows, cache, _ = run
    converted = fsl.convert_feat_to_psc(rows, cache, 1)
    (feat / "psc/normalization.json").unlink()
    recovered = fsl._normalize_contrast_manifest_table(converted)
    assert recovered.psc_cope_file.eq("").all()


def test_divisor_cannot_bypass_derivative_validation(fsl, run):
    feat, rows, cache, _ = run
    with open(feat / "design.fsf", "a") as stream:
        stream.write("\nset fmri(con_real1.2) 1\n")
    with pytest.raises(Exception, match="derivative"):
        fsl.convert_feat_to_psc(rows, cache, 1, divisors=["A=1"])
