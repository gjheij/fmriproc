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
    """
    Determine the next available working directory for a contrast update.

    Contrast updates are stored as monotonically numbered subdirectories named
    ``contrast_update_NNN`` within the run-level working directory. Existing
    directories matching this naming convention are inspected, their numeric
    suffixes are parsed, and the next integer after the largest existing suffix is
    returned.

    Directories whose names begin with ``contrast_update_`` but do not contain a
    valid integer suffix are ignored.

    Parameters
    ----------
    base_work_dir : pathlib.Path
        Run-level working directory containing zero or more
        ``contrast_update_NNN`` subdirectories.

    Returns
    -------
    pathlib.Path
        Path for the next contrast-update directory. The directory is not created
        by this function.

    Notes
    -----
    The returned index is based on directory names rather than the presence or
    validity of files inside those directories. Consumers that need the latest
    *valid* contrast update should use `_latest_run_contrasts_json` instead.

    Examples
    --------
    If ``base_work_dir`` contains ``contrast_update_001`` and
    ``contrast_update_004``, this function returns a path ending in
    ``contrast_update_005``.
    """
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
    """
    Normalize a subject identifier by removing an optional ``sub-`` prefix.

    Parameters
    ----------
    subject : str
        Subject identifier, optionally prefixed with the BIDS ``sub-`` entity
        prefix.

    Returns
    -------
    str
        Subject identifier without the leading ``sub-`` prefix.

    Examples
    --------
    ``"sub-22"`` becomes ``"22"``, whereas ``"22"`` is returned unchanged.
    """
    return subject[4:] if subject.startswith("sub-") else subject


def entity_label(entities: dict[str, Any]) -> str:
    """
    Construct a human-readable BIDS-style label from run entities.

    The label always contains subject and task entities and conditionally includes
    session, acquisition, direction, echo, and run entities when those values are
    present. The result is intended primarily for logging, run identification, and
    manifest bookkeeping.

    Parameters
    ----------
    entities : dict[str, Any]
        Mapping containing BIDS entities. ``subject`` and ``task`` are expected to
        be present. Optional recognized keys include ``session``, ``acquisition``,
        ``direction``, ``echo``, and ``run``.

    Returns
    -------
    str
        Underscore-separated BIDS-like entity label.

    Raises
    ------
    KeyError
        If a required ``subject`` or ``task`` entry is absent.

    Examples
    --------
    An entity mapping containing subject ``22``, session ``1``, task ``SC2F``, and
    run ``3`` produces ``sub-22_ses-1_task-SC2F_run-3``.
    """
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
    """
    Extract BIDS entities suitable for locating files belonging to one BOLD run.

    Only entities that identify the acquisition/run independently of a particular
    derivative suffix or description are retained. Missing or ``None`` values are
    omitted from the returned mapping.

    Parameters
    ----------
    entities : dict[str, Any]
        Complete entity mapping for a BOLD or derivative file.
    include_space : bool, optional
        If ``True``, include the ``space`` entity when available. By default,
        spatial normalization is excluded so sidecars without a space entity can
        still be located.

    Returns
    -------
    dict[str, Any]
        Filtered entity mapping containing available values among ``subject``,
        ``session``, ``task``, ``acquisition``, ``direction``,
        ``reconstruction``, ``run``, ``echo``, ``part``, and optionally
        ``space``.

    Notes
    -----
    The function deliberately omits suffix-, datatype-, description-, and
    extension-specific entities because those are normally supplied separately to
    a BIDS query.
    """
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
    """
    Parse one command-line T-contrast specification.

    The accepted syntax is::

        NAME;T;condition1,condition2;weight1,weight2[;canonical_name]

    Inline contrasts are restricted to T contrasts. Condition and weight lists
    must contain the same number of entries, and all weights must be convertible
    to floating-point values.

    Parameters
    ----------
    spec : str
        Semicolon-delimited contrast specification supplied by the user.

    Returns
    -------
    dict[str, Any]
        Parsed contrast with keys ``name``, ``type``, ``conditions``,
        ``weights``, and ``canonical_name``. Weights are returned as floats and
        the statistic type is normalized to ``"T"``.

    Raises
    ------
    click.ClickException
        If the specification contains the wrong number of fields, has empty
        required fields, requests a non-T statistic, contains unequal numbers of
        conditions and weights, or contains non-numeric weights.

    Notes
    -----
    When the optional canonical name is omitted, the contrast name itself is used
    as the canonical higher-level name.
    """
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
    """
    Create one event-versus-implicit-baseline T contrast per condition.

    Each supplied condition becomes an independent T contrast with a single
    weight of ``1.0``. The contrast name and canonical higher-level name are both
    the original condition name.

    Parameters
    ----------
    conditions : Sequence[str]
        Condition or explanatory-variable names present in the first-level model.

    Returns
    -------
    contrasts : list[tuple[Any, ...]]
        Contrast tuples in Nipype/FSL form:
        ``(name, "T", [condition], [1.0])``.
    canonical_names : dict[str, str]
        Mapping from each generated contrast name to the same condition name.

    Notes
    -----
    These contrasts test each modelled event against FSL's implicit baseline; they
    do not construct pairwise condition comparisons.
    """
    contrasts = [(condition, "T", [condition], [1.0]) for condition in conditions]
    canonical_names = {condition: condition for condition in conditions}
    return contrasts, canonical_names


def load_contrasts(
    path: str | None,
    inline_specs: Sequence[str] = (),
) -> tuple[list[tuple[Any, ...]], dict[str, str]]:
    """
    Load and normalize user-defined statistical contrasts.

    Contrasts may be supplied from a JSON file or from previously parsed inline
    specifications. JSON contrasts may use either positional list form or mapping
    form. An optional canonical name allows differently named first-level
    contrasts to map onto a common higher-level contrast identity.

    Parameters
    ----------
    path : str or None
        Path to a JSON contrast definition file. Must be ``None`` when
        ``inline_specs`` is non-empty.
    inline_specs : Sequence[str], optional
        Inline contrast specifications accepted by `parse_inline_contrast`.

    Returns
    -------
    contrasts : list[tuple[Any, ...]]
        Normalized contrast tuples suitable for the first-level model. T-contrast
        weights are converted to floats.
    canonical_names : dict[str, str]
        Mapping from each local contrast name to its canonical higher-level name.

    Raises
    ------
    click.ClickException
        If file and inline specifications are supplied simultaneously, a
        definition has an unsupported structure or statistic type, duplicate
        names occur, required mapping keys are missing, or T-contrast conditions
        and weights differ in length.
    json.JSONDecodeError
        If the supplied JSON file is not valid JSON.

    Notes
    -----
    T and F contrasts are accepted from JSON. Inline command-line contrasts are
    restricted to T contrasts by `parse_inline_contrast`.
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
    """
    Identify T-contrast conditions that are unavailable in a run.

    Parameters
    ----------
    contrasts : Sequence[tuple[Any, ...]]
        Contrast definitions containing name, statistic, referenced conditions,
        and weights.
    conditions : Sequence[str]
        Condition names available in the current first-level run.

    Returns
    -------
    set[str]
        Union of all condition names referenced by T contrasts but absent from the
        run.

    Notes
    -----
    F contrasts are ignored by this validation step because their estimability is
    handled separately by `filter_estimable_contrasts`.
    """
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
    """
    Resolve confound-selection options into regular expressions.

    For fMRIPrep ``timeseries`` confounds, named presets are translated through
    ``CONFOUND_OPTIONS`` and arbitrary user expressions are accepted directly.
    The special ``ENIGMA`` preset expands to the predefined ENIGMA confound
    categories. Duplicate expressions are removed while preserving order.

    Parameters
    ----------
    no_confounds : bool
        Disable confound loading entirely when ``True``.
    confounds_suffix : str
        Confound-file suffix. Supported values are ``"timeseries"``, ``"physio"``,
        and ``"custom"``.
    confound_subtype : str
        Named preset, comma-separated presets/regular expressions, or ``ENIGMA``
        for ``timeseries`` files.
    extra_regexes : Sequence[str], optional
        Additional regular expressions supplied independently of
        ``confound_subtype``.

    Returns
    -------
    list[str] or None
        Ordered regular expressions for ``timeseries`` confounds. ``None`` means
        either that confounds are disabled or that every numeric column should be
        considered for ``physio``/``custom`` inputs.

    Raises
    ------
    click.ClickException
        If a regular expression is invalid, no timeseries confounds are selected,
        extra regular expressions are used with an unsupported suffix, or
        ``confounds_suffix`` is unsupported.

    Notes
    -----
    The function emits a short description of the resolved confound strategy to
    the Click log.
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
    """
    Validate HRF basis options and construct a Nipype Level1Design basis mapping.

    Supported basis families are FSL double-gamma, gamma, custom basis functions,
    and no convolution. Option combinations that are incompatible with the
    selected basis are rejected before model construction.

    Parameters
    ----------
    basis_name : str
        Basis family. Supported values are ``"dgamma"``, ``"gamma"``,
        ``"custom"``, and ``"none"``.
    derivatives : bool
        Include temporal derivatives where supported.
    gamma_sigma : float or None
        Gamma-function sigma parameter. Valid only for the ``gamma`` basis.
    gamma_delay : float or None
        Gamma-function delay parameter. Valid only for the ``gamma`` basis.
    custom_path : pathlib.Path or None
        Path to a custom FSL basis function file. Required only for the
        ``custom`` basis.

    Returns
    -------
    dict[str, Any]
        Basis dictionary suitable for ``nipype.interfaces.fsl.Level1Design``.

    Raises
    ------
    click.ClickException
        If unsupported options are combined, a required custom basis file is not
        specified, derivatives are requested for unsupported basis types, or the
        basis name is unknown.
    """
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
    """
    Execute a BIDS query expected to resolve to at most one file.

    Parameters
    ----------
    layout : bids.BIDSLayout
        Initialized BIDS layout used for the query.
    description : str
        Human-readable description included in error messages.
    required : bool, optional
        If ``True``, absence of a matching file is an error. If ``False``, return
        ``None`` when no match exists.
    **query : Any
        Entity and metadata filters forwarded to ``BIDSLayout.get``.

    Returns
    -------
    str or None
        Absolute path to the unique matched file, or ``None`` when no file is
        found and ``required`` is ``False``.

    Raises
    ------
    click.ClickException
        If a required file is absent or more than one unique file matches the
        query.

    Notes
    -----
    Duplicate paths returned by the BIDS layout are collapsed before uniqueness
    is checked.
    """
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
    """
    Select DataFrame columns using full regular-expression matches.

    Parameters
    ----------
    dataframe : pandas.DataFrame
        Table whose column names will be tested.
    regexes : Iterable[str]
        Regular expressions. A column is selected when any expression fully
        matches its complete name.

    Returns
    -------
    list[str]
        Matching column names in their original DataFrame order.

    Notes
    -----
    Expressions are compiled once before scanning the columns. Matching uses
    ``Pattern.fullmatch`` rather than substring matching.
    """
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
    Filter contrast definitions to those estimable for the current run.

    A T contrast is retained only when all of its referenced conditions are
    available. An F contrast is retained only when all T contrasts that it
    references survive the T-contrast filtering step.

    Parameters
    ----------
    contrasts : Sequence[tuple[Any, ...]]
        T and/or F contrast definitions.
    available_conditions : Sequence[str]
        Conditions represented by the current run's design.

    Returns
    -------
    estimable_contrasts : list[tuple[Any, ...]]
        T contrasts followed by F contrasts that remain estimable.
    skipped_names : list[str]
        Descriptions of skipped contrasts. Missing conditions are included in the
        description for T contrasts.

    Notes
    -----
    The function permits a common contrast specification to be applied across
    runs that do not necessarily contain identical event sets, while preventing
    invalid contrast vectors from reaching FEAT.
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
    """
    Locate the authoritative contrast manifest for one run working directory.

    Contrast-update manifests take precedence over the original run-level
    ``contrasts.json``. Among updates, the manifest from the highest numeric
    ``contrast_update_NNN`` directory that actually contains a
    ``contrasts.json`` file is selected.

    Parameters
    ----------
    run_work_dir : pathlib.Path
        Run-level directory under the derivative ``work`` tree.

    Returns
    -------
    pathlib.Path or None
        Path to the preferred ``contrasts.json`` file, or ``None`` when neither an
        update manifest nor an original run manifest exists.

    Notes
    -----
    Update directories without ``contrasts.json`` are deliberately ignored. This
    prevents incomplete or dry-run update directories from superseding the last
    completed contrast definition.
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
    """
    Check whether a recovered contrast-manifest record still references real data.

    A record is considered usable only when it contains non-empty ``feat_dir``,
    ``cope_file``, and ``varcope_file`` values, the FEAT directory currently
    exists, and both statistical images currently exist as files.

    Parameters
    ----------
    record : dict[str, Any]
        One serialized contrast-manifest record.

    Returns
    -------
    bool
        ``True`` when the referenced FEAT directory, COPE, and VARCOPE all exist;
        otherwise ``False``.

    Notes
    -----
    This check prevents deleted or moved analyses from being resurrected when the
    dataset-wide manifest is reconstructed from historical work directories.
    """
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
    """
    Load and validate records from one run-level ``contrasts.json`` file.

    Malformed files and records are skipped with warnings. Valid records must be
    mapping objects, contain a ``run_label``, and reference currently existing
    FEAT, COPE, and VARCOPE outputs.

    Parameters
    ----------
    path : pathlib.Path
        Path to a run-level or contrast-update ``contrasts.json``.

    Returns
    -------
    list[dict[str, Any]]
        Valid, filesystem-backed manifest records copied from the JSON payload.

    Notes
    -----
    An unreadable JSON file, non-list top-level object, malformed record, missing
    run label, or stale output reference does not propagate into the rebuilt
    dataset manifest.

    The function is intentionally conservative because work directories may
    outlive the corresponding derivative outputs.
    """
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
    """
    Reconstruct dataset-level contrast state from completed run work directories.

    Every immediate subdirectory of ``<deriv_dir>/work`` is treated as a
    candidate run. For each run, `_latest_run_contrasts_json` determines the
    authoritative manifest, preferring the highest completed contrast update.
    Records whose referenced FEAT/COPE/VARCOPE outputs no longer exist are
    discarded.

    Parameters
    ----------
    deriv_dir : pathlib.Path
        Root directory of the level-1 FEAT derivatives.

    Returns
    -------
    pandas.DataFrame
        Reconstructed manifest table. An empty DataFrame is returned when no work
        tree or no usable records are available.

    Notes
    -----
    Duplicate ``run_label``/``cope`` pairs are reduced to the last selected
    record. List-valued ``conditions`` and ``weights`` are serialized as compact
    JSON strings to match the dataset TSV representation.

    The function reports the number of usable run manifests and stale manifests
    encountered during reconstruction.
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
    """
    Normalize the schema and ordering of a contrast-manifest table.

    The canonical manifest columns are created when absent, existing additional
    columns are retained, missing values are converted to empty strings, and all
    columns are normalized to string representation.

    Rows are sorted deterministically using numeric-aware subject, session, run,
    and cope keys while preserving textual labels as secondary sort keys.

    Parameters
    ----------
    table : pandas.DataFrame
        Contrast-manifest table to normalize.

    Returns
    -------
    pandas.DataFrame
        Normalized and deterministically ordered table.

    Notes
    -----
    Temporary numeric sort columns are discarded before returning. Numeric-aware
    sorting ensures, for example, that run 10 follows run 9 rather than run 1.
    """
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
    """
    Rebuild the dataset-wide ``contrast_manifest.tsv`` from existing analyses.

    The level-1 work tree is scanned for run-level contrast provenance. The newest
    completed contrast-update manifest is preferred for each run, stale records
    whose FEAT/COPE/VARCOPE files have disappeared are excluded, and the resulting
    table is normalized before being written.

    Parameters
    ----------
    deriv_dir : pathlib.Path
        Root directory containing the level-1 derivatives and ``work`` directory.
    dry_run : bool, optional
        If ``True``, report the intended rebuild without reading/writing the
        manifest state.

    Returns
    -------
    pathlib.Path
        Path to the dataset-wide ``contrast_manifest.tsv``.

    Raises
    ------
    click.ClickException
        If no usable contrast records can be reconstructed.

    Notes
    -----
    The rebuild acquires the same advisory ``fcntl`` lock used for incremental
    manifest updates. The TSV is written through a process-unique temporary file
    and atomically renamed, making explicit rebuilds safe with respect to
    concurrent manifest writers.
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
    """
    Persist run-level contrast provenance and update the dataset-wide manifest.

    One record is generated for each T contrast, using FSL's T-contrast COPE
    numbering. The exact current run/update mapping is first written to
    ``contrasts.json`` in the run working directory. The dataset-wide
    ``contrast_manifest.tsv`` is then updated under an advisory file lock.

    If the dataset manifest is missing or empty, its previous state is rebuilt
    from completed run work directories before the current run is merged.

    Parameters
    ----------
    work_dir : pathlib.Path
        Working directory for the current run or contrast update.
    deriv_dir : pathlib.Path
        Level-1 derivative root containing ``contrast_manifest.tsv``.
    entities : dict[str, Any]
        BIDS entities for the current run.
    label : str
        Unique run label used to replace stale entries for the same run.
    output_dir : pathlib.Path
        FEAT output directory referenced by generated COPE and VARCOPE records.
    contrasts : Sequence[tuple[Any, ...]]
        Current contrast definitions.
    canonical_names : dict[str, str]
        Mapping from local contrast names to canonical higher-level names.
    dry_run : bool, optional
        If ``True``, return without modifying either manifest.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If no T contrasts are available or an existing/rebuilt dataset manifest
        lacks the required ``run_label`` field.

    Notes
    -----
    The lock covers the complete read/rebuild, merge, write, and rename
    transaction. This prevents lost updates when multiple first-level jobs finish
    in parallel.

    Both JSON and TSV writes use process-unique temporary files followed by
    atomic replacement.
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
    Load nuisance regressors from a tabular confound file.

    The confound table is required to contain exactly one row per BOLD volume.
    Columns may either be selected using regular-expression full matches or, when
    ``regexes`` is ``None``, by retaining every numeric column. Non-finite values
    are replaced with zero and constant regressors are discarded.

    Parameters
    ----------
    confounds_file : str
        Path to a tab-separated confound file.
    regexes : list[str] or None
        Column-selection regular expressions. ``None`` selects all numeric
        columns.
    expected_rows : int
        Expected number of time points, normally the BOLD fourth dimension.
    require_all_regexes : bool
        If ``True``, fail when any requested pattern matches no column. Otherwise
        unmatched expressions generate warnings.

    Returns
    -------
    regressor_names : list[str]
        Selected non-constant column names.
    regressors : list[list[float]]
        Regressor values in Nipype orientation: one inner list per regressor over
        time.

    Raises
    ------
    click.ClickException
        If row counts disagree, required regexes are unmatched, no usable columns
        remain, or all selected columns are constant.

    Notes
    -----
    NaN values commonly introduced by derivative confound columns on the first
    volume are explicitly converted to zero.
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
    Patch run-specific fields in a generated first-level FEAT configuration.

    The generated FSF is made self-contained by explicitly setting its output
    directory, input BOLD file, and spatial smoothing kernel. Optionally,
    preprocessing operations already performed by fMRIPrep are disabled.

    Parameters
    ----------
    fsf_path : str
        Path to the FSF file to modify in place.
    output_dir : str
        FEAT output directory written to ``fmri(outputdir)``.
    bold_file : str
        Input BOLD image written to ``feat_files(1)``.
    disable_feat_preprocessing : bool
        Disable FEAT motion correction, slice timing, brain extraction, and
        registration when ``True``.
    smoothing_fwhm : float
        Spatial smoothing kernel in millimetres FWHM. A value of zero disables
        smoothing.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If ``smoothing_fwhm`` is negative or the generated FSF does not contain an
        expected output-directory setting.

    Notes
    -----
    Registration DOF is kept at a valid menu value even when FEAT registration is
    disabled. The function modifies the supplied FSF in place.
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
    Replace first-level T-contrast definitions in an existing FEAT FSF.

    Existing task EV names and derivative settings are parsed from the FSF.
    Requested contrasts are mapped from named original EVs into both FSL's
    original-EV and real-EV spaces. Existing contrast and F-test declarations are
    removed and a new contrast block is appended.

    Parameters
    ----------
    fsf_path : pathlib.Path
        Existing or copied first-level FSF to update in place.
    contrasts : Sequence[tuple[Any, ...]]
        T-contrast definitions of the form
        ``(name, "T", conditions, weights)`` or a compatible five-field form.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If EV declarations cannot be read, EV names are ambiguous, contrast
        definitions are malformed, non-T contrasts are supplied, names are
        duplicated, conditions are missing, contrast vectors are all zero, or
        original EVs cannot be safely expanded into FEAT's declared real-EV
        dimensionality.

    Notes
    -----
    Temporal derivatives are handled by assigning each original contrast weight
    to the main real EV and assigning zero to its derivative EV.

    Basis expansions more complicated than one optional temporal derivative per
    original EV are rejected rather than silently producing an incorrect
    contrast.

    After this function, ``feat_model`` must be run to regenerate ``design.con``.
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
    """
    Update contrasts in an existing first-level FEAT analysis without refitting the design.

    The existing design specification is copied into a dedicated update working
    directory, contrast definitions are replaced, and ``feat_model`` regenerates
    the associated design files. The regenerated design matrix is required to be
    numerically identical to the original before FILM statistics are replaced.

    Parameters
    ----------
    feat_dir : pathlib.Path
        Existing first-level ``.feat`` directory.
    work_dir : pathlib.Path
        Dedicated ``contrast_update_NNN`` working directory.
    deriv_dir : pathlib.Path
        Level-1 derivative root containing the dataset contrast manifest.
    entities : dict[str, Any]
        BIDS run entities used for manifest records.
    label : str
        Unique run label.
    contrasts : Sequence[tuple]
        New T-contrast definitions.
    canonical_names : Mapping
        Mapping from local contrast names to canonical names.
    dry_run : bool
        If ``True``, create and validate updated design files but do not rerun
        FILM or modify contrast manifests.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If required existing FEAT files are absent or the regenerated design
        matrix differs from the original.
    subprocess.CalledProcessError
        If ``feat_model`` or downstream FSL commands fail.

    Notes
    -----
    The design matrix equality check is a central safety invariant: contrast
    updates are permitted only when the underlying first-level model remains
    unchanged.
    """    
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
    """
    Recover the original ``film_gls`` command from a FEAT statistics logfile.

    Parameters
    ----------
    feat_dir : pathlib.Path
        Existing FEAT directory containing ``stats/logfile``.

    Returns
    -------
    list[str]
        Shell-tokenized original ``film_gls`` command, including the executable.

    Raises
    ------
    click.ClickException
        If ``stats/logfile`` does not exist or no command whose executable basename
        is ``film_gls`` can be found.

    Notes
    -----
    Parsing uses ``shlex.split`` so quoted command-line arguments are preserved
    correctly.
    """
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
    """
    Construct a FILM command for an updated contrast set.

    The original ``film_gls`` invocation is recovered from the FEAT logfile so
    run-specific estimation options are preserved. Arguments identifying the
    input data, output statistics directory, design matrix, and contrast file are
    replaced with paths appropriate to the updated analysis.

    Parameters
    ----------
    feat_dir : pathlib.Path
        Existing FEAT directory.
    new_con_file : pathlib.Path
        Newly generated ``design.con``.

    Returns
    -------
    list[str]
        Command argument vector suitable for ``subprocess.run``.

    Notes
    -----
    Unrecognized or additional original FILM options are intentionally retained.
    Only ``--in``, ``--rn``, ``--pd``, and ``--con`` are replaced.
    """
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
    """
    Back up FEAT design and statistical outputs before a contrast update.

    Parameters
    ----------
    feat_dir : pathlib.Path
        Existing FEAT analysis directory.
    update_work_dir : pathlib.Path
        Contrast-update working directory in which a new ``backup`` directory will
        be created.

    Returns
    -------
    None

    Raises
    ------
    FileExistsError
        If the target backup directory already exists.

    Notes
    -----
    Existing ``design.con``, ``design.fts``, and ``design.fsf`` files are copied
    when present. The complete ``stats`` directory is recursively copied when it
    exists.

    The backup makes a contrast update reversible without requiring the original
    first-level model to be recomputed.
    """    
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
    """
    Recompute FILM statistics and FEAT post-statistics for updated contrasts.

    The original FILM estimation options are reused with the new contrast file.
    Before modifying the FEAT directory, existing statistical and design outputs
    are backed up. The old statistics directory is removed, updated contrast/FSF
    files are installed, FILM is rerun, required outputs are validated, and
    post-statistics are regenerated.

    Parameters
    ----------
    feat_dir : pathlib.Path
        FEAT directory whose contrast statistics will be replaced.
    update_work_dir : pathlib.Path
        Contrast-update working directory used for backups.
    new_con_file : pathlib.Path
        Updated FSL contrast file.
    new_fsf_file : pathlib.Path
        Updated FEAT configuration.
    dry_run : bool
        If ``True``, print the FILM command but modify nothing.
    contrasts : Sequence[tuple]
        Updated contrast definitions used when regenerating post-statistics.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If FILM finishes without required residual/DOF outputs or produces no
        z-statistic images.
    subprocess.CalledProcessError
        If FILM or post-statistics commands fail.

    Notes
    -----
    This operation intentionally preserves the original design matrix while
    recomputing only contrast-dependent statistical products.
    """    
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
    """
    Resolve a required FSL executable from ``PATH``.

    Parameters
    ----------
    name : str
        Executable name.

    Returns
    -------
    str
        Resolved executable path.

    Raises
    ------
    click.ClickException
        If the executable cannot be located on ``PATH``.
    """
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
    """
    Read and convert a numeric ``fmri(...)`` setting from an FSF file.

    Parameters
    ----------
    fsf_path : pathlib.Path
        FEAT configuration file.
    key : str
        Name inside ``fmri(key)``.
    value_type : type, optional
        Callable used to convert the textual value. Defaults to ``float``.

    Returns
    -------
    Any
        Parsed value converted using ``value_type``.

    Raises
    ------
    click.ClickException
        If the key cannot be found or its value cannot be converted.

    Notes
    -----
    Quoted and unquoted scalar values are supported.
    """    
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
    """
    Read the first parseable floating-point token from a text file.

    Parameters
    ----------
    path : pathlib.Path
        Small FSL output file containing at least one numeric token.

    Returns
    -------
    float
        First token that can be converted to ``float``.

    Raises
    ------
    click.ClickException
        If the file does not exist or contains no numeric token.
    """
    if not path.is_file():
        raise click.ClickException(f"Required file is missing: {path}")
    for token in path.read_text(encoding="utf-8", errors="replace").split():
        try:
            return float(token)
        except ValueError:
            continue
    raise click.ClickException(f"No numeric value found in {path}")


def _parse_smoothest_output(output: str) -> tuple[float, int, float]:
    """
    Extract smoothness parameters from FSL ``smoothest`` output.

    Parameters
    ----------
    output : str
        Standard output produced by ``smoothest``.

    Returns
    -------
    dlh : float
        Estimated smoothness determinant term.
    volume : int
        Search volume rounded to the nearest integer.
    resels : float
        Number of resolution elements.

    Raises
    ------
    click.ClickException
        If any of ``DLH``, ``VOLUME``, or ``RESELS`` cannot be parsed.
    """
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
    """
    Find numerically indexed FSL statistic images.

    Parameters
    ----------
    stats_dir : pathlib.Path
        Directory containing statistic NIfTI files.
    stem : str
        Filename stem such as ``"zstat"``, ``"cope"``, or ``"tstat"``.

    Returns
    -------
    list[tuple[int, pathlib.Path]]
        ``(index, path)`` pairs ordered numerically by statistic index.

    Notes
    -----
    Both ``.nii`` and ``.nii.gz`` forms are recognized. Files whose names do not
    exactly match ``<stem><integer>.nii[.gz]`` are ignored.
    """
    found: dict[int, Path] = {}
    pattern = re.compile(rf"^{re.escape(stem)}(\d+)\.nii(?:\.gz)?$")
    for path in stats_dir.glob(f"{stem}*.nii*"):
        match = pattern.match(path.name)
        if match:
            found[int(match.group(1))] = path
    return sorted(found.items())


def _remove_old_poststats(feat_dir: Path) -> None:
    """
    Remove FEAT post-statistical products that would become stale.

    Parameters
    ----------
    feat_dir : pathlib.Path
        FEAT directory whose post-statistics are about to be regenerated.

    Returns
    -------
    None

    Notes
    -----
    Thresholded z-statistics, cluster masks/tables, local-maxima tables, rendered
    images, volume files, ramp images, and the ``tsplot`` directory are removed
    when present.

    Raw FILM statistics in ``stats`` are not removed by this function.
    """
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
    """
    Regenerate first-level FEAT post-statistics after contrast replacement.

    Run-dependent quantities are recovered from the updated FEAT directory rather
    than hard-coded. Residual smoothness is estimated with ``smoothest`` and each
    z-statistic is masked, cluster-thresholded, summarized, and rendered using FSL
    utilities. Optional time-series plots and FEAT HTML sections are subsequently
    regenerated.

    Parameters
    ----------
    feat_dir : pathlib.Path
        Existing FEAT directory containing updated FILM outputs.
    contrasts : Sequence[tuple]
        Contrast definitions corresponding to the current z-statistic ordering.
    overwrite : bool, optional
        Remove previously generated post-statistical products before rebuilding.
    generate_tsplot : bool, optional
        Generate time-series plots and associated report content when ``True``.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If required FEAT inputs, threshold parameters, FSL commands, statistic
        images, or expected products are unavailable.
    subprocess.CalledProcessError
        If an invoked FSL post-statistics command fails.

    Notes
    -----
    Degrees of freedom are read from ``stats/dof``. Cluster-forming and
    probability thresholds are read from ``design.fsf``. DLH and search volume are
    estimated from ``stats/res4d`` and the FEAT mask using ``smoothest``.

    This reproduces contrast-dependent post-stats without repeating the complete
    first-level FEAT preprocessing/model workflow.
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
    """
    Read the numeric matrix section of an FSL VEST matrix file.

    Parameters
    ----------
    path : pathlib.Path
        FSL ``.mat`` or other VEST-formatted matrix file containing a ``/Matrix``
        marker.

    Returns
    -------
    numpy.ndarray
        Two-dimensional floating-point matrix formed from all non-empty lines
        following ``/Matrix``.

    Raises
    ------
    click.ClickException
        If the file does not contain a ``/Matrix`` section.
    ValueError
        If a matrix token cannot be converted to floating point.
    """    
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
    """
    Verify that regenerated and existing FEAT design matrices are equivalent.

    Parameters
    ----------
    existing : pathlib.Path
        Original ``design.mat``.
    generated : pathlib.Path
        Newly generated ``design.mat`` produced during contrast updating.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If the matrices differ in shape or are not numerically equal within the
        configured tolerances.

    Notes
    -----
    Numerical equality is tested with ``numpy.allclose`` using ``rtol=1e-7`` and
    ``atol=1e-8``. The maximum absolute discrepancy is reported on failure.

    This check prevents a contrast-only update from silently modifying the
    underlying model.
    """    
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
    """
    Require an external executable to be available on ``PATH``.

    Parameters
    ----------
    name : str
        Executable name.

    Returns
    -------
    str
        Resolved executable path.

    Raises
    ------
    click.ClickException
        If the executable cannot be found.
    """
    if shutil.which(name) is None:
        raise click.ClickException(
            f"Required executable {name!r} was not found on PATH."
        )


def parse_run_selectors(values: tuple[str, ...]) -> tuple[str, ...]:
    """
    Normalize command-line run selectors into explicit BIDS run labels.

    Individual values, comma-separated lists, repeated options, and inclusive
    integer ranges are supported. Zero-padded labels are retained when supplied
    as literal values.

    Parameters
    ----------
    values : Sequence[str]
        Raw run-selection arguments.

    Returns
    -------
    set[str]
        Explicit selected run labels.

    Raises
    ------
    click.ClickException
        If a range expression is malformed or represents an invalid descending or
        otherwise unsupported range.

    Examples
    --------
    Accepted forms include ``"1"``, ``"01"``, ``"1,3,5"``, ``"1-4"``, and
    combinations supplied through repeated options.
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
    """
    Replace a marker-delimited section of a FEAT HTML report.

    Parameters
    ----------
    text : str
        Complete HTML document.
    start_marker : str
        Marker delimiting the beginning of the managed section.
    end_marker : str
        Marker delimiting the end of the managed section.
    replacement : str
        New content to place between the markers.

    Returns
    -------
    str
        HTML text containing the replaced section.

    Notes
    -----
    This helper allows generated post-statistics content to be updated without
    rewriting unrelated sections of FEAT's HTML report.
    """
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
    """
    Regenerate contrast and time-series sections of FEAT's post-stats report.

    The function reads current contrast definitions and available post-statistical
    outputs and updates the managed portions of ``report_poststats.html`` so the
    report reflects newly generated contrast statistics.

    Parameters
    ----------
    feat_dir : pathlib.Path
        FEAT directory containing post-statistical outputs.
    contrasts : Sequence[tuple]
        Current contrast definitions.
    generate_tsplot : bool, optional
        Include time-series plot report content when available/requested.

    Returns
    -------
    None

    Notes
    -----
    Only marker-delimited sections managed by this workflow are replaced; other
    FEAT report content is preserved.
    """
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
    """
    Resolve a required external command.

    Parameters
    ----------
    name : str
        Command name to locate on ``PATH``.

    Returns
    -------
    str
        Absolute or executable path returned by ``shutil.which``.

    Raises
    ------
    click.ClickException
        If the required command is unavailable.
    """    
    executable = shutil.which(name)
    if executable is None:
        raise click.ClickException(
            f"Required FSL executable {name!r} was not found on PATH."
        )
    return executable


def _existing_nifti(path: Path) -> Path:
    """
    Resolve an existing NIfTI image from a path or extensionless image root.

    Parameters
    ----------
    path : pathlib.Path
        Candidate image path. The path may already include ``.nii`` or
        ``.nii.gz`` or may be an extensionless FSL image root.

    Returns
    -------
    pathlib.Path
        Resolved path to the existing NIfTI image.

    Raises
    ------
    click.ClickException
        If no matching image exists.

    Notes
    -----
    For extensionless input, ``.nii.gz`` is tried before ``.nii``.
    """    
    candidates = [path]
    if not str(path).endswith((".nii", ".nii.gz")):
        candidates += [Path(str(path) + ".nii.gz"), Path(str(path) + ".nii")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise click.ClickException(f"Required image does not exist: {path}")


def _normalize_selector(values: Sequence[str]) -> set[str]:
    """
    Normalize comma-separated selector values into a set.

    Parameters
    ----------
    values : Sequence[str]
        Raw selector strings, each potentially containing comma-separated values.

    Returns
    -------
    set[str]
        Non-empty, whitespace-trimmed selector values.

    Notes
    -----
    No numeric interpretation or range expansion is performed.
    """    
    selected: set[str] = set()
    for raw in values:
        for value in str(raw).split(","):
            value = value.strip()
            if value:
                selected.add(value)
    return selected


def _safe_label(value: str, max_length: int = 80) -> str:
    """
    Convert arbitrary text into a filesystem-safe label.

    Parameters
    ----------
    value : str
        Input text.
    max_length : int, optional
        Maximum output length. Defaults to 80 characters.

    Returns
    -------
    str
        Sanitized label containing only alphanumeric characters, periods,
        underscores, and hyphens.

    Notes
    -----
    Unsupported character sequences become hyphens, repeated hyphens are
    collapsed, leading/trailing punctuation is stripped, and an empty result
    becomes ``"contrast"``.
    """    
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    label = re.sub(r"-+", "-", label).strip("-._") or "contrast"
    return label[:max_length]


def _entity_text(value: object) -> str:
    """
    Convert an optional tabular entity value to text.

    Parameters
    ----------
    value : object
        Entity value that may be ``None`` or a pandas missing value.

    Returns
    -------
    str
        Empty string for missing values; otherwise ``str(value)``.
    """    
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _write_vest_matrix(path: Path, matrix: Sequence[Sequence[float]]) -> None:
    """
    Write a numeric matrix in FSL VEST format.

    Parameters
    ----------
    path : pathlib.Path
        Destination file.
    matrix : Sequence[Sequence[float]]
        Rectangular numeric matrix. Rows correspond to observations and columns
        to design waves.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If the matrix is empty, has zero columns, or contains rows of inconsistent
        length.

    Notes
    -----
    The output contains ``/NumWaves``, ``/NumPoints``, ``/PPheights``, and
    ``/Matrix`` declarations expected by FSL tools.
    """    
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
    """
    Write an FSL VEST T-contrast file.

    Both the historical one-wave fixed-effects form and arbitrary multi-wave,
    multi-contrast group designs are supported.

    Parameters
    ----------
    path : pathlib.Path
        Destination ``design.con`` path.
    names : str or Sequence[str]
        Single contrast name or ordered collection of names.
    matrix : Sequence[Sequence[float]] or None, optional
        Contrast matrix. Each row represents one contrast and each column one
        design wave. When ``names`` is a single string and ``matrix`` is omitted,
        a one-by-one contrast matrix containing ``1.0`` is generated.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If names or matrix rows are absent, the number of names differs from the
        number of matrix rows, the matrix has zero waves, or row widths differ.

    Notes
    -----
    Contrast names are sanitized only for embedded newline/carriage-return
    characters; their substantive labels are preserved.

    The generated file includes FSL ``/ContrastNameN``, ``/NumWaves``,
    ``/NumContrasts``, ``/PPheights``, ``/RequiredEffect``, and ``/Matrix``
    sections.
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
    """
    Read the residual degrees of freedom from a first-level FEAT analysis.

    Parameters
    ----------
    feat_dir : pathlib.Path
        First-level FEAT directory containing ``stats/dof``.

    Returns
    -------
    float
        First numeric token found in the DOF file.

    Raises
    ------
    click.ClickException
        If the DOF file is absent or contains no numeric value.
    """    
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
    """
    Execute or display an external command for the fixed-effects workflow.

    Parameters
    ----------
    command : Sequence[str]
        Command argument vector.
    cwd : pathlib.Path
        Working directory.
    dry_run : bool
        If ``True``, display the command without executing it.

    Returns
    -------
    None

    Raises
    ------
    subprocess.CalledProcessError
        If command execution is enabled and the process exits unsuccessfully.
    """    
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
    """
    Combine multiple first-level estimates using FLAME fixed effects.

    COPE, VARCOPE, and first-level DOF images are merged across inputs. Subject/run
    masks are intersected, a one-column fixed-effects design is written, and
    ``flameo`` is executed in fixed-effects mode.

    Parameters
    ----------
    rows : pandas.DataFrame
        Manifest rows belonging to one canonical contrast and fixed-effects
        grouping unit.
    output_dir : pathlib.Path
        Destination second-level analysis directory.
    canonical_name : str
        Canonical contrast name represented by the inputs.
    overwrite : bool
        Permit replacement of an existing output directory.
    dry_run : bool
        Display commands and intended outputs without modifying files.

    Returns
    -------
    dict[str, Any]
        Record describing the resulting second-level analysis, including its input
        count, output directory, and principal COPE/VARCOPE/T/Z statistic paths.

    Raises
    ------
    click.ClickException
        If required inputs are missing, the output already exists without
        overwrite permission, or analysis prerequisites are invalid.
    subprocess.CalledProcessError
        If FSL merging, masking, or FLAME execution fails.

    Notes
    -----
    All observations are assigned to one variance group and receive a fixed-effect
    design value of one.
    """    
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
    """
    Write an FSL variance-group file containing one group.

    Parameters
    ----------
    path : pathlib.Path
        Destination ``design.grp`` file.
    n_subjects : int
        Number of observations/subjects.

    Returns
    -------
    None

    Notes
    -----
    Every observation is assigned group number ``1``.
    """
    _write_vest_matrix(path, [[1.0] for _ in range(number_of_subjects)])


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    dry_run: bool,
) -> None:
    """
    Execute an external command with consistent logging and dry-run handling.

    Parameters
    ----------
    command : Sequence[str]
        Executable and arguments.
    cwd : pathlib.Path
        Working directory used for execution.
    dry_run : bool
        If ``True``, print the command without executing it.

    Returns
    -------
    None

    Raises
    ------
    subprocess.CalledProcessError
        If execution is enabled and the command returns a non-zero exit status.

    Notes
    -----
    Arguments are rendered with shell-safe quoting for diagnostic output, while
    execution itself uses the argument sequence directly rather than invoking a
    shell.
    """    
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
    """
    Determine whether a contrast manifest contains level-1 or level-2 estimates.

    Common mandatory columns are validated first. When the requested level is
    explicit, it is returned directly after validation. Automatic detection uses
    columns characteristic of each manifest level.

    Parameters
    ----------
    manifest : pandas.DataFrame
        Loaded contrast-manifest table.
    requested_level : str
        ``"1"``, ``"2"``, or the automatic-selection value used by the caller.

    Returns
    -------
    str
        ``"1"`` for first-level inputs or ``"2"`` for second-level inputs.

    Raises
    ------
    click.ClickException
        If required common columns are missing or automatic detection is
        ambiguous.

    Notes
    -----
    Level-1 hints include run-level and FEAT-directory fields. Level-2 hints
    include the number of combined inputs and second-level directory fields.
    """    
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
    """
    Resolve the source analysis directory represented by a manifest row.

    Parameters
    ----------
    row : pandas.Series
        Contrast-manifest row.
    input_level : str
        Input analysis level, normally ``"1"`` or ``"2"``.

    Returns
    -------
    pathlib.Path
        Resolved analysis directory.

    Notes
    -----
    For level-2 input, ``second_level_dir`` is preferred. Otherwise ``feat_dir``
    is used when present. As a final fallback, the analysis directory is inferred
    as the grandparent of ``cope_file``, reflecting the conventional
    ``<analysis>/stats/copeN`` layout.
    """    
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
    Parse a group-level T-contrast specification.

    The specification uses the form::

        NAME;w1,w2,...

    where the number of weights must equal the number of group-design columns.

    Parameters
    ----------
    specification : str
        User-supplied group contrast.
    design_columns : Sequence[str]
        Ordered group-design columns against which weights are interpreted.

    Returns
    -------
    name : str
        Contrast name.
    weights : list[float]
        Numeric contrast vector.

    Raises
    ------
    click.ClickException
        If the specification is malformed, unnamed, contains non-numeric values,
        or has a weight count inconsistent with the design matrix.

    Examples
    --------
    For design columns ``["Intercept", "age"]``, ``"AgePositive;0,1"`` tests the
    positive age effect.
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
    Construct a cross-subject design matrix and its T contrasts.

    An intercept is always included as the first design column. Optional
    subject-level covariates are loaded, aligned to the requested subjects,
    validated, optionally demeaned, and appended as additional columns.

    Parameters
    ----------
    subjects : Sequence[str]
        Ordered subject identifiers defining design-matrix row order.
    covariates_file : pathlib.Path or None
        Optional table containing subject-level covariates.
    covariate_names : Sequence[str]
        Covariate columns to include.
    demean_covariates : bool
        Subtract each selected covariate's sample mean before inclusion.
    group_contrast_specs : Sequence[str]
        Explicit group-level contrast specifications. If empty, a default
        intercept/GroupMean contrast is created.

    Returns
    -------
    design_columns : list[str]
        Ordered design-column names, beginning with ``Intercept``.
    design_matrix : list[list[float]]
        Subject-by-wave design matrix.
    contrast_names : list[str]
        Ordered group contrast names.
    contrast_matrix : list[list[float]]
        Contrast vectors in design-column space.
    subject_table : pandas.DataFrame
        Subject table containing identifiers and processed covariates.

    Raises
    ------
    click.ClickException
        If covariate data cannot uniquely and completely map onto the requested
        subjects, requested columns are missing, values are non-numeric or
        otherwise invalid, or contrast vectors do not match the design width.
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
    """
    Create a common analysis mask from source analysis directories.

    Each analysis directory's ``mask`` image is resolved, masks are concatenated
    along the fourth dimension with ``fslmerge``, and ``fslmaths -Tmin -bin`` is
    used to retain only voxels present in every input mask.

    Parameters
    ----------
    analysis_dirs : Sequence[pathlib.Path]
        Source FEAT or higher-level analysis directories.
    output_dir : pathlib.Path
        Directory in which intermediate and final masks are written.
    dry_run : bool
        Display commands without executing them.

    Returns
    -------
    pathlib.Path
        Expected path to the gzipped intersection mask.

    Raises
    ------
    click.ClickException
        If a source mask or required FSL command cannot be located.
    subprocess.CalledProcessError
        If mask construction fails.
    """    
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
    """
    Create a common binary mask from explicitly resolved subject mask files.

    Parameters
    ----------
    mask_files : Sequence[pathlib.Path]
        Existing mask images in subject/input order.
    output_dir : pathlib.Path
        Group analysis output directory.
    dry_run : bool
        Display the FSL merge/masking commands without executing them.

    Returns
    -------
    pathlib.Path
        Expected final gzipped intersection mask.

    Notes
    -----
    Masks are merged in time and reduced using ``-Tmin -bin``, so a voxel is
    included only if it is present in every subject mask.
    """
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
    """
    Run a highest-level cross-subject FLAME analysis.

    The function validates that each subject contributes exactly one independent
    estimate, resolves registered COPE/VARCOPE/mask inputs, verifies image
    geometry, builds the group design, merges subject statistic images, constructs
    an intersection mask, writes FSL VEST design files, and executes ``flameo``
    using the requested run mode.

    Parameters
    ----------
    rows : pandas.DataFrame
        Manifest rows for one canonical contrast.
    input_level : str
        Source manifest level, ``"1"`` or ``"2"``.
    output_dir : pathlib.Path
        Group-analysis output directory.
    canonical_name : str
        Canonical contrast represented by the subject inputs.
    runmode : str
        FLAME run mode passed to ``flameo``.
    covariates_file : pathlib.Path or None
        Optional subject-level covariate table.
    covariate_names : Sequence[str]
        Covariates to include in the design.
    demean_covariates : bool
        Demean selected covariates before model construction.
    group_contrast_specs : Sequence[str]
        Explicit group T contrasts.
    registration_mode : str
        Strategy used to obtain common-space inputs.
    registered_subdir : str
        Subdirectory used for precomputed/created registered images.
    overwrite : bool
        Permit replacement of an existing group output.
    dry_run : bool
        Report the planned analysis without modifying data.

    Returns
    -------
    list[dict[str, Any]]
        One output record per group contrast, containing group-analysis identity
        and paths to contrast-specific statistics.

    Raises
    ------
    click.ClickException
        If subjects are duplicated, fewer than two independent subjects are
        available, output replacement is forbidden, registered inputs cannot be
        resolved, geometry is incompatible, or group-design validation fails.
    subprocess.CalledProcessError
        If FSL merging, registration, masking, or FLAME execution fails.

    Notes
    -----
    A level-1 manifest containing multiple runs for the same subject is explicitly
    rejected because those runs are not independent group observations. Such runs
    must first be combined with the fixed-effects second-level workflow.

    When ``registration_mode`` is ``featregapply`` in dry-run mode, geometry
    validation is deferred because registered files do not yet exist.

    The function also writes reproducibility tables and ``analysis.json`` during
    a real run.
    """    
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
    """
    Resolve common-space COPE, VARCOPE, and mask inputs for one analysis row.

    The source analysis directory is derived from the manifest row and the
    requested registration strategy is applied. Depending on configuration, the
    function may use native/current outputs, pre-existing registered outputs, or
    invoke FEAT registration application to create registered images.

    Parameters
    ----------
    row : pandas.Series
        Input manifest row.
    input_level : str
        Source manifest level.
    registration_mode : str
        Registration strategy selected for the group analysis.
    registered_subdir : str
        Subdirectory containing or receiving registered statistics.
    dry_run : bool
        Report registration commands without executing them.

    Returns
    -------
    cope_file : pathlib.Path
        Resolved COPE image.
    varcope_file : pathlib.Path
        Resolved VARCOPE image.
    mask_file : pathlib.Path
        Resolved analysis mask.
    analysis_dir : pathlib.Path
        Source FEAT or higher-level analysis directory.

    Raises
    ------
    click.ClickException
        If source or registered files required by the selected mode cannot be
        resolved.
    subprocess.CalledProcessError
        If an on-demand registration command fails.
    """
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
    """
    Require two NIfTI images to have compatible spatial geometry.

    Parameters
    ----------
    reference_path : pathlib.Path
        Reference image defining expected dimensions and affine transform.
    candidate_path : pathlib.Path
        Image to compare with the reference.
    description : str
        Human-readable label used in validation errors.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If the images differ in their first three dimensions or affine matrices.

    Notes
    -----
    The check targets spatial compatibility. It does not require identical voxel
    data or statistic values.
    """
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
    """
    Validate spatial geometry for all COPE, VARCOPE, and mask inputs in a group.

    Within each subject/input, the VARCOPE and mask must match the corresponding
    COPE geometry. Across subjects, each COPE must also match the spatial geometry
    of the first COPE used as the group reference.

    Parameters
    ----------
    cope_files : Sequence[pathlib.Path]
        Subject/input COPE images.
    varcope_files : Sequence[pathlib.Path]
        Corresponding VARCOPE images.
    mask_files : Sequence[pathlib.Path]
        Corresponding masks.

    Returns
    -------
    None

    Raises
    ------
    click.ClickException
        If input list lengths are inconsistent, no group reference is available,
        or any within-subject or across-subject spatial geometry mismatch is
        detected.

    Notes
    -----
    Validation occurs before images are merged for group analysis, providing an
    early and more interpretable failure than allowing FSL tools to operate on
    misregistered data.
    """
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


def resolve_group_reference(
    rows: pd.DataFrame,
    input_level: str | int,
) -> Path:
    """Resolve the common standard-space template used by level-3 inputs."""
    input_level = str(input_level).strip()

    if input_level == "1":
        column = "feat_dir"
    elif input_level == "2":
        column = "second_level_dir"
    else:
        raise ValueError(f"Unsupported input level: {input_level!r}")

    if column not in rows.columns:
        raise click.ClickException(
            f"Input-level {input_level} manifest lacks required {column!r} column "
            "needed to resolve the group template reference."
        )

    refs: list[Path] = []
    missing: list[Path] = []

    for value in rows[column].fillna("").astype(str).unique():
        value = value.strip()
        if not value:
            continue

        reference = (Path(value) / "reg" / "standard.nii.gz").resolve()
        if reference.is_file():
            refs.append(reference)
        else:
            missing.append(reference)

    if not refs:
        details = ""
        if missing:
            details = "\n  " + "\n  ".join(str(path) for path in missing[:10])
        raise click.ClickException(
            f"Could not resolve standard-space reference from manifest column "
            f"{column!r}.{details}"
        )

    reference = refs[0]
    reference_img = nib.load(str(reference))

    for candidate in refs[1:]:
        image = nib.load(str(candidate))
        if image.shape != reference_img.shape or not np.allclose(
            image.affine,
            reference_img.affine,
            rtol=0.0,
            atol=1e-4,
        ):
            raise click.ClickException(
                "Level-3 inputs do not share one standard-space reference grid:\n"
                f"  {reference}\n"
                f"  {candidate}"
            )

    return reference


def _write_poststats_report(
    feat_dir: Path,
    *,
    title: str,
    contrast_names: list[str] | None = None,
    z_threshold: float = 2.3,
    background: Path | None = None,
) -> Path:
    """Create an interactive FEAT poststats-style HTML QC report.

    The report contains:
    - an in-browser orthogonal NIfTI viewer with slice navigation;
    - live positive/negative Z thresholding and opacity controls;
    - voxel and world-coordinate readout;
    - a static PNG fallback;
    - descriptive connected-component cluster tables.

    The connected components are *not* cluster-corrected inference.
    """
    from datetime import datetime
    import html
    import math
    import os

    feat_dir = Path(feat_dir).resolve()
    stats_dir = feat_dir / "stats"
    report_dir = feat_dir / "report_poststats_files"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = feat_dir / "report_poststats.html"

    zstats = sorted(
        stats_dir.glob("zstat*.nii.gz"),
        key=lambda p: int("".join(ch for ch in p.name if ch.isdigit()) or "0"),
    )

    if background is not None:
        background = Path(background).resolve()
        if not background.is_file():
            raise click.ClickException(
                f"Poststats background/reference does not exist: {background}"
            )
    else:
        background_candidates = [
            feat_dir / "mean_func.nii.gz",
            feat_dir / "example_func.nii.gz",
            feat_dir / "mask.nii.gz",
            feat_dir / "reg_standard" / "mean_func.nii.gz",
            feat_dir / "reg_standard" / "example_func.nii.gz",
            feat_dir / "reg" / "standard.nii.gz",
        ]
        background = next(
            (path.resolve() for path in background_candidates if path.is_file()),
            None,
        )

    def rel(path: Path) -> str:
        """Return a report-relative URL without dereferencing symlinks."""
        path = Path(path)

        if not path.is_absolute():
            path = feat_dir / path

        return os.path.relpath(
            str(path.absolute()),
            str(feat_dir),
        )

    # Expose the template through a stable report-local browser URL.
    #
    # Do not make the HTML fetch the original level-1/level-2 path directly:
    # the report may be served from a different HTTP document root and a path
    # containing several ".." components is fragile. Prefer a relative symlink
    # (zero additional storage), then a hardlink, and finally a real copy when
    # the underlying filesystem does not support links (e.g. some /mnt/* setups).
    background_url = None
    if background is not None:
        local_background = report_dir / "background.nii.gz"

        def _same_file(left: Path, right: Path) -> bool:
            try:
                return left.exists() and os.path.samefile(left, right)
            except OSError:
                return False

        if local_background.is_symlink():
            try:
                if local_background.resolve() != background:
                    local_background.unlink()
            except OSError:
                local_background.unlink(missing_ok=True)
        elif local_background.exists() and not _same_file(
            local_background,
            background,
        ):
            # This file is report-generated state, so replace a stale asset.
            local_background.unlink()

        if not local_background.exists():
            created = False

            # 1) Relative symlink: no duplicated template data.
            try:
                target = os.path.relpath(
                    str(background),
                    str(local_background.parent),
                )
                local_background.symlink_to(target)
                created = local_background.exists()
            except OSError:
                created = False

            # A broken/unsupported symlink must not block the fallback paths.
            if local_background.is_symlink() and not created:
                local_background.unlink(missing_ok=True)

            # 2) Hardlink: also zero duplicated data when source/destination
            # are on the same filesystem.
            if not created:
                try:
                    os.link(background, local_background)
                    created = local_background.exists()
                except OSError:
                    created = False

            # 3) Copy: portable last resort.
            if not created:
                shutil.copy2(background, local_background)
                created = local_background.exists()

            if not created:
                raise click.ClickException(
                    f"Could not create report-local background asset from "
                    f"{background}"
                )

        # Always use the report-local URL in the HTML. This is intentionally
        # independent of the symlink/hardlink/copy implementation above.
        background_url = rel(local_background)

    def make_clusters(z_file: Path):
        try:
            from scipy import ndimage
        except Exception:
            return [], []

        img = nib.load(str(z_file))
        data = np.asanyarray(img.dataobj, dtype=float)
        if data.ndim > 3:
            data = np.squeeze(data)
        if data.ndim != 3:
            return [], []

        finite = np.isfinite(data)
        voxel_volume = abs(float(np.linalg.det(img.affine[:3, :3])))
        structure = ndimage.generate_binary_structure(3, 3)

        def one_side(mask, sign):
            labels, n_labels = ndimage.label(mask & finite, structure=structure)
            rows = []

            for label_id in range(1, n_labels + 1):
                coords = np.argwhere(labels == label_id)
                if coords.size == 0:
                    continue

                values = data[labels == label_id]
                local = (
                    int(np.nanargmax(values))
                    if sign > 0
                    else int(np.nanargmin(values))
                )
                peak_voxel = coords[local]
                peak_z = float(values[local])
                xyz = nib.affines.apply_affine(img.affine, peak_voxel)

                rows.append(
                    {
                        "voxels": int(coords.shape[0]),
                        "volume_mm3": float(coords.shape[0] * voxel_volume),
                        "peak_z": peak_z,
                        "x": float(xyz[0]),
                        "y": float(xyz[1]),
                        "z": float(xyz[2]),
                    }
                )

            rows.sort(key=lambda row: row["voxels"], reverse=True)
            return rows[:25]

        return (
            one_side(data >= z_threshold, +1),
            one_side(data <= -z_threshold, -1),
        )

    def render_stat(z_file: Path, png_file: Path) -> str | None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as exc:
            return f"Python plotting dependencies unavailable: {exc}"

        z_img = nib.as_closest_canonical(nib.load(str(z_file)))
        z = np.asanyarray(z_img.dataobj, dtype=float)
        if z.ndim > 3:
            z = np.squeeze(z)
        if z.ndim != 3:
            return f"Expected 3D Z-stat image, got shape {z.shape}"

        bg = None
        if background is not None:
            try:
                bg_img = nib.as_closest_canonical(nib.load(str(background)))
                bg_data = np.asanyarray(bg_img.dataobj, dtype=float)
                if bg_data.ndim > 3:
                    bg_data = np.squeeze(bg_data)
                if bg_data.shape == z.shape:
                    bg = bg_data
            except Exception:
                bg = None

        finite = np.isfinite(z)
        supra = finite & (np.abs(z) >= z_threshold)

        if np.any(supra):
            peak_flat = np.nanargmax(
                np.where(supra, np.abs(z), np.nan)
            )
            peak = np.unravel_index(peak_flat, z.shape)
        else:
            peak = tuple(int(v // 2) for v in z.shape)

        vmax = (
            float(np.nanmax(np.abs(z[finite])))
            if np.any(finite)
            else z_threshold
        )
        vmax = max(vmax, z_threshold + 1e-6)
        masked = np.ma.masked_where(~supra, z)

        slices = [
            ("Sagittal", peak[0], lambda a, i: a[i, :, :]),
            ("Coronal", peak[1], lambda a, i: a[:, i, :]),
            ("Axial", peak[2], lambda a, i: a[:, :, i]),
        ]

        fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))

        for ax, (label, index, cutter) in zip(axes, slices):
            if bg is not None:
                bg_slice = cutter(bg, index).T
                finite_bg = bg_slice[np.isfinite(bg_slice)]
                if finite_bg.size:
                    lo, hi = np.nanpercentile(finite_bg, [2, 98])
                    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
                        lo, hi = None, None
                else:
                    lo, hi = None, None

                ax.imshow(
                    bg_slice,
                    cmap="gray",
                    origin="lower",
                    vmin=lo,
                    vmax=hi,
                )
            else:
                ax.set_facecolor("black")

            ax.imshow(
                cutter(masked, index).T,
                cmap="coolwarm",
                origin="lower",
                vmin=-vmax,
                vmax=vmax,
                alpha=0.90,
            )
            ax.set_title(f"{label}  voxel={index}")
            ax.axis("off")

        fig.suptitle(
            f"{title} — {z_file.name} — |Z| ≥ {z_threshold:g}",
            fontsize=12,
        )
        fig.tight_layout()
        fig.savefig(png_file, dpi=140, bbox_inches="tight")
        plt.close(fig)
        return None

    def cluster_table(rows, heading):
        if not rows:
            return (
                f"<h4>{html.escape(heading)}</h4>"
                "<p class='muted'>No supra-threshold clusters.</p>"
            )

        body = []
        for i, row in enumerate(rows, 1):
            body.append(
                "<tr>"
                f"<td>{i}</td>"
                f"<td>{row['voxels']}</td>"
                f"<td>{row['volume_mm3']:.1f}</td>"
                f"<td>{row['peak_z']:.3f}</td>"
                f"<td>{row['x']:.1f}</td>"
                f"<td>{row['y']:.1f}</td>"
                f"<td>{row['z']:.1f}</td>"
                "</tr>"
            )

        return (
            f"<h4>{html.escape(heading)}</h4>"
            "<table><thead><tr>"
            "<th>#</th><th>Voxels</th><th>mm³</th><th>Peak Z</th>"
            "<th>x (mm)</th><th>y (mm)</th><th>z (mm)</th>"
            "</tr></thead><tbody>"
            + "".join(body)
            + "</tbody></table>"
        )

    sections = []

    for index, z_file in enumerate(zstats, start=1):
        contrast_name = (
            contrast_names[index - 1]
            if contrast_names and index - 1 < len(contrast_names)
            else f"Contrast {index}"
        )

        png = report_dir / f"zstat{index}.png"
        render_error = render_stat(z_file, png)
        pos_clusters, neg_clusters = make_clusters(z_file)

        links = []
        for stem in ("cope", "varcope", "tstat", "zstat"):
            candidate = stats_dir / f"{stem}{index}.nii.gz"
            if candidate.is_file():
                links.append(
                    f"<a href='{html.escape(rel(candidate))}'>"
                    f"{html.escape(candidate.name)}</a>"
                )

        static_html = (
            f"<details class='static-fallback'>"
            f"<summary>Static snapshot</summary>"
            f"<img src='{html.escape(rel(png))}' "
            f"alt='{html.escape(contrast_name)}'>"
            f"</details>"
            if png.is_file()
            else (
                "<p class='warn'>Could not render static image: "
                f"{html.escape(render_error or 'unknown error')}</p>"
            )
        )

        if background_url is not None:
            viewer_html = f"""
<div
  class="nv-lite"
  id="viewer-{index}"
  data-background="{html.escape(background_url)}"
  data-overlay="{html.escape(rel(z_file))}"
  data-threshold="{z_threshold:g}"
>
  <div class="viewer-status">Loading interactive NIfTI viewer…</div>
  <div class="viewer-controls">
    <label>Z threshold
      <input class="threshold" type="range" min="0" max="10" step="0.1"
             value="{z_threshold:g}">
      <output class="threshold-value">{z_threshold:g}</output>
    </label>
    <label>Overlay opacity
      <input class="opacity" type="range" min="0" max="1" step="0.05"
             value="0.80">
      <output class="opacity-value">0.80</output>
    </label>
    <span class="coord-readout"></span>
  </div>
  <div class="orthogonal-grid">
    <div class="plane">
      <div class="plane-title">Sagittal</div>
      <canvas class="slice-canvas" data-axis="0"></canvas>
      <input class="slice-slider" data-axis="0" type="range" min="0" max="1" value="0">
    </div>
    <div class="plane">
      <div class="plane-title">Coronal</div>
      <canvas class="slice-canvas" data-axis="1"></canvas>
      <input class="slice-slider" data-axis="1" type="range" min="0" max="1" value="0">
    </div>
    <div class="plane">
      <div class="plane-title">Axial</div>
      <canvas class="slice-canvas" data-axis="2"></canvas>
      <input class="slice-slider" data-axis="2" type="range" min="0" max="1" value="0">
    </div>
  </div>
  <p class="viewer-help">
    Click or drag directly in any image to move the synchronized crosshair.
    Use the mouse wheel to step through slices; the sliders remain available as
    secondary controls. Threshold and opacity update live.
  </p>
</div>
"""
        else:
            viewer_html = (
                "<p class='warn'>Interactive viewer unavailable: "
                "no background/template image could be resolved.</p>"
            )

        sections.append(
            "<section>"
            f"<h2>{html.escape(contrast_name)}</h2>"
            f"<p>{' · '.join(links)}</p>"
            f"{viewer_html}"
            f"{static_html}"
            "<p class='muted'>Cluster tables below are descriptive connected "
            f"components at |Z| ≥ {z_threshold:g}; no multiple-comparison "
            "correction is implied.</p>"
            f"{cluster_table(pos_clusters, f'Positive Z ≥ {z_threshold:g}')}"
            f"{cluster_table(neg_clusters, f'Negative Z ≤ -{z_threshold:g}')}"
            "</section>"
        )

    design_links = []
    for name in ("design.mat", "design.con", "design.grp"):
        path = feat_dir / name
        if path.is_file():
            design_links.append(
                f"<a href='{html.escape(name)}'>{html.escape(name)}</a>"
            )

    if not zstats:
        sections.append(
            "<section><h2>Statistics</h2>"
            "<p class='warn'>No stats/zstat*.nii.gz files were found.</p></section>"
        )

    bg_text = html.escape(str(background)) if background is not None else "none"

    # Self-contained minimal NIfTI-1 reader/viewer. No CDN dependency.
    interactive_js = r"""
<script>
(() => {
  "use strict";

  function showFileProtocolWarning(root, error) {
    const status = root.querySelector(".viewer-status");
    status.classList.add("viewer-error");
    const extra = location.protocol === "file:"
      ? " Browsers normally block NIfTI fetches from file://. From the project root, run: python -m http.server 8000 and open the report through http://localhost:8000/…"
      : "";
    status.textContent = "Interactive viewer could not load: " + error + extra;
  }

  async function inflateIfNeeded(buffer) {
    const bytes = new Uint8Array(buffer);
    if (bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b) {
      if (!("DecompressionStream" in window)) {
        throw new Error("this browser does not provide DecompressionStream for .nii.gz");
      }
      const ds = new DecompressionStream("gzip");
      const stream = new Blob([buffer]).stream().pipeThrough(ds);
      return await new Response(stream).arrayBuffer();
    }
    return buffer;
  }

  async function fetchBuffer(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    return inflateIfNeeded(await response.arrayBuffer());
  }

  function parseNifti(buffer) {
    const view = new DataView(buffer);
    let little = true;
    if (view.getInt32(0, true) !== 348) {
      if (view.getInt32(0, false) !== 348) {
        throw new Error("not a NIfTI-1 single-file image");
      }
      little = false;
    }

    const dims = [];
    for (let i = 0; i < 8; i++) dims.push(view.getInt16(40 + i * 2, little));
    const nx = dims[1], ny = dims[2], nz = dims[3];
    if (!(nx > 0 && ny > 0 && nz > 0)) throw new Error("invalid NIfTI dimensions");

    const datatype = view.getInt16(70, little);
    const voxOffset = Math.max(352, Math.floor(view.getFloat32(108, little)));
    let slope = view.getFloat32(112, little);
    const inter = view.getFloat32(116, little);
    if (!Number.isFinite(slope) || slope === 0) slope = 1;

    const nvox = nx * ny * nz;

    function readTyped(kind, bytes) {
      const out = new Float32Array(nvox);
      let offset = voxOffset;
      for (let i = 0; i < nvox; i++, offset += bytes) {
        let value;
        switch (kind) {
          case "u8": value = view.getUint8(offset); break;
          case "i8": value = view.getInt8(offset); break;
          case "i16": value = view.getInt16(offset, little); break;
          case "u16": value = view.getUint16(offset, little); break;
          case "i32": value = view.getInt32(offset, little); break;
          case "u32": value = view.getUint32(offset, little); break;
          case "f32": value = view.getFloat32(offset, little); break;
          case "f64": value = view.getFloat64(offset, little); break;
          default: throw new Error("unsupported datatype");
        }
        out[i] = value * slope + inter;
      }
      return out;
    }

    let data;
    switch (datatype) {
      case 2: data = readTyped("u8", 1); break;
      case 4: data = readTyped("i16", 2); break;
      case 8: data = readTyped("i32", 4); break;
      case 16: data = readTyped("f32", 4); break;
      case 64: data = readTyped("f64", 8); break;
      case 256: data = readTyped("i8", 1); break;
      case 512: data = readTyped("u16", 2); break;
      case 768: data = readTyped("u32", 4); break;
      default: throw new Error(`unsupported NIfTI datatype code ${datatype}`);
    }

    const sformCode = view.getInt16(254, little);
    let affine = [
      [1,0,0,0],
      [0,1,0,0],
      [0,0,1,0],
      [0,0,0,1],
    ];

    if (sformCode > 0) {
      affine = [[], [], [], [0,0,0,1]];
      for (let row = 0; row < 3; row++) {
        const base = 280 + row * 16;
        for (let col = 0; col < 4; col++) {
          affine[row][col] = view.getFloat32(base + col * 4, little);
        }
      }
    } else {
      const pix = [
        view.getFloat32(80, little) || 1,
        view.getFloat32(84, little) || 1,
        view.getFloat32(88, little) || 1,
      ];
      affine[0][0] = pix[0];
      affine[1][1] = pix[1];
      affine[2][2] = pix[2];
    }

    return {nx, ny, nz, data, affine};
  }

  function percentileSample(data, p) {
    const maxSamples = 100000;
    const step = Math.max(1, Math.floor(data.length / maxSamples));
    const values = [];
    for (let i = 0; i < data.length; i += step) {
      const v = data[i];
      if (Number.isFinite(v)) values.push(v);
    }
    values.sort((a,b) => a-b);
    if (!values.length) return 0;
    const idx = Math.max(0, Math.min(values.length - 1, Math.round((values.length - 1) * p)));
    return values[idx];
  }

  function voxelIndex(vol, x, y, z) {
    return x + vol.nx * (y + vol.ny * z);
  }

  function world(aff, x, y, z) {
    return [
      aff[0][0]*x + aff[0][1]*y + aff[0][2]*z + aff[0][3],
      aff[1][0]*x + aff[1][1]*y + aff[1][2]*z + aff[1][3],
      aff[2][0]*x + aff[2][1]*y + aff[2][2]*z + aff[2][3],
    ];
  }

  function overlayColor(z, threshold, alphaScale) {
    const a = Math.max(0, Math.min(1, alphaScale));
    if (z >= threshold) {
      const t = Math.max(0, Math.min(1, (z - threshold) / Math.max(1, 6 - threshold)));
      return [255, Math.round(135 * (1 - t)), 40, Math.round(255 * a)];
    }
    if (z <= -threshold) {
      const t = Math.max(0, Math.min(1, (-z - threshold) / Math.max(1, 6 - threshold)));
      return [40, Math.round(150 * (1 - t)), 255, Math.round(255 * a)];
    }
    return null;
  }

  function initViewer(root, bg, zvol) {
    if (bg.nx !== zvol.nx || bg.ny !== zvol.ny || bg.nz !== zvol.nz) {
      throw new Error(
        `background/stat dimensions differ: ${bg.nx}×${bg.ny}×${bg.nz} vs ${zvol.nx}×${zvol.ny}×${zvol.nz}`
      );
    }

    const state = {
      xyz: [Math.floor(bg.nx/2), Math.floor(bg.ny/2), Math.floor(bg.nz/2)],
      threshold: parseFloat(root.dataset.threshold || "2.3"),
      opacity: 0.8,
    };

    // Start at the strongest absolute Z voxel.
    let peak = -Infinity, peakIndex = 0;
    for (let i = 0; i < zvol.data.length; i++) {
      const a = Math.abs(zvol.data[i]);
      if (Number.isFinite(a) && a > peak) {
        peak = a;
        peakIndex = i;
      }
    }
    state.xyz[2] = Math.floor(peakIndex / (bg.nx * bg.ny));
    const remainder = peakIndex - state.xyz[2] * bg.nx * bg.ny;
    state.xyz[1] = Math.floor(remainder / bg.nx);
    state.xyz[0] = remainder - state.xyz[1] * bg.nx;

    const bgLo = percentileSample(bg.data, 0.02);
    const bgHi = percentileSample(bg.data, 0.98);
    const bgRange = Math.max(1e-8, bgHi - bgLo);

    const sliders = [...root.querySelectorAll(".slice-slider")];
    const canvases = [...root.querySelectorAll(".slice-canvas")];
    const threshold = root.querySelector(".threshold");
    const opacity = root.querySelector(".opacity");
    const thresholdOut = root.querySelector(".threshold-value");
    const opacityOut = root.querySelector(".opacity-value");
    const coords = root.querySelector(".coord-readout");
    const status = root.querySelector(".viewer-status");

    const dims = [bg.nx, bg.ny, bg.nz];
    sliders.forEach((slider, axis) => {
      slider.max = String(dims[axis] - 1);
      slider.value = String(state.xyz[axis]);
      slider.addEventListener("input", () => {
        state.xyz[axis] = parseInt(slider.value, 10);
        renderAll();
      });
    });

    threshold.max = String(Math.max(5, Math.ceil(peak)));
    threshold.addEventListener("input", () => {
      state.threshold = parseFloat(threshold.value);
      thresholdOut.value = state.threshold.toFixed(1);
      renderAll();
    });

    opacity.addEventListener("input", () => {
      state.opacity = parseFloat(opacity.value);
      opacityOut.value = state.opacity.toFixed(2);
      renderAll();
    });

    function clampVoxel(value, size) {
      return Math.max(0, Math.min(size - 1, Math.round(value)));
    }

    function pointerToPlaneVoxel(canvas, axis, event) {
      const rect = canvas.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return null;

      // Convert CSS/display coordinates back to the canvas bitmap. The current
      // renderer only flips the vertical axis, so horizontal coordinates map
      // directly while vertical coordinates are inverted here.
      const uDisplay =
        (event.clientX - rect.left) * canvas.width / rect.width;
      const vDisplay =
        (event.clientY - rect.top) * canvas.height / rect.height;

      const u = clampVoxel(uDisplay, canvas.width);
      const v = clampVoxel(
        canvas.height - 1 - vDisplay,
        canvas.height,
      );

      if (axis === 0) {
        // Sagittal plane: x is fixed; pointer controls y and z.
        return [state.xyz[0], u, v];
      }
      if (axis === 1) {
        // Coronal plane: y is fixed; pointer controls x and z.
        return [u, state.xyz[1], v];
      }

      // Axial plane: z is fixed; pointer controls x and y.
      return [u, v, state.xyz[2]];
    }

    function moveCrosshairFromPointer(canvas, axis, event) {
      const xyz = pointerToPlaneVoxel(canvas, axis, event);
      if (xyz === null) return;

      state.xyz[0] = clampVoxel(xyz[0], bg.nx);
      state.xyz[1] = clampVoxel(xyz[1], bg.ny);
      state.xyz[2] = clampVoxel(xyz[2], bg.nz);
      renderAll();
    }

    canvases.forEach((canvas, axis) => {
      let dragging = false;

      canvas.addEventListener("pointerdown", event => {
        event.preventDefault();
        dragging = true;
        canvas.setPointerCapture(event.pointerId);
        moveCrosshairFromPointer(canvas, axis, event);
      });

      canvas.addEventListener("pointermove", event => {
        if (!dragging) return;
        event.preventDefault();
        moveCrosshairFromPointer(canvas, axis, event);
      });

      canvas.addEventListener("pointerup", event => {
        if (!dragging) return;
        dragging = false;
        if (canvas.hasPointerCapture(event.pointerId)) {
          canvas.releasePointerCapture(event.pointerId);
        }
      });

      canvas.addEventListener("pointercancel", event => {
        dragging = false;
        if (canvas.hasPointerCapture(event.pointerId)) {
          canvas.releasePointerCapture(event.pointerId);
        }
      });

      canvas.addEventListener("lostpointercapture", () => {
        dragging = false;
      });

      canvas.addEventListener("wheel", event => {
        event.preventDefault();
        const delta = event.deltaY > 0 ? 1 : -1;
        state.xyz[axis] = Math.max(
          0,
          Math.min(dims[axis] - 1, state.xyz[axis] + delta),
        );
        renderAll();
      }, {passive:false});
    });

    function planeSize(axis) {
      if (axis === 0) return [bg.ny, bg.nz];
      if (axis === 1) return [bg.nx, bg.nz];
      return [bg.nx, bg.ny];
    }

    function sample(axis, u, v) {
      if (axis === 0) return [state.xyz[0], u, v];
      if (axis === 1) return [u, state.xyz[1], v];
      return [u, v, state.xyz[2]];
    }

    function crosshair(axis) {
      if (axis === 0) return [state.xyz[1], state.xyz[2]];
      if (axis === 1) return [state.xyz[0], state.xyz[2]];
      return [state.xyz[0], state.xyz[1]];
    }

    function renderCanvas(canvas, axis) {
      const [w, h] = planeSize(axis);
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      const img = ctx.createImageData(w, h);

      for (let v = 0; v < h; v++) {
        for (let u = 0; u < w; u++) {
          const [x,y,z] = sample(axis, u, v);
          const idx = voxelIndex(bg, x, y, z);
          const g = Math.max(0, Math.min(255, Math.round(255 * (bg.data[idx] - bgLo) / bgRange)));

          // Flip vertical axis for conventional radiological-looking display.
          const outV = h - 1 - v;
          const out = 4 * (u + w * outV);
          img.data[out] = g;
          img.data[out+1] = g;
          img.data[out+2] = g;
          img.data[out+3] = 255;

          const c = overlayColor(zvol.data[idx], state.threshold, state.opacity);
          if (c) {
            const a = c[3] / 255;
            img.data[out]   = Math.round(img.data[out]   * (1-a) + c[0] * a);
            img.data[out+1] = Math.round(img.data[out+1] * (1-a) + c[1] * a);
            img.data[out+2] = Math.round(img.data[out+2] * (1-a) + c[2] * a);
          }
        }
      }

      ctx.putImageData(img, 0, 0);

      const [cu, cvRaw] = crosshair(axis);
      const cv = h - 1 - cvRaw;
      ctx.strokeStyle = "#00ff66";
      ctx.lineWidth = Math.max(1, Math.round(Math.min(w,h) / 180));
      ctx.beginPath();
      ctx.moveTo(cu + 0.5, 0);
      ctx.lineTo(cu + 0.5, h);
      ctx.moveTo(0, cv + 0.5);
      ctx.lineTo(w, cv + 0.5);
      ctx.stroke();
    }

    function renderAll() {
      canvases.forEach((canvas, axis) => renderCanvas(canvas, axis));
      sliders.forEach((slider, axis) => slider.value = String(state.xyz[axis]));

      const [x,y,z] = state.xyz;
      const mm = world(bg.affine, x, y, z);
      const zvalue = zvol.data[voxelIndex(zvol, x, y, z)];
      coords.textContent =
        `voxel [${x}, ${y}, ${z}] · mm [${mm.map(v => v.toFixed(1)).join(", ")}] · Z=${Number.isFinite(zvalue) ? zvalue.toFixed(3) : "n/a"}`;
    }

    status.textContent = `Interactive viewer ready · ${bg.nx}×${bg.ny}×${bg.nz}`;
    status.classList.add("viewer-ready");
    renderAll();
  }

  async function boot(root) {
    try {
      const [bgBuffer, zBuffer] = await Promise.all([
        fetchBuffer(root.dataset.background),
        fetchBuffer(root.dataset.overlay),
      ]);
      initViewer(root, parseNifti(bgBuffer), parseNifti(zBuffer));
    } catch (error) {
      showFileProtocolWarning(root, error.message || String(error));
    }
  }

  document.querySelectorAll(".nv-lite").forEach(boot);
})();
</script>
"""

    html_text = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)} — poststats</title>
<style>
body {{
  font-family: Arial, sans-serif;
  margin: 2rem auto;
  max-width: 1220px;
  line-height: 1.4;
  color: #222;
}}
h1 {{
  border-bottom: 3px solid #444;
  padding-bottom: .35rem;
}}
h2 {{
  border-bottom: 1px solid #bbb;
  padding-bottom: .25rem;
  margin-top: 2.2rem;
}}
img {{
  max-width: 100%;
  border: 1px solid #aaa;
  background: #000;
}}
table {{
  border-collapse: collapse;
  width: 100%;
  margin: .6rem 0 1.2rem;
}}
th, td {{
  border: 1px solid #ccc;
  padding: .35rem .55rem;
  text-align: right;
}}
th:first-child, td:first-child {{
  text-align: center;
}}
a {{ color: #0645ad; }}
.meta {{
  background: #f4f4f4;
  padding: .8rem 1rem;
  border: 1px solid #ddd;
}}
.muted, .viewer-help {{
  color: #666;
  font-size: .92rem;
}}
.warn, .viewer-error {{
  color: #9b2c2c;
  font-weight: bold;
}}
.viewer-ready {{
  color: #176b37;
  font-weight: bold;
}}
.nv-lite {{
  border: 1px solid #bbb;
  padding: .8rem;
  background: #fafafa;
  margin: .8rem 0 1rem;
}}
.viewer-controls {{
  display: flex;
  flex-wrap: wrap;
  gap: 1rem 2rem;
  align-items: center;
  margin: .6rem 0 .8rem;
}}
.viewer-controls label {{
  display: flex;
  align-items: center;
  gap: .45rem;
}}
.coord-readout {{
  font-family: monospace;
  margin-left: auto;
}}
.orthogonal-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .8rem;
}}
.plane {{
  min-width: 0;
}}
.plane-title {{
  text-align: center;
  font-weight: bold;
  margin-bottom: .25rem;
}}
.slice-canvas {{
  display: block;
  width: 100%;
  height: auto;
  background: #000;
  image-rendering: auto;
  border: 1px solid #666;
  cursor: crosshair;
  touch-action: none;
  user-select: none;
}}
.slice-slider {{
  width: 100%;
}}
.static-fallback {{
  margin: .8rem 0;
}}
.static-fallback summary {{
  cursor: pointer;
  font-weight: bold;
  margin-bottom: .4rem;
}}
@media (max-width: 800px) {{
  .orthogonal-grid {{ grid-template-columns: 1fr; }}
  .coord-readout {{ width: 100%; margin-left: 0; }}
}}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="meta">
<strong>FEAT directory:</strong> {html.escape(str(feat_dir))}<br>
<strong>Background:</strong> {bg_text}<br>
<strong>Initial display threshold:</strong> |Z| ≥ {z_threshold:g}<br>
<strong>Generated:</strong> {datetime.now().isoformat(timespec="seconds")}<br>
<strong>Design:</strong> {' · '.join(design_links) if design_links else 'not available'}
</div>
{''.join(sections)}
{interactive_js}
</body>
</html>
"""

    temporary = report_file.with_name(report_file.name + ".tmp")
    temporary.write_text(html_text, encoding="utf-8")
    temporary.replace(report_file)
    return report_file



def _write_gfeat_report_index(
    gfeat_dir: Path,
    *,
    title: str | None = None,
) -> Path:
    """Create a visual contrast browser for a FEAT ``.gfeat`` directory.

    The index auto-discovers ``contrast-*.feat`` children. Each card links to
    ``report_poststats.html`` and uses ``report_poststats_files/zstat1.png`` as
    a preview when available. A small advisory lock makes repeated/concurrent
    refreshes safe when level-2/level-3 contrasts finish in parallel.
    """
    from datetime import datetime
    import html

    gfeat_dir = Path(gfeat_dir).resolve()
    if not gfeat_dir.is_dir():
        raise click.ClickException(
            f"Cannot create gfeat report index; directory does not exist: "
            f"{gfeat_dir}"
        )

    index_file = gfeat_dir / "index.html"
    lock_file = gfeat_dir / ".report_index.lock"

    def _contrast_name(feat_dir: Path) -> str:
        name = feat_dir.name
        if name.startswith("contrast-") and name.endswith(".feat"):
            return name[len("contrast-"):-len(".feat")]
        return feat_dir.stem

    def _natural_key(value: str) -> list[object]:
        return [
            int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", value)
        ]

    with open(lock_file, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            contrast_dirs = sorted(
                (
                    path
                    for path in gfeat_dir.glob("contrast-*.feat")
                    if path.is_dir()
                ),
                key=lambda path: _natural_key(_contrast_name(path)),
            )

            cards: list[str] = []
            ready_count = 0

            for feat_dir in contrast_dirs:
                contrast_name = _contrast_name(feat_dir)
                report = feat_dir / "report_poststats.html"
                preview = (
                    feat_dir
                    / "report_poststats_files"
                    / "zstat1.png"
                )

                report_rel = os.path.relpath(report, gfeat_dir)
                preview_rel = os.path.relpath(preview, gfeat_dir)

                if report.is_file():
                    ready_count += 1
                    status = "<span class='status ready'>Interactive report</span>"
                    action = (
                        f"<a class='button' href='{html.escape(report_rel)}'>"
                        "Open report <span aria-hidden='true'>→</span></a>"
                    )
                    card_class = "contrast-card"
                else:
                    status = "<span class='status pending'>Report pending</span>"
                    action = (
                        "<span class='button disabled'>Report unavailable</span>"
                    )
                    card_class = "contrast-card unavailable"

                if preview.is_file():
                    media = (
                        f"<a class='preview-link' href='{html.escape(report_rel)}'>"
                        f"<img loading='lazy' src='{html.escape(preview_rel)}' "
                        f"alt='Z-stat preview for {html.escape(contrast_name)}'>"
                        "</a>"
                        if report.is_file()
                        else (
                            f"<div class='preview-link'>"
                            f"<img loading='lazy' src='{html.escape(preview_rel)}' "
                            f"alt='Z-stat preview for {html.escape(contrast_name)}'>"
                            "</div>"
                        )
                    )
                else:
                    media = (
                        "<div class='preview-placeholder'>"
                        "<span>No preview yet</span>"
                        "</div>"
                    )

                # Add a small semantic tag without imposing experiment-specific
                # assumptions on the ordering.
                if "minus" in contrast_name.lower():
                    kind = "Difference"
                else:
                    kind = "Contrast"

                cards.append(
                    f"""
<article class="{card_class}" data-name="{html.escape(contrast_name.lower())}">
  {media}
  <div class="card-body">
    <div class="card-topline">
      <span class="kind">{kind}</span>
      {status}
    </div>
    <h2>{html.escape(contrast_name)}</h2>
    {action}
  </div>
</article>
"""
                )

            display_title = (
                title.strip()
                if title and title.strip()
                else gfeat_dir.name.removesuffix(".gfeat")
            )

            html_text = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(display_title)} — FEAT contrasts</title>
<style>
:root {{
  color-scheme: light;
  --page: #f4f6f8;
  --surface: #ffffff;
  --surface-soft: #f8fafb;
  --text: #17202a;
  --muted: #68737d;
  --border: #d8dee4;
  --accent: #2457a6;
  --accent-dark: #173d78;
  --ready: #1b6f42;
  --ready-bg: #e9f7ef;
  --pending: #8a5a00;
  --pending-bg: #fff6dd;
  --shadow: 0 4px 16px rgba(22, 32, 42, 0.08);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  background: var(--page);
  color: var(--text);
}}
header {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}}
.header-inner,
main {{
  width: min(1500px, calc(100% - 40px));
  margin: 0 auto;
}}
.header-inner {{
  padding: 30px 0 24px;
}}
.eyebrow {{
  margin: 0 0 7px;
  color: var(--accent);
  font-size: .78rem;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}}
h1 {{
  margin: 0;
  font-size: clamp(1.6rem, 3vw, 2.35rem);
  line-height: 1.15;
}}
.summary {{
  margin-top: 12px;
  color: var(--muted);
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
}}
main {{
  padding: 28px 0 48px;
}}
.toolbar {{
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 22px;
}}
.search {{
  width: min(460px, 100%);
  padding: 11px 13px;
  font: inherit;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
  gap: 20px;
}}
.contrast-card {{
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow);
}}
.contrast-card.hidden {{
  display: none;
}}
.preview-link {{
  display: block;
  aspect-ratio: 16 / 8.3;
  overflow: hidden;
  background: #101214;
  border-bottom: 1px solid var(--border);
}}
.preview-link img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform .18s ease;
}}
.contrast-card:not(.unavailable) .preview-link:hover img {{
  transform: scale(1.015);
}}
.preview-placeholder {{
  aspect-ratio: 16 / 8.3;
  display: grid;
  place-items: center;
  color: #929aa1;
  background:
    linear-gradient(135deg, #171a1d 0%, #24282c 100%);
  border-bottom: 1px solid var(--border);
}}
.card-body {{
  display: flex;
  flex: 1;
  flex-direction: column;
  padding: 16px;
}}
.card-topline {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}}
.kind {{
  color: var(--muted);
  font-size: .78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .05em;
}}
.status {{
  border-radius: 999px;
  padding: 4px 8px;
  font-size: .74rem;
  font-weight: 700;
}}
.status.ready {{
  color: var(--ready);
  background: var(--ready-bg);
}}
.status.pending {{
  color: var(--pending);
  background: var(--pending-bg);
}}
.contrast-card h2 {{
  margin: 12px 0 18px;
  font-size: 1.16rem;
  overflow-wrap: anywhere;
}}
.button {{
  margin-top: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 7px;
  background: var(--accent);
  color: #fff;
  text-decoration: none;
  font-weight: 700;
}}
.button:hover {{
  background: var(--accent-dark);
}}
.button.disabled {{
  background: #e4e8eb;
  color: #818a92;
  cursor: default;
}}
.empty {{
  padding: 32px;
  color: var(--muted);
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: 10px;
}}
footer {{
  margin-top: 28px;
  color: var(--muted);
  font-size: .85rem;
}}
@media (max-width: 600px) {{
  .header-inner,
  main {{
    width: min(100% - 24px, 1500px);
  }}
}}
</style>
</head>
<body>
<header>
  <div class="header-inner">
    <p class="eyebrow">FEAT group results</p>
    <h1>{html.escape(display_title)}</h1>
    <div class="summary">
      <span><strong>{len(contrast_dirs)}</strong> contrasts</span>
      <span><strong>{ready_count}</strong> interactive reports ready</span>
      <span>Generated {datetime.now().isoformat(timespec="seconds")}</span>
    </div>
  </div>
</header>
<main>
  <div class="toolbar">
    <input
      id="contrast-search"
      class="search"
      type="search"
      placeholder="Filter contrasts…"
      aria-label="Filter contrasts"
    >
  </div>
  {
      '<div class="grid" id="contrast-grid">' + ''.join(cards) + '</div>'
      if cards
      else '<div class="empty">No contrast-*.feat directories found.</div>'
  }
  <footer>
    Click a preview or “Open report” to inspect the interactive Z-stat viewer.
  </footer>
</main>
<script>
(() => {{
  const input = document.getElementById("contrast-search");
  if (!input) return;

  input.addEventListener("input", () => {{
    const query = input.value.trim().toLowerCase();
    document.querySelectorAll(".contrast-card").forEach(card => {{
      const name = card.dataset.name || "";
      card.classList.toggle("hidden", query && !name.includes(query));
    }});
  }});
}})();
</script>
</body>
</html>
"""

            temporary = index_file.with_name(
                f".{index_file.name}.{os.getpid()}.tmp"
            )
            try:
                temporary.write_text(html_text, encoding="utf-8")
                temporary.replace(index_file)
            finally:
                if temporary.exists():
                    temporary.unlink()

        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return index_file


def _maybe_write_gfeat_report_index(
    feat_dir: Path,
) -> Path | None:
    """Refresh the parent .gfeat visual index when applicable."""
    gfeat_dir = Path(feat_dir).resolve().parent
    if gfeat_dir.suffix != ".gfeat":
        return None

    try:
        index = _write_gfeat_report_index(gfeat_dir)
        click.echo(f"Group report index: {index}")
        return index
    except Exception as error:
        click.echo(
            f"[WARN] Could not refresh group report index for {gfeat_dir}: "
            f"{error}",
            err=True,
        )
        return None


def _maybe_write_poststats_report(
    feat_dir: Path,
    *,
    title: str,
    contrast_names: list[str] | None,
    enabled: bool,
    z_threshold: float,
    background: Path | None = None,
) -> Path | None:
    if not enabled:
        return None

    try:
        report = _write_poststats_report(
            feat_dir,
            title=title,
            contrast_names=contrast_names,
            z_threshold=z_threshold,
            background=background,
        )
        click.echo(f"Poststats report: {report}")

        index = _maybe_write_gfeat_report_index(feat_dir)

        if index is not None:
            gfeat_dir = Path(feat_dir).resolve().parent
            click.echo(
                "  To browse all contrast reports:\n"
                f"    cd {gfeat_dir}\n"
                "    python -m http.server 8000\n"
                "  Then visit: http://localhost:8000/"
            )
        else:
            click.echo(
                "  To view the interactive report:\n"
                f"    cd {feat_dir}\n"
                "    python -m http.server 8000\n"
                f"  Then visit: http://localhost:8000/{report.name}"
            )

        return report
    except Exception as error:
        click.echo(
            f"[WARN] Could not generate poststats report for {feat_dir}: {error}",
            err=True,
        )
        return None



def _group_contrast_names(specs: tuple[str, ...]) -> list[str]:
    """Return group-contrast names in the same order used for output COPEs."""
    if not specs:
        return ["GroupMean"]

    names: list[str] = []
    for spec in specs:
        name = str(spec).split(";", 1)[0].strip()
        if not name:
            raise click.ClickException(
                f"Invalid --group-contrast specification with empty name: {spec!r}"
            )
        names.append(name)
    return names


def _records_from_existing_group_output(
    *,
    rows: pd.DataFrame,
    input_level: int,
    output_dir: Path,
    session: str,
    task: str,
    canonical_name: str,
    runmode: str,
    group_contrast_specs: tuple[str, ...],
    registration_mode: str,
    registered_subdir: str,
) -> list[dict[str, Any]]:
    """Reconstruct level-3 manifest records from an existing group FEAT output.

    This is deliberately strict about the statistical outputs needed to prove
    that the analysis completed. Existing directories that are incomplete are
    reported as errors instead of being silently entered into the manifest.
    """
    stats_dir = output_dir / "stats"
    if not stats_dir.is_dir():
        raise click.ClickException(
            f"Existing group output is incomplete; missing stats directory: {stats_dir}"
        )

    number_of_subjects = int(rows["subject"].nunique())
    number_of_inputs = int(len(rows))
    contrast_names = _group_contrast_names(group_contrast_specs)

    records: list[dict[str, Any]] = []

    for index, group_contrast in enumerate(contrast_names, start=1):
        cope = stats_dir / f"cope{index}.nii.gz"
        varcope = stats_dir / f"varcope{index}.nii.gz"
        tstat = stats_dir / f"tstat{index}.nii.gz"
        zstat = stats_dir / f"zstat{index}.nii.gz"

        required = [cope, tstat, zstat]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise click.ClickException(
                "Existing group output is incomplete; missing mandatory file(s): "
                + ", ".join(missing)
            )

        records.append(
            {
                "session": session,
                "task": task,
                "canonical_name": canonical_name,
                "group_contrast": group_contrast,
                "input_level": input_level,
                "runmode": runmode,
                "registration_mode": registration_mode,
                "registered_subdir": registered_subdir,
                "number_of_inputs": number_of_inputs,
                "number_of_subjects": number_of_subjects,
                "group_dir": str(output_dir),
                "cope_file": str(cope),
                "varcope_file": str(varcope) if varcope.is_file() else "",
                "tstat_file": str(tstat),
                "zstat_file": str(zstat),
            }
        )

    return records

