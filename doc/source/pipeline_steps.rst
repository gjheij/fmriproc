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
    ---------------------

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

    For further details, see the `slicetiming <https://github.com/gjheij/fmriproc/blob/main/fmriproc/image.py#L14>`_ function.

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
    master -m 02b --func_only

    # MRIqc for anatomical images only
    master -m 02b --anat_only

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
    master -m 16 --no_raw

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

Tips for FSL's FEAT
-------------------

Format fMRIprep_-Confounds for FEAT
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
