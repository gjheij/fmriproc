.. include:: links.rst

Pipeline Steps
==============

Step-by-step run-through
------------------------

The input dataset is required to be in valid **BIDS (Brain Imaging Data Structure)** format.
The directory pointing to the project should be specified in the ``~/.spinoza_config`` file (see :ref:`spinoza_config_example`) as ``$DIR_PROJECTS``.
Then specify the project name as ``$PROJECT``. It is assumed your converted data lives in:

.. code-block:: bash    

    $DIR_PROJECTS/$PROJECT/<subjects>

It is also assumed your ``T1w`` files have the ``acq-(ME)MP(2)RAGE`` tag in the filename.
This is because the package can deal with either of these, or an *average* of MP2RAGE and MP2RAGEME acquisitions 
(see e.g., `this article <https://www.sciencedirect.com/science/article/pii/S105381192031168X?via%3Dihub>`_).
So, a typical folder structure would look like this:

.. code-block:: bash

    tree $DIR_PROJECTS/$PROJECT/sub-001
    sub-001
    └── ses-1
        ├── anat
        │   ├── sub-001_ses-1_acq-3DTSE_T2w.nii.gz
        │   ├── sub-001_ses-1_acq-3DTSE_T2w.json
        │   ├── sub-001_ses-1_acq-MP2RAGE_inv-1_part-mag.nii.gz
        │   ├── sub-001_ses-1_acq-MP2RAGE_inv-1_part-phase.nii.gz
        │   ├── sub-001_ses-1_acq-MP2RAGE_inv-2_part-mag.nii.gz
        │   └── sub-001_ses-1_acq-MP2RAGE_inv-2_part-phase.nii.gz
        ├── fmap  # for distortion correction
        │   ├── sub-001_ses-1_task-2R_run-1_epi.json
        │   └── sub-001_ses-1_task-2R_run-1_epi.nii.gz
        ├── func  # BOLD files
        │   ├── sub-001_ses-1_task-2R_run-1_bold.json
        │   └── sub-001_ses-1_task-2R_run-1_bold.nii.gz    
        └── phase  # for NORDIC
            └── sub-001_ses-1_task-2R_run-1_bold_ph.nii.gz

The pipeline is controlled through the ``master`` script.
Using the ``-m`` flag, different modules can be executed.
Since all file paths have been set using the setup file, this doesn’t require much input.
Type ``master`` in the command line to see the different modules.
The modules mostly depend on previous steps, but some (especially for preprocessing anatomical images) can be skipped.

**Data Conversion**
First, we need to convert our **DICOMs/PARRECs** to NIfTI files. We do this by placing the raw files in the ``sourcedata`` folder of our project:

.. code-block:: bash

    tree $DIR_PROJECTS/$PROJECT/sourcedata/sub-001
    sub-001
    └── ses-1
        ├── task  # put the outputs from Exptools2 here
        │   ├── sub-001_ses-1_task-2R_run-1_Logs
        │   │   ├── sub-001_ses-1_task-2R_run-1_Screenshots
        │   │   │   └── <bunch of png-files>
        │   │   ├── sub-001_ses-1_task-2R_run-1_desc-screen.json
        │   │   ├── sub-001_ses-1_task-2R_run-1_events.tsv
        │   │   ├── sub-001_ses-1_task-2R_run-1_settings.yml
        │   ├── sub-001_ses-1_task-2R_run-2_Logs
        │   └── sub-001_ses-1_task-2R_run-3_Logs
        └── Raw files (DICOMs/PARRECs)  # individual files, not a folder!

PAR/REC files should be placed directly in the ``sub-<subID>/<ses-sesID>/*`` folder:

.. code-block:: bash

    $DIR_PROJECTS/$PROJECT/sourcedata/sub-<subID>/ses-<sesID>
    ├── log.txt
    ├── nifti  # converted files
    │   └── ...
    ├── su_31032023_1043064_16_1_acq-mp2rage_desc-anat_t1wV4.par
    ├── su_31032023_1043064_16_1_acq-mp2rage_desc-anat_t1wV4.rec
    ├── su_31032023_1059524_18_1_task-scenes_run-1_acq-3depi_boldV4.par
    ├── su_31032023_1059524_18_1_task-scenes_run-1_acq-3depi_boldV4.rec
    ├── su_31032023_1105288_19_1_task-scenes_run-1_acq-3depi_epiV4.par
    └── su_31032023_1105288_19_1_task-scenes_run-1_acq-3depi_epiV4.rec



.. note::

    **File Naming within PAR/DCM Files**

    The conversion combines the ``PatientName`` and ``ProtocolName`` to generate a BIDSified filename.
    To ensure the pipeline recognizes the files, certain elements must be present, such as:
    
    - ``sub-`` (subject ID)
    - ``ses-`` (optional session ID)
    - ``acq-MPRAGE_T1w`` (for anatomical)
    - ``T2w`` (for structural T2-weighted)
    - ``*_bold`` (for functional data)
    - ``*_epi`` (for fieldmaps)
    
    The ``PatientName`` is set at the scanner console while registering the participant, and the ``ProtocolName`` is the sequence name.

    If renaming files post-acquisition, use:

    .. code-block:: bash

        for par in /path/to/par/*.PAR; do
          call_replace "registered_name" "sub-01_ses-1" "${par}"
        done

        # And for functionals:
        call_replace "protocol_name" "task-rest_run-1_bold" "bold.par"
        call_replace "protocol_name" "task-rest_run-1_epi" "epi.par"

    For **DICOM files**, the `pydicom`-based function can be used:

    .. code-block:: bash

        call_dcm /path/to/6_dzne-bn_fmri_0p9iso_TR2p9_3x2z1_RefEpi_E00_M "PatientName,ProtocolName" "sub-01_ses-1,task-rest_bold"
        call_dcm /path/to/8_dzne-bn_fmri_0p9iso_TR2p9_3x2z1_RefEpi_revPE_E00_M "PatientName,ProtocolName" "sub-01_ses-1,task-rest_epi"
        call_dcm /path/to/9_dzne-bn_MPRAGE_UPCS_0p6iso_p3__GT "PatientName,ProtocolName" "sub-01_ses-1,acq-MPRAGE_T1w"

    This modifies metadata by specifying key-value pairs.

.. code-block:: bash

    # standard options
    master -m 02a -s 01,02 -n 2

    # submit to cluster
    master -m 02a -s 01,02 -n 2 --sge

    # use specific TR (see NOTE below)
    master -m 02a -s 01,02 -t 2.9

    # use specific PhaseEncodingDirection for BOLD (will be inverted for FMAP) (see NOTE below)
    master -m 02a -s 01,02 -n 2 --ap/--pa/--lr/--rl

.. admonition:: Populating JSON Sidecars
    :class: note 

    Additionally, the pipeline attempts to read the **phase-encoding direction** from the PAR/DCM file, though this is not always reliable.
    There are multiple ways to populate the `PhaseEncodingDirection` field in your JSON files:

    .. rubric:: **Phase Encoding Direction Options**
    
    1. Accept defaults: ``AP`` for BOLD and ``PA`` for fieldmaps.
    2. Set ``export PE_DIR_BOLD=<value>`` in the configuration file (one of ``AP``, ``PA``, ``LR``, or ``RL``).

        - This sets the **BOLD** phase-encoding direction, and the pipeline assumes the opposite for fieldmaps.

    3. Use one of the following flags when calling ``master``:

        - ``--ap``, ``--pa``, ``--lr``, or ``--rl``
        - These specify the **BOLD** phase-encoding direction.

    4. Manually edit the JSON files after processing (less recommended).

    .. rubric:: **IntendedFor Field**

    The pipeline can automatically populate the ``IntendedFor`` field in the JSON files, provided one of these conditions is met:

    1. Each **BOLD** acquisition has a corresponding fieldmap (**recommended**).
    2. One **fieldmap** is used for every two **BOLD** acquisitions.
    3. A single **fieldmap** is used for all **BOLD** runs.

    If your dataset follows a different structure, you may need to manually edit the ``IntendedFor`` field.

    .. rubric:: **SliceTiming Calculation**

    If you have a **2D acquisition**, the pipeline can populate the `SliceTiming` field.
    It determines this information from:

        - **TR**, **number of slices**, and **multiband factor** (from the PAR-file).
        - Assumes **interleaved acquisition**.

    For further details, see the `slicetiming <https://fmriproc.readthedocs.io/en/latest/classes/image.html#fmriproc.image.slice_timings>`_ function.

    .. rubric:: **Repetition Time (TR) Handling**

    The **Repetition Time (TR)** can be determined using several strategies:

    1. **Manual specification** via the ``-t <tr>`` flag when calling ``master -m 02a``.
    2. **For DICOM files**, the pipeline applies:

        - Parsing TR from filename (e.g., ``TR2.9``, ``TR=2.9``, ``TR_2p9``, ``_TR2p9_``).
        - Extracting TR from the **DICOM header** (sometimes unreliable).
        - Calculating **TR = NumSlices × SliceMeasurementDuration** (for 2D acquisitions).
        - Applying multi-band correction **(TR / MultiBandFactor)** for multi-band sequences.

    3. **For PAR files**, the TR is determined from the **timing between volumes**, either:
    
        - Using the **first interval**, or
        - Averaging across the entire run.

    The pipeline then **corrects the NIfTI headers** accordingly.

**MRI Quality Control (MRIqc)**
Once data has been converted to NIfTI, **basic QC** can be performed using `MRIqc`.
This generates a report for all BOLD and anatomical images.

To run **MRIqc for functional images only**:

.. code-block:: bash

    # only functional files
    master -m 02b --func-only

    # MRIqc for anatomical images only
    master -m 02b --anat-only

    # specific session
    master -m 02b -n 1

**Anatomical Preprocessing with Pymp2rage**
The next step involves **creating T1w/T1map images** from the **first and second inversion images** using **Pymp2rage**.

.. admonition:: Multiple Anatomical Images in a Session
    :class: tip
    
    Most regular sessions will have an **MP2RAGE** or **MPRAGE** as the anatomical reference.
    The pipeline can handle these cases automatically.
    However, in more complex cases with **multiple MPRAGEs**, **MPRAGE + T1map**, or **MP2RAGE + MP2RAGEME**, 
    additional considerations are needed.

    .. rubric:: **Multiple MPRAGEs**

    If you have multiple **MPRAGE** acquisitions, they should include a **run-<runID>** identifier (e.g., ``run-1`` will be used as the reference).
    In this case, set ``DATA=AVERAGE``.

    **Example Folder Structure (Raw Data):**

    .. code-block:: bash

        /path/to/projects/some_project/sub-04
        └── ses-1
            └── anat
                ├── sub-04_ses-1_acq-MPRAGE_run-1_T1w.nii.gz
                └── sub-04_ses-1_acq-MPRAGE_run-2_T1w.nii.gz

    **Example Folder Structure (Processed Output):**

    .. code-block:: bash

        /path/to/projects/some_project/derivatives/pymp2rage/sub-04
        └── ses-1
            ├── spm_mask.m
            ├── sub-04_ses-1_acq-AVERAGE_T1w.nii.gz
            ├── sub-04_ses-1_acq-AVERAGE_desc-spm_mask.nii.gz
            ├── sub-04_ses-1_acq-MPRAGE_run-1_T1w.nii.gz
            ├── sub-04_ses-1_acq-MPRAGE_run-1_desc-spm_mask.nii.gz
            ├── sub-04_ses-1_acq-MPRAGE_run-2_T1w.nii.gz
            ├── sub-04_ses-1_acq-MPRAGE_run-2_desc-spm_mask.nii.gz
            └── sub-04_ses-1_acq-MPRAGE_run-2_space-run1_T1w.nii.gz

    .. rubric:: **MPRAGE + T1map**
    
    With **MP2RAGE**, a **T1map** is generated, but **MPRAGE** does not produce one.
    However, you can still include a separate **T1map**, which will be registered to the **T1w** image.

    **Example Folder Structure:**

    .. code-block:: bash

        /path/to/projects/some_project/sub-03
        └── ses-1
            └── anat
                ├── sub-03_ses-1_acq-MPRAGE_T1w.nii.gz
                └── sub-03_ses-1_acq-VFA_T1map.nii.gz

    .. rubric:: **MP2RAGE + MP2RAGEME**

    **MP2RAGEME** is an extension of **MP2RAGE**, introducing additional echoes for multi-contrast imaging.
    In this case, the **MP2RAGEME** images are registered to **MP2RAGE**.
    Additional parametric maps can be warped using:

    .. code-block:: bash

        export WARP_2_MP2RAGE=("T1w" "T1map" "R2starmap")

    **Example Folder Structure:**

    .. code-block:: bash

        /path/to/projects/some_project/sub-05
        └── ses-1
            └── anat
                ├── sub-05_ses-1_acq-MP2RAGE_inv-1_part-mag.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGE_inv-1_part-phase.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGE_inv-2_part-mag.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGE_inv-2_part-phase.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-1_part-mag.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-1_part-phase.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-2_echo-1_part-mag.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-2_echo-1_part-phase.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-2_echo-2_part-mag.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-2_echo-2_part-phase.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-2_echo-3_part-mag.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-2_echo-3_part-phase.nii.gz
                ├── sub-05_ses-1_acq-MP2RAGEME_inv-2_echo-4_part-mag.nii.gz
                └── sub-05_ses-1_acq-MP2RAGEME_inv-2_echo-4_part-phase.nii.gz


To run this step:

.. code-block:: bash

    master -m 04  # spinoza_qmrimaps

If you already have a **T1w** or **T1map** file (e.g., from Siemens data), you can **skip** this step.

If you have multiple acquisitions (e.g., **MP2RAGE + MP2RAGEME**, or multiple **MPRAGE** images), you can **average them** together:

.. code-block:: bash

    master -m 05a  # spinoza_registration (anat-to-anat)
    master -m 06   # spinoza_averageanatomies

This step only applies if **DATA=AVERAGE** is specified in the setup file.

**Registering Anatomical Images to MNI Space**
To register anatomical images to **MNI space**, use:

.. code-block:: bash

    master -m 05b  # spinoza_registration (anat-to-MNI)
    
    # use affine registration
    master -m 05b --affine

This generates transformation matrices and MNI-aligned images.

**Bias Correction & Brain Extraction**
Bias correction is applied to remove **intensity inhomogeneities**. To apply **bias correction and denoising**:

.. code-block:: bash

    master -m 08  # spinoza_biassanlm

    # use spm
    master -m 08 --spm

    # use N4BiasFieldCorrection
    master -m 08 --n4

To perform **brain extraction** using CAT12:

.. code-block:: bash

    master -m 09  # spinoza_brainextraction

    # full processing including Bias correction & SANLM
    master -m 09 --full

**Running FreeSurfer**
Once anatomical preprocessing is complete, FreeSurfer reconstruction can be run **outside** of fMRIPrep:

.. code-block:: bash

    master -m 14  # spinoza_freesurfer

    # brainmask, white matter, pial edits
    master -m 14 -s 00 -r 23 -e {wm,pial,cp,aseg}  

    # expert options
    master -m 14 -s 00 -x expert.opts

**Running fMRIPrep**
Once FreeSurfer has finished, fMRIPrep can be run:

.. note::

    **Running fMRIPrep**

    The pipeline allows for three ways to run fMRIprep_:

    - `Singularity Image <https://www.nipreps.org/apps/singularity/>`_: Recommended for HPC clusters.
    - `fMRIPrep-Docker <https://fmriprep.org/en/latest/installation.html#the-fmriprep-docker-wrapper>`_: A Docker wrapper around ``fmriprep``.
      
      For installation of Docker, see `here <https://www.nipreps.org/apps/docker/>`_.
      This is the recommended approach for local laptop/PC usage.
    - **fMRIPrep Executable**: When you install fMRIprep_ via ``pip``, it includes an ``fmriprep`` executable.
      
      If you choose this method, consider installing `fpreputils <https://reproducibility.stanford.edu/fmriprep-tutorial-running-the-docker-image/>`_,
      which provides the ``fmriprep`` executable along with additional functions for handling **partial FOV** acquisitions (such as **surface coil acquisitions**).

.. code-block:: bash

    master -m 15 --func  # Include functional data

    # run specific task
    master -m 15 -t <task_name>

    # use configuration file
    master -m 15 --func -u $DIR_SCRIPTS/misc/fmriprep_config.json

    # skip fMRIPrep entirely and only fetch transformation files
    master -m 15 --warp-only

**Denoising Functional Data (Pybest)**
To apply **Pybest denoising** on the functional data:

.. code-block:: bash

    master -m 16  # spinoza_denoising

    # do not use unzscoring
    master -m 16 --no-raw

    # submit to cluster
    master -m 16 --sge -j 10

**pRF Fitting**
To run **pRF fitting** with **pRFpy**, use:

.. code-block:: bash

    master -m 17  # spinoza_fitprfs

    # use DN-model
    master -m 17 --norm

    # cut the first 4 volumes
    master -m 17 -s 006 --norm -v 4 -j 25

**Final Steps: Nighres-Based Segmentations**
These modules **optimize cortical segmentations** and should be run in sequence:

.. code-block:: bash

    master -m 20  # spinoza_segmentmgdm
    master -m 21  # spinoza_extractregions
    master -m 22  # spinoza_cortexreconstruction
    master -m 23  # spinoza_layering

To use **Wagstyl's equivolumetric layering**, instead of **Nighres' volumetric layering**:

.. code-block:: bash

    master -m 23 --surface


Vanilla pipeline
----------------

Below is a **step-by-step guide** on how to execute the preprocessing pipeline.

1. **Convert Raw Data to NIfTI**

   .. code-block:: bash

      master -m 02a -s <subjectID> -n <sessionID>

2. **Run Quality Control with MRIQC**

   .. code-block:: bash

      master -m 02b -s <subjectID> -n <sessionID>

3. **Apply NORDIC Denoising (Optional)**

   .. code-block:: bash

      master -m 10 -s <subjectID> -n <sessionID> --sge

4. **Run FreeSurfer Surface Reconstruction**

   .. code-block:: bash

      master -m 14 -s <subjectID> -n <sessionID>

5. **Run fMRIprep**

   .. code-block:: bash

      master -m 15 -s <subjectID> -n <sessionID> --func

6. **Denoise Functional Data with Pybest**

   .. code-block:: bash

      master -m 16 -s <subjectID> -n <sessionID> --sge


Running FEAT
============

After preprocessing with fMRIPrep, statistical analyses can be run with
FSL FEAT through the ``spinoza_feat`` wrapper.

The FEAT workflow consists of three analysis levels:

1. **First level** -- fit the GLM separately to each functional run.
2. **Second level** -- combine runs within a subject using fixed-effects analysis.
3. **Third level** -- combine subjects in a group-level analysis.

Between the first and second level, the registration information expected by
FEAT must be reconstructed from the transformations generated by fMRIPrep.
This is handled by ``spinoza_featreg``.

A typical workflow therefore looks like::

    fMRIPrep
        |
        v
    FEAT level 1
        |
        +---- contrast_manifest.tsv
        |
        v
    spinoza_featreg
        |
        v
    FEAT level 2
        |
        +---- contrast_manifest_level2.tsv
        |
        v
    FEAT level 3


First-level analysis
--------------------

The first-level analysis fits a separate GLM to every selected functional run.
Use FEAT level 1 for this::

    master -m 28 \
        -l 1 \
        -j 6 \
        -x '--task SC2F --space T1w --dry-run --desc masked'

The ``-l 1`` argument selects first-level FEAT analysis.

Options supplied through ``-x`` are passed to ``call_feat``. For example,
``--task`` selects the task and ``--space`` determines which preprocessed
BOLD images are used.
It is usually useful to run with ``--dry-run`` first. This generates or
checks the FEAT designs without immediately running all analyses.
Once the designs have been inspected, remove ``--dry-run`` to run the
first-level analyses.

Subjects can also be restricted explicitly::

    master -m 28 \
        -l 1 \
        -s 01,02,03 \
        -j 3 \
        -x '--task SC2F --space T1w --desc masked'

Alternatively, subjects can be supplied directly to ``call_feat`` through
the pass-through arguments when appropriate.
If you have run ``pybest``, you can specify ``--desc pybest`` to use the denoised BOLD images.

The first-level output consists of one ``.feat`` directory for each run,
for example::

    derivatives/feat/level1/
    |-- sub-01_ses-1_task-SC2F_run-1_space-T1w.feat/
    |-- sub-01_ses-1_task-SC2F_run-2_space-T1w.feat/
    |-- sub-02_ses-1_task-SC2F_run-1_space-T1w.feat/
    `-- ...


Contrasts
~~~~~~~~~

Contrasts define the statistical effects that should be tested after fitting
the GLM. They can be supplied explicitly, for example::

    master -m 28 \
        -l 1 \
        -x '--task SC2F \
            --space T1w \
            --contrast "USp;T;USp;1"'

Multiple contrasts may be generated for a single first-level analysis::

    master -m 28 \
        -l 1 \
        -x '--task SC2F \
            --space T1w \
            --contrast "USp;T;USp;1" \
            --contrast "Threat;T;CSpu,CSm;1,-1"'

Each contrast produces a corresponding ``cope`` image. These cope images,
rather than the complete first-level model, are the inputs to the higher-level
FEAT analyses.


The contrast manifest
---------------------

A central part of the ``spinoza_feat`` workflow is the **contrast manifest**.
After the first-level analyses, ``call_feat`` records the available contrast
outputs in::

    derivatives/feat/level1/contrast_manifest.tsv

The manifest acts as an index between analysis levels. Conceptually, each row
identifies a statistical image produced by a particular first-level analysis,
together with the metadata needed to find and combine it at the next level.

For example, it associates information such as::

    subject
    session
    task
    run
    contrast
    cope
    FEAT directory

The exact columns depend on the version of the FEAT scripts, but the important
idea is that **higher-level analyses do not need to rediscover contrast images
by searching arbitrary FEAT directories**. Instead, they select the appropriate
COPEs from the manifest.
For example, suppose every subject has three runs and every run contains the
contrast ``USp``. The level-1 manifest conceptually contains entries such as::

    sub-01  run-1  USp  cope1
    sub-01  run-2  USp  cope1
    sub-01  run-3  USp  cope1
    sub-02  run-1  USp  cope1
    sub-02  run-2  USp  cope1
    sub-02  run-3  USp  cope1

At level 2, the three ``USp`` COPEs belonging to ``sub-01`` can therefore be
combined independently of those belonging to ``sub-02``.
This also avoids relying on the numerical COPE number alone. ``cope1`` is an
implementation detail of a particular first-level design; the contrast name
in the manifest describes the statistical effect that should be propagated
to the next analysis level.


Registration for higher-level FEAT analyses
-------------------------------------------

fMRIPrep performs spatial registration outside of FEAT. Consequently, a FEAT
directory generated from fMRIPrep data does not necessarily contain the
``reg`` and ``reg_standard`` information expected by higher-level FSL tools.
``spinoza_featreg`` reconstructs this registration information using the
transformations generated by fMRIPrep. It can operate on both first-level and
second-level FEAT directories.
The FEAT level is selected with ``-l``:

* ``-l 1`` operates on ``derivatives/feat/level1``;
* ``-l 2`` operates on ``derivatives/feat/level2``.

This distinction is important when first-level analyses are performed in T1w
space but the final group analysis should be performed in MNI space. In that
case, the recommended workflow is:

1. Run the first-level analyses in T1w space.
2. Run the second-level fixed-effects analyses in T1w space.
3. Reconstruct the T1w-to-MNI registration on the **second-level** FEAT
   directories.
4. Run the third-level analysis using the registered second-level results.

For example, after completing the second-level analyses::

    master \
        -m 27 \
        -l 2 \
        -x '--input-t1w --mni'

This creates the registration information required to transform each
second-level fixed-effects result from T1w space into the configured MNI
space.

Registration strategies
~~~~~~~~~~~~~~~~~~~~~~~

The registration strategy depends independently on two things:

* the space of the FEAT input data;
* the space required by the subsequent analysis.

``spinoza_featreg`` supports the following combinations:

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Input space
     - Target space
     - Registration
   * - native/functional
     - T1w
     - BOLDref -> T1w
   * - native/functional
     - MNI
     - BOLDref -> T1w -> MNI
   * - T1w
     - T1w
     - identity registration
   * - T1w
     - MNI
     - identity BOLDref -> T1w, followed by T1w -> MNI

The input-space flags are explicit because the input space should not have to
be inferred exclusively from the name of the ``.feat`` directory.
Use ``--func`` for FEAT data in native functional space and ``--input-t1w``
for FEAT data that have already been resampled to T1w space. The target is
selected with ``--anat`` or ``--mni``.
The transformations themselves are obtained from the fMRIPrep derivatives.
``spinoza_featreg`` converts or injects these transformations into the
representation expected by FEAT.

Template space
~~~~~~~~~~~~~~

For MNI registration, ``spinoza_featreg`` distinguishes between the template
**space** and the actual TemplateFlow reference image used as the output
sampling grid.

The relevant options are:

``--tpl-home``
    TemplateFlow archive/cache directory.

``--tpl-space``
    TemplateFlow space, for example ``MNI152NLin6Asym``.

``--tpl-res``
    TemplateFlow resolution used for the ``reg_standard`` reference grid.

When available, the default template space and resolution are derived from
the first entry in ``$FPREP_ANAT_SPACES``. For example::

    FPREP_ANAT_SPACES="MNI152NLin6Asym:res-1 MNI152NLin2009cAsym:res-1"

results in the defaults::

    --tpl-space MNI152NLin6Asym
    --tpl-res 1

This keeps the FEAT registration target consistent with the standard-space
configuration used by the package for fMRIPrep.

``--tpl-home`` defaults to ``$TEMPLATEFLOW_HOME`` when that variable is set,
and otherwise to the standard local TemplateFlow cache.

The template settings can always be overridden explicitly. For example::

    master \
        -m 27 \
        -l 2 \
        -x '--input-t1w --mni \
            --tpl-space MNI152NLin2009cAsym \
            --tpl-res 1'

or, when using a custom TemplateFlow installation::

    master \
        -m 27 \
        -l 2 \
        -x '--input-t1w --mni \
            --tpl-home /path/to/templateflow \
            --tpl-space MNI152NLin6Asym \
            --tpl-res 1'

First-level registration
~~~~~~~~~~~~~~~~~~~~~~~~

For first-level FEAT directories containing native-space BOLD data, register
the functional data directly to MNI with::

    master \
        -m 27 \
        -l 1 \
        -x '--func --mni'

This reconstructs the BOLDref-to-T1w registration and combines it with the
fMRIPrep T1w-to-MNI transformation.

To register native-space BOLD data only to the anatomical T1w space::

    master \
        -m 27 \
        -l 1 \
        -x '--func --anat'

If the first-level FEAT data are already in T1w space and the desired target
is also T1w, an identity registration can be injected with::

    master \
        -m 27 \
        -l 1 \
        -x '--input-t1w --anat'

If the first-level data are in T1w space but need to be made available in MNI
space::

    master \
        -m 27 \
        -l 1 \
        -x '--input-t1w --mni'

Second-level registration
~~~~~~~~~~~~~~~~~~~~~~~~~

Second-level fixed-effects analyses inherit the spatial space of their
first-level inputs. Therefore, when first-level analyses are performed in T1w
space, the second-level fixed-effects results are also in T1w space.

If the subsequent third-level analysis should operate in MNI space, run
``spinoza_featreg`` on the **level-2** results::

    master \
        -m 27 \
        -l 2 \
        -x '--input-t1w --mni'

For a second-level directory such as::

    derivatives/feat/level2/
    `-- sub-22_ses-1_task-SC2F_fixedfx.gfeat/
        `-- contrast-USp.feat/

the registration is created inside the individual contrast FEAT directory.
Conceptually, the transformation is::

    second-level statistical image
                |
                | identity
                v
               T1w
                |
                | fMRIPrep T1w -> MNI
                v
               MNI

Because FSL's registration utilities expect several files normally found in
first-level FEAT directories, ``spinoza_featreg`` creates the required
compatibility images for second-level FEAT directories when necessary.

The resulting ``reg`` and ``reg_standard`` information can then be used by
the third-level analysis.

Subject selection
~~~~~~~~~~~~~~~~~

Registration can be restricted to one or more subjects using the normal
master subject selector. For example::

    master \
        -m 27 \
        -l 2 \
        -s 001 \
        -x '--input-t1w --mni'

This is useful for testing the registration workflow on a single participant
before processing the complete dataset.


Second-level analysis
---------------------

Level 2 combines multiple runs **within the same subject**.

For example, if a subject has three runs containing the ``USp`` contrast,
level 2 can combine::

    sub-01 run-1 USp \
    sub-01 run-2 USp  -->  sub-01 USp
    sub-01 run-3 USp /

This is typically a fixed-effects analysis: the runs are treated as repeated
measurements from the same subject rather than as independent subjects.

Run the second level with::

    master -m 28 \
        -l 2 \
        -x '--contrast USp'

Additional selection criteria can be supplied as required by ``call_feat2``.
For example, a minimum number of runs can be required::

    master -m 28 \
        -l 2 \
        -p /mnt/d/fMRI/SC2F \
        -x '--contrast USp --min-runs 2'

Level 2 reads the first-level contrast manifest to determine which first-level
COPEs belong together.

Its outputs are stored under::

    derivatives/feat/level2/

After successful level-2 analyses, another manifest is generated::

    derivatives/feat/level2/contrast_manifest_level2.tsv

This is the same basic idea as the first-level manifest, but its entries now
represent **subject-level contrast estimates** rather than individual runs.

Conceptually, the transformation is::

    contrast_manifest.tsv
          |
          | group by subject + contrast
          v
      FEAT level 2
          |
          v
    contrast_manifest_level2.tsv


Third-level analysis
--------------------

Level 3 performs the group analysis across subjects.
At this stage, the input is normally the subject-level contrast estimates
created at level 2.
For example, the level-2 manifest may contain::

    sub-01  USp  cope1
    sub-02  USp  cope1
    sub-03  USp  cope1
    ...
    sub-25  USp  cope1

A third-level analysis of ``USp`` combines those subject-level COPEs into a
group model.

For example::

    master -m 28 \
        -l 3 \
        -p /mnt/d/fMRI/SC2F \
        --local \
        -x '--contrast USp --registration-mode reg-standard'

A FLAME analysis can, for example, be requested with::

    master -m 28 \
        -l 3 \
        -p /mnt/d/fMRI/SC2F \
        -x '--contrast USp --runmode flame1 --min-subjects 10'

Level 3 normally reads::

    derivatives/feat/level2/contrast_manifest_level2.tsv

and selects the subject-level COPEs matching the requested contrast and other
selection criteria.

The conceptual hierarchy is therefore::

    run-1 --\
    run-2 ----> level 2: sub-01 USp --\
    run-3 --/                           \
                                         \
    run-1 --\                             \
    run-2 ----> level 2: sub-02 USp -------> level 3: group USp
    run-3 --/                             /
                                         /
                  ... ------------------/


Complete example
----------------

A complete analysis for a task called ``SC2F`` could therefore look like the
following.

First, run the first-level models::

    master \
        -m 28 \
        -l 1 \
        -j 6 \
        -x '--task SC2F --space T1w --desc masked'

Next, inject the fMRIPrep registrations into the resulting FEAT directories.
Here the first-level data are in T1w space and the final higher-level analysis
will use MNI space::

    # -j = maximum concurrency, not cores per job
    master \
        -m 27 \
        -l 2 \
        -j 5 \
        --sge \
        -x '--input-t1w     # 1st level is in T1w space \
            --mni           # 2nd level in MNI space \
            --tpl-space MNI152NLin2009cAsym' 

Finally, run the group-level model::

    master \
        -m 28 \
        -l 3 \
        -x '--registration-mode reg-standard'

Summary
-------

The important distinction between the three FEAT levels is the unit being
combined:

.. list-table::
   :header-rows: 1

   * - Level
     - Unit
     - Input
     - Output
   * - 1
     - Run
     - preprocessed BOLD
     - run-level COPEs
   * - 2
     - Subject
     - run-level COPEs
     - subject-level COPEs
   * - 3
     - Group
     - subject-level COPEs
     - group statistics

The contrast manifests connect these stages. They provide an explicit record
of which statistical images correspond to which subjects, runs, and contrasts,
allowing ``call_feat2`` and ``call_feat3`` to select their inputs without
depending on fragile directory searches or COPE numbers alone.

Single-trial estimation and multivariate decoding
=================================================

For multivariate analyses, single-trial parameter estimates can first be generated with
``stglm`` and subsequently analysed with PANIC. The corresponding Spinoza wrappers are:

* ``spinoza_singletrials`` -- generates subject-wise single-trial estimates using
  ``call_stglm``.
* ``spinoza_decoding`` -- performs subject-wise multivariate decoding using
  ``call_panic``.

In the ``master`` workflow these correspond to:

.. code-block:: text

    29  Single-trial estimation
    30  Decoding

The overall workflow is:

.. code-block:: text

    fMRIPrep / pybest
          |
          v
    single-trial estimation
    spinoza_singletrials
          |
          v
    single-trial beta estimates
          |
          v
    multivariate decoding
    spinoza_decoding
          |
          v
    decoding results


Generating single-trial estimates
---------------------------------

Single-trial estimates are generated with ``spinoza_singletrials``, which wraps
``call_stglm``. The latter configures and runs [stglm](https://github.com/gjheij/stglm) for an individual subject,
whereas ``spinoza_singletrials`` handles subject selection and parallel execution.

.. code-block:: bash

    master \
        -m 29 \
        -l 8 \
        -j 6 \
        -q intelsr_medium \
        -x '--space T1w --confounds-subset ENIGMA'

For this module, the relevant ``master`` options map onto
``spinoza_singletrials`` as follows:

.. list-table::
   :header-rows: 1

   * - master option
     - Meaning
   * - ``-m 29``
     - Select the single-trial estimation module
   * - ``-s``
     - Subject selection
   * - ``-l``
     - Maximum number of simultaneously running subjects
   * - ``-j``
     - CPUs per subject
   * - ``-q``
     - SLURM partition
   * - ``-p``
     - Project directory
   * - ``-t``
     - Task
   * - ``--local``
     - Run locally
   * - ``-x``
     - Additional ``call_stglm`` arguments

Note that ``-m`` cannot be used for the maximum number of jobs at the ``master``
level because it is already used to select the module. Therefore ``master -l``
maps onto ``spinoza_singletrials -m``.


Confound handling
~~~~~~~~~~~~~~~~~

For fMRIPrep-derived data, nuisance regressors can be selected using a predefined
confound subset. For example:

.. code-block:: bash

    master \
        -m 29 \
        -l 8 \
        -j 4 \
        -t HRA \
        -x '--space T1w --confounds-subset ENIGMA'

A different confound-file type can be selected with ``--confounds-suffix``. For
example:

.. code-block:: bash

    -x '--confounds-suffix physio'

Confounds can be disabled entirely with:

.. code-block:: bash

    -x '--no-confounds'


Using pybest data
~~~~~~~~~~~~~~~~~

For pybest-derived BOLD data, use the ``--pybest`` convenience option:

.. code-block:: bash

    master \
        -m 29 \
        -l 8 \
        -j 4 \
        -t HRA \
        -x '--pybest'

This selects pybest input and disables additional confound regression.


GLMsingle
~~~~~~~~~

``call_stglm`` can also use [GLMsingle](https://github.com/cvnlab/GLMsingle) for single-trial estimation. In that case,
use ``--glm-single`` and provide the corresponding JSON configuration file.

For example:

.. code-block:: bash

    master \
        -m 29 \
        -l 8 \
        -j 1 \
        -x "--glm-single"

The default CPU allocation for GLMsingle is one CPU unless explicitly overridden.


Multivariate decoding
---------------------

After generating the single-trial estimates, multivariate decoding can be performed
with [PANIC](https://github.com/gjheij/panic) using ``spinoza_decoding``.

``spinoza_decoding`` wraps ``call_panic`` and provides subject-wise job scheduling.
As for ``spinoza_singletrials``, the number of simultaneously running subjects can
be controlled independently from the number of CPUs allocated to each subject.

Decoding is module 30:

.. code-block:: bash

    # change default permutations
    n_permutations=500 # default = 1000
    master \
        -m 30 \
        -l 8 \
        -j 6 \
        -x "--lss --set decoding_settings.n_permutations=${n_permutations}"

For the decoding module:

.. list-table::
   :header-rows: 1

   * - master option
     - Meaning
   * - ``-m 30``
     - Select the decoding module
   * - ``-s``
     - Subject selection
   * - ``-l``
     - Maximum number of simultaneously running subjects
   * - ``-j``
     - CPUs per subject
   * - ``-q``
     - SLURM partition
   * - ``-r``
     - ROI base directory
   * - ``-p``
     - Project directory
   * - ``-o``
     - Overwrite existing decoding outputs
   * - ``--local``
     - Run locally
   * - ``-x``
     - Arguments passed to ``call_panic``/PANIC


ROI-based decoding
~~~~~~~~~~~~~~~~~~

For ROI-based analyses, specify the ROI base directory with ``-r``:

.. code-block:: bash

    master \
        -m 30 \
        -s 015 \
        -l 1 \
        -j 12 \
        -q main \
        -p "${site_path}" \
        -r "${roi_base}" \
        -x "-f ${site_path}/config.yml \
            --lss \
            --set decoding_settings.n_permutations=${n_permutations} \
            --set general_settings.tmp_dir=${site_path}/.cache"

``spinoza_decoding`` constructs the subject-specific ROI path internally. When the
PANIC configuration itself supplies ``roi_dict`` as a dictionary, the internally
generated value can be removed with:

.. code-block:: bash

    --unset roi_dict

For example:

.. code-block:: bash

    # also use custom config file
    master \
        -m 30 \
        -l 8 \
        -j 6 \
        -q intelsr_medium \
        -x "-f /some/path/config.yml \
            --lss \
            --set decoding_settings.n_permutations=${n_permutations} \
            --set general_settings.tmp_dir=${lustre_path}/${site_name}/.cache \
            --set general_settings.save_dir=${lustre_path}/${site_name}/derivatives/panic \
            --unset roi_dict"


Searchlight decoding
~~~~~~~~~~~~~~~~~~~~

Searchlight analyses can be requested with ``--searchlight``. Searchlight-specific
PANIC settings can be supplied using ``--set``.

For example:

.. code-block:: bash

    master \
        -m 30 \
        -l 8 \
        -j 6 \
        -q main \
        -p "${site_path}" \
        -r "${roi_base}" \
        -x "--searchlight \
            --set decoding_settings.n_permutations=${n_permutations} \
            --set general_settings.tmp_dir=${site_path}/.cache \
            --set decoding_settings.searchlight.radius=${radius}"

Because searchlight analyses can be computationally expensive, ``-l`` and ``-j``
should be chosen with the available cluster resources in mind. ``-l`` controls how
many subjects run simultaneously, whereas ``-j`` controls the resources available
to each individual subject.

The two stages should be considered separately: ``spinoza_singletrials`` generates
the trial-wise parameter estimates that form the input to the multivariate analysis,
whereas ``spinoza_decoding`` performs the classification or searchlight analysis on
those estimates.

Tips for FSL's FEAT
-------------------

Case: Use fMRIprep_-Confounds for FEAT
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you don't want to denoise your data using **pybest**, but instead want to include the confounds from fMRIprep_ in the **FEAT** analysis, use ``call_fprep2feat``.
This generates ``txt`` files compatible with **FEAT** based on the confound file.

These are the available options:

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    call_fprep2feat

    Convert the confound regressor files as per output of fMRIprep to FEAT-compatible text files. Be-
    cause the file from fmriprep has a loooot of regressors, we'll filter them by default. Use 'motion'
    [default] to include just the motion parameters; 'motion+acompcor' for motion + anatomical component regres-
    sors, or 'full' for everything (excluding 'global signal').

    Usage:
      call_fprep2feat <fprep_directory> <type>

    Example:
      call_fprep2feat <derivatives>/fmriprep/<subject>/<ses->/func motion

    ---------------------------------------------------------------------------------------------------

Case: Using MNI152NLin6Asym Files from fMRIPrep in FEAT
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you have data from fMRIprep_ in **MNI152NLin6Asym** (**FSL MNI**) space, you can directly use those files in the **first-level analysis**.
For a **subsequent group analysis**, you will need the **registration files**.
Since the data is already in **MNI space**, you need to inject the **identity matrix** and define the ``mean_func`` as ``standard``.

To do this quickly for an entire folder containing ``.feat`` directories, use ``call_injectmatrices``:

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    call_injectmatrices

    Follow workflow https://mumfordbrainstats.tumblr.com/post/166054797696/feat-registration-workaround
    To use fMRIprep output in FEAT. Uses the mean of the functional run as 'standard', rather than the
    MNI152-image.

    Args:
      -p <project dir>  project root folder (defaults to DIR_DATA_HOME)
      -l <level1 tag>   tag for level1 analysis (e.g., 'level1' [default] or 'level1_confounds')
      -f <feat dir>     directory where your subject-specific feat-directories live (defaults to DIR-
                        DATA_HOME/derivatives/feat/<level1_tag>)

    Example:
      call_injectmatrices # run script for all .feat-folders in DIR_DATA_HOME/derivatives/feat/<level1_tag>
      call_injectmatrices -p feat_dir/sub-01 # run script for all feat-folders in 'feat_dir/sub-01'

    ---------------------------------------------------------------------------------------------------

Case: Using fMRIPrep Registration Files for FEAT
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can also use the **registration files** from fMRIprep_ (generated via ANTs_) in FSL_.
This requires additional steps, which are detailed in the 
`ants2fsl guide <https://github.com/gjheij/fmriproc/blob/main/fmriproc/misc/ants2fsl.md>`_.

This guide describes how to **convert ITK warps to FSL-compatible warps**, including the **non-linear field**.
It uses functions from:

- C3D_-suite
- FSL_
- **wb_command** (from the `Human Connectome Project <https://www.humanconnectome.org/software/get-connectome-workbench>`_).

To install `wb_command`, follow these steps:

1. Download the correct file for your distribution.
2. Extract the file and place it in ``~/local_bin`` (create this folder if it doesn’t exist).
3. Locate the ``wb_command`` inside ``workbench/bin*linux64``:
    
    .. code-block:: bash

        (fmriproc) [heij@minerva local_bin]$ tree -L 2 workbench/
        workbench/
        ├── bin_rh_linux64
        │   ├── mesagl_wb_view
        │   ├── wb_command
        │   ├── wb_import
        │   ├── wb_shortcuts
        │   └── wb_view

4. Add the full path of ``wb_command`` to your ``~/.bash_profile``:

    .. code-block:: bash

        WB=`readlink -f ~/local_bin/workbench/bin_rh_linux64`
        export PATH=${PATH}:${WB}

5. Run ``source ~/.bash_profile`` or restart your terminal for changes to take effect.
6. Follow the conversion steps in the `ants2fsl guide <https://github.com/gjheij/fmriproc/blob/main/fmriproc/misc/ants2fsl.md>`_. Filepaths, subject IDs, session IDs, and task IDs may differ, but the general workflow is outlined in the guide.

Case: Running fMRIPrep on Extremely Partial FOV Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

fMRIprep_ does not handle **severely limited FOVs** well, such as data from **surface coils**.
To address this, the `fpreputils repository <https://github.com/gjheij/fpreputils/tree/main>`_ describes a workflow that:

- Runs parts of fMRIprep_ on partial FOV data.
- Performs **motion/distortion correction**, **registration**, and **confound extraction**.
- Requires a **whole-brain acquisition** for brain masks and tissue segmentation.
