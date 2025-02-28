# fMRIproc repository

![plot](https://github.com/gjheij/fmriproc/blob/main/doc/imgs/overview.png)

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

## Policy & To Do

- [x] refactor `linescanning`-repository: most fitting procedures are in [lazyfmri](https://github.com/gjheij/lazyfmri), while surface-based processing is done by [cxutils](https://github.com/gjheij/cxutils)
- [x] Docstrings in numpy format.
- [x] Examples of applications for package (add notebooks to `doc/source/examples`)
- Port documentation from `linescanning` to `fmriproc`
- Make pipeline more agnostic to CAT12-version. Now r1113 is recommended (or at least, I've always used that version)
- Make compatible with SIEMENS data
- ..
