Configuration Setup
===================

fMRIproc requires a `spinoza_config` file for specifying project paths, processing parameters, and software dependencies.

.. _spinoza_config_example:

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

.. tip::

    You can either use the ``license.txt`` file or generate one.

    If you're using a ``singularity`` image for fMRIPrep, this must be placed along the ``FPREP_BINDING`` variable.
    This variable tells the Singularity image where to bind, and thus, where to start looking for files.

    If your binding path is ``/some/dir/``, but your license file is in ``~/license.txt``, it will fail because it will not recognize the file.

    By default, the binding path is set to ``$(dirname ${DIR_PROJECTS})``, one directory up from your projects.
    This is also where your logs will end up, so if you copy the license file (either the generated one or the one in ``${REPO_DIR}/misc/license.txt``) 
    to ``${DIR_PROJECTS}``, you should be good to go.

Running `fMRIproc` on clusters
------------------------------

The pipeline also has several functions/modules that can run on a cluster (SoGE/SLURM).
You can check if you have access to either with:

.. code-block:: bash

    # Check scheduler type
    if command -v qsub >/dev/null 2>&1; then
        echo "soge"
    elif command -v sbatch >/dev/null 2>&1; then
        echo "slurm"
    else
        echo "Neither SoGE (qsub) nor SLURM (sbatch) detected." >&2
    fi

By default, the configuration file contains a setup for **SoGE**:

.. code-block:: bash

    export SGE_QUEUE_LONG="long.q@jupiter"
    export SGE_QUEUE_SHORT="short.q@jupiter"

If you have access to a **SLURM** system, you'll want to adapt these queues so that jobs are correctly submitted.
In SLURM, queues are referred to as **partitions**.
The equivalent of **SGE queues** (``qstat`` → ``long.q@jupiter``) in SLURM is the partition name (``sinfo`` → ``long,jupiter``).

SLURM partitions are typically defined in ``sinfo``, and they can look like:

.. code-block:: bash

    $ sinfo
    PARTITION  AVAIL  TIMELIMIT  NODES  STATE NODELIST
    debug      up     1:00:00    2      idle  node01,node02
    short      up     4:00:00    10     mix   node[03-12]
    long       up     7-00:00:00 20     alloc node[13-32]
    jupiter    up     7-00:00:00 15     idle  node[33-47]

Here’s how you can map **SGE queues** to **SLURM partitions**:

.. code-block:: bash

    export SGE_QUEUE_LONG="long"
    export SGE_QUEUE_SHORT="short"

The following functions can be submitted (regardless of SoGE/SLURM) using the ``--sge`` flag:

- ``call_feat``
- ``call_freesurfer``
- ``spinoza_scanner2bids``    [-m 02a]
- ``spinoza_mriqc``           [-m 02b]
- ``spinoza_qmrimap``         [-m 04]
- ``spinoza_registration``    [-m 05*]
- ``spinoza_nordic``          [-m 10]
- ``spinoza_freesurfer``      [-m 14]
- ``spinoza_fmriprep``        [-m 15]
- ``spinoza_denoising``       [-m 16]
- ``spinoza_mgdm``            [-m 20]
- ``spinoza_subcortex``       [-m 24]

The specific queue and number of cores can be adjusted using the ``-q <queue>`` and ``-j <n_cpus>`` flags.

.. important::

    After editing the file, you need to run ``source ~/.bash_profile`` again for the changes to take effect.

Setting up Matlab Runtime
------------------------------

MATLAB® Runtime contains the libraries needed to run compiled MATLAB applications on a target system without a licensed copy of MATLAB.
The developers from CAT12 have provided a standalone version of CAT12 precompiled with SPM.
This means we can run CAT12 and SPM functions without a MATLAB license.

First, download the MCR installer:

.. code-block:: bash

    cd ~/Downloads

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # mac (UNTESTED: paths below are representative for Linux install [WSL-tested])
        mcr_link="https://ssd.mathworks.com/supportfiles/downloads/R2023b/Release/7/deployment_files/installer/complete/maci64/MATLAB_Runtime_R2023b_Update_7_maci64.dmg.zip"
        cmd="curl -O"
    else
        # Linux uses GNU sed
        mcr_link="https://ssd.mathworks.com/supportfiles/downloads/R2017b/deployment_files/R2017b/installers/glnxa64/MCR_R2017b_glnxa64_installer.zip"
        cmd="wget"
    fi

    # download
    ${cmd} ${mcr_link}

Then, unzip and install the MCR (``-mode silent`` is necessary for versions older than 2022).
For Linux, run the following commands:

.. code-block:: bash

    mkdir ~/software/MCR_R2017b
    unzip $(basename ${mcr_link}) -d ~/software/MCR_R2017b
    sudo ./install -agreeToLicense yes -mode silent

    # if you do not have sudo rights use:
    dest_folder="~/software/MATLAB/MATLAB_Runtime"
    ./install -agreeToLicense yes -mode silent -destinationFolder ${dest_folder}

For macOS, double-click the extracted ``.dmg`` file, then double-click the MATLAB icon.
This will launch the installer.

The installation will take a few minutes.
If you have used ``sudo``, it will place the output in ``/usr/local/MATLAB/MATLAB_Runtime/v93``.
If you have used ``-destinationFolder``, it'll be different.
For macOS, the default installation path is ``/Applications/MATLAB/MATLAB_Runtime/``.
Regardless, this path needs to be in the ``~/.bash_profile`` file as ``MCRROOT``.
The installer will also echo other paths that need to be added to the ``~/.bash_profile`` file (``LD_LIBRARY_PATH``), but this is not necessary.
These paths will be added only when MCR is actually called to avoid messing up the environment.

.. code-block:: bash

    # add this to your ~/.bash_profile (or whatever you used for -destinationFolder)
    # The 'v93' will be there regardless
    if [[ "$OSTYPE" == "darwin"* ]]; then
        export MCRROOT="/Applications/MATLAB/MATLAB_Runtime/R2023b"
    else
        export MCRROOT="/usr/local/MATLAB/MATLAB_Runtime/v93"
    fi

Next, install the standalone version of CAT12:

.. code-block:: bash

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # mac (UNTESTED: paths below are representative for Linux install [WSL-tested])
        cat_link="https://www.neuro.uni-jena.de/cat12/cat12_latest_R2023b_MCR_Mac.zip"
        cmd="curl -O"
    else
        # Linux uses GNU sed
        cat_link="https://www.neuro.uni-jena.de/cat12/cat12_latest_R2017b_MCR_Linux.zip"
        cmd="wget"
    fi

    # download
    ${cmd} ${cat_link}

    # unzip
    unzip $(basename ${cat_link} .zip) -d ~/software

Now, in your configuration file (e.g., ``~/.spinoza_config``), edit the ``$MATLAB_CMD`` variable:

.. code-block:: bash

    # set MATLAB_CMD and SPM_PATH variables depending on system and location
    # put these variables (not this if-statement) in your config-file!
    if [[ "$OSTYPE" == "darwin"* ]]; then
        install_dir="${HOME}/software/CAT12.9_R2023b_MCR_Mac"
        export MATLAB_CMD="${install_dir}/run_spm12.sh ${MCRROOT} script"
        export SPM_PATH="${install_dir}/spm12.app/Contents/Resources/spm12_mcr/Users/gaser/spm/spm12"
    else
        install_dir="${HOME}/software/CAT12.9_R2017b_MCR_Linux"
        export MATLAB_CMD="${install_dir}/run_spm12.sh ${MCRROOT} script"
        export SPM_PATH="${install_dir}/spm12_mcr/home/gaser/gaser/spm/spm12"
    fi

.. warning::

    With the MATLAB Runtime (MCR), the following functions are unavailable (because it's NOT a full MATLAB installation!):

    - NORDIC (``spinoza_nordic``)
    - Reconstruction of line-scanning data (``spinoza_linerecon``)
    - Sampling from MNI152 to FSAverage (``call_mni2fsaverage``)
    - There are probably more that haven't been verified yet.

    To run these functions, a full MATLAB installation is required.
