# fMRIproc repository

![plot](https://github.com/gjheij/fmriproc/blob/main/imgs/overview.png)

This repository contains all of the tools used during the acquisition and postprocessing of line scanning data at the Spinoza Centre for Neuroimaging in Amsterdam.
Note that we have a Philips scanner there, so all routines are tailored for the specific output of this scanner (e.g., PAR/REC files).
Some steps - especially at the beginning of the pipeline - will differ among vendors.
The main goal of the package is to create the most accurate segmentations (both volumetric and surface) by combining various software packages such as [Nighres](https://github.com/nighres/nighres), [fMRIprep](https://fmriprep.org/en/stable/usage.html), [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/), [CAT12](http://www.neuro.uni-jena.de/cat/index.html#DOWNLOAD), and [SPM](https://www.fil.ion.ucl.ac.uk/spm/software/spm12/). 
This package contains the minimum for the preprocessing of anatomical and functional data as well as denoising with [pybest](https://github.com/gjheij/pybest) and population receptive field routines with [prfpy](https://github.com/VU-Cog-Sci/prfpy).
HRF estimation, plotting, and other analysis approaches performed in my line-scanning projects can be found in the [lazyfmri](https://github.com/gjheij/lazyfmri) repository.

## In active development
This package is still in development and its API might change. 
Documentation for this package can be found at [readthedocs](https://linescanning.readthedocs.io/en/latest/) (not up to date)

## Installation

```bash
# create env (optional)
conda create env --name "fmriproc" python=3.11

# main installation
pip install git+https://github.com/gjheij/fmriproc

# finalize setup (adds stuff to ~/.bash_profile)
spinoza_setup setup

# final source
source ~/.bash_profile
```

If you're on a shared system (e.g., cluster) with a single installation, please copy the `spinoza_setup` file to a custom location.
You can find the file using `which spinoza_setup`.
This will give you the full path from the `bin` folder of the conda environment.
Copy this file to a folder, e.g., at the root of your actual project.
You then also neeed to change the `source ...` command in the `~/.bash_profile` file and `export SETUP_FILE=` in the setup file using `vi`, `gedit`, `atom`, `vscode`, or any other editor.
Adapt the command to point to your custom file and hit `source ~/.bash_profile`.

At this point, you will want to edit the `spinoza_setup` file to point to the correct paths.
These include:

```bash
# path to SPM folder (including cat12 in toolbox-folder)
export SPM_PATH=${PATH_HOME}/spm12

# singularity images (if used)
export MRIQC_SIMG=""
export FPREP_SIMG=""

# project information
export DIR_PROJECTS="/path/to/projects"
export PROJECT="project1"
export TASK_SES1=("task1")
export ACQ=("MP2RAGE")  # or ("MP2RAGE" "MP2RAGEME")
export PE_DIR_BOLD="AP" # phase encoding direction of functional files
export PATH_HOME=${DIR_PROJECTS}/logs # place where temp/intermediate/log files will be stored

# freesurfer
export FREESURFER_HOME=<path to FreeSurfer installation>
export FS_LICENSE=$FREESURFER_HOME/license.txt
source $FREESURFER_HOME/SetUpFreeSurfer.sh
```

After editing the file you want to run `source ~/.bash_profile` again for the changes to take effect.

Several other software packages need to be accessible from the command line for full functionality:
- [FSL](https://fsl.fmrib.ox.ac.uk/fsl/docs/#/) [recommended]: used for various manipulations of nifti-files, so this is recommended to have
- [ITK-Snap](https://linescanning.readthedocs.io/en/latest/installation.html) [optional/recommended]: very good for viewing 3D data and drawing masks/ROIs
- [ANTs](https://stnava.github.io/ANTs/) [recommended]: main registration method, so very useful to have
- [CAT12](https://neuro-jena.github.io/cat//index.html#DOWNLOAD) [recommended]: generates high quality tissue segmentations of anatomical files. Also used to generate accurate brain masks
- [SPM](https://www.fil.ion.ucl.ac.uk/spm/software/spm12/) (r1113 has been used most) [recommended]: houses CAT12 and allows for great bias correction
- [c3d](https://sourceforge.net/projects/c3d/) [optional]: useful for translation of transformation files between `ANTs` and `FSL`
- [Nighres](https://nighres.readthedocs.io/en/latest/installation.html) [optional]: very good segmentation software for high-resolution data. 
- [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall) [optional]: surface generation software. Not necessarily mandatory, as this can be done within `fMRIprep` too. Nevertheless, several helper-functions are useful to have.

Some functionalities regarding surface processing depend on the [cxutils](https://github.com/gjheij/cxutils)-package which wrap around [pycortex](https://github.com/gallantlab/pycortex).
To install this package too, run:

```bash
pip install git+https://github.com/gjheij/cxutils
```

This will also install `fmriproc` (again) and [lazyfmri](https://github.com/gjheij/lazyfmri).
Note that `cxutils` is only relevant for surface-related processing, as we have done for the line-scanning procedures.
The command line scripts for preprocessing of anatomical and functional data will work without this package.
Please be aware that `pycortex` is NOT supported for Windows!

## General pipeline

The input dataset is required to be in valid `BIDS (Brain Imaging Data Structure)` format. The directory pointing to the project should be specified in the ``spinoza_setup``-file as ``$DIR_PROJECTS``. Then specify the the project name as ``$PROJECT``. It is assumed your converted data lived in:

```bash    
$DIR_PROJECTS/$PROJECT/<subjects>
```

It is also assumed your ``T1w``-files have the ``acq-(ME)MP(2)RAGE`` tag in the filename. This is because the package can deal with either of these, or an *average* of MP2RAGE and MP2RAGEME acquisitions (see e.g., `<https://www.sciencedirect.com/science/article/pii/S105381192031168X?via%3Dihub>`_). So, a typical folder structure would look like this:

```bash
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
    ├── fmap # for distortion correction
    │   ├── sub-001_ses-1_task-2R_run-1_epi.json
    │   └── sub-001_ses-1_task-2R_run-1_epi.nii.gz
    ├── func # BOLD files
    │   ├── sub-001_ses-1_task-2R_run-1_bold.json
    │   └── sub-001_ses-1_task-2R_run-1_bold.nii.gz    
    └── phase # for nordic
        └── sub-001_ses-1_task-2R_run-1_bold_ph.nii.gz
```

The pipeline is controlled through the `master`-script.
Using the `-m`-flag, different modules can be executed.
As all the filepaths have been set using the setup file, this doesn't require much input.
Type `master` in the command line to see the different modules.
The modules are mostly depending on previous steps, but some steps (especially for the preprocessing of anatomical images) can be skipped.
In general, the pipeline is as follows:

First, we need to convert our DICOMs/PARRECs to nifti-files. We can do this by placing the DICOMs/PARRECs in the ``sourcedata``-folder of our project:

```bash
tree $DIR_PROJECTS/$PROJECT/sourcedata/sub-001
sub-001
└── ses-1
    ├── task # put the outputs from Exptools2 here
    │   ├── sub-001_ses-1_task-2R_run-1_Logs
    │   │   ├── sub-001_ses-1_task-2R_run-1_Screenshots
    │   │   │   └── <bunch of png-files>
    │   │   ├── sub-001_ses-1_task-2R_run-1_desc-screen.json
    │   │   ├── sub-001_ses-1_task-2R_run-1_events.tsv
    │   │   ├── sub-001_ses-1_task-2R_run-1_settings.yml
    │   ├── sub-001_ses-1_task-2R_run-2_Logs
    │   └── sub-001_ses-1_task-2R_run-3_Logs
    └── Raw files (DICOMs/PARRECs) # individual files, not a folder!
```

Once you've put the files there, you can run ``module 02a`` (if this doesn't do anything, you're probably on an older version.
This means you do not have access to `02b`; quality control with `MRIqc`).
This will convert your data to nifti's and store them according to BIDS.
You can use the ``-n`` flag to specify with which session we're dealing.
This creates the folder structure outlined above.
If you also have phase data from your BOLD, then it creates an additional `phase`-folder, which can be used for ``NORDIC`` later on.
If you have a non-linescanning acquisition (i.e., standard whole-brain-ish data), we'll set the coordinate system to `LPI` for all image.
This ensures we can use later outputs from fMRIprep on our native data, which will help if you want to combine segmentations from different software packages (affine matrices are always a pain;
check [here](https://nipy.org/nibabel/coordinate_systems.html) for a good explanation).
If you have extremely large par/rec files, `dcm2niix` [might fail](https://github.com/rordenlab/dcm2niix/issues/659).
To work around this, we monitor these error and attempt to re-run the conversion with [call_parrec2nii](https://github.com/gjheij/fmriproc/blob/main/bin/call_parrec2nii), which wraps `parrec2nii` that comes with nibabel.
Additionally, we also try to read the phase-encoding direction from the PAR-file, but this is practically impossible.
So there's two ways to automatically populate the `PhaseEncodingDirection` field in your json files: 

1) Accept defaults: `AP` for BOLD and `PA` for FMAP 
2) Set the `export PE_DIR_BOLD=<value>` in the setup file, with one of `AP`, `PA`, `LR`, or `RL`.
This sets the phase-encoding direction for the BOLD-data.
This value is automatically switched for accompanying fieldmaps.
3) use one of the following flags in your call to `master`: `--ap`, `--pa`, `--lr` or `--rl`.
This again sets the phase-encoding for the BOLD-data, and assumes that the direction is opposite for the fieldmaps.
4) Manually change the value in your json files after processing (but we don't like manual work now, do we..).

The pipeline can automatically populate the `IntendedFor`-field in the json files.
It can do so if one of the following situations holds:

1) You have a fieldmap for every BOLD acquisition (recommended as it's easiest to deal with)
2) You have a fieldmap for every two BOLD acquisitions (gets a bit more tricky, but it can mangage)
3) You have one fieldmap for all BOLD acquisitions

If this is not the case for you, you'll have to manually fill in the `IntendedFor` field..
It can also populate the `SliceTiming`-field if you have a 2D acquisition.
It does so by reading the TR, number of slices, and multiband factor from the PAR-file (so I don't know how this would work for Siemens data).
It assumes an interleaved acquisition.
For further details, see the [slicetiming](https://github.com/gjheij/fmriproc/blob/main/fmriproc/image.py#L14)-function.

Next, we can do some basic quality control using MRIqc. This internally generates a report for all your BOLD files (and anatomical files should you so desire). Because the pipeline does custom processing on the anatomicals, I generally run this with the `--func_only` flag, to only include the functional data. 

```bash
master -m 02b --func_only               # run func pipeline only
master -m 02b --anat_only               # run anat pipeline only
master -m 02b -n 1                      # limit processing to a certain session
```


After converting our data to nifti, we need to create our T1w/T1map images from the first and second inversion images. We can do this quite easily with Pymp2rage.
If you do not combine **INV1** and **INV2** yourself, - you already have a ``T1w``-/ ``T1map``-file in ``DIR_DATA_HOME`` - you can skip the part below (in case you're using Siemens data, the T1 is generally sufficient to continue with):

```bash
master -m 04 # spinoza_qmrimaps
```

If you have multiple acquisition (e.g., `MP2RAGE` and `MP2RAGEME`, or multiple `MPRAGE`'s) that you'd like to average, you can register them together with `module 05a`.
Here, we'll assume that the reference space is `MP2RAGE`, and register the `MP2RAGEME` to that image.
To then average together, use `module 06`.
Note that this will only have an effect if you specified ``DATA=AVERAGE`` in the setup file.
**If you have only 1 image type, skip this step**. 

```bash
master -m 05a # spinoza_registration (anat-to-anat)    
master -m 06  # spinoza_averageanatomies
```

If you have a ``T2w``-image, you can create a sagittal sinus mask.
We can do this by taking the T1w/T2w-ratio (if you do not, see `module 12`). 
However, this ratio will also highlight areas in the subcortex, which would be removed if we don't do something.
In the ``misc`` folder, we provide a heavily dilated sinus mask in MNI-space that we use to exclude the T2-values from the subcortex.
First, we register the subject's anatomy to the MNI-space, use these warp files to transform the dilated sinus mask to subject space, and multiply our sinus mask derived from the T2 with that dilated mask.
This way, we exclude any subcortical voxels from being masked out.
This procedure will lead to a file called ``<subject>_<ses-?>_acq-(ME)MP(2)RAGE_desc-mni_sinus`` in the ``derivatives/masked_(me)mp(2)rage/<subject>/<ses-?>`` folder.
If you do *NOT* have a ``T2w``-file, skip these steps and continue to ``module 08``.
For both registration steps (05a/05b), you can specify additional long flags: ``--affine`` (run affine registration), ``--rigid`` (run rigid registration), ``--syn`` (run SyN registration).

```bash
master -m 05b # spinoza_registration (anat-to-MNI)
master -m 07 # spinoza_sinusfrommni

# optional
master -m 05b --affine # use affine registration instead of SyN (is faster, but less accurate)
```

Bias correct (*SPM*) and denoise (*SANLM*) your ``T1w``-image.
If you did not use Pymp2rage_, we'll be looking for the ``T1w``-file in ``DIR_DATA_HOME/<subject>/<ses>/anat``.
If you did use Pymp2rage, we'll be looking for the file in ``<DIR_DATA_HOME>/derivatives/pymp2rage/<subject>/<ses>``, otherwise we'll default to ``$DIR_DATA_HOME``.
If you want additional bias correction after denoising, use ``--biascorr``

```bash
master -m 08                  # spinoza_biassanlm
master -m 08 --biascorr       # do bias correction after denoising 
```

Perform brain extraction and white/gray matter + CSF segmentations with CAT12.
If you've skipped the previous step because you want a more thorough denoising of your data, you can specify ``--full`` to do iterative filtering of the data.
Beware, though, that this is usually a bit overkill as it makes your images look cartoon'ish.

```bash
master -m 09 # spinoza_brainextraction

# optional
master -m 09 --full
```

As previously mentioned, if we have phase data with our BOLD data, we can apply NORDIC-denoising.
This expects a `phase` folder to be present in the BIDS-folder of the subjects.
If there isn't one and you still called this module, we'll do NORDIC denoising based on the magnitude files only.
With this module, we can specify the ``--sge`` flag to submit individual jobs to the cluster.
This module will back up you un-NORDIC'ed data in a `no_nordic` folder, while overwriting the functional file in `func`.
Messages about the nature of NORDIC denoising are added to the json-files so we can disentangle them later.

```bash
master -m 10 # spinoza_brainextraction

# optional
master -m 10 --sge
```

If you do not have a T2-image, we need to apply manual labor.
Use `module 12` to open ITK-Snap, and start drawing in the sagittal sinus.
Once done, save and close ITK-Snap, which will save the sagittal sinus mask to your `manual_masks`-folder.
You can skip this step if you're not reaally interested in visual cortex and don't want to deal with the sagittal sinus.

```bash
master -m 12 # spinoza_sagittalsinus
```

The whole point of this pipeline is to create a very good segmentation of the surface and tissue.
To help FreeSurfer with that, we can create a mask to get rid of the most obvious garbage in the brain (i.e., sagittal sinus & dura), as this generally has the same intensity as grey matter.
By now, we should already have a pretty decent sinus mask created by subtracting a relatively crude brain mask (from SPM) with a more accurate brain mask from CAT12.
We can further enhance this by adding the sagittal sinus mask we created earlier.
With `module 13`, we combine all of these separate mask, enhance them with manual edits, and set everything in the mask to zero in the T1w-image so that FreeSurfer is not going to be confused by the sinus (this is basically a *pial edit*-phase before FreeSurfer).
Creates a ``desc-outside.nii.gz`` mask in the ``derivatives/masked_(me)mp(2)rage/<subject>/<ses-?>`` folder that contains the sinus, dura, and tentorium (stuff between the cerebellum and cortex).

```bash
master -m 13 # spinoza_masking
master -m 13 --no_manual # directly apply mask to T1w, no manual intervention
```

That was basically the preprocessing of the anatomicals files.
We can now run FreeSurfer reconstruction *outside* of fMRIprep.
This is because the newest version of FreeSurfer deals better with ``T2w``-images than the version used in fMRIprep (although, by now fMRIprep is bundled with a newer version too).
If you have a cluster available (detected via the ``$PLACE`` variable in the spinoza_setup file), we'll automatically submit the job, running all stages of `recon-all`.
Check [call_freesurfer](https://github.com/gjheij/fmriproc/blob/main/bin/call_freesurfer) for information about further editing/debugging modes.
If you've skipped all of the previous preprocessing, we'll look in an hierarchical manner for the T1w-files:
first, we'll look in `$DIR_DATA_DERIV/masked_mp2rage` (assuming you've run the preprocessing), then `$DIR_DATA_DERIV/denoising` (denoised, but un-masked), `$DIR_DATA_DERIV/pymp2rage` (un-denoised, un-masked), `$DIR_DATA_HOME` (raw output from the scanner).
It also has the ability to process your edits made on the `brainmask.mgz` or white matter, and you can also specify an expert option file (see [this example](https://github.com/gjheij/fmriproc/blob/main/misc/example_experts.opts) for inspiration).

```bash
master -m 14
master -m 14 -s 00 -r 23 -e {wm,pial,cp,aseg} # insert your edits (one of wm, pial, cp, or aseg)
master -m 14 -s 00 -x expert.opts             # use an expert option file
```

Once you're satisfied with the surface reconstruction, you can proceed with fMRIprep.
By default this runs fMRIprep with the ``--anat-only`` option, but you can use ``-t`` or ``--func`` flag to include functional data in as well.
If you have multiple tasks in your session and you'd like to preprocess only a particular task, you can specify ``-t <task ID>`` instead of ``--func``.
Alternatively, you can use ``-u <config file>`` (see `DIR_SCRIPTS/misc/fmriprep_config.json`).
I use this because most of my sessions will have line-scanning data that cannot be preprocessed by fMRIprep.
Therefore, I use `DIR_SCRIPTS/misc/fmriprep_config.json` to only include data from `ses-1`.
If there's no `$DIR_DATA_DERIV/masked_mp2rage`-folder, we'll default straight to `$DIR_DATA_HOME`.
fMRIprep's bold-reference images are sometimes a bit wonky, so we're creating those again after fMRIPrep has finished.
In addition, we'll copy the `bold-to-T1w`-registration files to the output folder as well, just so we have everything in one place.
This avoids that we have to request the MNI152 outputs, as we have all the registration files needed in case we'd still want them (saves some disk space).
To skip fMRIPrep and only create new bold-reference images and copy the registration files, use ``--warp-only``.

```bash
master -m 15 # spinoza_fmriprep
master -m 15 --func       # include functional data (same as -t func)
master -m 15 -t <task_name> # preprocess a specific task (maps to '--task-ID' from fMRIprep) 
master -m 15 --func -u $DIR_SCRIPTS/misc/fmriprep_config.json # run fMRIPrep with specific configuration
master -m 15 --local # run fmriprep locally; in case of SGE, do not submit singularity job

# optional (generally run after successful completion)
master -m 15 --warp-only # only create new bold-reference images and copy the registration files
master -m 15 --fd # fetch framewise displacement files
```

We then proceed by denoising the functional data using Pybest.
This takes the ``confound``-file generated by fMRIprep and denoised the functional data.
By default I do this in ``fsnative``, so if you want a different space to be processed you'll need to adapt ``spinoza_setup`` accordingly (`PYBEST_SPACE`) or pass the appropriate flag.
By default Pybest zscores the data, which in some cases is undesirable.
We'll un-zscore the output from pybest and save the unzscored data in `unzscored`-folder, rather than `denoising`.
You can then use this data to standardize however you see fit (for later pRF-fitting, this data is standardized following the method from Marco Aqil, where the timecourses are shifted such that the median of the timepoints without any stimulation are set to zero).
If you do not want this additional unzscoring, use ``--no_raw``.
Use ```--sge`` to submit the job to the cluster in case you have one available.

```bash
master -m 16 # spinoza_denoising

# optional
master -m 16 --no_raw     # turn of unzscoring
master -m 16 --sge -j 10  # submit to cluster + change number of cores
master -m 16 --func       # use volumetric space
```

You can do some pRF-fitting as well.
If you did not use Pybest for denoising, we'll use fMRIprep-output as input for the pRF-fitting.
All models specified within pRFpy are available, as well as several other options:

- ``--grid``, run a grid fit only, no iterative fitting;
- ``-c``, list of values to clip the design matrix with (if ``--no_clip`` is NOT specified);
- ``-v``, cut a number of volumes from the beginning (generally recommended, use ``-v 4`` to cut the first 4 volumes, the design will automatically adjusted);
- ``--zscore``, use the zscore'd output from pybest;
- ``--multi_design``, used if you have multiple pRF designs within a session so the correct screenshots are used for the design matrix;
- ``--local``, do not submit the job to the cluster (can be useful for debugging);
- ``-p``, specifies which model to use (can be one of ['gauss', 'css', 'dog', 'norm'], or use - ``--css``, ``--dog``, ``--norm`` flags);
- ``-t``, fit a specific task (if you have mutliple in a session).
It's advised to copy the pRF-analysis template from the *fmriproc*-repository to ``$DIR_DATA_HOME/code`` and adjust settings there.
Do NOT rename the settings file, otherwise [call_prf](https://github.com/gjheij/fmriproc/blob/main/bin/call_prf) will fail.

See `master -m 17 --help` for more options.

```bash
master -m 17 # spinoza_fitprfs

# added options
master -m 17 --norm # run divisive-normalization (DN-) model
master -m 17 --multi_design # multiple designs in a session
master -m 17 -s 006 --norm -v 4 -j 25 # cut 4 volumes, use DN model, use 25 cores
```

Continuing with the anatomical pipeline, we now enter the Nighres stage, to fully optimize the quality of segmentations.
These modules can be run pretty much successively, and consist of ``MGDM``, ``region extaction``, ``CRUISE``, and ``volumetric layering``:

```bash
master -m 20 # spinoza_segmentmgdm
master -m 21 # spinoza_extractregions > also combines ALL previous segmentations into optimized levelsets
master -m 22 # spinoza_cortexreconstruction > currently mimicks CRUISE, rather than running it
master -m 23 # spinoza_layering > by default uses Nighres; use --surface to use Wagstyl's equivolumetric layering based on FreeSurfer output
```

A vanilla pipeline would look something like this.
Make sure to run one by one, unless modules are separated with comma's.
Some modules run via the cluster, so they're not compatible with chaining other modules.

- convert files to nifti:
    ```bash
    subID=001
    sesID=1
    master -m 02a -s ${subID} -n ${sesID} --sge
    ```

- run quality controls:
    ```bash
    master -m 02b -s ${subID} -n ${sesID} -j 10
    ```

- run NORDIC (if you have phase-data):
    ```bash
    master -m 10 -s ${subID} -n ${sesID} --sge
    ```

- run FreeSurfer:
    ```bash
    master -m 14 -s ${subID} -n ${sesID} -j 10

    # rerun depending on edits
    master -m 14 -s ${subID} -n ${sesID} -r 23 -e pial -j 10
    ```

- run fMRIprep:
    ```bash
    master -m 15 ${subID} -n ${sesID} --func -j 10
    ```

- run pybest:
    ```bash
    master -m 16 -s ${subID} -n ${sesID} --sge -c 20 -j 10
    ```

## Running fMRIprep
The pipeline allows for three ways to run fMRIprep:
- [singularity](https://www.nipreps.org/apps/singularity/)-image: recommended for HPC's.
- [fmriprep-docker](https://fmriprep.org/en/latest/installation.html#the-fmriprep-docker-wrapper): docker wrapper around `fmriprep`.
For installation of docker, see [here](https://www.nipreps.org/apps/docker/). 
This is the recommended way for local laptop/PC usage.
- [fmriprep]()-executable: when you install fmriprep with `pip`, it comes with an `fmriprep`-executable.
If you want to go down this route, you might as well install [fpreputils](https://reproducibility.stanford.edu/fmriprep-tutorial-running-the-docker-image/), which will install the `fmriprep`-executable as well as functions to deal with partial FOV acquisitions (such as surface coils acquisitions).

## Tips and tricks for FSL-feat

### Confounds
If you don't want to denoise your data using pybest, but instead want to include the confounds from fMRIprep in the FEAT analysis, use `call_fprep2feat`.
This generates `txt`-files compatible with FEAT based on the confound file.
These are the options:

```
---------------------------------------------------------------------------------------------------
call_fprep2feat

Convert the confound regressor files as per output of fMRIprep to FEAT-compatible text files. Be-
cause the file from fmriprep has a loooot of regressors, we'll filter them by default. Use 'motion'
[default] to include just the motion parameters; 'motion+acompcor' for motion + anatomical component regres-
rors, or 'full' for everything (excluding 'global signal').

Usage:
  call_fprep2feat <fprep_directory> <type>

Example:
  call_fprep2feat <derivatives>/fmriprep/<subject>/<ses->/func motion

---------------------------------------------------------------------------------------------------
```

### Case: use MNI152NLin6Asym-files from fMRIprep for FEAT
If you have data from fMRIprep in MNI152NLin6Asym (FSL MNI) space, you can directly use those files in the first level analysis.
To then do a subsequent group analysis, you need the registration files.
Because it is already in MNI-space, you need to inject the identity matrix and define the `mean_func` as `standard`.
You can quickly do so for an entire folder containing `.feat`-folders with `call_injectmatrices`:

```
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
```

### Case: use fMRIprep registration files for FEAT
You can also use the registration files from fMRIprep (using ANTs) for FSL.
This requires a bit more steps, which are described in the [ants2fsl](https://github.com/gjheij/fmriproc/blob/main/fmriproc/misc/ants2fsl.md)-file.
This file describes the steps to convert ITK warps to FSL warps, including the non-linear field.
It does so by using functions from the `c3d`-suite, FSL, and the `wb_command` from the [human connectome project](https://www.humanconnectome.org/software/get-connectome-workbench).
The latter is easily installable with the following steps:

- Download the correct file for your distribution
- Extract the file and place it in a folder `~/local_bin` (make this folder if it doesn't exist)
- The `wb_command` lives inside the `workbench/bin*linux64` (or alike) folder:
    ```bash
    (fmriproc) [heij@minerva local_bin]$ tree -L 2 workbench/
    workbench/
    ├── bin_rh_linux64
    │   ├── mesagl_wb_view
    │   ├── wb_command
    │   ├── wb_import
    │   ├── wb_shortcuts
    │   └── wb_view
    ```
- The full path up to the `wb_command` needs to be added to the path.
Add the following line to `~/.bash_profile`:

    ```bash
    WB=`readlink -f ~/local_bin/workbench/bin_rh_linux64`
    export PATH=${PATH}:${WB}
    ```

- Run `source ~/.bash_profile` or re-open an terminal so that the changes take effect.

- Follow the steps described [here](https://github.com/gjheij/fmriproc/blob/main/fmriproc/misc/ants2fsl.md).
Note that filepaths, subject IDs, session IDs, and task IDs may differ, but the general jist is described there.

### Case: fMRIprep on extremely partial FOV data
fMRIprep does not deal very well with data with severely limited FOVs.
This includes data from the surface coils.
The [fpreputils](https://github.com/gjheij/fpreputils/tree/main)-repository describes a workflow that allows you to run parts of fMRIprep including motion/distortion correction, registration, and confound extraction on partial FOV data.
Note that this workflow does need a whole-brain acquisition to extract some data from (e.g., a brain mask and tissue segmentations).

## Policy & To Do

- [x] refactor `linescanning`-repository: most fitting procedures are in [lazyfmri](https://github.com/gjheij/lazyfmri), while surface-based processing is done by [cxutils](https://github.com/gjheij/cxutils)
- [x] Docstrings in numpy format.
- [x] Examples of applications for package (add notebooks to `doc/source/examples`)
- Port documentation from `linescanning` to `fmriproc`
- Make pipeline more agnostic to CAT12-version. Now r1113 is recommended (or at least, I've always used that version)
- Make compatible with SIEMENS data
- ..
