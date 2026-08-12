#!/usr/bin/env python3
"""
Run first-level FSL FEAT analyses on fMRIPrep BOLD derivatives.

Dependencies:
    pip install click pandas nibabel pybids nipype

System dependency:
    FSL must be installed and `feat` must be available on PATH.
"""

from __future__ import annotations

import fcntl
import html
import json
import shlex
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence

import click
import nibabel as nib
import numpy as np
import pandas as pd
from bids import BIDSLayout


CONFOUND_OPTIONS: dict[str, str] = {
    "ICA-AROMA": r"aroma_motion_[0-9]+",
    "Motion parameters": r"(trans|rot)_[xyz]",
    "Derivatives of motion parameters": r"(trans|rot)_[xyz]_derivative1",
    "Motion parameters squared": r"(trans|rot)_[xyz]_power2",
    "Derivatives of motion parameters squared": r"(trans|rot)_[xyz]_derivative1_power2",
    "Motion scrubbing": r"motion_outlier[0-9]+",
    "aCompCor (top five components)": r"a_comp_cor_0[0-4]",
    "White matter signal": r"white_matter",
    "CSF signal": r"csf",
    "Global signal": r"global_signal",
}


ENIGMA_CONFOUND_SUBTYPES = [
    "Motion parameters",
    "Derivatives of motion parameters",
    "Motion parameters squared",
    "Derivatives of motion parameters squared",
    "aCompCor (top five components)",
]


LEVEL1_HINT_COLUMNS = {"run", "run_label", "contrast_name", "feat_dir"}
LEVEL2_HINT_COLUMNS = {"number_of_inputs", "second_level_dir"}


COMMON_REQUIRED_COLUMNS = {
    "subject",
    "session",
    "task",
    "canonical_name",
    "cope_file",
    "varcope_file",
}



def next_contrast_update_dir(base_work_dir: Path) -> Path:
    """Return the next available contrast-update working directory."""
    prefix = "contrast_update_"

    indices = []

    for child in base_work_dir.iterdir():
        if not child.is_dir():
            continue

        if child.name.startswith(prefix):
            try:
                indices.append(int(child.name[len(prefix):]))
            except ValueError:
                pass

    next_index = max(indices, default=0) + 1

    return base_work_dir / f"{prefix}{next_index:03d}"


def normalize_subject(subject: str) -> str:
    """Remove an optional sub- prefix."""
    return subject[4:] if subject.startswith("sub-") else subject


def entity_label(entities: dict[str, Any]) -> str:
    """Create a readable BIDS entity label for messages."""
    parts = [f"sub-{entities['subject']}"]

    if entities.get("session") is not None:
        parts.append(f"ses-{entities['session']}")

    parts.append(f"task-{entities['task']}")

    if entities.get("acquisition") is not None:
        parts.append(f"acq-{entities['acquisition']}")

    if entities.get("direction") is not None:
        parts.append(f"dir-{entities['direction']}")

    if entities.get("echo") is not None:
        parts.append(f"echo-{entities['echo']}")

    if entities.get("run") is not None:
        parts.append(f"run-{entities['run']}")

    return "_".join(parts)


def query_shared_entities(
    entities: dict[str, Any],
    *,
    include_space: bool = False,
) -> dict[str, Any]:
    """Return entities useful for locating a sidecar belonging to one BOLD run."""
    keys = [
        "subject",
        "session",
        "task",
        "acquisition",
        "direction",
        "reconstruction",
        "run",
        "echo",
        "part",
    ]

    if include_space:
        keys.append("space")

    return {
        key: entities[key]
        for key in keys
        if entities.get(key) is not None
    }


def parse_inline_contrast(spec: str) -> dict[str, Any]:
    """Parse NAME;T;condition1,condition2;weight1,weight2[;canonical]."""
    fields = [field.strip() for field in spec.split(";")]
    if len(fields) not in {4, 5}:
        raise click.ClickException(
            "--contrast must use "
            "'Name;T;event1,event2;weight1,weight2' "
            "with an optional fifth canonical-name field."
        )

    name, statistic, condition_field, weight_field = fields[:4]
    canonical_name = fields[4] if len(fields) == 5 else name
    conditions = [item.strip() for item in condition_field.split(",") if item.strip()]
    weight_strings = [item.strip() for item in weight_field.split(",") if item.strip()]

    if not name or not conditions or not weight_strings:
        raise click.ClickException(f"Invalid --contrast specification: {spec!r}")
    if statistic.upper() != "T":
        raise click.ClickException(
            "Inline --contrast currently supports T contrasts only; "
            "use --contrasts-file for F contrasts."
        )
    if len(conditions) != len(weight_strings):
        raise click.ClickException(
            f"Contrast {name!r} has {len(conditions)} events but "
            f"{len(weight_strings)} weights."
        )
    try:
        weights = [float(value) for value in weight_strings]
    except ValueError as error:
        raise click.ClickException(
            f"Contrast {name!r} contains a non-numeric weight."
        ) from error

    return {
        "name": name,
        "type": "T",
        "conditions": conditions,
        "weights": weights,
        "canonical_name": canonical_name or name,
    }


def default_baseline_contrasts(
    conditions: Sequence[str],
) -> tuple[list[tuple[Any, ...]], dict[str, str]]:
    """Create one event-versus-implicit-baseline contrast per run EV."""
    contrasts = [(condition, "T", [condition], [1.0]) for condition in conditions]
    canonical_names = {condition: condition for condition in conditions}
    return contrasts, canonical_names


def load_contrasts(
    path: str | None,
    inline_specs: Sequence[str] = (),
) -> tuple[list[tuple[Any, ...]], dict[str, str]]:
    """
    Load contrasts and their canonical higher-level names.

    Accepted JSON forms are either:

        [name, type, conditions, weights]
        [name, type, conditions, weights, canonical_name]

    or an object with keys ``name``, ``type``, ``conditions``, ``weights``,
    and optional ``canonical_name``. The four-field form remains backward
    compatible and uses ``name`` as its canonical name.
    """
    if path is not None and inline_specs:
        raise click.ClickException(
            "Use either --contrasts-file or one or more --contrast options, not both."
        )

    if path is not None:
        with open(path, encoding="utf-8") as file:
            raw_contrasts: Sequence[Any] = json.load(file)
    else:
        raw_contrasts = [parse_inline_contrast(spec) for spec in inline_specs]

    contrasts: list[tuple[Any, ...]] = []
    canonical_names: dict[str, str] = {}

    for index, raw in enumerate(raw_contrasts, start=1):
        if isinstance(raw, dict):
            try:
                name = raw["name"]
                statistic = raw["type"]
                condition_names = raw["conditions"]
                weights = raw["weights"]
            except KeyError as error:
                raise click.ClickException(
                    f"Contrast {index} is missing key {error.args[0]!r}."
                ) from error
            canonical_name = raw.get("canonical_name", name)
        elif isinstance(raw, (list, tuple)) and len(raw) in {4, 5}:
            name, statistic, condition_names, weights = raw[:4]
            canonical_name = raw[4] if len(raw) == 5 else name
        else:
            raise click.ClickException(
                f"Contrast {index} must have four or five fields, or be an "
                "object with name/type/conditions/weights."
            )

        name = str(name)
        statistic = str(statistic).upper()
        canonical_name = str(canonical_name)

        if name in canonical_names:
            raise click.ClickException(f"Duplicate contrast name: {name!r}")

        if statistic not in {"T", "F"}:
            raise click.ClickException(
                f"Contrast {name!r} has unsupported type {statistic!r}."
            )

        if statistic == "T":
            if len(condition_names) != len(weights):
                raise click.ClickException(
                    f"Contrast {name!r} has different numbers of conditions "
                    "and weights."
                )
            contrast = (
                name,
                "T",
                [str(condition) for condition in condition_names],
                [float(weight) for weight in weights],
            )
        else:
            contrast = (
                name,
                "F",
                list(condition_names),
                list(weights),
            )

        contrasts.append(contrast)
        canonical_names[name] = canonical_name

    return contrasts, canonical_names


def validate_t_contrasts(
    contrasts: Sequence[tuple[Any, ...]],
    conditions: Sequence[str],
) -> set[str]:
    """Return condition names referenced by T contrasts but absent from a run."""
    available = set(conditions)
    missing: set[str] = set()

    for _name, statistic, contrast_conditions, _weights in contrasts:
        if statistic == "T":
            missing.update(set(contrast_conditions) - available)

    return missing


def resolve_confound_regexes(
    *,
    no_confounds: bool,
    confounds_suffix: str,
    confound_subtype: str,
    extra_regexes: Sequence[str] = (),
) -> list[str] | None:
    """Resolve named presets and arbitrary regexes for confound columns.

    For ``timeseries`` files, ``confound_subtype`` may be ``ENIGMA``, a
    comma-separated list of named presets, or raw regular expressions.
    Repeatable ``--confound-regex`` values are appended to that selection.

    ``None`` means no column subselection for physio/custom files, or no
    confound loading at all when ``--no-confounds`` is used.
    """
    if no_confounds:
        click.echo("Confounds: disabled.")
        return None

    if confounds_suffix == "timeseries":
        if confound_subtype == "ENIGMA":
            search_list = ENIGMA_CONFOUND_SUBTYPES
        else:
            search_list = [
                item.strip()
                for item in confound_subtype.split(",")
                if item.strip()
            ]

        if not search_list and not extra_regexes:
            raise click.ClickException(
                "No confound categories or regexes were specified."
            )

        regexes: list[str] = []
        for item in search_list:
            regex = CONFOUND_OPTIONS.get(item, item)
            try:
                re.compile(regex)
            except re.error as error:
                raise click.ClickException(
                    f"Invalid confound regex {regex!r}: {error}"
                ) from error
            regexes.append(regex)

        for regex in extra_regexes:
            regex = regex.strip()
            if not regex:
                continue
            try:
                re.compile(regex)
            except re.error as error:
                raise click.ClickException(
                    f"Invalid --confound-regex {regex!r}: {error}"
                ) from error
            regexes.append(regex)

        # Preserve order while removing duplicate expressions.
        regexes = list(dict.fromkeys(regexes))
        click.echo(
            f"Confounds: {confound_subtype!r}; regexes={regexes}"
        )
        return regexes

    if extra_regexes:
        raise click.ClickException(
            "--confound-regex is only supported with "
            "--confounds-suffix timeseries."
        )

    if confounds_suffix in {"physio", "custom"}:
        click.echo(
            f"Confounds: using every numeric column from "
            f"suffix-{confounds_suffix} files."
        )
        return None

    raise click.ClickException(
        "--confounds-suffix must be one of "
        "'timeseries', 'physio', or 'custom'."
    )


def build_level1_bases(
    *,
    basis_name: str,
    derivatives: bool,
    gamma_sigma: float | None,
    gamma_delay: float | None,
    custom_path: Path | None,
) -> dict[str, Any]:
    """Validate CLI basis options and build Level1Design.bases."""
    basis_name = basis_name.lower()

    if basis_name == "dgamma":
        if gamma_sigma is not None or gamma_delay is not None:
            raise click.ClickException(
                "--gamma-sigma and --gamma-delay require --basis gamma."
            )
        if custom_path is not None:
            raise click.ClickException(
                "--basis-custom-path requires --basis custom."
            )
        return {"dgamma": {"derivs": derivatives}}

    if basis_name == "gamma":
        if custom_path is not None:
            raise click.ClickException(
                "--basis-custom-path requires --basis custom."
            )

        options: dict[str, Any] = {"derivs": derivatives}
        if gamma_sigma is not None:
            options["gammasigma"] = gamma_sigma
        if gamma_delay is not None:
            options["gammadelay"] = gamma_delay
        return {"gamma": options}

    if basis_name == "custom":
        if custom_path is None:
            raise click.ClickException(
                "--basis custom requires --basis-custom-path."
            )
        if derivatives:
            raise click.ClickException(
                "Temporal derivatives are not supported with --basis custom."
            )
        if gamma_sigma is not None or gamma_delay is not None:
            raise click.ClickException(
                "--gamma-sigma and --gamma-delay require --basis gamma."
            )
        return {"custom": {"bfcustompath": str(custom_path.resolve())}}

    if basis_name == "none":
        if derivatives:
            raise click.ClickException(
                "Temporal derivatives are not supported with --basis none."
            )
        if gamma_sigma is not None or gamma_delay is not None:
            raise click.ClickException(
                "--gamma-sigma and --gamma-delay require --basis gamma."
            )
        if custom_path is not None:
            raise click.ClickException(
                "--basis-custom-path requires --basis custom."
            )
        return {"none": {}}

    raise click.ClickException(f"Unsupported basis function: {basis_name!r}")


def find_single_file(
    layout: BIDSLayout,
    *,
    description: str,
    required: bool = True,
    **query: Any,
) -> str | None:
    """Run a BIDS query that should identify one file."""
    matches = sorted(set(layout.get(return_type="file", **query)))

    if not matches:
        if required:
            raise click.ClickException(
                f"No {description} found for query: {query}"
            )
        return None

    if len(matches) > 1:
        formatted = "\n  ".join(matches)
        raise click.ClickException(
            f"Multiple {description} files matched query {query}:\n"
            f"  {formatted}"
        )

    return os.path.abspath(matches[0])


def select_columns_by_regex(
    dataframe: pd.DataFrame,
    regexes: Iterable[str],
) -> list[str]:
    """Select columns once, preserving dataframe column order."""
    compiled = [re.compile(regex) for regex in regexes]

    return [
        column
        for column in dataframe.columns
        if any(pattern.fullmatch(column) for pattern in compiled)
    ]


def filter_estimable_contrasts(
    contrasts: Sequence[tuple[Any, ...]],
    available_conditions: Sequence[str],
) -> tuple[list[tuple[Any, ...]], list[str]]:
    """
    Keep only contrasts whose required conditions exist in this run.

    F contrasts are retained only when all referenced T contrasts survive.
    """
    available = set(available_conditions)

    estimable_t: list[tuple[Any, ...]] = []
    skipped_names: list[str] = []

    for contrast in contrasts:
        name, statistic, contrast_conditions, weights = contrast

        if statistic != "T":
            continue

        missing = set(contrast_conditions) - available

        if missing:
            skipped_names.append(
                f"{name} (missing: {', '.join(sorted(missing))})"
            )
            continue

        estimable_t.append(contrast)

    surviving_t_names = {
        contrast[0]
        for contrast in estimable_t
    }

    estimable_f: list[tuple[Any, ...]] = []

    for contrast in contrasts:
        name, statistic, referenced_t_contrasts, weights = contrast

        if statistic != "F":
            continue

        # Depending on how your F contrasts are represented, these may be
        # contrast names or T-contrast tuples.
        referenced_names = {
            item[0] if isinstance(item, (list, tuple)) else item
            for item in referenced_t_contrasts
        }

        if referenced_names.issubset(surviving_t_names):
            estimable_f.append(contrast)
        else:
            skipped_names.append(name)

    return estimable_t + estimable_f, skipped_names


def _latest_run_contrasts_json(run_work_dir: Path) -> Path | None:
    """Return the newest valid per-run contrasts.json for one run work directory.

    Updated contrast sets take precedence over the original run manifest.  Only
    update directories that actually contain ``contrasts.json`` are considered,
    so an incomplete/dry-run update directory cannot hide the last valid update.
    """
    update_candidates: list[tuple[int, Path]] = []
    pattern = re.compile(r"^contrast_update_(\d+)$")

    for child in run_work_dir.iterdir():
        if not child.is_dir():
            continue
        match = pattern.match(child.name)
        if match is None:
            continue
        candidate = child / "contrasts.json"
        if candidate.is_file():
            update_candidates.append((int(match.group(1)), candidate))

    if update_candidates:
        update_candidates.sort(key=lambda item: item[0])
        return update_candidates[-1][1]

    original = run_work_dir / "contrasts.json"
    return original if original.is_file() else None


def _manifest_record_outputs_exist(record: dict[str, Any]) -> bool:
    """Return True only when the referenced first-level outputs still exist."""
    feat_dir_value = str(record.get("feat_dir", "")).strip()
    cope_value = str(record.get("cope_file", "")).strip()
    varcope_value = str(record.get("varcope_file", "")).strip()

    if not feat_dir_value or not cope_value or not varcope_value:
        return False

    feat_dir = Path(feat_dir_value)
    cope_file = Path(cope_value)
    varcope_file = Path(varcope_value)

    return (
        feat_dir.is_dir()
        and cope_file.is_file()
        and varcope_file.is_file()
    )


def _load_manifest_records(path: Path) -> list[dict[str, Any]]:
    """Load one per-run contrasts.json and keep only extant FEAT outputs."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        click.echo(
            f"[WARN] Could not read run contrast manifest {path}: {error}",
            err=True,
        )
        return []

    if not isinstance(payload, list):
        click.echo(
            f"[WARN] Ignoring non-list run contrast manifest: {path}",
            err=True,
        )
        return []

    records: list[dict[str, Any]] = []
    for index, record in enumerate(payload, start=1):
        if not isinstance(record, dict):
            click.echo(
                f"[WARN] Ignoring non-object record {index} in {path}",
                err=True,
            )
            continue
        if not record.get("run_label"):
            click.echo(
                f"[WARN] Ignoring record without run_label in {path}",
                err=True,
            )
            continue
        if not _manifest_record_outputs_exist(record):
            continue
        records.append(dict(record))

    return records


def _rebuild_contrast_manifest_from_work(deriv_dir: Path) -> pd.DataFrame:
    """Reconstruct the dataset manifest from existing level-1 work outputs.

    For each run directory under ``<deriv_dir>/work``, the highest numbered
    ``contrast_update_NNN/contrasts.json`` is used when present; otherwise the
    run's original ``contrasts.json`` is used.
    """
    work_root = deriv_dir / "work"
    if not work_root.is_dir():
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    selected_sources: list[Path] = []
    stale_sources: list[Path] = []

    for run_work_dir in sorted(path for path in work_root.iterdir() if path.is_dir()):
        manifest = _latest_run_contrasts_json(run_work_dir)
        if manifest is None:
            continue
        run_records = _load_manifest_records(manifest)
        if run_records:
            records.extend(run_records)
            selected_sources.append(manifest)
        else:
            # A manifest may be structurally valid but refer to a FEAT directory
            # that has since been removed. Do not resurrect such stale outputs.
            stale_sources.append(manifest)

    if not records:
        return pd.DataFrame()

    # A run should have only one selected source, but protect against stale or
    # duplicated work directories by keeping the last selected record set for
    # each run_label.
    table = pd.DataFrame.from_records(records)
    if "run_label" in table.columns:
        table = table.drop_duplicates(
            subset=["run_label", "cope"],
            keep="last",
        )

    for column in ("conditions", "weights"):
        if column in table.columns:
            table[column] = table[column].map(
                lambda value: (
                    value
                    if isinstance(value, str)
                    else json.dumps(value, separators=(",", ":"))
                )
            )

    click.echo(
        f"Rebuilt contrast manifest state from {len(selected_sources)} "
        f"existing run manifest(s); skipped {len(stale_sources)} stale run manifest(s)."
    )
    return table


def _normalize_contrast_manifest_table(table: pd.DataFrame) -> pd.DataFrame:
    """Normalize columns and deterministic numeric-aware ordering."""
    preferred_columns = [
        "subject",
        "session",
        "task",
        "run",
        "acquisition",
        "direction",
        "echo",
        "run_label",
        "cope",
        "contrast_name",
        "canonical_name",
        "conditions",
        "weights",
        "feat_dir",
        "cope_file",
        "varcope_file",
    ]

    for column in preferred_columns:
        if column not in table.columns:
            table[column] = ""

    extra_columns = [
        column for column in table.columns if column not in preferred_columns
    ]
    table = table[preferred_columns + extra_columns].copy()

    for column in table.columns:
        table[column] = table[column].fillna("").astype(str)

    table["_subject_sort"] = pd.to_numeric(table["subject"], errors="coerce")
    table["_session_sort"] = pd.to_numeric(table["session"], errors="coerce")
    table["_run_sort"] = pd.to_numeric(table["run"], errors="coerce")
    table["_cope_sort"] = pd.to_numeric(table["cope"], errors="coerce")

    return table.sort_values(
        [
            "_subject_sort", "subject",
            "_session_sort", "session",
            "task",
            "_run_sort", "run",
            "_cope_sort", "cope",
        ],
        kind="stable",
        na_position="last",
    ).drop(
        columns=[
            "_subject_sort",
            "_session_sort",
            "_run_sort",
            "_cope_sort",
        ]
    )



def rebuild_contrast_manifest(
    deriv_dir: Path,
    *,
    dry_run: bool = False,
) -> Path:
    """Rebuild the dataset-wide contrast manifest from existing run work output.

    For each run under ``<deriv_dir>/work``, the highest numbered
    ``contrast_update_NNN/contrasts.json`` that actually exists is preferred;
    otherwise the original run-level ``contrasts.json`` is used.  The rebuild
    holds the same advisory lock used by normal manifest updates and replaces
    the TSV atomically.
    """
    deriv_dir = Path(deriv_dir).resolve()
    manifest_path = deriv_dir / "contrast_manifest.tsv"

    if dry_run:
        click.echo(
            f"DRY RUN: would rebuild {manifest_path} from {deriv_dir / 'work'}"
        )
        return manifest_path

    deriv_dir.mkdir(parents=True, exist_ok=True)
    lock_path = deriv_dir / ".contrast_manifest.tsv.lock"

    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            table = _rebuild_contrast_manifest_from_work(deriv_dir)
            if table.empty:
                raise click.ClickException(
                    "No usable contrasts.json files were found under "
                    f"{deriv_dir / 'work'}"
                )

            table = _normalize_contrast_manifest_table(table)

            fd, temporary_manifest_name = tempfile.mkstemp(
                prefix=".contrast_manifest.",
                suffix=".tsv.tmp",
                dir=str(deriv_dir),
                text=True,
            )
            os.close(fd)
            temporary_manifest = Path(temporary_manifest_name)
            try:
                table.to_csv(temporary_manifest, sep="\t", index=False)
                temporary_manifest.replace(manifest_path)
            finally:
                if temporary_manifest.exists():
                    temporary_manifest.unlink()
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    run_count = table["run_label"].nunique() if "run_label" in table.columns else 0
    click.echo(
        f"Rebuilt dataset contrast manifest: {manifest_path} "
        f"({run_count} run(s), {len(table)} contrast row(s))"
    )
    return manifest_path

def write_contrast_manifest(
    *,
    work_dir: Path,
    deriv_dir: Path,
    entities: dict[str, Any],
    label: str,
    output_dir: Path,
    contrasts: Sequence[tuple[Any, ...]],
    canonical_names: dict[str, str],
    dry_run: bool = False,
) -> None:
    """Write per-run contrast provenance and update the dataset-wide manifest.

    The dataset-wide TSV is concurrency-safe.  If it is missing or empty, its
    prior state is reconstructed from existing run work directories before the
    current run is merged.  Contrast-update directories are resolved by using
    the highest numbered update that contains a valid ``contrasts.json``.
    """
    if dry_run:
        click.echo("DRY RUN: contrast manifests were not modified.")
        return

    records: list[dict[str, Any]] = []
    cope_number = 0

    for contrast in contrasts:
        name, statistic, conditions, weights = contrast
        if str(statistic).upper() != "T":
            continue

        cope_number += 1
        records.append(
            {
                "subject": str(entities["subject"]),
                "session": "" if entities.get("session") is None else str(entities["session"]),
                "task": str(entities["task"]),
                "run": "" if entities.get("run") is None else str(entities["run"]),
                "acquisition": "" if entities.get("acquisition") is None else str(entities["acquisition"]),
                "direction": "" if entities.get("direction") is None else str(entities["direction"]),
                "echo": "" if entities.get("echo") is None else str(entities["echo"]),
                "run_label": label,
                "cope": cope_number,
                "contrast_name": str(name),
                "canonical_name": str(canonical_names.get(str(name), str(name))),
                "conditions": list(conditions),
                "weights": [float(weight) for weight in weights],
                "feat_dir": str(output_dir),
                "cope_file": str(output_dir / "stats" / f"cope{cope_number}.nii.gz"),
                "varcope_file": str(output_dir / "stats" / f"varcope{cope_number}.nii.gz"),
            }
        )

    if not records:
        raise click.ClickException(
            f"No T contrasts available for manifest entry: {label}"
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    deriv_dir.mkdir(parents=True, exist_ok=True)

    # Write this run/update's exact mapping using a process-unique temporary.
    json_path = work_dir / "contrasts.json"
    fd, temporary_json_name = tempfile.mkstemp(
        prefix=f".{json_path.stem}.",
        suffix=".json.tmp",
        dir=str(work_dir),
        text=True,
    )
    os.close(fd)
    temporary_json = Path(temporary_json_name)
    try:
        temporary_json.write_text(
            json.dumps(records, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_json.replace(json_path)
    finally:
        if temporary_json.exists():
            temporary_json.unlink()

    manifest_path = deriv_dir / "contrast_manifest.tsv"
    lock_path = deriv_dir / ".contrast_manifest.tsv.lock"
    new_table = pd.DataFrame.from_records(records)
    for column in ("conditions", "weights"):
        new_table[column] = new_table[column].map(
            lambda value: json.dumps(value, separators=(",", ":"))
        )

    # Atomic rename by itself does not prevent lost updates.  Hold the lock for
    # the entire read/rebuild -> merge -> write -> replace transaction.
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            if manifest_path.exists() and manifest_path.stat().st_size > 0:
                try:
                    existing = pd.read_csv(
                        manifest_path,
                        sep="\t",
                        dtype=str,
                        keep_default_na=False,
                    )
                except pd.errors.EmptyDataError:
                    existing = pd.DataFrame()
            else:
                click.echo(
                    f"Dataset contrast manifest is missing; rebuilding from "
                    f"{deriv_dir / 'work'}"
                )
                existing = _rebuild_contrast_manifest_from_work(deriv_dir)

            if not existing.empty:
                if "run_label" not in existing.columns:
                    raise click.ClickException(
                        f"Existing/rebuilt manifest lacks required 'run_label' column: "
                        f"{manifest_path}"
                    )
                existing = existing.loc[
                    existing["run_label"].astype(str) != str(label)
                ].copy()
                table = pd.concat(
                    [existing, new_table],
                    ignore_index=True,
                    sort=False,
                )
            else:
                table = new_table

            table = _normalize_contrast_manifest_table(table)

            fd, temporary_manifest_name = tempfile.mkstemp(
                prefix=".contrast_manifest.",
                suffix=".tsv.tmp",
                dir=str(deriv_dir),
                text=True,
            )
            os.close(fd)
            temporary_manifest = Path(temporary_manifest_name)
            try:
                table.to_csv(temporary_manifest, sep="\t", index=False)
                temporary_manifest.replace(manifest_path)
            finally:
                if temporary_manifest.exists():
                    temporary_manifest.unlink()
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    click.echo(f"Updated run manifest: {json_path}")
    click.echo(f"Updated dataset manifest: {manifest_path}")

def load_confounds(
    confounds_file: str,
    *,
    regexes: list[str] | None,
    expected_rows: int,
    require_all_regexes: bool,
) -> tuple[list[str], list[list[float]]]:
    """
    Load nuisance regressors in Nipype Bunch format.

    Returns:
        regressor_names
        regressors, where each inner list is one regressor over time
    """
    confounds = pd.read_csv(
        confounds_file,
        sep="\t",
        na_values=["n/a", "NA", "NaN"],
    )

    if len(confounds) != expected_rows:
        raise click.ClickException(
            f"Confound file has {len(confounds)} rows but the BOLD image has "
            f"{expected_rows} volumes: {confounds_file}"
        )

    if regexes is None:
        columns = [
            column
            for column in confounds.columns
            if pd.api.types.is_numeric_dtype(confounds[column])
        ]
    else:
        columns = select_columns_by_regex(confounds, regexes)

        unmatched = [
            regex
            for regex in regexes
            if not any(re.fullmatch(regex, column) for column in confounds.columns)
        ]

        if unmatched:
            message = (
                f"Confound patterns did not match any columns in "
                f"{confounds_file}: {unmatched}"
            )
            if require_all_regexes:
                raise click.ClickException(message)
            click.echo(f"[WARN] {message}", err=True)

    if not columns:
        raise click.ClickException(
            f"No usable confound columns selected from {confounds_file}"
        )

    selected = confounds.loc[:, columns].apply(
        pd.to_numeric,
        errors="coerce",
    )

    # fMRIPrep derivative columns commonly contain NaN in the first row.
    # Replacing remaining non-finite values with zero is explicit and stable.
    selected = selected.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    constant_columns = [
        column
        for column in selected.columns
        if selected[column].nunique(dropna=False) <= 1
    ]

    if constant_columns:
        click.echo(
            "[WARN] Dropping constant confound columns: "
            + ", ".join(constant_columns),
            err=True,
        )
        selected = selected.drop(columns=constant_columns)
        columns = [
            column
            for column in columns
            if column not in constant_columns
        ]

    if not columns:
        raise click.ClickException(
            f"All selected confounds were constant: {confounds_file}"
        )

    regressors = [
        selected[column].astype(float).tolist()
        for column in columns
    ]

    return columns, regressors


def patch_fsf(
    fsf_path: str,
    *,
    output_dir: str,
    bold_file: str,
    disable_feat_preprocessing: bool,
    smoothing_fwhm: float,
) -> None:
    """
    Patch output and input paths and disable duplicate FEAT preprocessing.

    Level1Design normally writes the input path through SpecifyModel, but it is
    patched explicitly here to make the generated FSF self-contained.
    """
    if smoothing_fwhm < 0:
        raise click.ClickException("smoothing_fwhm must be >= 0")

    replacements = {
        "set fmri(outputdir)": f'set fmri(outputdir) "{output_dir}"',
        "set feat_files(1)": f'set feat_files(1) "{bold_file}"',
        # FEAT spatial smoothing kernel, in mm FWHM. Zero disables smoothing.
        "set fmri(smooth)": f"set fmri(smooth) {float(smoothing_fwhm):g}",
    }

    if disable_feat_preprocessing:
        replacements.update(
            {
                # Motion correction
                "set fmri(mc)": "set fmri(mc) 0",
                # Slice timing
                "set fmri(st)": "set fmri(st) 0",
                # Brain extraction
                "set fmri(bet_yn)": "set fmri(bet_yn) 0",
                # Registration stages
                "set fmri(reg_yn)": "set fmri(reg_yn) 0",
                "set fmri(reg_standard_yn)": "set fmri(reg_standard_yn) 0",
                # Keep menu-valued registration DOF settings valid even when
                # registration itself is disabled.
                "set fmri(regstandard_dof)": "set fmri(regstandard_dof) 12",
            }
        )

    with open(fsf_path, encoding="utf-8") as file:
        lines = file.readlines()

    found: set[str] = set()
    patched: list[str] = []

    for line in lines:
        stripped = line.strip()
        replacement = None

        for prefix, value in replacements.items():
            if stripped.startswith(prefix):
                replacement = value
                found.add(prefix)
                break

        patched.append((replacement + "\n") if replacement else line)

    # outputdir should always exist in a valid first-level FSF.
    if "set fmri(outputdir)" not in found:
        raise click.ClickException(
            f"Generated FSF did not contain fmri(outputdir): {fsf_path}"
        )

    with open(fsf_path, "w", encoding="utf-8") as file:
        file.writelines(patched)


def patch_contrasts_in_fsf(
    fsf_path: Path,
    contrasts: Sequence[tuple[Any, ...]],
) -> None:
    """
    Replace T-contrast definitions in an existing first-level FEAT FSF.

    Each contrast must have the form:

        (name, "T", condition_names, weights)

    or:

        (name, "T", condition_names, weights, canonical_name)

    Contrast conditions are matched against `fmri(evtitleN)` entries in the
    existing FSF. Conditions not included in a contrast receive weight zero.

    `feat_model` should be run after this function to regenerate design.con.
    """
    text = fsf_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    evtitle_pattern = re.compile(
        r'^\s*set\s+fmri\(evtitle(\d+)\)\s+"(.*)"\s*$'
    )
    evs_orig_pattern = re.compile(
        r"^\s*set\s+fmri\(evs_orig\)\s+(\d+)\s*$"
    )

    ev_names_by_index: dict[int, str] = {}
    declared_evs_orig: int | None = None

    for line in lines:
        ev_match = evtitle_pattern.match(line)
        if ev_match:
            ev_index = int(ev_match.group(1))
            ev_names_by_index[ev_index] = ev_match.group(2)

        evs_match = evs_orig_pattern.match(line)
        if evs_match:
            declared_evs_orig = int(evs_match.group(1))

    if declared_evs_orig is None:
        raise click.ClickException(
            f"Could not find 'fmri(evs_orig)' in {fsf_path}"
        )

    if not ev_names_by_index:
        raise click.ClickException(
            f"Could not find any 'fmri(evtitleN)' entries in {fsf_path}"
        )

    # Some FSFs may include additional original EVs beyond the task EVs.
    # Unnamed EVs are retained in the vector with a zero contrast weight.
    ev_names = [
        ev_names_by_index.get(index, "")
        for index in range(1, declared_evs_orig + 1)
    ]

    duplicate_ev_names = {
        name
        for name in ev_names
        if name and ev_names.count(name) > 1
    }
    if duplicate_ev_names:
        raise click.ClickException(
            "The existing FSF contains duplicate EV names, so contrast "
            "conditions cannot be mapped unambiguously: "
            + ", ".join(sorted(duplicate_ev_names))
        )

    ev_index_by_name = {
        name: index
        for index, name in enumerate(ev_names, start=1)
        if name
    }

    derivative_pattern = re.compile(
        r"^\s*set\s+fmri\(deriv_yn(\d+)\)\s+([01])\s*$"
    )
    evs_real_pattern = re.compile(
        r"^\s*set\s+fmri\(evs_real\)\s+(\d+)\s*$"
    )

    derivatives_by_index: dict[int, bool] = {}
    declared_evs_real: int | None = None

    for line in lines:
        derivative_match = derivative_pattern.match(line)
        if derivative_match:
            derivatives_by_index[int(derivative_match.group(1))] = (
                derivative_match.group(2) == "1"
            )

        real_match = evs_real_pattern.match(line)
        if real_match:
            declared_evs_real = int(real_match.group(1))

    if declared_evs_real is None:
        raise click.ClickException(
            f"Could not find 'fmri(evs_real)' in {fsf_path}"
        )

    normalized_contrasts: list[
        tuple[str, list[str], list[float]]
    ] = []

    seen_names: set[str] = set()

    for contrast in contrasts:
        if len(contrast) not in {4, 5}:
            raise click.ClickException(
                f"Invalid contrast definition: {contrast!r}"
            )

        name = str(contrast[0]).strip()
        statistic = str(contrast[1]).upper()
        conditions = [str(value).strip() for value in contrast[2]]
        weights = [float(value) for value in contrast[3]]

        if statistic != "T":
            raise click.ClickException(
                f"Contrast {name!r} has type {statistic!r}; "
                "contrast-update mode currently supports T contrasts only."
            )

        if not name:
            raise click.ClickException(
                "Contrast names cannot be empty."
            )

        if name in seen_names:
            raise click.ClickException(
                f"Duplicate contrast name: {name!r}"
            )
        seen_names.add(name)

        if len(conditions) != len(weights):
            raise click.ClickException(
                f"Contrast {name!r} contains {len(conditions)} conditions "
                f"but {len(weights)} weights."
            )

        missing = [
            condition
            for condition in conditions
            if condition not in ev_index_by_name
        ]
        if missing:
            raise click.ClickException(
                f"Contrast {name!r} refers to EVs not present in the "
                f"existing FSF: {', '.join(missing)}"
            )

        normalized_contrasts.append((name, conditions, weights))

    if not normalized_contrasts:
        raise click.ClickException(
            "No estimable T contrasts were supplied for contrast updating."
        )

    # Remove all existing contrast and F-test definitions. These are rebuilt
    # below and then expanded by feat_model.
    contrast_line_patterns = [
        re.compile(r"^\s*set\s+fmri\(ncon_orig\)\s+"),
        re.compile(r"^\s*set\s+fmri\(ncon_real\)\s+"),
        re.compile(r"^\s*set\s+fmri\(nftests_orig\)\s+"),
        re.compile(r"^\s*set\s+fmri\(nftests_real\)\s+"),
        re.compile(r"^\s*set\s+fmri\(con_mode(?:_old)?\)\s+"),
        re.compile(r"^\s*set\s+fmri\(conname_orig\.\d+\)\s+"),
        re.compile(r"^\s*set\s+fmri\(conname_real\.\d+\)\s+"),
        re.compile(r"^\s*set\s+fmri\(con_orig\d+\.\d+\)\s+"),
        re.compile(r"^\s*set\s+fmri\(con_real\d+\.\d+\)\s+"),
        re.compile(r"^\s*set\s+fmri\(ftest_orig\d+\.\d+\)\s+"),
        re.compile(r"^\s*set\s+fmri\(ftest_real\d+\.\d+\)\s+"),
    ]

    retained_lines = [
        line
        for line in lines
        if not any(pattern.match(line) for pattern in contrast_line_patterns)
    ]

    number_of_contrasts = len(normalized_contrasts)

    contrast_block = [
        "",
        "# Contrast definitions added by call_feat",
        f"set fmri(ncon_orig) {number_of_contrasts}",
        f"set fmri(ncon_real) {number_of_contrasts}",
        "set fmri(nftests_orig) 0",
        "set fmri(nftests_real) 0",
        "set fmri(con_mode_old) orig",
        "set fmri(con_mode) orig",
        "",
    ]

    for contrast_index, (name, conditions, weights) in enumerate(
        normalized_contrasts,
        start=1,
    ):
        escaped_name = (
            name.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", " ")
            .replace("\r", " ")
        )

        weight_by_condition = dict(zip(conditions, weights))

        # Weights in original-EV space.
        original_weights = [
            float(weight_by_condition.get(ev_name, 0.0))
            for ev_name in ev_names
        ]

        if not any(weight != 0.0 for weight in original_weights):
            raise click.ClickException(
                f"Contrast {name!r} maps to an all-zero vector. "
                f"Requested conditions: {conditions}. "
                f"Available EVs: {ev_names}"
            )

        # Expand original EVs into FEAT's real-EV space.
        #
        # For a temporal derivative:
        #   original EV weight -> main real EV
        #   derivative real EV -> 0
        real_weights: list[float] = []

        for ev_index, original_weight in enumerate(
            original_weights,
            start=1,
        ):
            real_weights.append(original_weight)

            if derivatives_by_index.get(ev_index, False):
                real_weights.append(0.0)

        if len(real_weights) != declared_evs_real:
            raise click.ClickException(
                f"Cannot map contrasts safely into real-EV space: "
                f"constructed {len(real_weights)} weights, but the FSF declares "
                f"{declared_evs_real} real EVs. This may indicate basis-function "
                "expansion other than a single temporal derivative."
            )

        contrast_block.extend(
            [
                f"# Contrast {contrast_index}: {escaped_name}",
                (
                    f'set fmri(conname_orig.{contrast_index}) '
                    f'"{escaped_name}"'
                ),
                (
                    f'set fmri(conname_real.{contrast_index}) '
                    f'"{escaped_name}"'
                ),
            ]
        )

        for ev_index, weight in enumerate(original_weights, start=1):
            contrast_block.append(
                f"set fmri(con_orig{contrast_index}.{ev_index}) "
                f"{weight:.12g}"
            )

        for real_ev_index, weight in enumerate(real_weights, start=1):
            contrast_block.append(
                f"set fmri(con_real{contrast_index}.{real_ev_index}) "
                f"{weight:.12g}"
            )

        contrast_block.append("")

    fsf_path.write_text(
        "\n".join(retained_lines + contrast_block) + "\n",
        encoding="utf-8",
    )


# update contrast functions
def update_existing_feat_contrasts(
    *,
    feat_dir: Path,
    work_dir: Path,
    deriv_dir: Path,
    entities: dict[str, Any],
    label: str,
    contrasts: Sequence[tuple],
    canonical_names,
    dry_run: bool,
) -> None:
    click.echo("Updating contrasts in existing FEAT analysis")
    click.echo(f"FEAT directory : {feat_dir}")
    click.echo(f"Working directory: {work_dir}")

    existing_mat = feat_dir / "design.mat"
    existing_fsf = feat_dir / "design.fsf"
    filtered_data = feat_dir / "filtered_func_data.nii.gz"

    for path in (existing_mat, existing_fsf, filtered_data):
        if not path.exists():
            raise click.ClickException(
                f"Required FEAT file is missing: {path}"
            )

    click.echo("✓ Found existing design.fsf, design.mat and filtered_func_data")

    click.echo("Requested contrasts:")
    for index, contrast in enumerate(contrasts, start=1):
        click.echo(
            f"  {index:2d}. {contrast[0]}"
            f" [canonical: {canonical_names.get(contrast[0], contrast[0])}]"
        )

    #
    # Generate updated design files
    #
    design_root = work_dir / "design"
    update_fsf = design_root.with_suffix(".fsf")

    click.echo(f"Copying design.fsf -> {update_fsf}")
    shutil.copy2(existing_fsf, update_fsf)

    click.echo("Updating contrast definitions...")
    patch_contrasts_in_fsf(
        update_fsf,
        contrasts,
    )

    click.echo("Running feat_model...")
    subprocess.run(
        ["feat_model", str(design_root)],
        check=True,
        cwd=str(work_dir),
    )

    generated_mat = design_root.with_suffix(".mat")
    generated_con = design_root.with_suffix(".con")

    click.echo("Comparing generated design.mat against original...")
    verify_design_matrices_equal(existing_mat, generated_mat)
    click.echo("✓ Design matrix unchanged")

    click.echo(f"Generated design.con: {generated_con}")
    if dry_run:
        click.echo("")
        click.echo("DRY RUN")
        click.echo(f"Updated FSF : {update_fsf}")
        click.echo(f"Updated CON : {generated_con}")
        click.echo("Verified that design.mat is identical to the original.")
        click.echo("film_gls was not executed.")
        click.echo("The contrast manifest was not modified.")
        return

    rerun_film_with_updated_contrasts(
        feat_dir,
        work_dir,
        generated_con,
        update_fsf,
        False,
        contrasts
    )

    write_contrast_manifest(
        work_dir=work_dir,
        deriv_dir=deriv_dir,
        entities=entities,
        label=label,
        output_dir=feat_dir,
        contrasts=contrasts,
        canonical_names=canonical_names,
        dry_run=dry_run,
    )

    click.echo("✓ Contrast manifest updated")


def read_original_film_command(feat_dir: Path) -> list[str]:
    """Read the original film_gls command from <feat_dir>/stats/logfile."""
    logfile = feat_dir / "stats" / "logfile"

    if not logfile.is_file():
        raise click.ClickException(
            f"FILM logfile not found: {logfile}"
        )

    for raw_line in logfile.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        argv = shlex.split(line)

        if argv and Path(argv[0]).name == "film_gls":
            return argv

    raise click.ClickException(
        f"No film_gls command found in {logfile}"
    )


def build_updated_film_command(
    feat_dir: Path,
    new_con_file: Path,
) -> list[str]:
    """Reuse original FILM options with the updated contrast file."""
    original = read_original_film_command(feat_dir)

    executable = original[0]
    preserved: list[str] = []

    replace_prefixes = (
        "--in=",
        "--rn=",
        "--pd=",
        "--con=",
    )

    for argument in original[1:]:
        if argument.startswith(replace_prefixes):
            continue
        preserved.append(argument)

    return [
        executable,
        f"--in={feat_dir / 'filtered_func_data'}",
        f"--rn={feat_dir / 'stats'}",
        f"--pd={feat_dir / 'design.mat'}",
        *preserved,
        f"--con={new_con_file}",
    ]


def backup_existing_statistics(
    feat_dir: Path,
    update_work_dir: Path,
) -> None:
    backup_dir = update_work_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for filename in ("design.con", "design.fts", "design.fsf"):
        source = feat_dir / filename
        if source.exists():
            shutil.copy2(source, backup_dir / filename)

    stats_dir = feat_dir / "stats"
    if stats_dir.exists():
        shutil.copytree(stats_dir, backup_dir / "stats")


def rerun_film_with_updated_contrasts(
    feat_dir: Path,
    update_work_dir: Path,
    new_con_file: Path,
    new_fsf_file: Path,
    dry_run: bool,
    contrasts: Sequence[tuple],
) -> None:
    click.echo("Preparing FILM re-fit")
    click.echo(f"FEAT directory   : {feat_dir}")
    click.echo(f"Update work dir  : {update_work_dir}")
    click.echo(f"New contrast file: {new_con_file}")
    click.echo(f"New FSF file     : {new_fsf_file}")

    command = build_updated_film_command(
        feat_dir=feat_dir,
        new_con_file=new_con_file,
    )

    click.echo("FILM command:")
    click.echo("  " + shlex.join(command))

    if dry_run:
        click.echo("")
        click.echo("DRY RUN")
        click.echo("No FEAT files were modified.")
        click.echo("FILM and post-stats were not executed.")
        return

    click.echo("Backing up existing FEAT statistics and design files...")
    backup_existing_statistics(
        feat_dir,
        update_work_dir,
    )
    click.echo(
        f"Backup created under: {update_work_dir / 'backup'}"
    )

    stats_dir = feat_dir / "stats"

    if stats_dir.exists():
        click.echo(f"Removing existing statistics directory: {stats_dir}")
        shutil.rmtree(stats_dir)
    else:
        click.echo(
            f"No existing statistics directory found at {stats_dir}; "
            "a new one will be created."
        )

    click.echo("Installing updated contrast and FSF definitions...")
    shutil.copy2(
        new_con_file,
        feat_dir / "design.con",
    )
    shutil.copy2(
        new_fsf_file,
        feat_dir / "design.fsf",
    )

    click.echo("Running film_gls...")
    subprocess.run(
        command,
        check=True,
        cwd=str(feat_dir),
    )
    click.echo("FILM completed successfully.")

    required_film_outputs = [
        stats_dir / "res4d.nii.gz",
        stats_dir / "dof",
    ]

    missing_outputs = [
        path
        for path in required_film_outputs
        if not path.exists()
    ]

    if missing_outputs:
        raise click.ClickException(
            "FILM completed but required outputs are missing: "
            + ", ".join(str(path) for path in missing_outputs)
        )

    zstat_files = sorted(stats_dir.glob("zstat*.nii.gz"))

    if not zstat_files:
        raise click.ClickException(
            f"FILM completed but no zstat images were found in {stats_dir}"
        )

    click.echo(
        f"FILM generated {len(zstat_files)} z-statistic image(s)."
    )

    click.echo("Running updated FEAT post-statistics...")
    run_updated_poststats(
        feat_dir,
        contrasts,
        overwrite=True,
        generate_tsplot=True,
    )
    click.echo("Post-statistics completed successfully.")

    click.echo("")
    click.echo("Contrast update complete")
    click.echo(f"Updated FEAT directory: {feat_dir}")
    click.echo(
        f"Backup of previous results: {update_work_dir / 'backup'}"
    )


def _require_fsl_command(name: str) -> str:
    """Return an FSL executable path or fail with a clear message."""
    executable = shutil.which(name)
    if executable is None:
        raise click.ClickException(
            f"Required FSL executable {name!r} was not found on PATH."
        )
    return executable


def read_fsf_number(
    fsf_path: Path,
    key: str,
    *,
    value_type: type = float,
):
    pattern = re.compile(
        rf"^\s*set\s+fmri\({re.escape(key)}\)\s+"
        r'"?([^"\s]+)"?\s*$'
    )

    for line in fsf_path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        match = pattern.match(line)
        if match:
            try:
                return value_type(match.group(1))
            except ValueError as error:
                raise click.ClickException(
                    f"Invalid fmri({key}) value in {fsf_path}: "
                    f"{match.group(1)!r}"
                ) from error

    raise click.ClickException(
        f"Could not find fmri({key}) in {fsf_path}"
    )


def _read_scalar_file(path: Path) -> float:
    """Read the first numeric token from a small FSL text output file."""
    if not path.is_file():
        raise click.ClickException(f"Required file is missing: {path}")
    for token in path.read_text(encoding="utf-8", errors="replace").split():
        try:
            return float(token)
        except ValueError:
            continue
    raise click.ClickException(f"No numeric value found in {path}")


def _parse_smoothest_output(output: str) -> tuple[float, int, float]:
    """Parse DLH, VOLUME, and RESELS from FSL smoothest output."""
    values: dict[str, float] = {}
    for key in ("DLH", "VOLUME", "RESELS"):
        match = re.search(rf"\b{key}\s*(?:=)?\s*([-+0-9.eE]+)", output)
        if match:
            values[key] = float(match.group(1))
    missing = [key for key in ("DLH", "VOLUME", "RESELS") if key not in values]
    if missing:
        raise click.ClickException(
            "Could not parse smoothest output; missing: " + ", ".join(missing)
        )
    return values["DLH"], int(round(values["VOLUME"])), values["RESELS"]


def _indexed_stat_images(stats_dir: Path, stem: str) -> list[tuple[int, Path]]:
    """Return numbered FSL images such as zstat1, zstat2 in numeric order."""
    found: dict[int, Path] = {}
    pattern = re.compile(rf"^{re.escape(stem)}(\d+)\.nii(?:\.gz)?$")
    for path in stats_dir.glob(f"{stem}*.nii*"):
        match = pattern.match(path.name)
        if match:
            found[int(match.group(1))] = path
    return sorted(found.items())


def _remove_old_poststats(feat_dir: Path) -> None:
    """Remove post-stats products that would otherwise become stale."""
    file_patterns = (
        "thresh_zstat*",
        "cluster_mask_zstat*",
        "cluster_zstat*.txt",
        "lmax_zstat*.txt",
        "rendered_thresh_zstat*",
        "*.vol",
        ".ramp.gif",
    )
    for pattern in file_patterns:
        for path in feat_dir.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    tsplot_dir = feat_dir / "tsplot"
    if tsplot_dir.exists():
        shutil.rmtree(tsplot_dir)


def run_updated_poststats(
    feat_dir: Path,
    contrasts: Sequence[tuple],
    *,
    overwrite: bool = True,
    generate_tsplot: bool = True,
) -> None:
    """Recreate FEAT first-level post-stats after updated FILM contrasts.

    Values that vary by run are read from the existing FEAT directory:
    degrees of freedom from stats/dof, cluster thresholds from design.fsf,
    and DLH/volume from smoothest. No run-specific values are hard-coded.
    """
    stats_dir = feat_dir / "stats"
    mask = feat_dir / "mask"
    example_func = feat_dir / "example_func"
    filtered_func = feat_dir / "filtered_func_data"
    fsf_path = feat_dir / "design.fsf"

    for path in (stats_dir, mask, example_func, filtered_func, fsf_path):
        if not path.exists() and not Path(str(path) + ".nii.gz").exists():
            raise click.ClickException(f"Required post-stats input is missing: {path}")

    dof = int(round(_read_scalar_file(stats_dir / "dof")))
    threshold_mode = read_fsf_number(
        feat_dir / "design.fsf",
        "thresh",
        value_type=int,
    )
    z_threshold = read_fsf_number(
        feat_dir / "design.fsf",
        "z_thresh",
        value_type=float,
    )
    probability_threshold = read_fsf_number(
        feat_dir / "design.fsf",
        "prob_thresh",
        value_type=float,
    )
    
    smoothest       = _require_fsl_command("smoothest")
    fslmaths        = _require_fsl_command("fslmaths")
    fsl_cluster     = _require_fsl_command("fsl-cluster")
    cluster2html    = _require_fsl_command("cluster2html")
    fslstats        = _require_fsl_command("fslstats")
    overlay         = _require_fsl_command("overlay")
    slicer          = _require_fsl_command("slicer")
    tsplot          = _require_fsl_command("tsplot")

    if overwrite:
        _remove_old_poststats(feat_dir)

    smoothest_cmd = [
        smoothest, "-d", str(dof), "-m", "mask", "-r", "stats/res4d"
    ]
    click.echo("Post-stats smoothness command:")
    click.echo("  " + shlex.join(smoothest_cmd))
    smoothness = subprocess.run(
        smoothest_cmd, check=True, cwd=str(feat_dir), text=True, capture_output=True
    ).stdout
    (stats_dir / "smoothness").write_text(smoothness, encoding="utf-8")
    dlh, volume, resels = _parse_smoothest_output(smoothness)
    click.echo(f"Smoothness: DLH={dlh:g} VOLUME={volume} RESELS={resels:g}")

    zstats = _indexed_stat_images(stats_dir, "zstat")
    if not zstats:
        raise click.ClickException(f"No zstat images found in {stats_dir}")

    thresholded: list[tuple[int, Path]] = []
    for index, _zstat_path in zstats:
        thresh_root = feat_dir / f"thresh_zstat{index}"
        subprocess.run(
            [fslmaths, f"stats/zstat{index}", "-mas", "mask", str(thresh_root.name)],
            check=True, cwd=str(feat_dir),
        )
        (feat_dir / f"thresh_zstat{index}.vol").write_text(
            f"{volume}\n", encoding="utf-8"
        )

        cluster_command = [
            fsl_cluster,
            f"--in=thresh_zstat{index}",
            f"--thresh={z_threshold:g}",
            f"--othresh=thresh_zstat{index}",
            f"--oindex=cluster_mask_zstat{index}",
            "--connectivity=26",
            f"--olmax=lmax_zstat{index}.txt",
            "--scalarname=Z",
            f"--pthresh={probability_threshold:g}",
            f"--dlh={dlh:g}",
            f"--volume={volume}",
            f"--cope=stats/cope{index}",
        ]
        cluster_table = feat_dir / f"cluster_zstat{index}.txt"

        click.echo("Cluster command:")
        click.echo("  " + shlex.join(cluster_command))

        with open(cluster_table, "w", encoding="utf-8") as output_file:
            subprocess.run(
                cluster_command,
                check=True,
                cwd=str(feat_dir),
                stdout=output_file,
            )

        subprocess.run(
            [cluster2html, ".", f"cluster_zstat{index}"],
            check=True, cwd=str(feat_dir),
        )
        thresholded.append((index, thresh_root))

    positive_ranges: list[tuple[float, float]] = []
    for index, _ in thresholded:
        result = subprocess.run(
            [fslstats, f"thresh_zstat{index}", "-l", "0.0001", "-R"],
            check=True, cwd=str(feat_dir), text=True, capture_output=True,
        ).stdout.split()
        if len(result) >= 2:
            low, high = float(result[0]), float(result[1])
            if high > 0:
                positive_ranges.append((low, high))

    if positive_ranges:
        render_min = min(low for low, _ in positive_ranges if low > 0)
        render_max = max(high for _, high in positive_ranges)
    else:
        render_min = z_threshold
        render_max = z_threshold + 1.0
    if render_max <= render_min:
        render_max = render_min + 1.0

    click.echo(f"Rendering using zmin={render_min:g} zmax={render_max:g}")
    fsldir = os.environ.get("FSLDIR")
    ramp_source = Path(fsldir) / "etc" / "luts" / "ramp.gif" if fsldir else None
    if ramp_source and ramp_source.is_file():
        shutil.copy2(ramp_source, feat_dir / ".ramp.gif")

    for index, _ in thresholded:
        rendered = f"rendered_thresh_zstat{index}"
        subprocess.run(
            [
                overlay, "1", "0", "example_func", "-a",
                f"thresh_zstat{index}", f"{render_min:g}", f"{render_max:g}", rendered,
            ],
            check=True, cwd=str(feat_dir),
        )
        subprocess.run(
            [slicer, rendered, "-A", "750", f"{rendered}.png"],
            check=True, cwd=str(feat_dir),
        )

    tsplot_succeeded = False

    if generate_tsplot:
        tsplot_dir = feat_dir / "tsplot"
        tsplot_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [tsplot, ".", "-f", "filtered_func_data", "-o", "tsplot"],
            cwd=str(feat_dir),
            check=False,
        )

        tsplot_succeeded = result.returncode == 0

        if not tsplot_succeeded:
            click.echo(
                f"[WARN] tsplot failed with exit code {result.returncode}.",
                err=True,
            )

    update_poststats_html(
        feat_dir,
        contrasts,
        z_threshold=z_threshold,
        probability_threshold=probability_threshold,
        render_min=render_min,
        render_max=render_max,
        include_tsplots=tsplot_succeeded,
    )
    
def read_fsl_matrix(path: Path) -> np.ndarray:
    lines = path.read_text(encoding="utf-8").splitlines()

    try:
        matrix_start = lines.index("/Matrix") + 1
    except ValueError as error:
        raise click.ClickException(
            f"No /Matrix section found in {path}"
        ) from error

    rows = [
        [float(value) for value in line.split()]
        for line in lines[matrix_start:]
        if line.strip()
    ]

    return np.asarray(rows, dtype=float)


def verify_design_matrices_equal(
    existing: Path,
    generated: Path,
) -> None:
    old_matrix = read_fsl_matrix(existing)
    new_matrix = read_fsl_matrix(generated)

    if old_matrix.shape != new_matrix.shape:
        raise click.ClickException(
            "Updated design matrix shape differs from existing design: "
            f"{new_matrix.shape} versus {old_matrix.shape}."
        )

    if not np.allclose(
        old_matrix,
        new_matrix,
        rtol=1e-7,
        atol=1e-8,
    ):
        maximum_difference = float(
            np.max(np.abs(old_matrix - new_matrix))
        )
        raise click.ClickException(
            "Updated design matrix differs from the existing FEAT design. "
            f"Maximum absolute difference: {maximum_difference:g}. "
            "Refusing to update contrasts."
        )

    
def check_executable(name: str) -> None:
    """Require an external executable."""
    if shutil.which(name) is None:
        raise click.ClickException(
            f"Required executable {name!r} was not found on PATH."
        )


def parse_run_selectors(values: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize repeatable --run values, comma lists, and integer ranges.

    Accepted examples include ``--run 1``, ``--run 01``, ``--run 1,3,5``,
    ``--run 1-4``, and repeated options. Run labels are returned as strings so
    zero-padded BIDS labels such as ``01`` are preserved.
    """
    selected: list[str] = []

    for raw_value in values:
        value = str(raw_value).strip()
        if not value:
            raise click.ClickException("--run values cannot be empty.")

        # Permit shell-friendly list notation such as '[1,2,3]'.
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1].strip()

        for token in value.split(","):
            token = token.strip()
            if not token:
                raise click.ClickException(
                    f"Invalid --run selection {raw_value!r}: empty list element."
                )

            range_match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
            if range_match:
                start_text, stop_text = range_match.groups()
                start = int(start_text)
                stop = int(stop_text)
                if stop < start:
                    raise click.ClickException(
                        f"Invalid --run range {token!r}: end precedes start."
                    )

                # Preserve zero padding when either endpoint uses it.
                width = max(len(start_text), len(stop_text))
                preserve_padding = (
                    start_text.startswith("0") or stop_text.startswith("0")
                )
                for run_number in range(start, stop + 1):
                    run_label = (
                        f"{run_number:0{width}d}"
                        if preserve_padding
                        else str(run_number)
                    )
                    if run_label not in selected:
                        selected.append(run_label)
                continue

            # BIDS run entities are normally integer-like, but keeping this as
            # a string also supports zero-padded labels returned by PyBIDS.
            if not re.fullmatch(r"\d+", token):
                raise click.ClickException(
                    f"Invalid --run value {token!r}; expected an integer, "
                    "comma-separated integers, or an inclusive range such as 1-4."
                )

            if token not in selected:
                selected.append(token)

    return tuple(selected)


def _replace_html_section(
    text: str,
    section: str,
    content: str,
) -> str:
    """Replace content between FEAT report marker comments."""
    start = f"<!--{section}start-->"
    stop = f"<!--{section}stop-->"

    pattern = re.compile(
        rf"{re.escape(start)}.*?{re.escape(stop)}",
        flags=re.DOTALL,
    )

    replacement = f"{start}\n{content.rstrip()}\n{stop}"

    updated, count = pattern.subn(replacement, text, count=1)

    if count != 1:
        raise click.ClickException(
            f"Could not find a unique {section!r} section in report_poststats.html"
        )

    return updated


def update_poststats_html(
    feat_dir: Path,
    contrasts: Sequence[tuple],
    *,
    z_threshold: float,
    probability_threshold: float,
    render_min: float,
    render_max: float,
    include_tsplots: bool = True,
) -> None:
    """Regenerate contrast and time-series sections of report_poststats.html."""
    report_path = feat_dir / "report_poststats.html"

    if not report_path.is_file():
        raise click.ClickException(
            f"Post-stats report not found: {report_path}"
        )

    text = report_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    t_contrasts = [
        contrast
        for contrast in contrasts
        if str(contrast[1]).upper() == "T"
    ]

    if not t_contrasts:
        raise click.ClickException(
            "No T contrasts available for report_poststats.html"
        )

    methods_html = (
        "<hr><p><b>Analysis methods</b><br>"
        "FMRI data processing was carried out using FEAT "
        "(FMRI Expert Analysis Tool) Version 6.00, part of FSL "
        "(FMRIB's Software Library, www.fmrib.ox.ac.uk/fsl). "
        "Z (Gaussianised T/F) statistic images were thresholded using "
        f"clusters determined by Z&gt;{z_threshold:g} and a corrected "
        f"cluster significance threshold of P={probability_threshold:g} "
        "[Worsley 2001]."
    )

    text = _replace_html_section(
        text,
        "poststatsps",
        methods_html,
    )

    picture_lines = [
        "<hr><b>Thresholded activation images</b>",
        "&nbsp; &nbsp; &nbsp; &nbsp;",
        f"{render_min:.3g}",
        '<IMG BORDER=0 SRC=".ramp.gif">',
        f"{render_max:.3g}",
        "<p>",
        "",
    ]

    for index, contrast in enumerate(t_contrasts, start=1):
        name = html.escape(str(contrast[0]))

        picture_lines.extend(
            [
                (
                    f"<p>zstat{index} &nbsp;&nbsp;-&nbsp;&nbsp; "
                    f"C{index} ({name})<br>"
                ),
                (
                    f'<a href="cluster_zstat{index}.html">'
                    f'<IMG BORDER=0 '
                    f'SRC="rendered_thresh_zstat{index}.png"></a>'
                ),
                "",
            ]
        )

    text = _replace_html_section(
        text,
        "poststatspics",
        "\n".join(picture_lines),
    )

    if include_tsplots:
        tsplot_lines = [
            "<hr><b>Time series plots</b><p>",
        ]

        for index, _contrast in enumerate(t_contrasts, start=1):
            png_path = feat_dir / "tsplot" / f"tsplot_zstat{index}.png"
            html_path = feat_dir / "tsplot" / f"tsplot_zstat{index}.html"

            # Only include outputs that were actually generated.
            if png_path.exists() and html_path.exists():
                tsplot_lines.append(
                    f'<a href="tsplot/tsplot_zstat{index}.html">'
                    f'<IMG BORDER=0 '
                    f'SRC="tsplot/tsplot_zstat{index}.png"></a><br><br>'
                )

        if len(tsplot_lines) == 1:
            tsplot_lines.append(
                "<p>Time-series plots were not generated.</p>"
            )
    else:
        tsplot_lines = [
            "<hr><b>Time series plots</b><p>",
            "<p>Time-series plots were not generated.</p>",
        ]

    text = _replace_html_section(
        text,
        "poststatstsplot",
        "\n".join(tsplot_lines),
    )

    temporary_path = report_path.with_suffix(".html.tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(report_path)

    click.echo(f"Updated post-stats report: {report_path}")

def _require_command(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise click.ClickException(
            f"Required FSL executable {name!r} was not found on PATH."
        )
    return executable


def _existing_nifti(path: Path) -> Path:
    candidates = [path]
    if not str(path).endswith((".nii", ".nii.gz")):
        candidates += [Path(str(path) + ".nii.gz"), Path(str(path) + ".nii")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise click.ClickException(f"Required image does not exist: {path}")


def _normalize_selector(values: Sequence[str]) -> set[str]:
    selected: set[str] = set()
    for raw in values:
        for value in str(raw).split(","):
            value = value.strip()
            if value:
                selected.add(value)
    return selected


def _safe_label(value: str, max_length: int = 80) -> str:
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    label = re.sub(r"-+", "-", label).strip("-._") or "contrast"
    return label[:max_length]


def _entity_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _write_vest_matrix(path: Path, matrix: Sequence[Sequence[float]]) -> None:
    rows = [list(map(float, row)) for row in matrix]
    if not rows or not rows[0]:
        raise click.ClickException(f"Cannot write empty matrix: {path}")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise click.ClickException(f"Inconsistent row widths for {path}")
    lines = [
        f"/NumWaves\t{width}",
        f"/NumPoints\t{len(rows)}",
        "/PPheights\t" + "\t".join("1" for _ in range(width)),
        "",
        "/Matrix",
    ]
    lines += ["\t".join(f"{v:.10g}" for v in row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_vest_contrast(
    path: Path,
    names: str | Sequence[str],
    matrix: Sequence[Sequence[float]] | None = None,
) -> None:
    """Write an FSL VEST design.con file.

    Supports both:
      * a simple one-wave/one-contrast fixed-effects design
      * arbitrary group-level contrast matrices
    """

    # Backward compatibility with calls like:
    # _write_vest_contrast(path, canonical_name)
    if isinstance(names, str):
        contrast_names = [names]

        if matrix is None:
            contrast_matrix = [[1.0]]
        else:
            contrast_matrix = [
                list(map(float, row))
                for row in matrix
            ]
    else:
        contrast_names = [str(name) for name in names]

        if matrix is None:
            raise click.ClickException(
                "A contrast matrix is required when multiple contrast names "
                "are supplied."
            )

        contrast_matrix = [
            list(map(float, row))
            for row in matrix
        ]

    if not contrast_names:
        raise click.ClickException(
            f"Cannot write a contrast file with no contrasts: {path}"
        )

    if not contrast_matrix:
        raise click.ClickException(
            f"Cannot write an empty contrast matrix: {path}"
        )

    if len(contrast_names) != len(contrast_matrix):
        raise click.ClickException(
            f"Contrast-name count ({len(contrast_names)}) does not match "
            f"contrast-matrix row count ({len(contrast_matrix)}): {path}"
        )

    num_waves = len(contrast_matrix[0])

    if num_waves == 0:
        raise click.ClickException(
            f"Contrast matrix has zero columns: {path}"
        )

    if any(len(row) != num_waves for row in contrast_matrix):
        raise click.ClickException(
            f"Inconsistent contrast row widths: {path}"
        )

    lines = []

    for index, name in enumerate(contrast_names, start=1):
        clean = (
            str(name)
            .replace("\n", " ")
            .replace("\r", " ")
        )
        lines.append(f"/ContrastName{index}\t{clean}")

    lines.extend([
        f"/NumWaves\t{num_waves}",
        f"/NumContrasts\t{len(contrast_matrix)}",
        "/PPheights\t"
        + "\t".join("1" for _ in contrast_matrix),
        "/RequiredEffect\t"
        + "\t".join("1" for _ in contrast_matrix),
        "",
        "/Matrix",
    ])

    lines.extend(
        "\t".join(f"{value:.10g}" for value in row)
        for row in contrast_matrix
    )

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _read_first_level_dof(feat_dir: Path) -> float:
    dof_file = feat_dir / "stats" / "dof"
    if not dof_file.is_file():
        raise click.ClickException(f"Missing first-level DOF file: {dof_file}")
    for token in dof_file.read_text(encoding="utf-8", errors="replace").split():
        try:
            value = float(token)
        except ValueError:
            continue
        if value <= 0:
            raise click.ClickException(f"Invalid DOF {value:g} in {dof_file}")
        return value
    raise click.ClickException(f"No numeric DOF found in {dof_file}")


def _run(command: Sequence[str], cwd: Path, dry_run: bool) -> None:
    click.echo("  " + shlex.join([str(v) for v in command]))
    if not dry_run:
        subprocess.run([str(v) for v in command], check=True, cwd=str(cwd))


def run_fixed_effects_group(
    rows: pd.DataFrame,
    output_dir: Path,
    canonical_name: str,
    overwrite: bool,
    dry_run: bool,
) -> dict[str, object]:
    fslmerge = _require_command("fslmerge")
    fslmaths = _require_command("fslmaths")
    flameo = _require_command("flameo")

    if output_dir.exists():
        if overwrite:
            click.echo(f"Removing existing output: {output_dir}")
            if not dry_run:
                shutil.rmtree(output_dir)
        else:
            raise click.ClickException(
                f"Output exists: {output_dir}. Use --overwrite to replace it."
            )
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=False)
    cwd = output_dir if not dry_run else output_dir.parent

    cope_files = [_existing_nifti(Path(v)) for v in rows["cope_file"]]
    varcope_files = [_existing_nifti(Path(v)) for v in rows["varcope_file"]]
    if "feat_dir" in rows.columns:
        feat_dirs = [Path(v).resolve() for v in rows["feat_dir"]]
    else:
        feat_dirs = [p.parent.parent for p in cope_files]

    n_inputs = len(cope_files)
    click.echo(f"Inputs: {n_inputs}")
    for i, row in enumerate(rows.itertuples(index=False), 1):
        click.echo(
            f"  {i:2d}. run={getattr(row, 'run')} "
            f"contrast={getattr(row, 'contrast_name')} "
            f"cope={getattr(row, 'cope_file')}"
        )

    cope_4d = output_dir / "filtered_func_data"
    varcope_4d = output_dir / "var_filtered_func_data"
    dof_4d = output_dir / "dof_var_filtered_func_data"
    mask_4d = output_dir / "mask_inputs"
    mask = output_dir / "mask"
    stats_dir = output_dir / "stats"

    click.echo("Merging COPEs:")
    _run([fslmerge, "-t", str(cope_4d), *map(str, cope_files)], cwd, dry_run)
    click.echo("Merging VARCOPEs:")
    _run([fslmerge, "-t", str(varcope_4d), *map(str, varcope_files)], cwd, dry_run)

    dof_images: list[Path] = []
    for i, (varcope, feat_dir) in enumerate(zip(varcope_files, feat_dirs), 1):
        dof = _read_first_level_dof(feat_dir)
        root = output_dir / f"dofvarcope_input_{i:03d}"
        click.echo(f"Creating DOF image {i}: dof={dof:g}")
        _run([fslmaths, str(varcope), "-mul", "0", "-add", f"{dof:g}", str(root)], cwd, dry_run)
        dof_images.append(Path(str(root) + ".nii.gz"))

    click.echo("Merging DOF images:")
    _run([fslmerge, "-t", str(dof_4d), *map(str, dof_images)], cwd, dry_run)

    masks = [_existing_nifti(feat_dir / "mask") for feat_dir in feat_dirs]
    click.echo("Creating intersection mask:")
    _run([fslmerge, "-t", str(mask_4d), *map(str, masks)], cwd, dry_run)
    _run([fslmaths, str(mask_4d), "-Tmin", "-bin", str(mask)], cwd, dry_run)

    design_mat = output_dir / "design.mat"
    design_con = output_dir / "design.con"
    design_grp = output_dir / "design.grp"
    if not dry_run:
        _write_vest_matrix(design_mat, [[1.0] for _ in range(n_inputs)])
        _write_vest_contrast(design_con, canonical_name)
        _write_vest_matrix(design_grp, [[1.0] for _ in range(n_inputs)])
        rows.to_csv(output_dir / "inputs.tsv", sep="\t", index=False)

    click.echo("Running FLAME fixed effects:")
    command = [
        flameo,
        f"--copefile={cope_4d}",
        f"--varcopefile={varcope_4d}",
        f"--dofvarcopefile={dof_4d}",
        f"--maskfile={mask}",
        f"--designfile={design_mat}",
        f"--tcontrastsfile={design_con}",
        f"--covsplitfile={design_grp}",
        "--runmode=fe",
        f"--ld={stats_dir}",
    ]
    _run(command, cwd, dry_run)

    if not dry_run:
        metadata = {
            "canonical_name": canonical_name,
            "number_of_inputs": n_inputs,
            "run_labels": rows["run_label"].astype(str).tolist(),
            "first_level_contrast_names": rows["contrast_name"].astype(str).tolist(),
        }
        (output_dir / "analysis.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )

    return {
        "number_of_inputs": n_inputs,
        "second_level_dir": str(output_dir),
        "cope_file": str(stats_dir / "cope1.nii.gz"),
        "varcope_file": str(stats_dir / "varcope1.nii.gz"),
        "tstat_file": str(stats_dir / "tstat1.nii.gz"),
        "zstat_file": str(stats_dir / "zstat1.nii.gz"),
    }


def write_group_file(path: Path, number_of_subjects: int) -> None:
    """Write one variance group containing all subjects."""
    _write_vest_matrix(path, [[1.0] for _ in range(number_of_subjects)])


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    dry_run: bool,
) -> None:
    click.echo("  " + shlex.join([str(value) for value in command]))

    if not dry_run:
        subprocess.run(
            [str(value) for value in command],
            check=True,
            cwd=str(cwd),
        )    


def detect_manifest_level(
    manifest: pd.DataFrame,
    requested_level: str,
) -> str:
    missing_common = COMMON_REQUIRED_COLUMNS - set(manifest.columns)
    if missing_common:
        raise click.ClickException(
            "Manifest is missing required columns: "
            + ", ".join(sorted(missing_common))
        )

    if requested_level in {"1", "2"}:
        return requested_level

    level2_score = len(LEVEL2_HINT_COLUMNS & set(manifest.columns))
    level1_score = len(LEVEL1_HINT_COLUMNS & set(manifest.columns))

    if level2_score > level1_score:
        return "2"

    if level1_score > 0:
        return "1"

    raise click.ClickException(
        "Could not determine whether the manifest is from call_feat or "
        "call_feat2. Use --input-level 1 or --input-level 2 explicitly."
    )


def analysis_dir_from_row(row: pd.Series, input_level: str) -> Path:
    if input_level == "2":
        value = row.get("second_level_dir", "")
        if value:
            return Path(value).resolve()

    value = row.get("feat_dir", "")
    if value:
        return Path(value).resolve()

    # Both manifests store cope images inside <analysis>/stats/.
    return Path(row["cope_file"]).resolve().parent.parent


def parse_group_contrast(
    specification: str,
    column_names: Sequence[str],
) -> tuple[str, list[float]]:
    """
    Parse NAME;w1,w2,... for the group design columns.

    Example:
        AgePositive;0,1
    when columns are Intercept, age.
    """
    fields = [field.strip() for field in specification.split(";")]

    if len(fields) != 2:
        raise click.ClickException(
            "--group-contrast must use 'Name;w1,w2,...'."
        )

    name, weights_text = fields
    if not name:
        raise click.ClickException("Group contrast names cannot be empty.")

    try:
        weights = [
            float(value.strip())
            for value in weights_text.split(",")
            if value.strip()
        ]
    except ValueError as error:
        raise click.ClickException(
            f"Group contrast {name!r} contains a non-numeric weight."
        ) from error

    if len(weights) != len(column_names):
        raise click.ClickException(
            f"Group contrast {name!r} has {len(weights)} weights, but the "
            f"design has {len(column_names)} columns: "
            + ", ".join(column_names)
        )

    if not any(weight != 0 for weight in weights):
        raise click.ClickException(
            f"Group contrast {name!r} is all zero."
        )

    return name, weights


def prepare_group_design(
    *,
    subjects: Sequence[str],
    covariates_file: Path | None,
    covariate_names: Sequence[str],
    demean_covariates: bool,
    group_contrast_specs: Sequence[str],
) -> tuple[list[str], list[list[float]], list[str], list[list[float]], pd.DataFrame]:
    """
    Create the cross-subject design matrix and T contrasts.

    The intercept is always the first design column.
    """
    subject_table = pd.DataFrame({"subject": list(subjects)})
    design_columns = ["Intercept"]
    design_matrix = [[1.0] for _ in subjects]

    if covariates_file is not None:
        covariates = pd.read_csv(
            covariates_file,
            sep="\t",
            dtype={"subject": str},
        )

        if "subject" not in covariates.columns:
            raise click.ClickException(
                f"Covariates file requires a 'subject' column: "
                f"{covariates_file}"
            )

        if covariates["subject"].duplicated().any():
            duplicates = sorted(
                covariates.loc[
                    covariates["subject"].duplicated(keep=False),
                    "subject",
                ].unique()
            )
            raise click.ClickException(
                "Covariates file contains duplicate subjects: "
                + ", ".join(duplicates)
            )

        requested_covariates = list(covariate_names)
        if not requested_covariates:
            requested_covariates = [
                column
                for column in covariates.columns
                if column != "subject"
            ]

        if not requested_covariates:
            raise click.ClickException(
                "No covariate columns were selected."
            )

        missing_columns = [
            column
            for column in requested_covariates
            if column not in covariates.columns
        ]
        if missing_columns:
            raise click.ClickException(
                "Covariates file is missing columns: "
                + ", ".join(missing_columns)
            )

        covariates = covariates[
            ["subject", *requested_covariates]
        ].copy()

        subject_table = subject_table.merge(
            covariates,
            on="subject",
            how="left",
            validate="one_to_one",
        )

        missing_subjects = subject_table.loc[
            subject_table[requested_covariates].isna().any(axis=1),
            "subject",
        ].tolist()
        if missing_subjects:
            raise click.ClickException(
                "Missing covariate values for subjects: "
                + ", ".join(missing_subjects)
            )

        for covariate_name in requested_covariates:
            values = pd.to_numeric(
                subject_table[covariate_name],
                errors="raise",
            ).astype(float)

            if demean_covariates:
                values = values - values.mean()

            if values.nunique(dropna=False) <= 1:
                raise click.ClickException(
                    f"Covariate {covariate_name!r} is constant for the "
                    "selected subjects."
                )

            design_columns.append(covariate_name)

            for row_index, value in enumerate(values.tolist()):
                design_matrix[row_index].append(float(value))

            subject_table[covariate_name] = values

    if group_contrast_specs:
        parsed = [
            parse_group_contrast(specification, design_columns)
            for specification in group_contrast_specs
        ]
        contrast_names = [name for name, _weights in parsed]
        contrast_matrix = [weights for _name, weights in parsed]
    else:
        contrast_names = ["GroupMean"]
        contrast_matrix = [
            [1.0] + [0.0] * (len(design_columns) - 1)
        ]

    return (
        design_columns,
        design_matrix,
        contrast_names,
        contrast_matrix,
        subject_table,
    )


def build_intersection_mask(
    *,
    analysis_dirs: Sequence[Path],
    output_dir: Path,
    dry_run: bool,
) -> Path:
    fslmerge = _require_fsl_command("fslmerge")
    fslmaths = _require_fsl_command("fslmaths")

    masks = [
        _existing_nifti(analysis_dir / "mask")
        for analysis_dir in analysis_dirs
    ]

    masks_4d = output_dir / "mask_inputs"
    output_mask = output_dir / "mask"

    click.echo("Creating intersection mask:")
    run_command(
        [fslmerge, "-t", str(masks_4d), *map(str, masks)],
        cwd=output_dir.parent if dry_run else output_dir,
        dry_run=dry_run,
    )
    run_command(
        [fslmaths, str(masks_4d), "-Tmin", "-bin", str(output_mask)],
        cwd=output_dir.parent if dry_run else output_dir,
        dry_run=dry_run,
    )

    return Path(str(output_mask) + ".nii.gz")


def build_intersection_mask_from_files(
    *,
    mask_files: Sequence[Path],
    output_dir: Path,
    dry_run: bool,
) -> Path:
    """Create an intersection mask from resolved subject masks."""
    fslmerge = _require_fsl_command("fslmerge")
    fslmaths = _require_fsl_command("fslmaths")

    masks_4d = output_dir / "mask_inputs"
    output_mask = output_dir / "mask"
    command_cwd = output_dir.parent if dry_run else output_dir

    click.echo("Creating intersection mask:")
    run_command(
        [fslmerge, "-t", str(masks_4d), *map(str, mask_files)],
        cwd=command_cwd,
        dry_run=dry_run,
    )
    run_command(
        [fslmaths, str(masks_4d), "-Tmin", "-bin", str(output_mask)],
        cwd=command_cwd,
        dry_run=dry_run,
    )

    return Path(str(output_mask) + ".nii.gz")


def run_cross_subject_analysis(
    *,
    rows: pd.DataFrame,
    input_level: str,
    output_dir: Path,
    canonical_name: str,
    runmode: str,
    covariates_file: Path | None,
    covariate_names: Sequence[str],
    demean_covariates: bool,
    group_contrast_specs: Sequence[str],
    registration_mode: str,
    registered_subdir: str,
    overwrite: bool,
    dry_run: bool,
) -> list[dict[str, Any]]:
    fslmerge = _require_fsl_command("fslmerge")
    flameo = _require_fsl_command("flameo")

    if output_dir.exists():
        if overwrite:
            click.echo(f"Removing existing group output: {output_dir}")
            if not dry_run:
                shutil.rmtree(output_dir)
        else:
            raise click.ClickException(
                f"Group output already exists: {output_dir}. "
                "Use --overwrite to replace it."
            )

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=False)

    command_cwd = output_dir if not dry_run else output_dir.parent

    rows = rows.copy()
    rows["subject"] = rows["subject"].astype(str)

    # A highest-level model must have exactly one independent observation per
    # subject for a given canonical contrast.
    duplicate_subjects = sorted(
        rows.loc[
            rows["subject"].duplicated(keep=False),
            "subject",
        ].unique()
    )
    if duplicate_subjects:
        if input_level == "1":
            raise click.ClickException(
                "The level-1 manifest contains multiple inputs for these "
                "subjects: "
                + ", ".join(duplicate_subjects)
                + ". Combine their runs with call_feat2 first, then pass "
                "contrast_manifest_level2.tsv to call_feat3."
            )

        raise click.ClickException(
            "The level-2 manifest contains duplicate subject estimates: "
            + ", ".join(duplicate_subjects)
        )

    rows = rows.sort_values("subject", kind="stable").reset_index(drop=True)
    subjects = rows["subject"].tolist()

    if len(subjects) < 2:
        raise click.ClickException(
            "Cross-subject analysis requires at least two subjects."
        )

    resolved_inputs = [
        resolve_registered_input(
            row=row,
            input_level=input_level,
            registration_mode=registration_mode,
            registered_subdir=registered_subdir,
            dry_run=dry_run,
        )
        for _, row in rows.iterrows()
    ]

    cope_files = [item[0] for item in resolved_inputs]
    varcope_files = [item[1] for item in resolved_inputs]
    mask_files = [item[2] for item in resolved_inputs]
    analysis_dirs = [item[3] for item in resolved_inputs]

    if dry_run and registration_mode == "featregapply":
        click.echo(
            "Geometry validation deferred until featregapply creates "
            "registered outputs."
        )
    else:
        verify_group_geometry(
            cope_files,
            varcope_files,
            mask_files,
        )

    (
        design_columns,
        design_matrix,
        contrast_names,
        contrast_matrix,
        subject_table,
    ) = prepare_group_design(
        subjects=subjects,
        covariates_file=covariates_file,
        covariate_names=covariate_names,
        demean_covariates=demean_covariates,
        group_contrast_specs=group_contrast_specs,
    )

    click.echo(f"Subjects: {len(subjects)}")
    click.echo("Design columns: " + ", ".join(design_columns))
    click.echo("Group contrasts:")
    for index, (name, weights) in enumerate(
        zip(contrast_names, contrast_matrix),
        start=1,
    ):
        click.echo(
            f"  {index:2d}. {name}: "
            + ", ".join(f"{weight:g}" for weight in weights)
        )

    click.echo("Subject inputs:")
    for index, (_, row) in enumerate(rows.iterrows(), start=1):
        source = (
            row.get("run_label", "")
            or row.get("second_level_dir", "")
            or row["cope_file"]
        )
        click.echo(
            f"  {index:2d}. sub-{row['subject']}: {source}"
        )

    cope_4d = output_dir / "cope_inputs"
    varcope_4d = output_dir / "varcope_inputs"
    stats_dir = output_dir / "stats"

    click.echo("Merging subject COPE images:")
    run_command(
        [fslmerge, "-t", str(cope_4d), *map(str, cope_files)],
        cwd=command_cwd,
        dry_run=dry_run,
    )

    click.echo("Merging subject VARCOPE images:")
    run_command(
        [fslmerge, "-t", str(varcope_4d), *map(str, varcope_files)],
        cwd=command_cwd,
        dry_run=dry_run,
    )

    group_mask_file = build_intersection_mask_from_files(
        mask_files=mask_files,
        output_dir=output_dir,
        dry_run=dry_run,
    )

    design_mat = output_dir / "design.mat"
    design_con = output_dir / "design.con"
    design_grp = output_dir / "design.grp"

    if not dry_run:
        _write_vest_matrix(design_mat, design_matrix)
        _write_vest_contrast(
            design_con,
            contrast_names,
            contrast_matrix,
        )
        write_group_file(design_grp, len(subjects))

        subject_table.to_csv(
            output_dir / "subjects.tsv",
            sep="\t",
            index=False,
        )

        input_records = []
        for (
            (_, row),
            cope_file,
            varcope_file,
            subject_mask_file,
            analysis_dir,
        ) in zip(
            rows.iterrows(),
            cope_files,
            varcope_files,
            mask_files,
            analysis_dirs,
        ):
            input_records.append(
                {
                    "subject": row["subject"],
                    "session": _entity_text(row["session"]),
                    "task": _entity_text(row["task"]),
                    "canonical_name": canonical_name,
                    "input_level": input_level,
                    "analysis_dir": str(analysis_dir),
                    "registration_mode": registration_mode,
                    "registered_subdir": registered_subdir,
                    "cope_file": str(cope_file),
                    "varcope_file": str(varcope_file),
                    "mask_file": str(subject_mask_file),
                }
            )

        pd.DataFrame.from_records(input_records).to_csv(
            output_dir / "inputs.tsv",
            sep="\t",
            index=False,
        )

    click.echo(f"Running cross-subject model ({runmode}):")
    flameo_command = [
        flameo,
        f"--copefile={cope_4d}",
        f"--varcopefile={varcope_4d}",
        f"--maskfile={group_mask_file}",
        f"--designfile={design_mat}",
        f"--tcontrastsfile={design_con}",
        f"--covsplitfile={design_grp}",
        f"--runmode={runmode}",
        f"--ld={stats_dir}",
    ]
    run_command(
        flameo_command,
        cwd=command_cwd,
        dry_run=dry_run,
    )

    if not dry_run:
        metadata = {
            "input_level": input_level,
            "canonical_name": canonical_name,
            "number_of_subjects": len(subjects),
            "subjects": subjects,
            "runmode": runmode,
            "registration_mode": registration_mode,
            "registered_subdir": registered_subdir,
            "design_columns": design_columns,
            "group_contrasts": [
                {"name": name, "weights": weights}
                for name, weights in zip(
                    contrast_names,
                    contrast_matrix,
                )
            ],
        }
        (output_dir / "analysis.json").write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )

    records: list[dict[str, Any]] = []
    for contrast_index, contrast_name in enumerate(
        contrast_names,
        start=1,
    ):
        records.append(
            {
                "session": _entity_text(rows.iloc[0]["session"]),
                "task": _entity_text(rows.iloc[0]["task"]),
                "canonical_name": canonical_name,
                "group_contrast": contrast_name,
                "input_level": input_level,
                "runmode": runmode,
                "registration_mode": registration_mode,
                "registered_subdir": registered_subdir,
                "number_of_subjects": len(subjects),
                "group_dir": str(output_dir),
                "cope_file": str(
                    stats_dir / f"cope{contrast_index}.nii.gz"
                ),
                "varcope_file": str(
                    stats_dir / f"varcope{contrast_index}.nii.gz"
                ),
                "tstat_file": str(
                    stats_dir / f"tstat{contrast_index}.nii.gz"
                ),
                "zstat_file": str(
                    stats_dir / f"zstat{contrast_index}.nii.gz"
                ),
            }
        )

    return records


def resolve_registered_input(
    *,
    row: pd.Series,
    input_level: str,
    registration_mode: str,
    registered_subdir: str,
    dry_run: bool,
) -> tuple[Path, Path, Path, Path]:
    """Resolve COPE, VARCOPE, mask, and source analysis directory."""
    analysis_dir = analysis_dir_from_row(row, input_level)

    if registration_mode == "prealigned":
        return (
            _existing_nifti(Path(row["cope_file"])),
            _existing_nifti(Path(row["varcope_file"])),
            _existing_nifti(analysis_dir / "mask"),
            analysis_dir,
        )

    if registration_mode == "featregapply":
        featregapply = _require_fsl_command("featregapply")
        click.echo(f"Applying FEAT registration: {analysis_dir}")
        run_command(
            [featregapply, str(analysis_dir)],
            cwd=analysis_dir,
            dry_run=dry_run,
        )

    registered_dir = analysis_dir / registered_subdir

    cope_text = str(row.get("cope", "")).strip()
    if cope_text:
        try:
            cope_number = int(float(cope_text))
        except ValueError as error:
            raise click.ClickException(
                f"Invalid cope number {cope_text!r} for {analysis_dir}"
            ) from error
    else:
        # call_feat2 produces one subject-level COPE for each canonical effect.
        cope_number = 1

    if dry_run and registration_mode == "featregapply":
        return (
            registered_dir / "stats" / f"cope{cope_number}.nii.gz",
            registered_dir / "stats" / f"varcope{cope_number}.nii.gz",
            registered_dir / "mask.nii.gz",
            analysis_dir,
        )

    return (
        _existing_nifti(registered_dir / "stats" / f"cope{cope_number}"),
        _existing_nifti(registered_dir / "stats" / f"varcope{cope_number}"),
        _existing_nifti(registered_dir / "mask"),
        analysis_dir,
    )


def verify_matching_geometry(
    reference_path: Path,
    candidate_path: Path,
    *,
    description: str,
    affine_tolerance: float = 1e-5,
) -> None:
    """Require matching 3D dimensions and affine matrices."""
    reference = nib.load(str(reference_path))
    candidate = nib.load(str(candidate_path))

    if reference.shape[:3] != candidate.shape[:3]:
        raise click.ClickException(
            f"{description} dimensions differ:\n"
            f"  reference: {reference_path} {reference.shape[:3]}\n"
            f"  candidate: {candidate_path} {candidate.shape[:3]}"
        )

    if not np.allclose(
        reference.affine,
        candidate.affine,
        rtol=0.0,
        atol=affine_tolerance,
    ):
        raise click.ClickException(
            f"{description} affine matrices differ:\n"
            f"  reference: {reference_path}\n"
            f"  candidate: {candidate_path}"
        )


def verify_group_geometry(
    cope_files: Sequence[Path],
    varcope_files: Sequence[Path],
    mask_files: Sequence[Path],
) -> None:
    """Validate within-subject and across-subject image geometry."""
    if not cope_files:
        raise click.ClickException("No group inputs were supplied.")

    for cope_file, varcope_file, mask_file in zip(
        cope_files,
        varcope_files,
        mask_files,
    ):
        verify_matching_geometry(
            cope_file,
            varcope_file,
            description="COPE/VARCOPE",
        )
        verify_matching_geometry(
            cope_file,
            mask_file,
            description="COPE/mask",
        )

    for path in cope_files[1:]:
        verify_matching_geometry(
            cope_files[0],
            path,
            description="Cross-subject COPE",
        )

    for path in varcope_files[1:]:
        verify_matching_geometry(
            varcope_files[0],
            path,
            description="Cross-subject VARCOPE",
        )

    for path in mask_files[1:]:
        verify_matching_geometry(
            mask_files[0],
            path,
            description="Cross-subject mask",
        )

    click.echo("✓ All group inputs share a common voxel grid and affine")
