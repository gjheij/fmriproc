"""Regression checks for FEAT orchestration without an FSL installation."""

import importlib.util
import json
import os
import runpy
import subprocess
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import click
import nibabel as nib
import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner


@pytest.fixture
def fsl(monkeypatch):
    # Regression checks should not trigger dependency version-check telemetry.
    monkeypatch.setenv("NIPYPE_NO_ET", "1")
    monkeypatch.setenv("NO_ET", "1")
    # Load the module independently of unrelated package-level MRI dependencies.
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("fmriproc.fsl", root / "fmriproc" / "fsl.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    package = types.ModuleType("fmriproc")
    package.fsl = module
    monkeypatch.setitem(sys.modules, "fmriproc", package)
    monkeypatch.setitem(sys.modules, "fmriproc.fsl", module)
    return module


def write_image(path, affine=None, volumes=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    shape = (2, 2, 2) if volumes is None else (2, 2, 2, volumes)
    nib.save(nib.Nifti1Image(np.ones(shape), np.eye(4) if affine is None else affine), path)
    return path


def test_entity_labels_distinguish_derivatives(fsl):
    base = {"subject": "1", "task": "test", "run": 1}
    assert fsl.entity_label(base) == "sub-1_task-test_run-1"
    for entity in ("reconstruction", "part", "space", "resolution", "density", "desc"):
        assert fsl.entity_label({**base, entity: "a"}) != fsl.entity_label({**base, entity: "b"})
    assert fsl.entity_label({**base, "res": "2", "den": "32k"}).endswith("_res-2_den-32k")
    assert fsl.normalize_analysis_entities({"resolution": "", "res": "2"})["resolution"] == "2"
    with pytest.raises(click.ClickException, match="Conflicting"):
        fsl.entity_label({**base, "resolution": "1", "res": "2"})


@pytest.mark.parametrize("entity", [
    "space", "resolution", "density", "desc", "reconstruction", "part",
    "acquisition", "direction", "echo", "source_dataset",
])
def test_shared_entities_reject_mixed_inputs(fsl, entity):
    for other in ("b", ""):
        with pytest.raises(click.ClickException, match=f"different {entity}"):
            fsl.shared_analysis_entities(pd.DataFrame([{entity: "a"}, {entity: other}]))
    assert fsl.shared_analysis_entities(pd.DataFrame([{entity: "a"}, {entity: "a"}]))[entity] == "a"


def test_entity_manifest_roundtrip(fsl, tmp_path):
    entities = {
        "subject": "1", "task": "test", "run": "1", "space": "MNI",
        "res": "2", "den": "32k", "desc": "preproc", "reconstruction": "a",
        "part": "mag", "source_dataset": str(tmp_path),
    }
    dataset_description = tmp_path / "dataset_description.json"
    dataset_description.write_text('{"Name": "fMRIPrep"}')
    bold = tmp_path / "sub-1" / "func" / "bold.nii.gz"
    assert fsl.source_dataset(str(bold)) == str(tmp_path)
    label = fsl.entity_label(entities)
    output = tmp_path / f"{label}.feat"
    write_image(output / "stats" / "cope1.nii.gz")
    write_image(output / "stats" / "varcope1.nii.gz")
    fsl.write_contrast_manifest(
        work_dir=tmp_path / "work" / label, deriv_dir=tmp_path, entities=entities,
        label=label, output_dir=output, contrasts=[("A", "T", ["A"], [1])], canonical_names={},
    )
    table = pd.read_csv(tmp_path / "contrast_manifest.tsv", sep="\t", dtype=str, keep_default_na=False)
    record = table.iloc[0].to_dict()
    expected = fsl.normalize_analysis_entities(entities)
    assert {key: record[key] for key in expected} == expected
    rebuilt = fsl._rebuild_contrast_manifest_from_work(tmp_path).iloc[0].to_dict()
    assert {key: rebuilt[key] for key in expected} == expected
    provenance = fsl.analysis_provenance(table)
    assert provenance["inputs"][0]["resolution"] == "2"
    assert str(dataset_description) in [record["path"] for record in provenance["files"]]


@pytest.mark.parametrize("values, message", [
    ({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8]}, "rank deficient"),
    ({"a": [1, 2], "b": [1, 3]}, "rank deficient"),
    ({"a": [1, 2]}, "no residual"),
    ({"a": [1, 2, np.inf]}, "finite"),
])
def test_invalid_group_design(fsl, tmp_path, values, message):
    subjects = [str(i) for i in range(len(values["a"]))]
    path = tmp_path / "covariates.tsv"
    pd.DataFrame({"subject": subjects, **values}).to_csv(path, sep="\t", index=False)
    with pytest.raises(click.ClickException, match=message):
        fsl.prepare_group_design(
            subjects=subjects, covariates_file=path, covariate_names=list(values),
            demean_covariates=False, group_contrast_specs=[],
        )


def test_valid_group_design_and_contrast(fsl, tmp_path):
    path = tmp_path / "covariates.tsv"
    pd.DataFrame({"subject": ["1", "2", "3"], "age": [20, 30, 40]}).to_csv(path, sep="\t", index=False)
    columns, matrix, names, weights, _ = fsl.prepare_group_design(
        subjects=["3", "1", "2"], covariates_file=path, covariate_names=["age"],
        demean_covariates=True, group_contrast_specs=["Age;0,1"],
    )
    assert columns == ["Intercept", "age"]
    assert matrix == [[1, 10], [1, -10], [1, 0]]
    assert names == ["Age"] and weights == [[0, 1]]
    with pytest.raises(click.ClickException, match="non-finite"):
        fsl.parse_group_contrast("Bad;0,nan", columns)


@pytest.mark.parametrize("contrast, valid", [([1, 0], False), ([1, 1], True)])
def test_firstlevel_contrast_estimability(fsl, tmp_path, contrast, valid):
    root = tmp_path / "design"
    fsl._write_vest_matrix(root.with_suffix(".mat"), [[1, 1], [2, 2], [3, 3]])
    fsl._write_vest_contrast(root.with_suffix(".con"), ["A"], [contrast])
    if valid:
        fsl.verify_first_level_design(root)
    else:
        with pytest.raises(click.ClickException, match="not estimable"):
            fsl.verify_first_level_design(root)


def test_fixed_effects_geometry_checked_before_overwrite(fsl, tmp_path, monkeypatch):
    rows = []
    for run in (1, 2):
        directory = tmp_path / f"run-{run}.feat"
        affine = np.eye(4)
        affine[0, 3] = run
        cope = write_image(directory / "stats" / "cope1.nii.gz", affine)
        varcope = write_image(directory / "stats" / "varcope1.nii.gz", affine)
        write_image(directory / "mask.nii.gz", affine)
        rows.append({"cope_file": str(cope), "varcope_file": str(varcope), "feat_dir": str(directory)})
    output = tmp_path / "fixed.feat"
    output.mkdir()
    sentinel = output / "keep"
    sentinel.touch()
    monkeypatch.setattr(fsl, "_require_command", lambda name: name)
    with pytest.raises(click.ClickException, match="affine matrices differ"):
        fsl.run_fixed_effects_group(pd.DataFrame(rows), output, "A", True, False)
    assert sentinel.exists()


def test_geometry_requires_equal_input_counts(fsl, tmp_path):
    image = write_image(tmp_path / "image.nii.gz")
    with pytest.raises(click.ClickException, match="counts differ"):
        fsl.verify_group_geometry([image], [], [image])


def test_provenance_rejects_changed_inputs_and_settings(fsl, tmp_path):
    image = write_image(tmp_path / "cope.nii.gz")
    rows = pd.DataFrame({"subject": ["1"], "cope_file": [str(image)], "varcope_file": [str(image)]})
    original = fsl.analysis_provenance(rows, runmode="flame1")
    with pytest.raises(click.ClickException, match="no verifiable provenance"):
        fsl.verify_analysis_provenance(tmp_path, original)
    fsl.write_analysis_provenance(tmp_path, original)
    fsl.verify_analysis_provenance(tmp_path, fsl.analysis_provenance(rows, runmode="flame1"))
    with pytest.raises(click.ClickException, match="differ"):
        fsl.verify_analysis_provenance(tmp_path, fsl.analysis_provenance(rows, runmode="ols"))
    image.write_bytes(b"changed input")
    with pytest.raises(click.ClickException, match="differ"):
        fsl.verify_analysis_provenance(tmp_path, fsl.analysis_provenance(rows, runmode="flame1"))


def test_manifest_merge_preserves_other_analyses_and_replaces_contrasts(fsl, tmp_path):
    path = tmp_path / "manifest.tsv"
    fsl.merge_analysis_manifest(path, pd.DataFrame([
        {"analysis": "a", "contrast": "old"}, {"analysis": "b", "contrast": "keep"},
    ]), ["analysis"])
    fsl.merge_analysis_manifest(path, pd.DataFrame([{"analysis": "a", "contrast": "new"}]), ["analysis"])
    assert pd.read_csv(path, sep="\t").to_dict("records") == [
        {"analysis": "b", "contrast": "keep"}, {"analysis": "a", "contrast": "new"},
    ]


def test_concurrent_manifest_updates(fsl, tmp_path):
    path = tmp_path / "manifest.tsv"

    def write_one(index):
        fsl.merge_analysis_manifest(path, pd.DataFrame([{"analysis": str(index)}]), ["analysis"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write_one, range(12)))
    assert len(pd.read_csv(path, sep="\t")) == 12


def test_multiple_confound_sources(fsl, tmp_path):
    primary = tmp_path / "confounds.tsv"
    additional = tmp_path / "physio.tsv"
    pd.DataFrame({"motion": [0, 1, 2], "ignored": [1, 2, 3]}).to_csv(primary, sep="\t", index=False)
    pd.DataFrame({
        "motion": [2, 1, 0], "cardiac": [1, np.nan, 2],
        "constant": [1, 1, 1], "text": ["a", "b", "c"],
    }).to_csv(additional, sep="\t", index=False)
    sources = [
        {"file": str(primary), "regexes": ["motion"], "prefix": ""},
        {"file": str(additional), "regexes": None, "prefix": "additional_1_"},
    ]
    names, regressors, provenance = fsl.load_confound_sources(
        sources, expected_rows=3, require_all_regexes=True,
    )
    assert names == ["motion", "additional_1_motion", "additional_1_cardiac"]
    assert regressors == [[0, 1, 2], [2, 1, 0], [1, 0, 2]]
    assert provenance[1]["columns"] == ["motion", "cardiac"]
    assert provenance[1]["file"] == str(additional)
    with pytest.raises(click.ClickException, match="specified more than once"):
        fsl.load_confound_sources(sources + [sources[0]], expected_rows=3, require_all_regexes=True)
    sources[1]["prefix"] = ""
    with pytest.raises(click.ClickException, match="Duplicate confound"):
        fsl.load_confound_sources(sources, expected_rows=3, require_all_regexes=True)
    with pytest.raises(click.ClickException, match="rows but the BOLD image"):
        fsl.load_confound_sources(sources[:1], expected_rows=4, require_all_regexes=True)


def test_additional_confound_path_templates(fsl, tmp_path):
    filename = tmp_path / "sub-01_run-02_physio.tsv"
    filename.touch()
    pattern = str(tmp_path / "sub-{subject}_run-{run}_physio.tsv")
    assert fsl.resolve_additional_confound_file(pattern, {"subject": "01", "run": "02"}) == str(filename)
    with pytest.raises(click.ClickException, match="Cannot resolve"):
        fsl.resolve_additional_confound_file(pattern, {"subject": "01"})
    with pytest.raises(click.ClickException, match="does not exist"):
        fsl.resolve_additional_confound_file(pattern, {"subject": "01", "run": "03"})


def test_censor_regressors_use_union_and_strict_thresholds(fsl, tmp_path):
    path = tmp_path / "confounds.tsv"
    pd.DataFrame({
        "framewise_displacement": [np.nan, 0.9, 1.0, 0.1, 0.2],
        "std_dvars": [np.nan, 1, 2, 2, 1],
    }).to_csv(path, sep="\t", index=False)
    names, regressors, provenance = fsl.make_censor_regressors(
        str(path), columns=["framewise_displacement", "std_dvars"],
        thresholds=[0.9, 1.5], expected_rows=5,
    )
    assert names == ["censor_volume_0002", "censor_volume_0003"]
    assert regressors == [[0, 0, 1, 0, 0], [0, 0, 0, 1, 0]]
    assert provenance["volumes"] == [2, 3]
    assert provenance["criteria"][0]["comparison"] == ">"
    names, regressors, provenance = fsl.make_censor_regressors(
        str(path), columns=["framewise_displacement"], thresholds=[2], expected_rows=5,
    )
    assert names == [] and regressors == [] and provenance["volumes"] == []


def test_feat_run_lock_excludes_other_writers_and_releases(fsl, tmp_path):
    lock = fsl.acquire_feat_run_lock(tmp_path, "run-1")
    assert lock is not None
    try:
        assert fsl.acquire_feat_run_lock(tmp_path, "run-1") is None
        other = fsl.acquire_feat_run_lock(tmp_path, "run-2")
        assert other is not None
        other.close()
    finally:
        lock.close()
    next_lock = fsl.acquire_feat_run_lock(tmp_path, "run-1")
    assert next_lock is not None
    next_lock.close()


def test_feat_completion_waits_for_report_even_when_statistics_exist(fsl, tmp_path, monkeypatch, capsys):
    for stem in ("cope", "varcope", "tstat", "zstat"):
        write_image(tmp_path / "stats" / f"{stem}1.nii.gz")
    report = tmp_path / "report.html"
    report.write_text("STILL RUNNING")
    clock = [0.0]
    waits = []

    def sleep(seconds):
        clock[0] += seconds
        waits.append(seconds)
        if len(waits) == 2:
            report.write_text("<b>Finished</b> at 2026-10-22 12:00:00")

    monkeypatch.setattr(fsl.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fsl.time, "sleep", sleep)
    fsl.wait_for_feat_completion(tmp_path, 1, timeout=180, poll_interval=60)
    assert waits == [60, 60]
    assert capsys.readouterr().out.count("Waiting for FEAT completion:") == 1


def test_logged_commands_stream_output_and_report_return(fsl, tmp_path, capfd):
    fsl.run_logged_command([
        sys.executable, "-c",
        "import sys; print('child stdout', flush=True); print('child stderr', file=sys.stderr, flush=True)",
    ], tmp_path)
    captured = capfd.readouterr()
    assert "Working directory: " + str(tmp_path) in captured.out
    assert captured.out.index("Running:") < captured.out.index("child stdout")
    assert captured.out.index("child stdout") < captured.out.index("Command returned successfully")
    assert "child stderr" in captured.err


def test_logged_command_failure_is_reported_and_propagated(fsl, tmp_path, capfd):
    with pytest.raises(subprocess.CalledProcessError) as error:
        fsl.run_logged_command([sys.executable, "-c", "raise SystemExit(7)"], tmp_path)
    assert error.value.returncode == 7
    captured = capfd.readouterr()
    assert "Running:" in captured.out
    assert "Command failed after" in captured.err
    assert "Command returned successfully" not in captured.out


def test_feat_completion_allows_outputs_to_appear_after_launch(fsl, tmp_path, monkeypatch):
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds
        for stem in ("cope", "varcope", "tstat", "zstat"):
            write_image(tmp_path / "stats" / f"{stem}1.nii.gz")
        (tmp_path / "report.html").write_text("Finished at 2026-10-22")

    monkeypatch.setattr(fsl.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fsl.time, "sleep", sleep)
    fsl.wait_for_feat_completion(tmp_path, 1, timeout=10, poll_interval=1)
    assert clock[0] == 1


def test_feat_completion_missing_statistics_and_timeout(fsl, tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(fsl.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fsl.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    with pytest.raises(click.ClickException, match="Timed out waiting"):
        fsl.wait_for_feat_completion(tmp_path, 1, timeout=3, poll_interval=1)
    (tmp_path / "report.html").write_text("Finished at 2026-10-22")
    with pytest.raises(click.ClickException, match="outputs are incomplete"):
        fsl.wait_for_feat_completion(tmp_path, 1, timeout=120, poll_interval=15)


def test_wrapper_submissions_preserve_previous_scripts_and_job_lists(tmp_path):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    logs = project / "code" / "logs"
    logs.mkdir(parents=True)
    old_runner = logs / "spinoza_feat_L1_runner.sh"
    old_runner.write_text("existing runner")
    old_queue = logs / "spinoza_feat_L1_jobs.txt"
    old_queue.write_text("existing queue")
    for subject in ("01", "02"):
        filename = (
            project / "derivatives" / "fmriprep" / f"sub-{subject}" / "func"
            / f"sub-{subject}_task-test_run-01_space-T1w_desc-preproc_bold.nii.gz"
        )
        filename.parent.mkdir(parents=True)
        filename.touch()
    helper_dir = tmp_path / "helpers"
    helper_dir.mkdir()
    helper = helper_dir / "call_bashhelper"
    helper.write_text("start_timer() { :; }\nend_timer() { :; }\n")
    helper.chmod(0o755)
    env = os.environ.copy()
    env.pop("SETUP_FILE", None)
    env["PATH"] = str(helper_dir) + os.pathsep + env["PATH"]
    command = ["bash", str(root / "shell" / "spinoza_feat"), "--dry-run", "-l", "1"]
    result = subprocess.run(command + ["-s", "01", str(project), "--", "--task", "test"],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    first = next(logs.glob("spinoza_feat_L1_submission.*"))
    runner = first / "spinoza_feat_L1_runner.sh"
    queue = first / "spinoza_feat_L1_jobs.txt"
    runner_bytes = runner.read_bytes()
    assert queue.read_text() == "01\t01\n"
    assert str(queue) in runner.read_text()
    result = subprocess.run(command + ["-s", "02", str(project), "--", "--task", "test"],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    submissions = list(logs.glob("spinoza_feat_L1_submission.*"))
    assert len(submissions) == 2
    second = next(path for path in submissions if path != first)
    assert (second / "spinoza_feat_L1_jobs.txt").read_text() == "02\t01\n"
    assert runner.read_bytes() == runner_bytes
    assert queue.read_text() == "01\t01\n"
    assert old_runner.read_text() == "existing runner"
    assert old_queue.read_text() == "existing queue"


@pytest.mark.parametrize("run_filter, expected_count, offset", [(None, 8, 1), ("2", 2, 0)])
def test_run_based_wrapper_discovers_and_dispatches_exact_runs(tmp_path, run_filter, expected_count, offset):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    for subject in ("01", "02"):
        directory = project / "derivatives" / "fmriprep" / f"sub-{subject}" / "func"
        directory.mkdir(parents=True)
        for run in ("01", "02", "03", "04"):
            for desc in ("preproc", "pybest"):
                (directory / f"sub-{subject}_task-test_run-{run}_space-T1w_desc-{desc}_bold.nii.gz").touch()
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    scripts = {
        "call_bashhelper": "start_timer() { :; }\nend_timer() { :; }\n",
        "scontrol": "#!/bin/sh\necho 'MaxArraySize = 100'\n",
        "sacctmgr": "#!/bin/sh\necho '50|'\n",
        "call_feat": (
            "#!/usr/bin/env python3\nimport json, os, sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['FEAT_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
        ),
    }
    for name, contents in scripts.items():
        path = helpers / name
        path.write_text(contents)
        path.chmod(0o755)
    env = os.environ.copy()
    env.pop("SETUP_FILE", None)
    env["PATH"] = str(helpers) + os.pathsep + env["PATH"]
    env["FEAT_CAPTURE"] = str(tmp_path / "captured.json")
    env["USER"] = "feat-test-user"
    command = [
        "bash", str(root / "shell" / "spinoza_feat"), "--dry-run", "-l", "1", "-m", "3",
        "-s", "01,02", str(project), "--", "--task", "test", "--space", "T1w", "--desc", "preproc",
    ]
    if run_filter:
        command += ["--run", run_filter]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    submission = next((project / "code" / "logs").glob("spinoza_feat_L1_submission.*"))
    queue = (submission / "spinoza_feat_L1_jobs.txt").read_text().splitlines()
    assert len(queue) == expected_count
    assert queue[offset] == "01\t02"
    env["SLURM_ARRAY_TASK_ID"] = "1"
    env["FEAT_BATCH_OFFSET"] = str(offset)
    result = subprocess.run(["bash", str(submission / "spinoza_feat_L1_runner.sh")],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    arguments = json.loads((tmp_path / "captured.json").read_text())
    assert arguments[arguments.index("--subject") + 1] == "01"
    assert arguments[arguments.index("--run") + 1] == "02"
    assert arguments.count("--run") == 1
    assert "--desc" in arguments and "preproc" in arguments


@pytest.mark.parametrize("columns, thresholds", [
    (["fd"], []), ([], [0.9]), (["fd", "fd"], [0.9, 1]),
    (["fd"], [np.inf]), (["fd"], [np.nan]), (["fd"], [-1]),
])
def test_censor_options_reject_invalid_specifications(fsl, columns, thresholds):
    with pytest.raises(click.UsageError):
        fsl.validate_censor_options(columns, thresholds)


@pytest.mark.parametrize("values, message", [
    ([0.1, np.nan, 0.2], "non-finite"),
    ([0.1, np.inf, 0.2], "non-finite"),
    ([np.inf, 0.1, 0.2], "non-finite"),
    ([1, 2, 3], "every BOLD volume"),
])
def test_censor_regressors_reject_invalid_data(fsl, tmp_path, values, message):
    path = tmp_path / "confounds.tsv"
    pd.DataFrame({"fd": values}).to_csv(path, sep="\t", index=False)
    with pytest.raises(click.ClickException, match=message):
        fsl.make_censor_regressors(str(path), columns=["fd"], thresholds=[0.9], expected_rows=3)
    with pytest.raises(click.ClickException, match="missing from"):
        fsl.make_censor_regressors(str(path), columns=["unknown"], thresholds=[0.9], expected_rows=3)
    with pytest.raises(click.ClickException, match="rows but the BOLD image"):
        fsl.make_censor_regressors(str(path), columns=["fd"], thresholds=[0.9], expected_rows=4)


def test_level2_reuse_requires_matching_runs(fsl, tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    command = runpy.run_path(str(root / "bin" / "call_feat2"))["main"]
    namespace = command.callback.__globals__
    rows = []
    for run in (1, 2, 3):
        directory = tmp_path / f"run-{run}.feat"
        cope = write_image(directory / "stats" / "cope1.nii.gz")
        varcope = write_image(directory / "stats" / "varcope1.nii.gz")
        rows.append({
            "subject": "1", "session": "", "task": "test", "run": str(run),
            "run_label": f"run-{run}", "cope": "1", "contrast_name": "A",
            "canonical_name": "A", "cope_file": str(cope), "varcope_file": str(varcope),
            "feat_dir": str(directory),
            "space": "MNI", "resolution": "2", "desc": "preproc",
        })
    manifest = tmp_path / "inputs.tsv"
    pd.DataFrame(rows).to_csv(manifest, sep="\t", index=False)

    def run_fixed(rows, output, canonical, overwrite, dry_run):
        stats = output / "stats"
        stats.mkdir(parents=True)
        result = {"number_of_inputs": len(rows), "second_level_dir": str(output)}
        for stem in ("cope", "varcope", "tstat", "zstat"):
            path = write_image(stats / f"{stem}1.nii.gz")
            result[f"{stem}_file"] = str(path)
        return result

    monkeypatch.setitem(namespace, "run_fixed_effects_group", run_fixed)
    monkeypatch.setitem(namespace, "_maybe_write_gfeat_report_index", lambda *args: None)
    args = ["--manifest", str(manifest), "--output-dir", str(tmp_path / "level2")]
    runner = CliRunner()
    result = runner.invoke(command, args)
    assert result.exit_code == 0, result.output
    table = pd.read_csv(tmp_path / "level2" / "contrast_manifest_level2.tsv", sep="\t", dtype=str)
    assert table.iloc[0]["space"] == "MNI"
    assert "_space-MNI_res-2_desc-preproc_fixedfx.gfeat" in table.iloc[0]["second_level_dir"]
    result = runner.invoke(command, args)
    assert result.exit_code == 0 and "1 reused" in result.output, result.output
    result = runner.invoke(command, args + ["--run", "1,2"])
    assert result.exit_code == 1 and "inputs or model settings differ" in result.output


def test_level3_reuse_requires_matching_model(fsl, tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    command = runpy.run_path(str(root / "bin" / "call_feat3"))["main"]
    namespace = command.callback.__globals__
    rows = []
    for subject in (1, 2, 3):
        directory = tmp_path / f"sub-{subject}.feat"
        cope = write_image(directory / "stats" / "cope1.nii.gz")
        varcope = write_image(directory / "stats" / "varcope1.nii.gz")
        rows.append({
            "subject": str(subject), "session": "", "task": "test", "canonical_name": "A",
            "number_of_inputs": 2, "second_level_dir": str(directory),
            "cope_file": str(cope), "varcope_file": str(varcope),
            "space": "MNI", "resolution": "2", "desc": "preproc",
        })
    manifest = tmp_path / "inputs.tsv"
    pd.DataFrame(rows).to_csv(manifest, sep="\t", index=False)

    def run_group(**kwargs):
        output = kwargs["output_dir"]
        record = {
            "session": "", "task": "test", "canonical_name": "A",
            "group_dir": str(output), "group_contrast": "GroupMean",
        }
        for stem in ("cope", "varcope", "tstat", "zstat"):
            record[f"{stem}_file"] = str(write_image(output / "stats" / f"{stem}1.nii.gz"))
        return [record]

    monkeypatch.setitem(namespace, "run_cross_subject_analysis", run_group)
    args = ["--manifest", str(manifest), "--output-dir", str(tmp_path / "level3"), "--no-report"]
    runner = CliRunner()
    result = runner.invoke(command, args)
    assert result.exit_code == 0, result.output
    table = pd.read_csv(tmp_path / "level3" / "contrast_manifest_level3.tsv", sep="\t", dtype=str)
    assert table.iloc[0]["space"] == "MNI"
    assert "_space-MNI_res-2_desc-preproc_group.gfeat" in table.iloc[0]["group_dir"]
    result = runner.invoke(command, args)
    assert result.exit_code == 0 and "1 reused" in result.output, result.output
    result = runner.invoke(command, args + ["--group-contrast", "Renamed;1"])
    assert result.exit_code == 1 and "inputs or model settings differ" in result.output


def test_analysis_entity_filters_preserve_unknown_streams(fsl):
    table = pd.DataFrame([
        {"desc": "preproc", "space": "MNI", "res": "2"},
        {"desc": "pybest", "space": "MNI", "res": "2"},
        {"desc": "preproc", "space": "T1w", "res": "1"},
        {},
    ])
    selected = fsl.filter_analysis_entities(table, desc=["preproc,pybest"], space=["MNI"])
    assert selected["desc"].tolist() == ["preproc", "pybest"]
    assert selected["resolution"].tolist() == ["2", "2"]
    normalized = fsl.filter_analysis_entities(table)
    assert normalized.iloc[-1]["desc"] == ""
    assert normalized.iloc[-1]["space"] == ""


def test_separate_desc_and_space_streams_across_levels(fsl, tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    level2 = runpy.run_path(str(root / "bin" / "call_feat2"))["main"]
    level3 = runpy.run_path(str(root / "bin" / "call_feat3"))["main"]
    rows = []
    for subject in (1, 2, 3):
        for desc in ("preproc", "pybest"):
            for space in ("MNI", "T1w"):
                for run in (1, 2):
                    label = f"sub-{subject}_run-{run}_space-{space}_desc-{desc}"
                    directory = tmp_path / "level1" / f"{label}.feat"
                    cope = write_image(directory / "stats" / "cope1.nii.gz")
                    varcope = write_image(directory / "stats" / "varcope1.nii.gz")
                    rows.append({
                        "subject": str(subject), "session": "", "task": "test",
                        "run": str(run), "run_label": label, "cope": "1",
                        "contrast_name": "A", "canonical_name": "A",
                        "cope_file": str(cope), "varcope_file": str(varcope),
                        "feat_dir": str(directory), "desc": desc, "space": space,
                    })
    manifest = tmp_path / "level1.tsv"
    pd.DataFrame(rows).to_csv(manifest, sep="\t", index=False)
    fixed_inputs = []
    group_inputs = []

    def outputs(output):
        return {
            f"{stem}_file": str(write_image(output / "stats" / f"{stem}1.nii.gz"))
            for stem in ("cope", "varcope", "tstat", "zstat")
        }

    def fixed(rows, output, canonical, overwrite, dry_run):
        fixed_inputs.append(rows)
        assert len(rows) == 2
        assert rows["desc"].nunique() == rows["space"].nunique() == 1
        return {"number_of_inputs": len(rows), "second_level_dir": str(output), **outputs(output)}

    def group(**kwargs):
        rows = kwargs["rows"]
        group_inputs.append(rows)
        assert len(rows) == rows["subject"].nunique() == 3
        assert rows["desc"].nunique() == rows["space"].nunique() == 1
        return [{
            "session": "", "task": "test", "canonical_name": "A",
            "group_dir": str(kwargs["output_dir"]), "group_contrast": "GroupMean",
            **outputs(kwargs["output_dir"]),
        }]

    monkeypatch.setitem(level2.callback.__globals__, "run_fixed_effects_group", fixed)
    monkeypatch.setitem(level2.callback.__globals__, "_maybe_write_gfeat_report_index", lambda *args: None)
    monkeypatch.setitem(level3.callback.__globals__, "run_cross_subject_analysis", group)
    runner = CliRunner()
    args2 = ["--manifest", str(manifest), "--output-dir", str(tmp_path / "level2")]
    result = runner.invoke(level2, args2)
    assert result.exit_code == 0, result.output
    assert len(fixed_inputs) == 12
    manifest2 = tmp_path / "level2" / "contrast_manifest_level2.tsv"
    table2 = pd.read_csv(manifest2, sep="\t", dtype=str)
    assert len(table2) == table2["second_level_dir"].nunique() == 12
    result = runner.invoke(level2, args2)
    assert result.exit_code == 0 and "12 reused" in result.output, result.output
    result = runner.invoke(level2, args2 + ["--desc", "preproc", "--space", "MNI"])
    assert result.exit_code == 0 and "3 reused" in result.output, result.output
    assert len(pd.read_csv(manifest2, sep="\t")) == 12

    args3 = ["--manifest", str(manifest2), "--output-dir", str(tmp_path / "level3"), "--no-report"]
    result = runner.invoke(level3, args3)
    assert result.exit_code == 0, result.output
    assert len(group_inputs) == 4
    manifest3 = tmp_path / "level3" / "contrast_manifest_level3.tsv"
    table3 = pd.read_csv(manifest3, sep="\t", dtype=str)
    assert len(table3) == table3["group_dir"].nunique() == 4
    assert set(zip(table3["desc"], table3["space"])) == {
        ("preproc", "MNI"), ("preproc", "T1w"), ("pybest", "MNI"), ("pybest", "T1w"),
    }
    result = runner.invoke(level3, args3 + ["--desc", "pybest", "--space", "MNI"])
    assert result.exit_code == 0 and "1 reused" in result.output, result.output
    assert len(pd.read_csv(manifest3, sep="\t")) == 4
    result = runner.invoke(level3, args3 + [
        "--desc", "preproc", "--desc", "pybest", "--space", "MNI,T1w",
    ])
    assert result.exit_code == 0 and "4 reused" in result.output, result.output


@pytest.fixture
def firstlevel(fsl, tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    script = runpy.run_path(str(root / "bin" / "call_feat"))
    command = script["run_firstlevel"]
    namespace = command.callback.__globals__
    bolds = [write_image(tmp_path / f"run-{run}_bold.nii.gz", volumes=60) for run in (1, 2)]
    events = tmp_path / "events.tsv"
    pd.DataFrame({"onset": [0, 20], "duration": [1, 1], "trial_type": ["A", "A"]}).to_csv(events, sep="\t", index=False)

    class Layout:
        def get(self, **query):
            return list(map(str, bolds)) if query["suffix"] == "bold" else [str(events)]

        def parse_file_entities(self, filename):
            return {"subject": "1", "task": "test", "run": Path(filename).name[4]}

        def get_metadata(self, filename):
            return {"RepetitionTime": 2}

    monkeypatch.setitem(namespace, "BIDSLayout", lambda *args, **kwargs: Layout())
    monkeypatch.setitem(namespace, "check_executable", lambda name: None)
    output = tmp_path / "derivatives"
    args = ["--bids-dir", str(tmp_path), "--deriv-dir", str(output), "--task", "test", "--no-confounds"]
    return command, args, output, namespace


def test_firstlevel_dry_run_preserves_existing_output(firstlevel):
    command, args, output, _ = firstlevel
    sentinel = output / "sub-1_task-test_run-1.feat" / "keep"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("original")
    result = CliRunner().invoke(command, args + ["--dry-run", "--overwrite"])
    assert result.exit_code == 0, result.output
    assert sentinel.read_text() == "original"
    assert not (output / "contrast_manifest.tsv").exists()


def test_firstlevel_skips_existing_outputs_before_model_preparation(firstlevel):
    command, args, output, _ = firstlevel
    directory = output / "sub-1_task-test_run-1.feat"
    directory.mkdir(parents=True)
    sentinel = directory / "keep"
    sentinel.write_text("original")
    result = CliRunner().invoke(command, args + ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Output exists; skipping" in result.output
    assert sentinel.read_text() == "original"
    assert not (output / "work" / "sub-1_task-test_run-1").exists()


def test_firstlevel_all_existing_outputs_are_a_successful_noop(firstlevel):
    command, args, output, _ = firstlevel
    for run in (1, 2):
        (output / f"sub-1_task-test_run-{run}.feat").mkdir(parents=True)
    result = CliRunner().invoke(command, args + ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert "2 run(s) skipped; 0 failed" in result.output
    assert not (output / "work").exists()


def test_firstlevel_skips_locked_runs_even_with_overwrite(firstlevel, fsl):
    command, args, output, _ = firstlevel
    lock = fsl.acquire_feat_run_lock(output, "sub-1_task-test_run-1")
    assert lock is not None
    try:
        result = CliRunner().invoke(command, args + ["--dry-run", "--overwrite"])
        assert result.exit_code == 0, result.output
        assert "Another job owns this run" in result.output
        assert not (output / "work" / "sub-1_task-test_run-1").exists()
    finally:
        lock.close()


@pytest.mark.parametrize("mode", ["literal", "template", "suffix"])
@pytest.mark.parametrize("primary_enabled", [True, False])
def test_firstlevel_enigma_and_additional_physio(firstlevel, tmp_path, monkeypatch, mode, primary_enabled):
    command, args, output, namespace = firstlevel
    if primary_enabled:
        args = [arg for arg in args if arg != "--no-confounds"]
    layout = namespace["BIDSLayout"]()
    original_get = layout.get
    primary = tmp_path / "confounds.tsv"
    columns = [
        f"{parameter}{suffix}"
        for parameter in ("trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z")
        for suffix in ("", "_derivative1", "_power2", "_derivative1_power2")
    ] + [f"a_comp_cor_0{i}" for i in range(5)]
    pd.DataFrame({name: np.arange(60) for name in columns}).to_csv(primary, sep="\t", index=False)
    for run in (1, 2):
        pd.DataFrame({"trans_x": np.arange(60), "cardiac": np.arange(60)[::-1]}).to_csv(
            tmp_path / f"run-{run}_physio.tsv", sep="\t", index=False,
        )

    def get(**query):
        if query["suffix"] == "timeseries":
            return [str(primary)]
        if query["suffix"] == "physio":
            return [str(tmp_path / f"run-{query['run']}_physio.tsv")]
        return original_get(**query)

    layout.get = get
    monkeypatch.setitem(namespace, "BIDSLayout", lambda *args, **kwargs: layout)
    original_model = namespace["SpecifyModel"]
    captured = []

    def model(**kwargs):
        captured.append(kwargs["subject_info"][0])
        return original_model(**kwargs)

    monkeypatch.setitem(namespace, "SpecifyModel", model)
    if mode == "suffix":
        extra = ["--additional-confounds-suffix", "physio"]
    else:
        filename = "run-1_physio.tsv" if mode == "literal" else "run-{run}_physio.tsv"
        extra = ["--additional-confounds", str(tmp_path / filename)]
    result = CliRunner().invoke(command, args + ["--dry-run", "--confound-subtype", "ENIGMA"] + extra)
    assert result.exit_code == 0, result.output
    assert len(captured) == 2
    for info in captured:
        assert len(info.regressor_names) == (31 if primary_enabled else 2)
        assert len(set(info.regressor_names)) == len(info.regressor_names)
        assert info.regressor_names[-2:] == ["additional_1_trans_x", "additional_1_cardiac"]
        assert len(info.regressors[-1]) == 60
    assert not list((output / "work").glob("*/confounds.json"))


def test_firstlevel_censoring_with_sensor_aliases_and_physio(firstlevel, tmp_path, monkeypatch):
    command, args, output, namespace = firstlevel
    args = [arg for arg in args if arg != "--no-confounds"]
    path = tmp_path / "confounds.tsv"
    columns = {
        name: np.arange(60, dtype=float)
        for name in ("trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z")
    }
    columns["framewise_displacement"] = np.zeros(60)
    columns["framewise_displacement"][[0, 3, 4]] = [np.nan, 1, 0.9]
    columns["std_dvars"] = np.zeros(60)
    columns["std_dvars"][[0, 3, 5]] = [np.nan, 2, 2]
    pd.DataFrame(columns).to_csv(path, sep="\t", index=False)
    physio = tmp_path / "physio.tsv"
    pd.DataFrame({"cardiac": np.arange(60)}).to_csv(physio, sep="\t", index=False)
    layout = namespace["BIDSLayout"]()
    original_get = layout.get
    layout.get = lambda **query: [str(path)] if query["suffix"] == "timeseries" else original_get(**query)
    monkeypatch.setitem(namespace, "BIDSLayout", lambda *args, **kwargs: layout)
    original_model = namespace["SpecifyModel"]
    captured = []

    def model(**kwargs):
        captured.append(kwargs["subject_info"][0])
        return original_model(**kwargs)

    monkeypatch.setitem(namespace, "SpecifyModel", model)
    result = CliRunner().invoke(command, args + [
        "--dry-run", "--confound-subtype", "Motion parameters",
        "--additional-confounds", str(physio),
        "--sensor-column", "framewise_displacement", "--sensor-threshold", "0.9",
        "--censor-column", "std_dvars", "--censor-threshold", "1.5",
    ])
    assert result.exit_code == 0, result.output
    assert len(captured) == 2
    for info in captured:
        assert len(info.regressor_names) == 9
        assert info.regressor_names[-2:] == ["censor_volume_0003", "censor_volume_0005"]
        assert np.flatnonzero(info.regressors[-2]).tolist() == [3]
        assert np.flatnonzero(info.regressors[-1]).tolist() == [5]
        assert "framewise_displacement" not in info.regressor_names


@pytest.mark.parametrize("options", [
    ["--sensor-column", "framewise_displacement"],
    ["--censor-threshold", "0.9"],
    ["--sensor-column", "framewise_displacement", "--sensor-threshold", "0.9"],
])
def test_firstlevel_invalid_censor_options_fail_before_processing(firstlevel, options):
    command, args, output, _ = firstlevel
    # The fixture disables the primary confounds; the complete pair is invalid
    # for that reason, while the other cases have unmatched option counts.
    result = CliRunner().invoke(command, args + ["--dry-run"] + options)
    assert result.exit_code == 2, result.output
    assert not output.exists()


def test_firstlevel_rejects_output_label_collisions(firstlevel, monkeypatch):
    command, args, output, namespace = firstlevel
    layout = namespace["BIDSLayout"]()
    layout.parse_file_entities = lambda filename: {"subject": "1", "task": "test", "run": "1"}
    monkeypatch.setitem(namespace, "BIDSLayout", lambda *args, **kwargs: layout)
    result = CliRunner().invoke(command, args + ["--dry-run"])
    assert result.exit_code == 1 and "same output label" in result.output
    assert not (output / "work").exists()


def test_firstlevel_separates_spaces_for_the_same_run(firstlevel, monkeypatch):
    command, args, output, namespace = firstlevel
    layout = namespace["BIDSLayout"]()
    layout.parse_file_entities = lambda filename: {
        "subject": "1", "task": "test", "run": "1",
        "space": "T1w" if "run-1" in filename else "MNI",
        "resolution": "2", "desc": "preproc",
    }
    monkeypatch.setitem(namespace, "BIDSLayout", lambda *args, **kwargs: layout)
    result = CliRunner().invoke(command, args + ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in (output / "work").iterdir()) == [
        "sub-1_task-test_run-1_space-MNI_res-2_desc-preproc",
        "sub-1_task-test_run-1_space-T1w_res-2_desc-preproc",
    ]


def test_firstlevel_partial_failure_has_nonzero_exit_and_no_failed_manifest(firstlevel, monkeypatch):
    command, args, output, namespace = firstlevel

    def run_feat(command, **kwargs):
        if command[0] == "feat_model":
            root = Path(command[1])
            root.with_suffix(".mat").write_text("/Matrix\n1\n2\n3\n")
            root.with_suffix(".con").write_text("/Matrix\n1\n")
            return
        if "run-2" in command[1]:
            raise subprocess.CalledProcessError(1, command)
        stats = output / "sub-1_task-test_run-1.feat" / "stats"
        stats.mkdir(parents=True)
        for stem in ("cope", "varcope", "tstat", "zstat"):
            (stats / f"{stem}1.nii.gz").touch()
        (stats.parent / "report.html").write_text("Finished at 2026-10-22 12:00:00")

    monkeypatch.setattr(namespace["subprocess"], "run", run_feat)
    result = CliRunner().invoke(command, args)
    assert result.exit_code == 1, result.output
    assert "1 failed" in result.output
    table = pd.read_csv(output / "contrast_manifest.tsv", sep="\t")
    assert table["run"].tolist() == [1]


def test_firstlevel_holds_lock_and_defers_manifest_for_async_feat(firstlevel, fsl, monkeypatch):
    command, args, output, namespace = firstlevel
    active = []
    clock = [0.0]
    waits = []

    def launch(command, **kwargs):
        if command[0] == "feat_model":
            root = Path(command[1])
            root.with_suffix(".mat").write_text("/Matrix\n1\n2\n3\n")
            root.with_suffix(".con").write_text("/Matrix\n1\n")
            return
        run = "1" if "run-1" in command[1] else "2"
        label = f"sub-1_task-test_run-{run}"
        directory = output / f"{label}.feat"
        directory.mkdir(parents=True)
        (directory / "report.html").write_text("STILL RUNNING")
        active[:] = [label, directory, run]

    def sleep(seconds):
        clock[0] += seconds
        label, directory, run = active
        assert fsl.acquire_feat_run_lock(output, label) is None
        assert (output / "work" / label / "feat_pending.json").is_file()
        manifest = output / "contrast_manifest.tsv"
        if manifest.exists():
            assert int(run) not in pd.read_csv(manifest, sep="\t")["run"].tolist()
        for stem in ("cope", "varcope", "tstat", "zstat"):
            write_image(directory / "stats" / f"{stem}1.nii.gz")
        (directory / "report.html").write_text("Finished at 2026-10-22")
        waits.append(run)

    monkeypatch.setattr(namespace["subprocess"], "run", launch)
    monkeypatch.setattr(fsl.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fsl.time, "sleep", sleep)
    result = CliRunner().invoke(command, args + ["--feat-poll-interval", "1"])
    assert result.exit_code == 0, result.output
    assert waits == ["1", "2"]
    assert not list((output / "work").glob("*/feat_pending.json"))
    assert len(pd.read_csv(output / "contrast_manifest.tsv", sep="\t")) == 2


def test_firstlevel_timeout_preserves_pending_state_and_blocks_overwrite(firstlevel, fsl, monkeypatch):
    command, args, output, namespace = firstlevel
    clock = [0.0]

    def launch(command, **kwargs):
        if command[0] == "feat_model":
            root = Path(command[1])
            root.with_suffix(".mat").write_text("/Matrix\n1\n2\n3\n")
            root.with_suffix(".con").write_text("/Matrix\n1\n")

    monkeypatch.setattr(namespace["subprocess"], "run", launch)
    monkeypatch.setattr(fsl.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fsl.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    result = CliRunner().invoke(command, args + ["--feat-wait-timeout", "2", "--feat-poll-interval", "1"])
    assert result.exit_code == 1, result.output
    assert "Timed out waiting" in result.output
    assert len(list((output / "work").glob("*/feat_pending.json"))) == 2
    assert not (output / "contrast_manifest.tsv").exists()
    result = CliRunner().invoke(command, args + ["--overwrite"])
    assert result.exit_code == 1, result.output
    assert "unconfirmed completion" in result.output
