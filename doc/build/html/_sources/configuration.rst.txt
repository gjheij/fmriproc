Configuration Setup
===================

fMRIproc requires a `spinoza_config` file for specifying project paths, processing parameters, and software dependencies.

Example `spinoza_config` File
-----------------------------

.. code-block:: bash

    # Project details
    export DIR_PROJECTS="/path/to/projects"
    export PROJECT="example_project"

    # Anatomical settings
    export ACQ=("MP2RAGE")
    export DATA="MP2RAGE"

    # Functional preprocessing
    export PE_DIR_BOLD="AP"

    # FreeSurfer settings
    export FREESURFER_HOME="/path/to/freesurfer"
    export FS_LICENSE="$FREESURFER_HOME/license.txt"

    # fMRIprep settings
    export FPREP_SIMG="/path/to/fmriprep.simg"
    export FPREP_BINDING="/path/to"

To activate changes, run:

.. code-block:: bash

   source ~/.bash_profile

