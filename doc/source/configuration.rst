.. include:: links.rst

Configuration Setup
===================

fMRIproc requires a `spinoza_config` file for specifying project paths, processing parameters, and software dependencies.

.. _spinoza_config_example:

Example `spinoza_config`
-----------------------------

.. code-block:: bash

    # stuff about the project
    export DIR_PROJECTS="/path/to/some/projects"
    export PROJECT="project_name1"
    export TASK_IDS=("task1") # ("task1" "task2" "task3")
    export PATH_HOME="${DIR_PROJECTS}/logs"
    export SUBJECT_PREFIX="sub-"

    # stuff about the anatomical configuration
    export ACQ=("MPRAGE")  # or ("MP2RAGE" "MP2RAGEME")
    export DATA=${ACQ[0]}   # or MP2RAGEME/AVERAGE
    export SEARCH_ANATOMICALS=("T2w" "FLAIR" "T1w")

    # phase encoding direction for BOLD; assume inverse for FMAP
    export PE_DIR_BOLD="AP"

    # GRID ENGINE
    export SGE_QUEUE_LONG="long.q@jupiter" # SGE_QUEUE_LONG="long" on SLURM
    export SGE_QUEUE_SHORT="short.q@jupiter" # SGE_QUEUE_LONG="long" on SLURM

    # MATLAB
    ## Full installation
    export SKIP_LINES=0
    export MATLAB_CMD="matlab -nosplash -nodisplay -batch" # find with 'which matlab'
    export SPM_PATH="/some/path/to/spm12"
    
    ## MCR
    install_dir="${HOME}/software/CAT12.9_R2023b_MCR_Mac"
    export MATLAB_CMD="${install_dir}/run_spm12.sh ${MCRROOT} script"
    export SPM_PATH="${install_dir}/spm12.app/Contents/Resources/spm12_mcr/Users/gaser/spm/spm12"

    # PYBEST
    export PYBEST_SPACE="fsnative"
    export PYBEST_N_COMPS=20

    # fMRIPREP
    export MRIQC_SIMG="/path/to/containers/containers_bids-mriqc--23.0.1.simg"
    export FPREP_SIMG="/path/to/containers/containers_bids-fmriprep--20.2.5.simg"
    export FPREP_OUT_SPACES="fsnative func"
    export FPREP_BINDING="$(dirname ${DIR_PROJECTS})" # binding directory for singularity image
    export FS_LICENSE=${REPO_DIR}/misc/license.txt # this thing needs to be along the FPREP_BINDING path!
    export CIFTI="" # leave empty if you don't want cifti output
    export DO_SYN=0 # set to zero if you do not want additional syn-distortion correction
    export BOLD_T1W_INIT="register" # default = register; for partial FOV, set to 'header'

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

.. warning::

    The SLURM implementation has not been tested yet because I don't have access to one.
    Please open an issue if you run into problems!

SLURM partitions are typically defined in ``sinfo``, and they can look like:

.. code-block:: bash

    $ sinfo # this is concocted.. 
    PARTITION  AVAIL  TIMELIMIT  NODES  STATE NODELIST
    debug      up     1:00:00    2      idle  node01,node02
    short      up     4:00:00    10     mix   node[03-12]
    long       up     7-00:00:00 20     alloc node[13-32]
    jupiter    up     7-00:00:00 15     idle  node[33-47]

Here's how you can map **SGE queues** to **SLURM partitions**:

.. code-block:: bash

    export SGE_QUEUE_LONG="long"
    export SGE_QUEUE_SHORT="short"

The following functions can be submitted (regardless of SoGE/SLURM) using the ``--sge`` flag:

- `call_feat <https://github.com/gjheij/fmriproc/blob/main/bin/call_feat>`
- `call_freesurfer <https://github.com/gjheij/fmriproc/blob/main/bin/call_freesurfer>`
- spinoza_scanner2bids_ [-m 02a]
- spinoza_mriqc_ [-m 02b]
- spinoza_qmrimaps_ [-m 04]
- spinoza_nordic_ [-m 10]
- spinoza_freesurfer_ [-m 14]
- spinoza_fmriprep_ [-m 15]
- spinoza_denoising_ [-m 16]
- spinoza_mgdm_ [-m 20]
- spinoza_subcortex_ [-m 24]

The specific queue and number of cores can be adjusted using the ``-q <queue>`` and ``-j <n_cpus>`` flags.

.. important::

    After editing the file, you need to run ``source ~/.bash_profile`` again for the changes to take effect.

Setting up `fmriprep-docker <https://fmriprep.org/en/stable/installation.html#containerized-execution-docker-and-singularity>`_
--------------------------------------------------------------------------------------------------------------------------------
To run fMRIPrep_ using docker, make sure the Docker Engine is installed. You can view the instructions `here <https://docs.docker.com/engine/install/>`_.
For Linux, check out `these instructions <https://docs.docker.com/desktop/setup/install/linux/>`_.
For Windows, I advise to use the `WSL v2 <https://learn.microsoft.com/en-us/windows/wsl/install>`_ distribution. In any case, you will need the `Docker Desktop <https://docs.docker.com/desktop/>`_.
After installing both of these softwares, generate a `.wslconfig`-file in `%USERPROFILE%`:

.. code-block:: ini

    [wsl2]
    memory=12GB   # Use 12GB of your 16GB RAM
    processors=6  # Use 6 of your 8 CPU cores
    swap=4GB      # Optional: Set swap file to 4GB

    # Use a dedicated virtual disk to avoid slow NTFS performance
    # Change this to match your setup
    disk=D:\WSL\Ubuntu-20.04\ext4.vhdx

    # Enable localhost access for Docker
    localhostForwarding=true

    # Enable faster file access to Windows drives (NTFS optimization)
    [automount]
    enabled=true
    root=/mnt
    options="metadata,umask=22,fmask=11"

You can then start the Docker Desktop, open a WSL-terminal (e.g., through `powershell`, then `wsl`), or through an integrated terminal in `VSCode <https://learn.microsoft.com/en-us/windows/wsl/tutorials/wsl-vscode>`_.

Note that the `fmriprep-docker`-executable should be available in the environment. This is not installed by default (to reduce dependencies).
Install it with:

.. code-block:: bash
    
    pip install fmriprep-docker # --dry-run | if you want to see what happens without actually executing

If you're going down this route, I would advise to use **tmux**. This is a terminal multiplexer that allows you to create, manage, and persist multiple terminal sessions within a single window. It is useful for running long processes, managing multiple shells, and detaching from and reattaching to sessions.

On **Ubuntu**, run:

.. code-block:: bash

    sudo apt update && sudo apt install tmux -y

    # for WSL
    sudo apt install xclip xsel

**1. Start a New tmux Session**
   To create a new session:
   
   .. code-block:: bash

      tmux new -s mysession

   This starts a session named `mysession`.

**2. Detach from a Session**
   To detach from a running session without stopping it:

   .. code-block:: bash

      Ctrl + b, then d

**3. List Existing Sessions**
   To view all active tmux sessions:

   .. code-block:: bash

      tmux ls

**4. Reattach to a Session**
   To reconnect to a running session:

   .. code-block:: bash

      tmux attach -t mysession

**5. Kill a Session**
   To terminate a tmux session:

   .. code-block:: bash

      tmux kill-session -t mysession

**6. Split Windows**
   To split the window into **horizontal** and **vertical** panes:

   .. code-block:: bash

      Ctrl + b, then %

   (for vertical split)

   .. code-block:: bash

      Ctrl + b, then "

   (for horizontal split)

**7. Switch Between Panes**
   Move between split panes:

   .. code-block:: bash

      Ctrl + b, then arrow keys

You can generate a `~/.tmux.conf`-file to improve clipboard sharing:

.. code-block:: bash

    (fmriproc) [gjheij@HP-Jurjen fmriproc]$ cat ~/.tmux.conf 
    set-option -g mouse on
    set -g default-terminal "screen-256color"
    set-option -g terminal-overrides ",xterm-256color:Tc"
    set-option -g set-clipboard on

Since **WSL2** does not natively support clipboard integration between Linux and Windows, **win32yank** is used as a bridge.

.. code-block:: bash

    wget -O ~/win32yank.exe https://github.com/equalsraf/win32yank/releases/download/v0.1.1/win32yank.exe
    chmod +x ~/win32yank.exe

Then add this to the `~/.tmux.conf`-file:

.. code-block:: bash
    
    # Bind copy to system clipboard
    bind-key -T copy-mode-vi y send-keys -X copy-pipe-and-cancel '~/win32yank.exe -i'
    bind-key -T copy-mode y send-keys -X copy-pipe-and-cancel '~/win32yank.exe -i'

    # Bind paste from Windows clipboard
    bind p run-shell "tmux set-buffer \"$(~/win32yank.exe -o)\"; tmux paste-buffer"

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


Setting up Nighres_
--------------------

Nighres is a Python package for processing of high-resolution neuroimaging data.
It developed out of CBS High-Res Brain Processing Tools and aims to make those tools easier to install, use and extend.
Nighres now includes new functions from the IMCN imaging toolkit.
Because of its dependency on Java, it requires a slightly more exotic installation (and I haven't managed to get it to work on MacOS, yet).

Start with cloning the repository:

.. code-block:: bash

    git clone https://github.com/nighres/nighres

Then make sure you install some Java stuff:

.. code-block:: bash

    # on ubuntu/WSL
    sudo apt-get install openjdk-8-jdk

The Nighres-installer will look for ``$JAVA_HOME/bin/javac``, where ``JAVA_HOME`` is automatically set as:

.. code-block:: bash

    detected_java=$(java -XshowSettings:properties -version 2>&1 | tr -d ' '| grep java.home | cut -f 2 -d '=')

In newer versions of **openjdk-8-jdk**, the **jre/** subfolder is no longer included, because it's now merged with the main JDK. So:

.. code-block:: bash
    
    # Expected path:
    /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/javac # wrong

    # Actual path:
    /usr/lib/jvm/java-8-openjdk-amd64/bin/javac     # correct

Thus, add the following to your ``~/.bash_profile``-file:

.. code-block:: bash

    # nighres
    export JCC_JDK="/usr/lib/jvm/java-8-openjdk-amd64"
    export JAVA_HOME="${JCC_JDK}"

And run `source ~/.bash_profile`. Then you can proceed with the next steps.
Navigate to the Nighres directory you downloaded and unpacked, and run the build script:

.. code-block:: bash

    ./build.sh

Which should end with this message:

.. code-block:: none

    =======
    You should now be able to install nighres with pip
    python3 -m pip install .
    =======

In which case, you can run:

.. code-block:: bash

    pip install .

Test the configuration with:

.. code-block:: bash
    
    # couple important modules
    python -c "from nighres.brain import mgdm_segmentation"
    python -c "from nighres.cortex import cruise_cortex_extraction"
    python -c "from nighres.laminar import volumetric_layering"
