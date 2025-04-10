.. include:: links.rst

fMRIproc Documentation
======================

.. image:: imgs/overview.png
   :alt: fmriproc overview
   :width: 600px
   :align: center

Welcome to the **fMRIproc** documentation. This pipeline is designed for the acquisition and post-processing of **line scanning** and **whole-brain/partial FOV BOLD** data at the **Spinoza Centre for Neuroimaging**.
This repository contains all of the tools used during the acquisition and postprocessing of line scanning data at the Spinoza Centre for Neuroimaging in Amsterdam.
Over time, it has evolved to also incorporate regular whole-brain/partial FOV BOLD data.
The main goal of the package is to create the most accurate segmentations (both volumetric and surface) by combining various software packages such as Nighres_, fMRIprep_, FreeSurfer_, and CAT12_. 
This package contains the minimum for the preprocessing of anatomical and functional data as well as denoising with Pybest_ and population receptive field routines with pRFpy_.
HRF estimation, plotting, and other analysis approaches performed in my line-scanning projects can be found in the `lazyfmri <https://github.com/gjheij/lazyfmri/tree/main>`_-repository.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   installation
   overview
   configuration
   pipeline_steps
   additional_software
   cluster_usage
   troubleshooting

.. toctree::
   :maxdepth: 1
   :caption: Example gallery

   nbs/lazyfmri
   nbs/prfmodelfitter
   nbs/prfviewer

.. toctree::
   :maxdepth: 1
   :caption: Reference
   
   classes/index
   generated_modules
