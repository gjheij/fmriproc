# fMRIproc repository

![plot](https://github.com/gjheij/fmriproc/blob/main/doc/imgs/overview.png)

This repository contains all of the tools used during the acquisition and postprocessing of line scanning data at the Spinoza Centre for Neuroimaging in Amsterdam.
The main goal of the package is to create the most accurate segmentations (both volumetric and surface) by combining various software packages such as [Nighres](https://github.com/nighres/nighres), [fMRIprep](https://fmriprep.org/en/stable/usage.html), [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/), [CAT12](http://www.neuro.uni-jena.de/cat/index.html#DOWNLOAD), and [SPM](https://www.fil.ion.ucl.ac.uk/spm/software/spm12/). 
This package contains the minimum for the preprocessing of anatomical and functional data as well as denoising with [pybest](https://github.com/gjheij/pybest) and population receptive field routines with [prfpy](https://github.com/VU-Cog-Sci/prfpy).
HRF estimation, plotting, and other analysis approaches performed in my line-scanning projects can be found in the [lazyfmri](https://github.com/gjheij/lazyfmri) repository.

## In active development
This package is still in development and its API might change. 
Documentation for this package can be found at [readthedocs](https://linescanning.readthedocs.io/en/latest/) (not up to date)

## Installation

```bash
# main installation
pip install git+https://github.com/gjheij/fmriproc

# finalize setup (adds stuff to ~/.bash_profile)
spinoza_setup setup

# final source
source ~/.bash_profile
```

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
- ..
