Overview of fMRIproc
====================

**fMRIproc** is designed to streamline preprocessing of fMRI data with an emphasis on **high-field imaging**.

Main Features
-------------

- **Automatic segmentation:** Uses multiple software packages like **fMRIprep, FreeSurfer, Nighres, CAT12, and SPM**.
- **Bias correction and denoising:** Utilizes **pybest** for BOLD data.
- **Compatibility with multiple acquisition types:** Supports **whole-brain, partial FOV, and line-scanning**.
- **Automated pipeline execution:** Easily manage preprocessing using the **master script**.

Why Use fMRIproc?
-----------------

Unlike general-purpose pipelines, **fMRIproc** is optimized for:

- **Visual cortex imaging**, handling segmentation issues caused by the **sagittal sinus**.
- **Flexible anatomical preprocessing**, allowing optimized segmentation across multiple tools.
- **BIDS compatibility**, ensuring standardized data organization.
