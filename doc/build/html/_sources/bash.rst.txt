.. include:: links.rst

------------
Bash modules
------------

The bash modules are controlled by the ``master`` script, and perform the big processing steps, from preprocessing to FreeSurfer_ and fMRIprep_. Most of these modules have the ``-s`` and ``-n`` flags, meaning you can limit processing to a particular subject (e.g., ``-s 001``) or session (e.g., ``-n 1``). By default, the ``<session>`` flag is set to ``1``, and the subject flag to ``all``. These flags trickle down from the ``master`` script, meaning this can be controlled by calling:

.. code:: bash

    $ master -m <module> -n <session> -s <subject>

Below the help information for each module, which can also be called with:

.. code:: bash

    $ master -m <module> -q

.. attention:: The help texts below might not always be up-to-date! Please click on the names of the script (e.g., `spinoza_lineplanning`) to get redirected to github, where it actually is up-to-date.

00: spinoza_lineplanning_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_lineplanning

    Quick registration of partial anatomy from ses-2 with whole brain anatomy from ses-1 to plan the line
    as accurately as possible.
    Assumes you have run the pycortex notebook to obtain the text file with the values describing the
    orientation of the line in the first session anatomy based on the minimal curvature (and pRF-mapping).
    This notebook should ouput a line_orientation.txt file in the pycortex/sub-xxx directory. It will
    complain if this file's not here, we need it!!
    Steps:
      - Convert data                          (call_dcm2niix)
      - Create initial matrix                 (itksnap)
      - Registration                          (call_antsregistration; ANTs)
      - Store output registration in txt file
      - Fetch output from pycortex notebook or spinoza_bestvertex
      - Calculate values from both files      (call_mrconsole)
    Usage:
      spinoza_lineplanning  -s <subject ID>
                            -n <session ID>
                            -i <path to raw session 2 anatomy>
                            -p <path to file containing the orientation of the line>
                            -h <which hemisphere> (left | right)
                            -o <overwrite point files> (omit if we should not overwrite)
    Example:
      spinoza_lineplanning -s sub-001 -n 3 -i /path/to/raw/ses-2 -a /path/to/ses-1_anat.nii.gz -p /path/to
                            /pycortex_file.csv -h "left"
    Notes:
      - You NEED ANTs for this to run
      - It also depends on python3; if something doesn't seem to work, try to update the package
        with python -m pip install <package> --upgrade
    Command with master:
      master -m 00 -s <subject> -h <hemi> -n <session>
      master -m 00 -s 001 -h left -n 3                    # use session 3
      master -m 00 -s 001 -h left -n 1                    # use session 1 (uses identity matrix)
    ---------------------------------------------------------------------------------------------------

02a: spinoza_scanner2bids_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_scanner2bids

    convert raw data from the scanner to nifti format. Depending on which session we're analyzing, we'll
    use either call_dcm2niix.py (session 1 - which is FromScannerToBIDS.py from M. Aqil) which can deal
    nicely with the anatomical and functional stuff or call_dcm2niix.sh, which is more specific for the
    line scanning stuff.

    Input options:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -d <depth>          search depth for dcm2niix
      <project root>      directory to output BIDSified data to
      <sourcedata>        directory containing to be converted data
      -q <queue>          submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -o|--ow             Overwrite existing output
      --full              Overwrite existing output + created nifti folder
      --lines             flag to tell we're dealing with a line-scanning session. By default 'regular',
                          which means standard whole-brain acquisitions.
      --inv               add individual inversion files from anatomies in 'anat' folder
      --take-avg-tr       Take the average over all TRs from the par file, rather than the first in the
                          sequence of TRs
      --ap|--pa|--lr|--rl Specifies the phase-encoding direction for the BOLD run. The phase-encoding 
                          for the FMAP will be automatically inverted. This flag can be specified to be
                          a bit more flexible than using the PE_DIR_BOLD-variable in the setup file
      --no_lpi            do not reorient files to LPI. If you want to use NORDIC or use fMRIprep's out-
                          puts on more raw data, I'd advise you to reorient to LPI and to NOT use this 
                          flag. This flag is mainly here because it can take some time with big files
                          which slows down debugging.
      --sge               submit individual subjects to cluster as call_parrec2nii can take a while..
      --phys              run only physiology conversion
      --skip_tr           do not overwrite the TR in the header during call_bids. Generally not recom-
                          mended, but exists for debugging purposes.

    Example:
      spinoza_scanner2bids /path/to/project_root /path/to/your/project/sourcedata     # regular
      spinoza_scanner2bids -n 1/path/to/project_root /path/to/your/project/sourcedata # regular|ses-1
      spinoza_scanner2bids (shows this help text)                                     # help
      spinoza_scanner2bids --lines -n 2 DIR_DATA_HOME DIR_DATA_SOURCE                 # lines|ses-2

    Notes:
      Assumes the following data structure:
      PROJECT
      └── sourcedata
          └── sub-001
              └── ses-1
                  ├── task
                  └── DICOMs/PARRECs
                  
      Converts to:
      PROJECT
      └── sub-001
          └── ses-1
              ├── anat
              ├── func
              ├── fmap
              └── phase

    ---------------------------------------------------------------------------------------------------------

02a: spinoza_mriqc_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_mriqc

    Quality control using MRIqc. It uses the singularity container defined in the setup file (variable
    MRIQC_SIMG).

    Usage:
      spinoza_mriqc [options] <project dir> <derivatives>

    Arguments:
      --local         don't submit to SGE, run locally
      --anat_only     only include anatomical images in the process (default is everything it can find)
      --func_only     only include functional images in the process (default is everything it can find)  
      --fd            only get FD-timecourse file without initializing MRIqc
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05. use 'group' 
                      if you want group statistics
      -n <session>    session ID (e.g., 1, 2, or none); If set, only data from this session will be 
                      used
      -j <cpus>       number of cores to use (default is 1)
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      <project dir>   directory containing the anatomical data. Can also be the regular project root
                      folder if you want MRIqc do the surface reconstruction
      <derivatives>   output folder for MRIqc; generally this will be <project>/derivatives

    Example:
      spinoza_mriqc <project>/derivatives/masked_mp2rage <project>/derivatives anat
      spinoza_mriqc -s 001 -n 1 -f <project> <project>/derivatives/masked_mp2rage <project>/deri-
                      vatives anat

    ---------------------------------------------------------------------------------------------------

03b: spinoza_lsprep_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_lsprep

    wrapper for call_lsprep that performs the reconstruction of the line data. Uses MRecon, so we can
    only run it on the spinoza cluster. It calls upon call_lsprep, which internally uses a template
    for the reconstruction with MRecon based on scripts provided by Luisa Raimondo.

    Usage:
      spinoza_lsprep [options] <project root directory> <sourcedata>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., "2,3" or "3"). Defaults to '2'; specify multiple 
                          sessions in a comma-separated list: "2,3,4"
      -j <n_cpus>         number of CPUs to use (default = 1)
      -q <queue>          submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -x <kwargs>         Additional commands to be passed to 'call_lsprep'. Format should
                          be comma-separated flags as follows: 
                            - if you specify a flag and values | <flag>=<value>
                            - if you specify a flag only | <flag>

                          combine as:
                          "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"

                          This allows bash commands to be translated to python commands

      -c|--sge            submit job to cluster (SGE)
      <project root>      base directory containing the derivatives and the subject's folders.
      <derivatives>       base directory to store the 'lsprep'-folder in 

    Eample:
      spinoza_lsprep -s 001 -n 3 --sge DIR_DATA_SOURCE DIR_DATA_DERIV
      spinoza_lsprep -s 001 -n 3 -x --filter_pca=0.18,--verbose DIR_DATA_SOURCE DIR_DATA_DERIV

    run with master:  
      "master -m 03b -s 008 -n 3" # use all defaults from call_lsprep
      "master -m 03b -s 008 -n 3 -x --filter_pca=0.18,--verbose,--no_button,--ow,--ica" # customize
      "master -m 03b -s 008 -n 3 --sge -x --filter_pca=0.18,--verbose,--ica" # customize # submit

    ---------------------------------------------------------------------------------------------------

04: spinoza_qmrimaps_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_qmrimaps

    wrapper for estimation of T1 and other parametric maps from the (ME)MP2RAGE sequences by throwing
    the two inversion and phase images in PYMP2RAGE (https://github.com/Gilles86/pymp2rage).

    Usage:
      spinoza_qmrimaps [options] <project root> <derivatives>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o|--ow             overwrite existing T1w/T1map files
      -f|--full           overwrite all existing files (including masks)
      -u                  use settings for universal pulse (UP) [parameters are hardcoded]
      <project root>      directory containing the T1w and T2w files; should generally be pymp2rage-
                          folder
      <derivatives>       path to output mask directory  

    Example:
      spinoza_qmrimaps DIR_DATA_HOME DERIVATIVES/pymp2rage
      spinoza_qmrimaps DIR_DATA_HOME DIR_DATA_DERIV
      spinoza_qmrimaps -s 999 -n 1 DIR_DATA_HOME DIR_DATA_DERIV/pymp2rage

    ---------------------------------------------------------------------------------------------------

05a/05b: spinoza_registration_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_registration

    Wrapper for registration with ANTs. This script should be preceded by spinoza_qmri maps. It utili-
    zes the variable ACQ in the setup script to derive what should be registered to what. In theory, 
    the first element of ACQ is taken as reference, and the second element will be registered to that. 
    If ACQ has only one element and 'MNI' is specified, this first element is registered to the MNI tem-
    plate. This step is relatively obsolete given that we don't really need it in MNI space + we can do 
    that step with fMRIprep, but can be useful if you need the registration file mapping T1w-to-MNI, 
    without warping the actual 4D file to MNI-space (saves disk space).

    Usage:
      spinoza_registration [options] <anat folder> <output folder> <registration type>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      --affine            use affine-registration (12 parameters)
      --rigid             use rigid-body registration (6 parameters). Default if <registration type> 
                          != 'mni' and no registration method is specified
      --syn               use SyN-diffeomorphic registration. Default if <registration type> == 'mni'
                          and no registration method is specified
      --ofsl              also output the matrix in FSL-compatible format (not available for SyN)
      -c|--sge            submit job to cluster (SGE); given that we have to rename files after regi-
                          stration, we'll wait for the job to finish if submitted. This can still help
                          with memory issues (e.g., if your local machine does not have enough RAM).
      --cmd               only echo command; can be useful to submit multiple subjects without waiting 
                          for the process to finish. This requires the master command to be re-run again
                          to apply and files
      -q <queue>          submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -j <n_cpus>         number of CPUs to use (default = 1)
      <anat folder>       folder containing images for registration. If DATA == "AVERAGE", we'll look
                          for T1w-images containing 'acq-MP2RAGE_' and 'acq-MP2RAGEME_', create a warp
                          file, and apply this file to MP2RAGEME-files with ('T1w' 'T1map' 'R2starmap
                          Files ending with something other than 'T1w' or 'T1map' will also be copied 
                          to have 'acq-AVERAGE' in the filename, rather than 'space-MP2RAGE'. This en-
                          sures compatibility with 'spinoza_sagittalsinus' when DATA == AVERAGE. Regis-
                          tered files will end up in the <anat folder>, the warp file itself in <output
                          folder>
      <output folder>     folder where warp files are stored. Registered files are stored in <anat fol-
                          der>
      <registration type> which registration should be carried out. If empty, we'll default to a regis-
                          tration between MP2RAGEME and MP2RAGE (assumes that DATA == AVERAGE). This 
                          version is called as 'master -m 05a'. If 'mni', we'll register the T1w-file
                          in <anat folder> with FSL's 1mm template (MNI152NLin6Asym). This version is 
                          called as 'master -m 05b'. If type == 'mni', we'll default to the first ele-
                          ment in ${ACQ[@]} to register to MNI. Generally, this will/should be MP2RAGE     

    Example:
      spinoza_registration <project>/derivatives/pymp2rage <project>/derivatives/ants mp2rage
      spinoza_registration -s 001 -n 1 <project>/derivatives/pymp2rage <project>/derivatives/ants

    ---------------------------------------------------------------------------------------------------

06: spinoza_averagesanatomies_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------------
    spinoza_averagesanatomies

    This script takes the MP2RAGE and MEMP2RAGE-derived T1-weighted images to calculate the average. This re-
    sults in an image that takes advantage of the better WM/GM contrast of the MP2RAGE and the QSM-properties
    of the MEMP2RAGE sequence. This will only happen if you have two elements in the ACQ variable of the setup 
    script and if the DATA-variable is set to "AVERAGE"

    Usage:
      spinoza_averagesanatomies [options] <anat folder> <output folder>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      <anat directory>    directory containing the files to be registered
      <output>            path to directory where registration file/outputs should be stored

    Example:
      spinoza_averagesanatomies DIR_DATA_DERIV DIR_DATA_DERIV
      spinoza_averagesanatomies -s 001 -n 1 DIR_DATA_DERIV DIR_DATA_DERIV

    ---------------------------------------------------------------------------------------------------------

07: spinoza_sinusfrommni_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_sinusfrommni

    This script takes the registration matrix from MNI to subject space to warp the sagittal sinus mask
    in MNI-space to the subject space. We then multiply this image with the T1w/T2w ratio to get a de-
    cent initial estimate of the sagittal sinus

    Usage:
      spinoza_sinusfrommni [options] <anat folder> <registration folder> <mask folder>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o|--ow             Overwrite existing output
      --itk               open itksnap to verify mask procedure
      <anat directory>    directory containing the T1w and T2w files; should generally be pymp2rage-
                          folder
      <registration>      path to directory where registration file is (output from spinoza_registration)
      <mask directory>    path to output mask directory (to put final 'sinus'-mask)

    Eample:
      spinoza_sinusfrommni DIR_DATA_DERIV/pymp2rage DIR_DATA_DERIV/ants DIR_DATA_DERIV/manual_masks
      spinoza_sinusfrommni -s 001 -n 1 DIR_DATA_DERIV/pymp2rage DIR_DATA_DERIV/ants DIR_DATA_DERIV/manual_masks

    ---------------------------------------------------------------------------------------------------

08: spinoza_biassanlm_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_biassanlm

    Sometimes CAT12 can be a bit of an overkill with smoothing and bias corrections. This script should
    be run prior to "spinoza_brainextraction", and runs a SANLM-filter over the image as well as an bias
    field correction with SPM. The subsequent "spinoza_brainextraction" should be run with the "-m brain"
    flag as to turn off bias correction and denoising with CAT12. The input image is expected to reside 
    in the input directory and to contain "acq-${DATA}" and end with *T1w.nii.gz.

    Usage:
      spinoza_biassanlm [options] <anat folder> <output folder>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      --biascorr          run bias correction with SPM (default = False)
      <anat dir>          parent directory containing the sub-xxx folders for anatomies. Can be e.g., 
                          DIR_DATA_HOME or DIR_DATA_HOME/derivatives/pymp2rage
      <output>            Output directory for the denoised images (something like DIR_DATA_DERIV/denoised)

    Example:
      spinoza_biascorrection DIR_DATA_DERIV/pymp2rage DIR_DATA_DERIV/denoised
      spinoza_biascorrection -s 001 -n 1 DIR_DATA_HOME DIR_DATA_DERIV/denoised
      spinoza_biascorrection -s 001 -n 1 -b DIR_DATA_HOME DIR_DATA_DERIV/denoised

    ----------------------------------------------------------------------------------------------------

09: spinoza_brainextraction_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_brainextraction

    wrapper for brain extraction with ANTs, FSL, or CAT12 If you use ANTs, specify a prefix; if you use 
    FSL, specify an output name. Not case sensitive (i.e., you can use ANTs/ants or FSL/fsl). Assumes 
    that if you select FSL, we brain extract the INV2 image and if we select ANTs/CAT12, we brain extract 
    the mp2rage T1w with bias field correction. If you want to brain extract something else, either use
    call_fslbet, call_antsbet, or call_cat12. It performs N4 biasfield correction internally. Make sure 
    you added the location of antsBrainExtraction.sh to your path e.g., in your ~/.bash_profile :
    \"export PATH=PATH:/directory/with/antsBrainExtraction.sh\"

    Usage:
      spinoza_brainextraction [options] <input dir> <skullstrip output> <mask output> <ants/FSL/cat12>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or n)
      -o                  overwrite existing files
      --full              do full processing with CAT12 including iterative SANLM filtering and bias 
                          correction. Default is just tissue segmentation. 
      --fs                use rawavg.mgz from FreeSurfer; overwrites the specified input
                          directory 
      --fprep             use desc-preproc_T1w from fMRIprep. The input is linked the '-n' flag
      <input directory>   directory for inputs
      <skullstrip>        directory for skull-stripped outputs
      <mask>              directory for masks
      <software>          which software to use: ants|FSL|CAT12

    Example:
      spinoza_brainextraction dir/to/t1w dir/to/skullstrip /dir/to/masks ants
      spinoza_brainextraction -o dir/to/pymp2rage dir/to/cat12 /dir/to/masks cat12
      spinoza_brainextraction -s 01,02 -n 2 dir/to/inv2 dir/to/skullstrip /dir/to/masks inv2

    ---------------------------------------------------------------------------------------------------

10: spinoza_nordic_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_nordic

    Run NORDIC denoising on whole-brain functional data. Expects a BIDS-like folder structure with the
    magnitude data in 'func' and the phase data in 'phase'. If phase data is not present, we'll attempt
    a magnitude-only NORDIC process. If NORDIC is being run, we'll copy the 'func'-folder as 'no_nordic' 
    folder to denote that not preprocessing has taken place, while keeping the data close. The NORDIC'ed 
    data will be placed in 'func', without any special tags to avoid that fMRIPrep gets confused. How-
    ever, it's likely you've produced the phase output with 'spinoza_scanner2bids', in which case the 
    files will be named properly. Thus, the folder structure is expected to be like:

    <dir_projects>
    └── <project>
        └── sub-<subject>
            └── ses-<session>
                ├── fmap
                │   ├── sub-<subject>_ses-<session>_task-<task_id>_run-<run_id>_epi.json
                │   └── sub-<subject>_ses-<session>_task-<task_id>_run-<run_id>_epi.nii.gz
                ├── func
                │   ├── sub-<subject>_ses-<session>_task-<task_id>_run-<run_id>_bold.json
                │   └── sub-<subject>_ses-<session>_task-<task_id>_run-<run_id>_bold.nii.gz
                └── phase
                    ├── sub-<subject>_ses-<session>_task-<task_id>_run-<run_id>_bold_ph.json
                    └── sub-<subject>_ses-<session>_task-<task_id>_run-<run_id>_bold_ph.nii.gz

    Usage:
      spinoza_nordic [options] <bids folder>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none
      --sge               submit individual NORDIC processes to the cluster for parallellization. If 
                          you do this, it's advised to have identifiable 'run-' flags in your filenames
                          so that the template file is not overwritten; this can cause problems. If you
                          do not have run identifiers in your filenames, please run serially. This flag
                          is inherited from 'master', so calling it there will pass on the flag here.
      --mag               use magnitude only
      <bids folder>       parent directory containing the sub-xxx folders for functional data. Can be 
                          e.g., DIR_DATA_HOME or DIR_DATA_HOME/derivatives/pymp2rage

    Example:
      spinoza_nordic DIR_DATA_HOME                          # run for all subjects
      spinoza_nordic -s 001 -n 1 DIR_DATA_HOME              # run for specific subject/session
      spinoza_nordic --sge DIR_DATA_HOME                    # submit to cluster

    ---------------------------------------------------------------------------------------------------

11: spinoza_dura_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_dura

    estimate the location of the skull and dura using nighres. You are to specify the path to the input
    T1w-images (e.g., pymp2rage), the input INV2 image (e.g., the bias field corrected INV2 in the ANTs
    folder, the nighres output folder, and the folder to store the masks.

    Usage:
      spinoza_dura [options] <anat folder> <INV2 folder> <nighres output> <mask output>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or n)
      -o                  overwrite existing files
      <anat directory>    folder containing the T1w-file
      <inv2 directory>    folder containing the INV2-image
      <nighres output>    output folder for Nighres
      <mask output>       output folder for masks

    Example:
      spinoza_dura T1wdir INV2dir nighresdir maskdir
      spinoza_dura -s 001 -n 1 T1wdir INV2dir nighresdir maskdir

    ---------------------------------------------------------------------------------------------------

12: spinoza_sagittalsinus_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_sagittalsinus

    This script creates the sagittal sinus mask based on the R2*-map from pymp2rage. It requires the user
    to refine the mask a bit, because the R2*-map is imperfect especially around the putamen and other
    iron-rich regions inside the brain. It will start ITKsnap for the user to do the editing.

    It can be run on a cluster, but then we need to have X-forwarding. If you're on a different SGE than
    the Spinoza Centre cluster, change the 'if [[ hostname != *"login-01"* ]]; then' line to your SGE's
    login node (where you can't open GUIs). It will try to open a GUI for everything other than that spe-
    cified node-name. For instance, if you're running this on your local system, your hostname will be
    that of your system, and will therefore attempt to open the specified GUI (default = ITKsnap, it will
    check if that exists. Other options are 'FSL' or 'FV' for freeview).
    If you have MEMP2RAGE-data, then the script will look for the R2*-file in the specified ANAT folder.
    If this is somewhere else, just copy it into that directory.

    Usage:
      spinoza_sagittalsinus [options] <anat folder> <mask folder> <software [itk|fv]>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or n)
      -o                  overwrite existing files
      <input directory>   folder where anatomical files live
      <skullstrip>        output folder for masks
      <software>          which software to use: FreeSurfer|FSL|ITK

    Example:
      spinoza_sagittalsinus DIR_ANAT DIR_MASKS SOFTWARE
      spinoza_sagittalsinus $DIR_DATA_DERIV/pymp2rage $DIR_DATA_DERIV/manual_masks itk
      spinoza_sagittalsinus -s 001 -n 1 $DIR_DATA_DERIV/pymp2rage $DIR_DATA_DERIV/manual_masks itk

    ---------------------------------------------------------------------------------------------------

13: spinoza_masking_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_masking

    Mask out the dura and skull from the T1-image to reduce noise. It follow Gilles' masking procedure,
    by setting the contents of dura ('outside') and other masks ('inside') to zero. The idea is to run
    this, run fMRIprep, check segmentations, manually edit it as "${SUBJECT_PREFIX}xxx_ses-1_acq-MP2RAGE_desc-manual
    wmseg" or something alike. These 'manualseg' will be taken as 'inside' to boost areas that were not
    counted as brain.

    Usage:
      spinoza_masking [options] <directory to anats> <output dir> <mask dir> <skullstrip dir> 

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      <anat dir>          parent directory containing the sub-xxx folders for anatomies
      <output skull>      output folder for masked T1w-image (with skull)
      <mask dir>          folder containing a bunch of masks from previous modules. Should contains files 
                          ending on;
                            -dura:   \"*dura_dil.nii.gz\", \"*cat_dura.nii.gz\", or \"*dura_orig.nii.gz\"
                            -brain:  \"*cat_mask.nii.gz\" or \"*gdh_mask.nii.gz\" 
                            -inv2:   \"*spm_mask.nii.gz\"
                            -sinus:  \"*sinus\"
      <output no skull>   output folder for brain-extracted output (generally the input for Nighres)

    Example:
      spinoza_masking <dir>/pymp2rage <dir>/masked_mp2rage <dir>/manual_masks <dir>/skullstripped
      spinoza_masking -s 01 -n 1 <dir>/pymp2rage <dir>/masked_mp2rage <dir>/manual_masks <dir>/skullstripped

    ---------------------------------------------------------------------------------------------------

14: spinoza_freesurfer_
=======================================================================================================

.. code-block:: none
        
    ---------------------------------------------------------------------------------------------------
    spinoza_freesurfer

    Surface parcellation with FreeSurfer. We only need to specify where to look for the T1w-image which
    stage we should run (default is 'all'), and where to look for a T2w-image if there is one.

    Usage:
      spinoza_freesurfer [options] <directory with anats> <stage> <T2-directory>

    Flagged arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or n)
      -e <start>          start stage (maps to '-r' from 'call_freesurfer'). Must be one of 'pial', 
                          'cp', or 'wm' if <freesurfer stage> != 'all'
      -j <cpus>           number of cores to use (default is 1)
      -o|--ow             overwrite existing files
      -x <file>           use expert file
      -q <queue>          submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      --force_exec        Force execution even though directory exists already
      --local             Force local processing even though cluster is available
      --no_highres        Turn of highres mode by setting '-highres' flag empty
      --no_t2             Do not reuse T2 with autorecon3. Must be used in concert with '-e' and
                          '-r'. By default, we'll re-use the T2 if present. Same flag should be 
                          used for not re-using FLAIR images  
      --sge               Submit the script to a cluster using a template script
      --xopts-use         maps to '-xopts-use' for existing expert option file; use existing file
      --xopts-clean       maps to '-xopts-clean' for existing expert option file; delete existing file
      --xopts-overwrite   maps to '-xopts-overwrite' for existing expert option file; use new file

    Positional arguments:
      <anat folder>       folder containing the T1w-file. In 'master', we'll look through various fol-
                          ders. In order of priority:
                            -'<derivatives>/masked_${DATA,,}'
                            -'<derivatives>/denoised'
                            -'<derivatives>/pymp2rage'
                            -'DIR_DATA_HOME'
                          this ensures a level of agnosticity about anatomical preprocessing. I.e., you
                          don't have to run the full pipeline if you don't want to.
      <freesurfer stage>  stage to run for FreeSurfer. By default 'all'
      <T2-folder>         if specified, we'll look for a '*T2w.nii.gz' or '*FLAIR.nii.gz' image to add 
                          to the FreeSurfer reconstruction.

    General approach for segmentation:
      - Run autorecon1:   call_freesurfer -s <subj ID> -t <T1> -p <T2> -r 1)      ~an hour
      - Fix skullstrip:   call_freesurfer -s <subj ID> -o gcut                    ~10 minutes
      - Run autorecon2:   call_freesurfer -s <subj ID> -r 2                       ~few hours
      - Fix errors with:
          - norm; then run call_freesurfer -s ${SUBJECT_PREFIX}001 -r 23 -e cp    ~few hours
          - pia;  then run call_freesurfer -s ${SUBJECT_PREFIX}001 -r 23 -e pial  ~few hours

    You can specify in which directory to look for anatomical scans in the first argument. Usually,
    this is one of the following options: DIR_DATA_HOME if we should use the T1w in the project/
    ${SUBJECT_PREFIX}xxx/anat directory, or DIR_DATA_DERIV/pymp2rage to use T1w-images derived from 
    pymp2rage, or DIR_DATA_DERIV/masked_mp2rage to use T1w-images where the dura and sagittal sinus 
    are masked out (should be default!). In any case, it assumes that the file is in YOURINPUT/
    ${SUBJECT_PREFIX}xxx/ses-1/. If the input is equal to the DIR_DATA_HOME variable, this will 
    be recognize and 'anat' will be appended to YOURINPUT/${SUBJECT_PREFIX}xxx/ses-1/anat.

    You can also specify a directory where the T2-weighted image is located. Do this the same way as de-
    scribed above. To you path, ${SUBJECT_PREFIX}xxx/ses-x will be appended if the input path is not 
    equal to DIR_DATA_HOME. Again, if it is, ${SUBJECT_PREFIX}xxx/ses-x/anat will be appended as well.

    Example:
      spinoza_freesurfer DIR_DATA_DERIV/masked_mp2rage all DIR_DATA_HOME
      spinoza_freesurfer -s 001 -n 1 DIR_DATA_ANAT all DIR_DATA_HOME

    Notes:
      When an expert options is passed, it will be copied to scripts/expert-options. Future calls to 
      recon-all, the user MUST explicitly specify how to treat this file. Options are (1) use the file 
      ('--xopts-use'), or (2) delete it ('--xopts-clean'). If this file exsts and the user specifies 
      another expert options file, then the user must also specify '--xopts-overwrite'.

    ---------------------------------------------------------------------------------------------------

15: spinoza_fmriprep_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_fmriprep

    preprocess structural and functional data with fMRIprep. It uses the singularity container in de-
    fined in the FPREP_SIMG-variable in the setup file. You can also run fmriprep through a docker image, 
    in which case 'fmriprep-docker' needs to be installed. To run fmriprep through docker, specify the
    '--docker' flag when running this module (e.g., 'master -m 15 --func --docker'). If we do not have
    access to singularity or docker, we can run fmriprep through the BIDSApp. 

    By default, this runs the anatomical pipeline only. This is to optimize the surface reconstruction
    first before injecting the functional data. The anatomical file can be in several places, which will
    be assessed hierarchically with 'find_hierarchical_anatomy' function in call_bashhelper. We'll look
    consecutively in:
      - DIR_DATA_DERIV/masked_mp2rage (output from master -m 13   [spinoza_masking])
      - DIR_DATA_DERIV/cat12          (output from master -m 09   [spinoza_brainextraction])
      - DIR_DATA_DERIV/denoised       (output from master -m 08   [spinoza_biassanlm])
      - DIR_DATA_DERIV/pymp2rage      (output from master -m 04   [spinoza_qmrimaps])
      - DIR_DATA_HOME (standard BIDS) (output from master -m 02a  [spinoza_scanner2bids]) 

    If you have a T2-weighted image as well, you can specify the root directory to that image. If it
    exists, we will copy it to the directory where the T1-weighted is located (<input directory>) so
    that it is included by fMRIprep.

    Usage:
      spinoza_fmriprep [options] <anat dir> <derivatives folder> <mode> <T2 dir>

    Arguments:
      -a <keep runs>    if you're running fMRIprep with MNI152* as output space, you're creating massive
                        files; oftentimes, you're mostly interested in the registration matrices, so by
                        default I'll remove the output nifti's so that the folder is not clogged. With 
                        this argument you can specify which runs to keep. Again, if not specified, all
                        nifti-files with space-MNI152*.nii.gz will be removed. The transformation matri-
                        ces will be left alone. Use '-a all' to keep all runs (not recommended..)
      -f <func dir>     directory containing functional data; used after running FreeSurfer outside of
                        fMRIprep <optional>
      -j <cpus>         number of cores to use (default is 1)
      -k <kwargs>       specify a file with additional arguments, similar to FreeSurfer's expert options.
                        See fmriproc/misc/fprep_options for an example. Please make sure you have a 
                        final empty white space at the end of the file, otherwise the parser gets confu-
                        sed. For VSCode: https://stackoverflow.com/a/44704969. If you run with master, the 
                        '-u' flag maps onto this
      -n <session>      session ID (e.g., 1, 2, or none); used to check for T1w-image. fMRIprep will do all
                        sessions it finds in the project root regardless of this argument. Use the bids fil-
                        ter file ('-k' flag) if you want fMRIPrep to to specific sessions/tasks/acquisitions.
      -q <queue>        submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -r <runs>         (re-)run specific runs by removing existing single_subject_<subj_id>_wf/func_preproc
                        _ses_1_*_run_<run_id>_*_wf folders. This should re-use the existing files for other 
                        runs, but re-run completely the requested runs
      -s <subject>      subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -t <task>         By default, the pipeline is setup to run fMRIPrep with '--anat-only'. You can in-
                        ject functional data with the '-t' flag; if you want ALL your tasks to be included,
                        use '-t func'. If you have a specific task that needs to be processed (in case ano-
                        ther task is already done), use '-t <task_id>'.
      -u <config>       configuration file as specified in /misc/fmriprep_config?.json
      -w <workdir>      custom working directory; defaults to PATH_HOME/fmriprep/<PROJECT>

    Positional:
      <anat dir>        directory containing the anatomical data. Can also be the regular project root
                        folder if you want fMRIprep do the surface reconstruction
      <derivatives>     output folder for fMRIprep; generally this will be <project>/derivatives
      <mode>            run anatomical workflow only with 'anat', or everything with 'func'
      <T2 dir>          if you have a T2w-file, but that is not in <anat dir> (because you preprocessed
                        the T1w-file, but not the T2w-file), you can specify the directory where it lives
                        here. Generally this will be the same as <func dir>

    Options:
      --clean           remove the single-subject workflow folder completely. This saves storage, but comes
                        at the price that it re-runs EVERYTHING if you restart the process.
      --docker          run fmriprep through docker image (requires 'fmriprep-docker' to be installed!)
      --fd              only fetch framewise displacement files
      --fetch_anat      retrieve the nifti-files in T1w-space
      --fetch_fsl       retrieve the MNI-transformed nifti-files (which are cleaned by default)
      --fetch_func      retrieve the nifti-files in func-space
      --func            same as '-t func'
      --local           don't submit to SGE, run locally
      --masks           used in combination with '--fetch_{fsl|func|anat}' to also fetch the brain masks
                        associated with the timeseries files
      --no_bbr          maps to '--force-no-bbr' in call_fmriprep
      --no_boldref      don't create new boldref images (mean over time) after fMRIprep has finished.
      --ow              only removes folders within single_subj workflow with "run-". If specific runs are 
                        requested with '-r', only these folders will be removed
      --remove_surf_wf  Remove surface reconstruction workflow folder; refreshes the surfaces used for re-
                        gistration and transformation
      --remove_wf       remove full single_subject workflow folder. Use \"--remove_surf_wf\" to specifically 
                        remove the surface reconstruction folder when you have new FreeSurfer output that 
                        fMRIPrep needs to use, or "--ow" to remove all folders within single_subj workflow
                        with "run-"
      --warp_only       skips fMRIPrep, but creates new boldref images (if '--no_boldref' is not specified) 
                        and copies the bold-to-T1w warps to the subject's output folder

    Example:
      spinoza_fmriprep <project>/derivatives/masked_mp2rage <project>/derivatives anat
      spinoza_fmriprep -s 001 -n 1 -f <project> <project>/derivatives/masked_mp2rage <project>/deri-
                      vatives anat
      master -m 15 -s 01 -n 1 --func -j 15    # run via master with singularity and 15 cores
      master -m 15 -s 01 -n 1 --func --docker # run via master with docker

    ---------------------------------------------------------------------------------------------------

16: spinoza_denoising_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_denoising

    wrapper for call_pybest that does the denoising of fMRI-data based on the confound file created
    during the preprocessing with fmriprep. By default, it will use FSNative, unless the PYBEST_SPACE
    variable in the setup file says something else, or if the '--fsaverage' flag is specified

    Usage:
      spinoza_denoising [options] <fmriprep directory> <pybest output directory>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -t <task ID>        limit pybest processing to a specific task. Default is all tasks in TASK_SES1
                          in the spinoza_setup-file Can also be comma-separated list: task1,task2
      -j <n_cpus>         number of CPUs to use (default = 1)
      -c <n_comps>        overwrite the PYBEST_N_COMPS-variable deciding the number of components for 
                          the PCA (default = 10)
      -o|--ow             overwrite existing files. Note that this does not delete the full ses-<> folder!
                          use --full to completely remove a folder
      --full              Overwrite (i.e., remove) existing output. In case of "-r 'all'", the entire
                          subject directory is removed
      -q <queue>          submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -x <kwargs>         other arguments that should be passed to pybest
      --sge               submit job to cluster (called with 'master -m <module> --sge')
      --no_raw            do NOT unzscore the output from pybest (default is to do so)
      --fsaverage         overwrite PYBEST_SPACE-variable and use FSAverage for pybest (defaults to fs-
                          native)
      --fsnative          overwrite PYBEST_SPACE-variable and use FSNative (defaults to fsnative)
      --func              overwrite PYBEST_SPACE-variable and use 'func'-space
      --anat              overwrite PYBEST_SPACE-variable and use 'T1w'-space
      --mni_fsl           overwrite PYBEST_SPACE-variable and use 'MNI152NLin6Asym_res-1'-space
      --mni_2009          overwrite PYBEST_SPACE-variable and use 'MNI152NLin2009cAsym_res-1'-space
      --force             force execution despite existing files
      <project root>      base directory containing the derivatives and the subject's folders.
      <derivatives>       path to the derivatives folder

    Eample:
      spinoza_denoising DIR_DATA_HOME DIR_DATA_DERIV
      spinoza_denoising -s 001 -n 1 DIR_DATA_HOME DIR_DATA_DERIV
      spinoza_denoising -o DIR_DATA_HOME DIR_DATA_DERIV

    Notes:
      There are multiple flags to change the PYBEST_SPACE-variable. If your desired space is not speci-
      fied, update the variable in the setup file.

    ---------------------------------------------------------------------------------------------------

17: spinoza_fitprfs_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_fitprfs

    Wrapper for call_prf that does the pRF-fitting using the output from pybest and the package pRFpy. 
    There's several options for design matrix cases (in order of priority):
      - Place a design-matrix file called 'design_task-<TASK_NAME>.mat' in DIR_DATA_HOME/code
      - A directory with log-directories. A global search for a directory containing "Screenshots" is 
        done. If more directories are found and '--one_design' is specified, we'll take the first dir
        ectory
      - A directory with log-directories, but '--one_design' is NOT specified, meaning that each run 
        will get a separate design matrix. This can be useful if you have multiple conditions that have 
        different designs.

    Usage:
      spinoza_fitprfs [options] <input dir> <output dir> <png dir>

    Options:
      -c              list of values used for clipping of design matrix. Format must be [<top>,<bottom>,
                      <left>,<right>]. Negative values will be set to zero within 'fmriproc.prf.
                      get_prfdesign'
      -f <n_folds>    if your pRF experiment contains multiple equal sequences, you can use this flag
                      to perform within-run averaging before percent-changing in call_prf. This should
                      be in concert with number of volumes removed from the beginning of the timeseries                  
      -k <kwargs>     specify a file with additional arguments, similar to FreeSurfer's expert options.
                      See fmriproc/misc/prf_options for an example. Please make sure you have a 
                      final empty white space at the end of the file, otherwise the parser gets confu-
                      sed. For VSCode: https://stackoverflow.com/a/44704969.
      -m <model>      one of ['gauss','dog','css','norm'] is accepted, default = "gauss"
      -n <session>    session ID (e.g., 1, 2, or none)
      -o              delete existing file and re-run analysis fully. Even if 'model=norm', we'll over-
                      write the Gaussian parameters. If not specified, and 'model=norm' while Gaussian 
                      parameters already exist, we'll inject them into the DN-model.
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -t <task ID>    If you have mutiple tasks specified in TASK_SES1 or you just have multiple tasks and 
                      you want to run only one, specify the task name here ('task-rest' is ignored).
                      You can also specify multiple tasks if you want to bypass the setup file completely. 
                      In that case, use the format '-t <task1>,<task2>,<task3>'
      -x <constr>     String or list of constraints to use for the gaussian and extended stage. By default, 
                      we'll use trust-constr minimization for both stages, but you can speed up the exten-
                      ded models with L-BGFS. Note that if you want the same minimizer for both stages, you 
                      can use the '--tc' or '--bgfs' tags. This input specifically allows you to specify a 
                      list of different minimizers for each stage, e.g., trust-constr for Gaussian model, 
                      and L-BGFS for extended model. The format should be '-x "tc,bgfs"'
      -j <n_jobs>     number of jobs to parallellize over; default is 10
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -r <TR>         set repetition time (TR) manually. Defaults to 1.5 if input != gifti's. Otherwise
                      we'll read it from gifti-files with 'dataset.ParseGiftiFile'
      -v <n_vols>     number of volumes to cut from the beginning of the timeseries (default = None)
      --bgfs          use L-BGFS minimization for both the Gaussian as well as the extended model. Use 
                      the '-x'flag if you want different minimizers for both stages
      --bold          re-calculate the BOLD timecourses; otherwise use existing '*hemi-LR_desc-avg_bold.npy'   
      --fsaverage     overwrite PYBEST_SPACE-variable and use FSAverage for fitting (see your setup file)
      --fsnative      overwrite PYBEST_SPACE-variable and use FSNative for fitting (see your setup file)
      --fix_hrf       fit the HRF going from Gaussian iterative fit to further fitting
      --grid          only run grid fit, skip iterative fit
      --no_hrf        do NOT fit the HRF during pRF-fitting. See 'call_prf' for more information
      --separate_hrf  fit the HRF in two stages. See 'call_prf' for more information
      --local         run locally even though we have SGE available.
      --merge_ses     average pRF data from all sessions
      --multi_design  specifies that for all runs in the dataset have run-/task-specific screenshot di-
                      rectories. This requires that the directory names you saved must match your naming 
                      scheme of functional files as we'll match on run-/task-ID
      --nelder        Use Nelder-Mead method for minimization.
                      Use the '-x' flag if you want different minimizers for both stages
      --no_clip       ensures that the design matrix is NOT clipped, despite the possible presence of 
                      screen delimiter files
      --no_fit        Stop the process before fitting, right after saving out averaged data. This was use-
                      ful for me to switch to percent-signal change without requiring a re-fit.
      --save_grid     Save out gridsearch parameters
      --no_bounds     Turn off grid bounds; sometimes parameters fall outside the grid parameter bounds, 
                      causing 'inf' values. This is especially troublesome when fitting a single time-
                      course. If you trust your iterative fitter, you can turn off the bounds and let 
                      the iterative take care of the parameters
      --raw           use the raw, un-zscore'd output from pybest, rather than percent signal change
      --refit         refit existing data; uses a simplified call to fmriproc.prf.pRFmodelFitting 
                      using call_prfrefit
      --tc            use trust-constr minimization for both the Gaussian as well as the extended model. 
                      Use the '-x' flag if you want different minimizers for both stages
      --zscore        use the zscore'd output from pybest, rather than percent signal change. If not spe-
                      cified, percent signal change is implemented as follows:
                        psc = signals*100/(mean(signals)) - median(signals_without_stimulus)
      --v1|--v1       only fit voxels from ?.V1/2_exvivo.thresh.label; the original dimensions will be 
                      maintained, but timecourses outside of the ROI are set to zero
        
    Arguments:
      <input dir>     base input directory with pybest data (e.g., 'DIR_DATA_DERIV/pybest'). You can also 
                      point to the fmriprep-folder, in which case the gifti's of 'fsnative' will be used.
      <output dir>    base output directory for prf data (e.g., 'DIR_DATA_DERIV/prf')
      <png dir>       base path of where sourcedata of subjects live. In any case, the subject ID will be
                      appended to this path (if applicable, so will session ID). Inside THAT directory, 
                      we'll search for directories with 'Screenshots'. So, if you specify DIR_DATA_SOURCE 
                      for 'sub-005' and 'ses-1', we'll search in DIR_DATA_SOURCE/sub-005/ses-1/* for di-
                      rectories with "Screenshots". If multiple directories are found, it depends on the 
                      options which directory is used: if --multi_design is specified, each directory will 
                      be matched with its corresponding functional run. If not, we'll take the 1st direc-
                      tory in the list.

    Models for pRF fitting:
      --gauss         run standard Gaussian model (default) [Dumoulin & Wandell, 2008]
      --dog           run difference-of-gaussian model (suppression) [Zuiderbaan, et al. 2013]
      --css           run compressive spatial summation model (compression) [Kay, et al. 2013]
      --norm          run divisive normalization model (suppresion+compression) [Aqil, et al. 2021]

    Eample:
      spinoza_fitprfs DIR_DATA_DERIV/prf DIR_DATA_DERIV/pybest DIR_DATA_SOURCE
      spinoza_fitprfs -s 001 -n 1 DIR_DATA_DERIV/prf DIR_DATA_DERIV/pybest DIR_DATA_SOURCE
      spinoza_fitprfs --multi_design DIR_DATA_DERIV/prf DIR_DATA_DERIV/pybest DIR_DATA_SOURCE
      spinoza_fitprfs -g -l DIR_DATA_DERIV/prf DIR_DATA_DERIV/pybest DIR_DATA_SOURCE
      spinoza_fitprfs -o DIR_DATA_DERIV/prf DIR_DATA_DERIV/pybest DIR_DATA_SOURCE

    ---------------------------------------------------------------------------------------------------


18: spinoza_bestvertex_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_bestvertex

    wrapper for call_targetvertex to calculate the best vertex and normal vector based on the minimal
    curvature given an ROI.

    this script requires input from FreeSurfer, so it won't do much if that hasn't run yet. Ideally, you
    should perform FreeSurfer with the pRF-mapping in fMRIprep (module before [13]), then run this thing
    so it can also take in the pRF to locate an even better vertex.

    Args:
      -o|--ow         rename existing file to numerically increasing (e.g., line_pycortex > line_pycor-
                      tex1.csv) so that a new line_pycortex.csv-file is created. Given that the original
                      file is NOT deleted, I consider this a soft-overwrite mode. You can always manual-
                      ly delete unwanted/unused files or use '--full' to remove the file.
      --aparc         specified ROI is part of the 'aparc.annot' atlas [default = False]. It is wise to 
                      use this function in combination with '--manual' to select a vertex from this ROI.
                      Available ROIs in this atlas are:
                        'caudalanteriorcingulate'
                        'caudalmiddlefrontal'
                        'corpuscallosum'
                        'cuneus'
                        'entorhinal'
                        'fusiform'
                        'inferiorparietal'
                        'inferiortemporal'
                        'isthmuscingulate'
                        'lateraloccipital'
                        'lateralorbitofrontal'
                        'lingual'
                        'medialorbitofrontal'
                        'middletemporal'
                        'parahippocampal'
                        'paracentral'
                        'parsopercularis'
                        'parsorbitalis'
                        'parstriangularis'
                        'pericalcarine'
                        'postcentral'
                        'posteriorcingulate'
                        'precentral'
                        'precuneus'
                        'rostralanteriorcingulate'
                        'rostralmiddlefrontal'
                        'superiorfrontal'
                        'superiorparietal'
                        'superiortemporal'
                        'supramarginal'
                        'frontalpole'
                        'temporalpole'
                        'transversetemporal'
                        'insula'
      --full          full overwrite mode
      --no_freeview   prevent FreeView from opening while verifying the location. ONLY do this if you
                      already know the position. Generally only used for debugging purposes.
      --no_srf        do not use size-response functions (SRFs) despite the usage of DN-model estimates
      --srf_file      search for file with SRFs (should be call "desc-srfs_centered.csv" in the subjects'
                      pRF folder, e.g., 'derivatives/prf/<subject>/ses-<x>/sub-001_desc-srfs_centered.csv')        
      --v1|--v2       use the pRF-estimates that you created with spinoza_fitprfs --v1/--v2
      --grid          use pRF-estimates from grid search; default is 'iter'
      --gallery       save all cortex-objects from 'optimal.TargetVertex()' in a figure. If pRFs and SRFs
                      are included, this will yield in a 4x5 grid with brainmaps of various kinds that 
                      were used in the selection process of the target vertex.
      --manual        use manual selection for the vertex, rather than minimizing for curvature     
      --no_epi        do not use EPI-intensities even though you could   
      --skip_prf_info skip the creation of the 'model-{}_desc-best_vertices.csv'. This can be useful if 
                      you want an indication of the pRF-properties, but want to refit yourself. This is 
                      the case where I use M. Aqil's fitting output, which has been fitted with an out-
                      dated screen distance.      
      -s <subject>    subject ID as used throughout the pipeline without prefix (e.g., 001 > 001)
      -n <session>    session ID used to extract the correct pRF-parameters. Will combined with <deriva-
                      tives>/prf/ses-<session>
      -l <line ses>   session ID for new line-scanning session; default = 2
      -t <task>       select pRF estimates from a particular task; by default the first element of TASK_
                      SES1 in spinoza_setup
      -v <vertices>   manually specify two vertices to use instead of having the program look for it. 
                      The format is important here and should always be: "<vertex in lh>,<vertex in rh>".
                      Always try to specify two vertices; doesn't matter too much if one is not relevant
      -e <epi_file>   Specify custom EPI-intensity file rather than looking in DIR_DATA_DERIV/fmriprep. 
                      Automatically sets --use_epi.
      <project root>  Path to where the subject-drectories are located; used to loop through subjects, 
                      unless the -s switch is triggered
      <derivatives>   Derivatives folder containing the output from pycortex and pRF-fitting. Looks for 
                      <derivatives>/freesurfer, <derivatives>/pycortex, and <derivatives>/prf for the 
                      surface reconstruction, pycortex-import, and pRF-data, respectively
      <ROI>           Region-of-interest to use. Should be a FreeSurfer-named label-file or a custom
                      file in the format of FreeSurfer label-file: you could for instance draw an ROI
                      in volume-space in FreeView, convert that to a label ("mri_vol2label") and insert
                      that to look for a vertex (might be useful for finding a mask representing indi-
                      vidual fingers when the motor cortex mask from FreeSurfer is to coarse).

                      If pRFs are used, we'll also try to include the mean intensities of the functional
                      data as criteria, to exclude veins

    Models for pRF fitting:
      --gauss         use standard Gaussian model (default) [Dumoulin & Wandell, 2008]
      --dog           use difference-of-gaussian model (suppression) [Zuiderbaan, et al. 2013]
      --css           use compressive spatial summation model (compression) [Kay, et al. 2013]
      --norm          use divisive normalization model (suppresion+compression) [Aqil, et al. 2021]

    Usage:
      spinoza_bestvertex [options] <sourcedata> <derivatives> <ROI>

    Example:
      spinoza_bestvertex DIR_DATA_HOME DIR_DATA_DERIV V1_exvivo.thresh
      spinoza_bestvertex -s 001 DIR_DATA_HOME DIR_DATA_DERIV V1_exvivo.thresh
      spinoza_bestvertex -s 001 -v "1957,8753" DIR_DATA_HOME DIR_DATA_DERIV V1_exvivo.thresh

    ---------------------------------------------------------------------------------------------------

19: spinoza_segmentfast_
=======================================================================================================

.. code-block:: none
    
    ---------------------------------------------------------------------------------------------------
    spinoza_segmentfast

    tissue segmentation with FAST using skullstripped inputs created during spinoza_maskaverages. It is
    important that the range of these images is set correctly, with T1w having a range of 0-4095, and
    the T1map having a range of (0,5050). This should automatically be the case if you have ran the py-
    mp2rage module in combination with the masking module prior to running this. If not, run call_rescale
    on these images.

    Usage:
      spinoza_segmentfast <-s sub> <-n ses> <skullstripped dir> <output dir> <overwrite>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      <anat folder>       folder containing the files required for FAST. Input must be skullstripped
      <output>            output folder (<subject>/[<ses->] will be appended!)

    Example:
      spinoza_segmentfast DIR_DATA_DERIV/skullstripped DIR_DATA_DERIV/fsl
      spinoza_segmentfast -s 001 -n 1 DIR_DATA_DERIV/skullstripped DIR_DATA_DERIV/fsl

    ---------------------------------------------------------------------------------------------------

20: spinoza_mgdm_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_mgdm

    Tissue segmentation using nighres' MGDM. It assumes that you've run module from this pipeline before,
    so that you're directory structure is like derivatives/<process>/${SUBJECT_PREFIX}xxx/ses-x. For this script, you
    need to give the path to the skullstripped directory up until ${SUBJECT_PREFIX}xxx, the output mgdm directory,
    and the directory containing masks that are used to filter out stuff in the MGDM segmentation.

    By default, it's set to overwrite existing files in order to be able to iterate over the structural
    preprocessing pipeline for optimizing the segmentations. To disable, run this particular module with
    the overwrite switch set to 'n': master -m <module> -o n

    Usage:
      spinoza_mgdm [options] <skullstripped> <mgdm> <masks>

    Arguments:
      -s <subject>      subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>      session ID (e.g., 1, 2, or none)
      -o                overwrite existing files
      --gdh             run GdH-pipeline version (call_gdhmgdm). Default = regular MGDM
      <skullstripped>   path to skullstripped data
      <mgdm>            path to output directory
      <masks>           path to masks

    Example:
      spinoza_mgdm SKULLSTRIP NIGHRES/mgdm MASKS
      spinoza_mgdm -s 001 -n 1 SKULLSTRIP NIGHRES/mgdm MASKS
      spinoza_mgdm -s 001 -n 1 --gdh SKULLSTRIP NIGHRES/mgdm MASKS

    ---------------------------------------------------------------------------------------------------

21: spinoza_extractregions_
=======================================================================================================

.. code-block:: none
    
    ---------------------------------------------------------------------------------------------------
    spinoza_extractregions

    region extraction using nighres. Calls on call_nighresextractregions; see that file for more info-
    rmation on the required inputs. This script is by default in overwrite mode, meaning that the files
    created earlier will be overwritten when re-ran. To disable, run this module as master -m <module>
    -o n. The second arguments points to the root directory of where the level set probabilities are
    stored. Normally, for region extraction, you use the output from MGDM. You can, however, create a
    custom levelset (see call_gdhcombine).

    For this, you will need four directories: the REGION directory (with tissue classification from
    MGDM), the FreeSurfer directory (read from you SUBJECTS_DIR), the fMRIprep-directory with tissue
    classification from FAST, and the MASK-directory containing manual edits. The REGION directory is
    the directory that will be created first, the FreeSurfer directory will be read from the SUBJECTS_DIR
    variable, the fMRIprep-directory you'll need to specify with the -f flag BEFORE (!!) the positional
    arguments, and the MASK-directory you will already specify.

    Usage:
      spinoza_extractregions [options] <nighres folder> <probability folder> <ROI>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      <nighres folder>    folder with nighres output
      <prob folder>       folder containing masks
      <region>            region to extract with Nighres

    Example:
      spinoza_extractregions DIR_DATA_DERIV/nighres DIR_DATA_DERIV/manual_masks cerebrum
      spinoza_extractregions -s -001 -n 1 -o DIR_DATA_DERIV/nighres DIR_DATA_DERIV/manual_masks cerebrum

    Notes:
      - If you want a custom levelset, specify the '-f' flag pointing to the fMRIprep-directory
      - Has the '-s' and '-n' switches to specify a particular subject and session if present
      - Region to be extracted can be one of:
        > left_cerebrum
        > right_cerebrum
        > cerebrum,
        > cerebellum
        > cerebellum_brainstem
        > subcortex
        > tissues(anat)
        > tissues(func)
        > brain_mask

    ---------------------------------------------------------------------------------------------------

22: spinoza_cortexrecon_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_cortexrecon

    cortex reconstruction using nighres. Calls on call_nighrescruise; see that file for more information
    on the required inputs. This script is by default in overwrite mode, meaning that the files created
    earlier will be overwritten when re-ran. To disable, run this module as master -m <module> -o n

    Usage:
      spinoza_cortexrecon [options] <project root dir> <prob seg dir> <region>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      <prob seg>          directory containing probabilities of tissue segmentation. By default it will 
                          use the MDGM output, but you can specify your own. E.g., in the case of GdH-
                          pipeline
      <project>           output folder for nighres
      <region>            region you wish to reconstruct. Should be same as spinoza_extractregions

    Example:
      spinoza_cortexrecon PROBSEGS CRUISE cerebrum
      spinoza_cortexrecon -s 001 -n 1 -o PROBSEGS CRUISE cerebellum

    ---------------------------------------------------------------------------------------------------

23: spinoza_layering_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_layering

    Equivolumetric layering with either nighres or Wagstyl's surface_tools, as specified by the third
    argument. Surface_tools is based on FreeSurfer, so make sure that has run before it. This script is
    by default in overwrite mode, meaning that the files created earlier will be overwritten when re-ran.
    This doesn't take too long, so it doesn't really matter and prevents the need for an overwrite switch.
    To disable, you can specify a condition before running this particular script.

    Usage:
      spinoza_layering [options] <input dir> <software>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -l <nr_layers>      number of layers to estimate (defaults: nighres=10; FreeSurfer=5)
      -o                  overwrite existing files
      <input folder>      if software == 'nighres', then we need the nighres output folder (generally 
                          DIR_DATA_DERIV/nighres). If software == 'freesurfer', then we need the SUB-
                          JECTS_DIR
      <software>          Possible inputs for software are:
                            Nighres: voxel-based layering
                            surface_tools: surface-based layering with Wagstyl's method

    Example:
      spinoza_layering SUBJECTS_DIR surface
      spinoza_layering DIR_DATA_DERIV/nighres nighres

    Notes:
      - The script will recognize any of the software inputs specified above, with these variations in
        capitalization.
      - The script will look for a surface_tools installation on the PATH and if it can't find it there,
        it will look for the first match in the HOME directory. To be sure, place the script either in
        the home directory or place it on the PATH.
      - If the script doesn't give an error before printing the starting time, it means it found the
        script.

    ---------------------------------------------------------------------------------------------------

24: spinoza_subcortex_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_subcortex

    Subcortex segmentation using Nighres' MASSP-algorithm. Calls on call_nighresmassp; see that file
    for more information on the required inputs.

    Usage:
      spinoza_subcortex [options] <project root dir> <prob seg dir> <region> <overwrite>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      <anat folder>       folder containing the files required for MASSP. Files should end with:
                            -"*_R1.nii.gz"   > 1/T1map file
                            -"*_R2s.nii.gz"  > 1/T2* file
                            -"*_QSM.nii.gz"  > QSM file
      <output>            output folder (<subject>/[<ses->] will be appended!)

    Example:
      spinoza_subcortex DIR_DATA_HOME DIR_DATA_DERIV/nighres
      spinoza_subcortex -s 001 -n 1 DIR_DATA_HOME DIR_DATA_DERIV/nighres

    ---------------------------------------------------------------------------------------------------

25: spinoza_line2surface_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_line2surface

    This script contains the registration cascade from single slice/line > multi-slice (9 slice) > low
    resolution MP2RAGE from session 2 > high resolution MP2RAGE from session 1 > FreeSurfer anatomy.
    In spinoza_lineplanning, we have created a matrix mapping the low resolution anatomy to the high
    resolution anatomy from session 1. Because the single- and multislice images are basically in the
    same space (header-wise) as the low resolution anatomical scan, we can just apply this matrix to the
    single- and multi-slice. We then have everything in the space of the high resolution anatomy from
    session 1.

    Now we need a matrix mapping the high resolution anatomical scan from session 1 with the FreeSurfer
    anatomy. For this, we can use FreeSurfer's bbregister, which registers an input image to orig.mgz.
    We can transform both matrices to FSL-format, so we can create a composite transformation matrix
    that we can apply to everything from session 2 with flirt. Because we need all these transformed
    files for pycortex, we will try to store all the files in the pycortex directory, but you can speci-
    fy this yourself (default is the pycortex directory).

    Easiest thing to do is run the "segmentation.ipynb" notebook to warp all segmentations to session 
    1, then everything - HOP - to FreeSurfer and Pycortex space using the matrix created with spinoza_
    lineplanning (this matrix you should definitely have..).

    Usage:
      spinoza_line2surface -s <subject number> -y <anat session 2> -o <outputdir> -i <input dir>

    Arguments:
      -s <sub number>         number of subject's FreeSurfer directory
      -y <anat ses 2>         anatomical image from session 2 as outputted by spinoza_lineplanning
      -o <output directory>   default is bids_root/derivatives/pycortex (easiest to set this to default
                              other make it the same as Pycortex' filestore) [<sub> will be appended]
      -i <directory to warp>  input directory that we need to warp to the surface; I'm assuming a struc-
                              ture like "<input dir>/<sub>/ses-2"

    Example:
      spinoza_line2surface -s ${SUBJECT_PREFIX}001 -y anat_session2 -d /output/directory/whatev

    ---------------------------------------------------------------------------------------------------

26: spinoza_profiling_
=======================================================================================================

.. code-block:: none

    ---------------------------------------------------------------------------------------------------
    spinoza_profiling

    Sample the profile values of a particular image using call_nighresprofsamp. Here, we provide the
    boundaries-image from nighres.layering module and have the program sample values from a particular
    dataset (e.g., T1map) across depth. The first argument specifies where the nighres output is, used
    for both the layering and profile sampling. The second argument is the main directory where we will
    find the file the we want to sample. The last argument specifies a tag to look for the to-be-sampled
    file (e.g., T1map)

    Usage:
      spinoza_profiling [options] <nighres input> <input folder> <extension for to-be-sampled file>

    Arguments:
      -s <subject>        subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>        session ID (e.g., 1, 2, or none)
      -o                  overwrite existing files
      <nighres>           parent directory containing the output files of Nighres
                            -<nighres>/<subject>/<session>/layering/*boundaries*
                            -<nighres>/<subject>/<session>/profiling/*lps_data.nii.gz
      <tag>               tag to use to look for to-be-sampled dataset (e.g., T1map)

    Example:
      spinoza_profiling NIGHRES DIR_DATA_HOME T1map
      spinoza_profiling -s 01 -n 2 NIGHRES DIR_DATA_HOME T1map

    ---------------------------------------------------------------------------------------------------
