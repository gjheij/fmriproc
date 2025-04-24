.. include:: links.rst

------------
Bash modules
------------

spinoza_averageanatomies_
====================================================================================================

.. code-block:: none

    spinoza_averagesanatomies
    
    This script takes the MP2RAGE and MEMP2RAGE-derived T1-weighted images to calculate the average.
    This results in an image that takes advantage of the better WM/GM contrast of the MP2RAGE and the
    QSM-properties of the MEMP2RAGE sequence. This will only happen if you have two elements in the
    \$ACQ variable of the \$CONFIG_FILE and if the \$DATA-variable is set to "AVERAGE".
    
    Usage:
      spinoza_averagesanatomies [arguments] [options] <anat folder> <output folder>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
    
    Positional:
      <input>         directory containing the files to be registered; generally the output from
                      pymp2rage (see 'spinoza_qmrimaps')
      <output>        path to directory where registration file/outputs should be stored
    
    Example:
      spinoza_averagesanatomies \$DIR_DATA_DERIV \$DIR_DATA_DERIV
      spinoza_averagesanatomies -s 001 -n 1 \$DIR_DATA_DERIV \$DIR_DATA_DERIV
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01

spinoza_bestvertex_
====================================================================================================

.. code-block:: none

    spinoza_bestvertex
    
    wrapper for call_targetvertex to calculate the best vertex and normal vector based on the minimal
    curvature given an ROI.
    
    this script requires input from FreeSurfer, so it won't do much if that hasn't run yet. Ideally,
    you should perform FreeSurfer with the pRF-mapping in fMRIprep (module before [13]), then run this
    thing so it can also take in the pRF to locate an even better vertex.
    
    Usage:
      spinoza_bestvertex [arguments] [options] <sourcedata> <derivatives> <ROI>
    
    Arguments:
      -s <subject>    subject ID as used throughout the pipeline without prefix (e.g., 001 > 001)
      -n <session>    session ID used to extract the correct pRF-parameters. Will combined with
                      \$DIR_DATA_DERIV/prf/ses-<session>
      -l <line ses>   session ID for new line-scanning session; default = 2
      -t <task>       select pRF estimates from a particular task; by default the first element of
                      TASK_IDS in \$CONFIG_FILE
      -v <vertices>   manually specify two vertices to use instead of having the program look for it.
                      The format is important here and should always be: "<vertex in lh>,<vertex in
                      rh>". Always try to specify two vertices; doesn't matter too much if one is not
                      relevant
      -e <epi_file>   Specify custom EPI-intensity file rather than looking in \$DIR_DATA_DERIV/
                      fmriprep. Automatically sets --use-epi.
    
    Options:
      -h|--help       print this help text
      -o|--ow         rename existing file to numerically increasing (e.g., line_pycortex > line_pycor-
                      tex1.csv) so that a new line_pycortex.csv-file is created. Given that the
                      original file is NOT deleted, I consider this a soft-overwrite mode. You can
                      always manually delete unwanted/unused files or use '--full' to remove the file.
      --aparc         specified ROI is part of the 'aparc.annot' atlas [default = False]. It is wise
                      to use this function in combination with '--manual' to select a vertex from this
                      ROI. Available ROIs in this atlas are:
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
      --no-freeview   prevent FreeView from opening while verifying the location. ONLY do this if you
                      already know the position. Generally only used for debugging purposes.
      --no-srf        do not use size-response functions (SRFs) despite the usage of DN-model estimates
      --srf-file      search for file with SRFs (should be call "desc-srfs_centered.csv" in the
                      subjects' pRF folder, e.g., 'derivatives/prf/<subject>/ses-<x>/
                      sub-001_desc-srfs_centered.csv')
      --v1|--v2       use the pRF-estimates that you created with spinoza_fitprfs --v1/--v2
      --grid          use pRF-estimates from grid search; default is 'iter'
      --gallery       save all cortex-objects from 'optimal.TargetVertex()' in a figure. If pRFs and
                      SRFs are included, this will yield in a 4x5 grid with brainmaps of various kinds
                      that were used in the selection process of the target vertex.
      --manual        use manual selection for the vertex, rather than minimizing for curvature
      --no-epi        do not use EPI-intensities even though you could
      --skip-prf-info skip the creation of the 'model-{}_desc-best_vertices.csv'. This can be useful
                      if you want an indication of the pRF-properties, but want to refit yourself.
                      This is the case where I use M. Aqil's fitting output, which has been fitted
                      with an outdated screen distance.
    
    Positional:
      <project root>  Path to where the subject-drectories are located; used to loop through subjects,
                      unless the -s switch is triggered
      <derivatives>   Derivatives folder containing the output from pycortex and pRF-fitting. Looks
                      for <derivatives>/freesurfer, <derivatives>/pycortex, and <derivatives>/prf for
                      the surface reconstruction, pycortex-import, and pRF-data, respectively
      <ROI>           Region-of-interest to use. Should be a FreeSurfer-named label-file or a custom
                      file in the format of FreeSurfer label-file: you could for instance draw an ROI
                      in volume-space in FreeView, convert that to a label ("mri_vol2label") and insert
                      that to look for a vertex (might be useful for finding a mask representing indi-
                      vidual fingers when the motor cortex mask from FreeSurfer is to coarse).
    
                      If pRFs are used, we'll also try to include the mean intensities of the
                      functional data as criteria, to exclude veins
    
    Models for pRF fitting:
      --gauss         use standard Gaussian model (default) [Dumoulin & Wandell, 2008]
      --dog           use difference-of-gaussian model (suppression) [Zuiderbaan, et al. 2013]
      --css           use compressive spatial summation model (compression) [Kay, et al. 2013]
      --norm          use divisive normalization model (suppresion+compression) [Aqil, et al. 2021]
    
    Usage:
      spinoza_bestvertex [options] <sourcedata> <derivatives> <ROI>
    
    Example:
      spinoza_bestvertex \$DIR_DATA_HOME \$DIR_DATA_DERIV V1_exvivo.thresh
      spinoza_bestvertex -s 001 \$DIR_DATA_HOME \$DIR_DATA_DERIV V1_exvivo.thresh
      spinoza_bestvertex -s 001 -v "1957,8753" \$DIR_DATA_HOME \$DIR_DATA_DERIV V1_exvivo.thresh
    
    Call with master:
      # search motor cortex
      master -m $(get_module_nr $(basename ${0})) --aparc -r precentral
    
      # use pRFs and select vertex manually
      master -m 18 -s 01 --norm --manual
    
      # use SRF and EPI files
      master -m $(get_module_nr $(basename ${0})) -s 01 --norm --manual -e mean_func.nii.gz --srf-file

spinoza_biassanlm_
====================================================================================================

.. code-block:: none

    spinoza_biassanlm
    
    Sometimes CAT12 can be a bit of an overkill with smoothing and bias corrections. This script should
    be run prior to "spinoza_brainextraction", and runs a SANLM-filter over the image as well as an
    bias field correction with SPM. The subsequent "spinoza_brainextraction" should be run with the
    "-m brain" flag as to turn off bias correction and denoising with CAT12. The input image is
    expected to reside in the input directory and to contain "acq-\${DATA}" and end with *T1w.nii.gz.
    By default, the previously created mask with SPM is used to boost performance on ANTs functions
    (e.g., SANLM/Bias correction).
    
    Usage:
      spinoza_biassanlm [arguments] [options] <anat folder> <output folder>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -j <cpus>       number of cores to use (default is 1)
      -l <lower>      lower percentile (default = 0.01) for call_winsorize
      -u <upper>      upper percentile (default = 0.99) for call_winsorize
      -x <kwargs>     Additional commands to be passed to 'call_antsbias'. Format should
                      be colon-separated flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>:<flag2>:<flag3>:<flag4>=<value>"
    
                      e.g.,
                        "-x -t=[0.25,0.005,250];-x=some_mask.nii.gz"
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --spm           run bias correction with SPM (default = False)
      --no-sanlm      do not run SANLM denoising (in case you don't have CAT12..)
      --no-mask       do not use SPM mask for SANLM/Bias correction with ANTs
      --n4            run bias correction with N4BiasCorrection (ANTs); if a mask is found with the
                      following search, this will be included (improves correction):
    
                        # output from spinoza_qmrimaps
                        spm_mask=\$(
                          find "\${INPUTDIR}" \\
                          -name "*acq-\${DATA}*" \\
                          -and -name "*spm_mask.nii.gz"
                        )
    
      --denoise       use SANLM algorithm implemented in ANTs (DenoiseImage), rather than
                      CAT12.
    
    Positional:
      <anat dir>      parent directory containing the sub-xxx folders for anatomies. Can be e.g.,
                      \$DIR_DATA_HOME or \$DIR_DATA_DERIV/pymp2rage
      <output>        Output directory for the denoised images (something like \$DIR_DATA_DERIV/
                      denoised)
    
    Example:
      spinoza_biassanlm DIR_DATA_DERIV/pymp2rage \$DIR_DATA_DERIV/denoised
      spinoza_biassanlm -s 001 -n 1 \$DIR_DATA_HOME \$DIR_DATA_DERIV/denoised
      spinoza_biassanlm -s 001 -n 1 -b \$DIR_DATA_HOME \$DIR_DATA_DERIV/denoised
    
      # run SANLM and Bias correction with ANTs
      spinoza_biassanlm -s 001 -n 1 -b \$DIR_DATA_HOME \$DIR_DATA_DERIV/denoised --n4 --denoise
    
    Call with master:
      # vanilla | use SPM for bias corr and SANLM
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # use ANTs
      master -m $(get_module_nr $(basename ${0})) -s 01 --n4 --denoise
    
      # pass kwargs to call_antsbias
      master -m $(get_module_nr $(basename ${0})) -s 01 --n4 -x -t=[0.25,0.005,250];-x=some_mask.nii.gz

spinoza_brainextraction_
====================================================================================================

.. code-block:: none

    spinoza_brainextraction
    
    wrapper for brain extraction with ANTs, FSL, or CAT12 If you use ANTs, specify a prefix; if you
    use FSL, specify an output name. Not case sensitive (i.e., you can use ANTs/ants or FSL/fsl).
    Assumes that if you select FSL, we brain extract the INV2 image and if we select ANTs/CAT12, we
    brain extract the mp2rage T1w with bias field correction. If you want to brain extract something
    else, either use call_fslbet, call_antsbet, or call_cat12. It performs N4 biasfield correction
    internally. Make sure you added the location of antsBrainExtraction.sh to your path e.g., in your
    ~/.bash_profile : \"export PATH=PATH:/directory/with/antsBrainExtraction.sh\"
    
    Usage:
      spinoza_brainextraction [arguments] [options] <input dir> <skullstrip output> <mask output>
      <ants/FSL/cat12>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or n)
      -l <lower>      lower percentile (default = 0.01) for call_winsorize
      -u <upper>      upper percentile (default = 0.99) for call_winsorize
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --full          do full processing with CAT12 including iterative SANLM filtering and bias
                      correction. Default is just tissue segmentation.
      --fs            use rawavg.mgz from FreeSurfer; overwrites the specified input
                      directory
      --fprep         use desc-preproc_T1w from fMRIprep. The input is linked the '-n' flag
    
    Positional:
      <input>         directory for inputs
      <skullstrip>    directory for skull-stripped outputs
      <mask>          directory for masks
      <software>      which software to use: ants|FSL|CAT12
    
    Example:
      spinoza_brainextraction \\
        \$DIR_DATA_DERIV/pymp2rage \\
        \$DIR_DATA_DERIV/cat12 \\
        \$DIR_DATA_DERIV/manual_masks \\
        cat12
    
      spinoza_brainextraction \\
        -s 01,02 \\
        -n 2 \\
        \$DIR_DATA_HOME \\
        \$DIR_DATA_DERIV/skullstripped \\
        \$DIR_DATA_DERIV/manual_masks \\
        fsl
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # use fMRIprep input
      master -m $(get_module_nr $(basename ${0})) -s 01 --fprep
    
      # specify bounds for call_winsorize
      master -m $(get_module_nr $(basename ${0})) -s 01 -l 0.05 -u 0.95

spinoza_config_
====================================================================================================

.. code-block:: none

    (No help text found)

spinoza_cortexrecon_
====================================================================================================

.. code-block:: none

    spinoza_cortexrecon
    
    cortex reconstruction using nighres. Calls on call_nighrescruise; see that file for more
    information on the required inputs. This script is by default in overwrite mode, meaning that the
    files created earlier will be overwritten when re-ran. To disable, run this module as master -m
    <module> -o n
    
    Usage:
      spinoza_cortexrecon [arguments] [options] <project root dir> <prob seg dir> <region>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      <prob seg>      directory containing probabilities of tissue segmentation. By default it will
                      use the MDGM output, but you can specify your own. E.g., in the case of GdH-
                      pipeline
      -x <kwargs>     Additional commands to be passed to 'cruise_cortex_extraction'. Format should
                      be comma-separated flags as follows:
                      - if you specify a flag and values | <flag>=<value>
                      - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      This allows bash commands to be translated to python commands
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
    
    Positional
      <project>       output folder for nighres
      <region>        region you wish to reconstruct. Should be same as spinoza_extractregions:
                        > left_cerebrum
                        > right_cerebrum
                        > cerebrum
                        > cerebellum
                        > cerebellum_brainstem
                        > subcortex
                        > tissues(anat)
                        > tissues(func)
                        > brain_mask
    
    Example:
      spinoza_cortexrecon \${DIR_DATA_DERIV}/manual_masks \${DIR_DATA_DERIV}/nighres cerebrum
      spinoza_cortexrecon \\
        -s 001 \\
        -n 1 \\
        \${DIR_DATA_DERIV}/nighres \${DIR_DATA_DERIV}/nighres cerebellum
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # run with nighres' segmentations rather than combined segmentations
      master -m $(get_module_nr $(basename ${0})) -s 01 -r subcortex -l nighres
    
      # specify ROI
      master -m $(get_module_nr $(basename ${0})) -s 01 -r subcortex
    
      # pass kwargs
      master -m $(get_module_nr $(basename ${0})) -s 01 -x max_iterations=100,wm_dropoff_dist=0.5

spinoza_denoising_
====================================================================================================

.. code-block:: none

    spinoza_denoising
    
    wrapper for call_pybest that does the denoising of fMRI-data based on the confound file created
    during the preprocessing with fmriprep. By default, it will use FSNative, unless the PYBEST_SPACE
    variable in the setup file says something else, or if the '--fsaverage' flag is specified
    
    Usage:
      spinoza_denoising [arguments] [options] <fmriprep directory> <pybest output directory>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -t <task ID>    limit pybest processing to a specific task. Default is all tasks in TASK_IDS
                      in the spinoza_setup-file Can also be comma-separated list: task1,task2
      -j <n_cpus>     number of CPUs to use (default = 1)
      -c <n_comps>    overwrite the \$PYBEST_N_COMPS-variable deciding the number of components for
                      the PCA (default = 20 as per Marco's investigations)
      -q <queue>      submit jobs to a specific queue. Defaults to \$SGE_QUEUE_LONG in \$CONFIG_FILE
      -x <kwargs>     Additional commands to be passed to 'pybest'. Format should be comma-separated
                      flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      This allows bash commands to be translated to python commands
    
    Options:
      -h|--help       print this help text
      -o|--ow         overwrite existing files. Note that this does not delete the full ses-<> folder!
                      use --full to completely remove a folder
      --full          Overwrite (i.e., remove) existing output. In case of "-r 'all'", the entire
                      subject directory is removed
      --sge           submit job to cluster (called with 'master -m <module> --sge')
      --no-raw        do NOT unzscore the output from pybest (default is to do so)
      --fsaverage     overwrite PYBEST_SPACE-variable and use FSAverage for pybest (defaults to fs-
                      native)
      --fsnative      overwrite PYBEST_SPACE-variable and use FSNative (defaults to fsnative)
      --func          overwrite PYBEST_SPACE-variable and use 'func'-space
      --anat          overwrite PYBEST_SPACE-variable and use 'T1w'-space
      --mni-fsl       overwrite PYBEST_SPACE-variable and use 'MNI152NLin6Asym_res-1'-space
      --mni-2009      overwrite PYBEST_SPACE-variable and use 'MNI152NLin2009cAsym_res-1'-space
      --force         force execution despite existing files
      --sge           submit job to cluster (SGE/SLURM)
      --pyb-only      run only pybest step.
      --post-only     run only post-processing step.
      --pre-only      run only pre-processing step.
      --force-exec    force the execution of Pybest regardless of existing files.
    
    Positional:
      <project root>  base directory containing the derivatives and the subject's folders.
      <derivatives>   path to the derivatives folder
    
    Eample:
      spinoza_denoising \$DIR_DATA_HOME \$DIR_DATA_DERIV
      spinoza_denoising -s 001 -n 1 \$DIR_DATA_HOME \$DIR_DATA_DERIV
      spinoza_denoising -o \$DIR_DATA_HOME \$DIR_DATA_DERIV
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # submit with 10 cores
      master -m $(get_module_nr $(basename ${0})) -s 01 -j 10 --sge
    
      # use volumetric space
      master -m $(get_module_nr $(basename ${0})) -s 01 --func
    
      # limit to specific tasks rather than \$TASK_IDS in \$CONFIG_FILE
      master -m $(get_module_nr $(basename ${0})) -s 01 --func -t rest,task1
    
    Notes:
      There are multiple flags to change the \$PYBEST_SPACE-variable. If your desired space is not
      specified, update the variable in the setup file.

spinoza_dura_
====================================================================================================

.. code-block:: none

    spinoza_dura
    
    estimate the location of the skull and dura using nighres. You are to specify the path to the input
    T1w-images (e.g., pymp2rage), the input INV2 image (e.g., the bias field corrected INV2 in the ANTs
    folder, the nighres output folder, and the folder to store the masks.
    
    Usage:
      spinoza_dura [arguments] [options] <anat folder> <INV2 folder> <nighres output> <mask output>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or n)
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
    
    Positional:
      <anat dir>      folder containing the T1w-file
      <inv2 dir>      folder containing the INV2-image
      <nighres out>   output folder for Nighres
      <mask output>   output folder for masks
    
    Example:
      spinoza_dura \${DIR_DATA_HOME} \${DIR_DATA_DERIV}/nighres \${DIR_DATA_DERIV}/manual_masks
      spinoza_dura \\
        -s 001 \\
        -n 1 \\
        \${DIR_DATA_HOME} \${DIR_DATA_DERIV}/nighres \${DIR_DATA_DERIV}/manual_masks
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01

spinoza_extractregions_
====================================================================================================

.. code-block:: none

    spinoza_extractregions
    
    region extraction using nighres. Calls on call_nighresextractregions; see that file for more info-
    rmation on the required inputs. This script is by default in overwrite mode, meaning that the files
    created earlier will be overwritten when re-ran. To disable, run this module as master -m <module>
    -o n. The second arguments points to the root directory of where the level set probabilities are
    stored. Normally, for region extraction, you use the output from MGDM. You can, however, create a
    custom levelset (see call_gdhcombine).
    
    For this, you will need four directories: the REGION directory (with tissue classification from
    MGDM), the FreeSurfer directory (read from you \$SUBJECTS_DIR), the fMRIprep-directory with tissue
    classification from FAST, and the MASK-directory containing manual edits. The REGION directory is
    the directory that will be created first, the FreeSurfer directory will be read from the
    \$SUBJECTS_DIR-variable, the fMRIprep-directory you'll need to specify with the -f flag BEFORE
    (!!) the positional arguments, and the \$MASKS-directory you will already specify.
    
    Usage:
      spinoza_extractregions [arguments] [options] <nighres out> <probability folder> <ROI>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --skip-combine  do not combine all segmentations, just exit after Nighres
    
    Positional:
      <nighres out>   folder with nighres output
      <prob folder>   folder containing masks
      <region>        region to extract with Nighres
    
    Example:
      spinoza_extractregions \$DIR_DATA_DERIV/nighres \$DIR_DATA_DERIV/manual_masks cerebrum
      spinoza_extractregions \\
        -s -001 \\
        -n 1 \\
        \$DIR_DATA_DERIV/nighres \$DIR_DATA_DERIV/manual_masks cerebrum
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # specify ROI
      master -m $(get_module_nr $(basename ${0})) -s 01 -r subcortex
    
      # only run Nighres
      master -m $(get_module_nr $(basename ${0})) -s 01 --skip-combine
    
    Notes:
      - If you want a custom levelset, specify the '-f' flag pointing to the fMRIprep-directory
      - Has the '-s' and '-n' switches to specify a particular subject and session if present
      - Region to be extracted can be one of:
        > left_cerebrum
        > right_cerebrum
        > cerebrum
        > cerebellum
        > cerebellum_brainstem
        > subcortex
        > tissues(anat)
        > tissues(func)
        > brain_mask

spinoza_fitprfs_
====================================================================================================

.. code-block:: none

    spinoza_fitprfs
    
    Wrapper for call_prf that does the pRF-fitting using the output from pybest and the package pRFpy.
    There's several options for design matrix cases (in order of priority):
      - Place a design-matrix file called 'design_task-<TASK_NAME>.mat' in DIR_DATA_HOME/code
      - A directory with log-directories. A global search for a directory containing "Screenshots" is
        done. If more directories are found and '--one-design' is specified, we'll take the first dir
        ectory
      - A directory with log-directories, but '--one-design' is NOT specified, meaning that each run
        will get a separate design matrix. This can be useful if you have multiple conditions that
        have different designs.
    
    Usage:
      spinoza_fitprfs [arguments] [options] <input dir> <output dir> <png dir>
    
    Arguments:
      -c <a,b,c,d>    list of values used for clipping of design matrix. Format must be [<top>,
                      <bottom>, <left>,<right>]. Negative values will be set to zero within 'fmriproc.
                      prf.get_prfdesign'
      -f <n_folds>    if your pRF experiment contains multiple equal sequences, you can use this flag
                      to perform within-run averaging before percent-changing in call_prf. This should
                      be in concert with number of volumes removed from the beginning of the
                      timeseries
      -k <kwargs>     specify a file with additional arguments, similar to FreeSurfer's expert options.
                      See linescanning/misc/prf_options for an example. Please make sure you have a
                      final empty white space at the end of the file, otherwise the parser gets confu-
                      sed. For VSCode: https://stackoverflow.com/a/44704969.
      -m <model>      one of ['gauss','dog','css','norm'] is accepted, default = "gauss"
      -n <session>    session ID (e.g., 1, 2, or none)
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -t <task ID>    If you have mutiple tasks specified in TASK_IDS or you just have multiple tasks
                      and you want to run only one, specify the task name here ('task-rest' is
                      ignored). You can also specify multiple tasks if you want to bypass the setup
                      file completely. In that case, use the format '-t <task1>,<task2>,<task3>'
      -x <constr>     String or list of constraints to use for the gaussian and extended stage. By
                      default, we'll use trust-constr minimization for both stages, but you can speed
                      up the extended models with L-BGFS. Note that if you want the same minimizer for
                      both stages, you can use the '--tc' or '--bgfs' tags. This input specifically
                      allows you to specify a list of different minimizers for each stage, e.g.,
                      trust-constr for Gaussian model, and L-BGFS for extended model. The format
                      should be '-x "tc,bgfs"'
      -j <n_cpus>     number of jobs to parallellize over; default is 10
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -r <TR>         set repetition time (TR) manually. Defaults to 1.5 if input != gifti's. Otherwise
                      we'll read it from gifti-files with 'dataset.ParseGiftiFile'
      -v <n_vols>     number of volumes to cut from the beginning of the timeseries (default = None)
    
    Options:
      -h|--help       print this help text
      -o|--ow         delete existing file and re-run analysis fully. Even if 'model=norm', we'll over-
                      write the Gaussian parameters. If not specified, and 'model=norm' while Gaussian
                      parameters already exist, we'll inject them into the DN-model.
      --bgfs          use L-BGFS minimization for both the Gaussian as well as the extended model. Use
                      the '-x'flag if you want different minimizers for both stages
      --bold          re-calculate the BOLD timecourses; otherwise use existing
                      '*hemi-LR_desc-avg_bold.npy'
      --fsaverage     overwrite PYBEST_SPACE-variable and use FSAverage for fitting (see your setup
                      file)
      --fsnative      overwrite PYBEST_SPACE-variable and use FSNative for fitting (see your setup
                      file)
      --fix-hrf       fit the HRF going from Gaussian iterative fit to further fitting
      --grid          only run grid fit, skip iterative fit
      --no-hrf        do NOT fit the HRF during pRF-fitting. See 'call_prf' for more information
      --separate-hrf  fit the HRF in two stages. See 'call_prf' for more information
      --local         run locally even though we have SGE available.
      --merge-ses     average pRF data from all sessions
      --multi-design  specifies that for all runs in the dataset have run-/task-specific screenshot di-
                      rectories. This requires that the directory names you saved must match your
                      naming
                      scheme of functional files as we'll match on run-/task-ID
      --nelder        Use Nelder-Mead method for minimization.
                      Use the '-x' flag if you want different minimizers for both stages
      --no-clip       ensures that the design matrix is NOT clipped, despite the possible presence of
                      screen delimiter files
      --no-fit        Stop the process before fitting, right after saving out averaged data. This was
                      useful for me to switch to percent-signal change without requiring a re-fit.
      --save-grid     Save out gridsearch parameters
      --no-bounds     Turn off grid bounds; sometimes parameters fall outside the grid parameter
                      bounds, causing 'inf' values. This is especially troublesome when fitting a
                      single timecourse. If you trust your iterative fitter, you can turn off the
                      bounds and let the iterative take care of the parameters
      --raw           use the raw, un-zscore'd output from pybest, rather than percent signal change
      --refit         refit existing data; uses a simplified call to fmriproc.prf.pRFmodelFitting
                      using call_prfrefit
      --tc            use trust-constr minimization for both the Gaussian as well as the extended
                      model. Use the '-x' flag if you want different minimizers for both stages
      --zscore        use the zscore'd output from pybest, rather than percent signal change. If not
                      specified, percent signal change is implemented as follows:
    
                        psc = signals*100/(mean(signals)) - median(signals_without_stimulus)
    
      --v1|--v1       only fit voxels from ?.V1/2_exvivo.thresh.label; the original dimensions will be
                      maintained, but timecourses outside of the ROI are set to zero
      --sge           submit job to cluster (SGE/SLURM)
    
    Positional:
      <input dir>     base input directory with pybest data (e.g., '\$DIR_DATA_DERIV/pybest'). You can
                      also point to the fmriprep-folder, in which case the gifti's of 'fsnative' will
                      be used.
      <output dir>    base output directory for prf data (e.g., '\$DIR_DATA_DERIV/prf')
      <png dir>       base path of where sourcedata of subjects live. In any case, the subject ID will
                      be appended to this path (if applicable, so will session ID). Inside THAT
                      directory, we'll search for directories with 'Screenshots'. So, if you specify
                      \$DIR_DATA_SOURCE for 'sub-005' and 'ses-1', we'll search in DIR_DATA_SOURCE/
                      sub-005/ses-1/* for directories with "Screenshots". If multiple directories are
                      found, it depends on the options which directory is used:
                        - if --multi-design is specified, each directory will be matched with its
                          corresponding functional run.
                        - If not, we'll take the 1st directory in the list.
    
    Models for pRF fitting:
      --gauss         run standard Gaussian model (default) [Dumoulin & Wandell, 2008]
      --dog           run difference-of-gaussian model (suppression) [Zuiderbaan, et al. 2013]
      --css           run compressive spatial summation model (compression) [Kay, et al. 2013]
      --norm          run divisive normalization model (suppresion+compression) [Aqil, et al. 2021]
      --abd           DN-model with fixed C-parameter [Aqil, et al. 2021]
      --abc           DN-model with fixed D-parameter [Aqil, et al. 2021]
    
    Eample:
      spinoza_fitprfs \$DIR_DATA_DERIV/prf \$DIR_DATA_DERIV/pybest \$DIR_DATA_SOURCE
      spinoza_fitprfs -s 001 -n 1 \$DIR_DATA_DERIV/prf \$DIR_DATA_DERIV/pybest \$DIR_DATA_SOURCE
      spinoza_fitprfs --multi-design \$DIR_DATA_DERIV/prf \$DIR_DATA_DERIV/pybest \$DIR_DATA_SOURCE
      spinoza_fitprfs -o \$DIR_DATA_DERIV/prf \$DIR_DATA_DERIV/pybest \$DIR_DATA_SOURCE
    
    Call with master:
      # vanilla (runs gaussian model)
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # norm+submit
      master -m $(get_module_nr $(basename ${0})) -s 01 --norm -j 25 --sge
    
      # use l-bgfs for all stages
      master -m $(get_module_nr $(basename ${0})) -s 01 --norm -j 25 --sge --bgfs
    
      # refit existing parameters
      master -m $(get_module_nr $(basename ${0})) -s 01 --norm -j 25 --sge --refit

spinoza_fmriprep_
====================================================================================================

.. code-block:: none

    spinoza_fmriprep
    
    preprocess structural and functional data with fMRIprep. It uses the singularity container in de-
    fined in the FPREP_SIMG-variable in the setup file. You can also run fmriprep through a docker
    image, in which case 'fmriprep-docker' needs to be installed. To run fmriprep through docker,
    specify the '--docker' flag when running this module (e.g., 'master -m 15 --func --docker'). If we
    do not have access to singularity or docker, we can run fmriprep through the BIDSApp.
    
    By default, this runs the anatomical pipeline only. This is to optimize the surface reconstruction
    first before injecting the functional data. The anatomical file can be in several places, which
    will be assessed hierarchically with 'find_hierarchical_anatomy' function in call_bashhelper.
    We'll look consecutively in:
      - DIR_DATA_DERIV/masked_mp2rage (output from master -m 13   [spinoza_masking])
      - DIR_DATA_DERIV/cat12          (output from master -m 09   [spinoza_brainextraction])
      - DIR_DATA_DERIV/denoised       (output from master -m 08   [spinoza_biassanlm])
      - DIR_DATA_DERIV/pymp2rage      (output from master -m 04   [spinoza_qmrimaps])
      - DIR_DATA_HOME (standard BIDS) (output from master -m 02a  [spinoza_scanner2bids])
    
    If you have a T2-weighted image as well, you can specify the root directory to that image. If it
    exists, we will copy it to the directory where the T1-weighted is located (<input directory>) so
    that it is included by fMRIprep.
    
    Usage:
      spinoza_fmriprep [arguments] [options] <anat dir> <derivatives folder> <mode> <T2 dir>
    
    Arguments:
      -a <keep>       if you're running fMRIprep with MNI152* as output space, you're creating massive
                      files; oftentimes, you're mostly interested in the registration matrices, so by
                      default I'll remove the output nifti's so that the folder is not clogged. With
                      this argument you can specify which runs to keep. Again, if not specified, all
                      nifti-files with space-MNI152*.nii.gz will be removed. The transformation matri-
                      ces will be left alone. Use '-a all' to keep all runs (not recommended..)
      -f <func dir>   directory containing functional data; used after running FreeSurfer outside of
                      fMRIprep <optional>
      -j <cpus>       number of cores to use (default is 1)
      -k <kwargs>     specify a file with additional arguments, similar to FreeSurfer's expert options.
                      See fmriproc/misc/fprep_options for an example. Please make sure you have a
                      final empty white space at the end of the file, otherwise the parser gets confu-
                      sed. For VSCode: https://stackoverflow.com/a/44704969. If you run with master,
                      the  '-u' flag maps onto this
      -n <session>    session ID (e.g., 1, 2, or none); used to check for T1w-image. fMRIprep will do
                      all sessions it finds in the project root regardless of this argument. Use the
                      bids filter file ('-k' flag) if you want fMRIPrep to to specific sessions/tasks/
                      acquisitions.
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -r <runs>       re-)run specific runs by removing existing single_subject_<subj_id>_wf/
                      func_preproc_ses_1_*_run_<run_id>_*_wf folders. This should re-use the existing
                      files for other runs, but re-run completely the requested runs
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -t <task>       By default, the pipeline is setup to run fMRIPrep with '--anat-only'. You can in-
                      ject functional data with the '-t' flag; if you want ALL your tasks to be
                      included, use '-t func'. If you have a specific task that needs to be processed
                      (in case another task is already done), use '-t <task_id>'.
      -u <config>     configuration file as specified in /misc/fmriprep_config?.json
      -w <workdir>    custom working directory; defaults to PATH_HOME/fmriprep/<PROJECT>
    
    Options:
      -h|--help       print this help text
      -o|--ow         only removes folders within single_subj workflow with "run-". If specific runs
                      are requested with '-r', only these folders will be removed
      --clean         remove the single-subject workflow folder completely. This saves storage, but
                      comes at the price that it re-runs EVERYTHING if you restart the process.
      --docker        run fmriprep through docker image (requires 'fmriprep-docker' to be installed!)
                      docker is not compatible with separate input folders for 'anat' and 'func', so
                      the input folder will be set to DIR_DATA_HOME by default. The T1w that is
                      present in the anat'-folder will be used as input.
      --fd            only fetch framewise displacement files
      --fetch-anat    retrieve the nifti-files in T1w-space
      --fetch-fsl     retrieve the MNI-transformed nifti-files (which are cleaned by default)
      --fetch-func    retrieve the nifti-files in func-space
      --func          same as '-t func'
      --sge           submit to SGE, if present.
      --masks         used in combination with '--fetch-{fsl|func|anat}' to also fetch the brain masks
                      associated with the timeseries files
      --no-bbr        maps to '--force-no-bbr' in call_fmriprep
      --no-boldref    don't create new boldref images (mean over time) after fMRIprep has finished.
      --remove-surf-wf  Remove surface reconstruction workflow folder; refreshes the surfaces used for
                      registration and transformation
      --remove-wf     remove full single_subject workflow folder. Use \"--remove-surf-wf\" to
                      specifically remove the surface reconstruction folder when you have new
                      FreeSurfer output that fMRIPrep needs to use, or "--ow" to remove all folders
                      within single_subj workflow with "run-"
      --warp-only     skips fMRIPrep, but creates new boldref images (if '--no-boldref' is not
                      specified) and copies the bold-to-T1w warps to the subject's output folder
    
    Positional:
      <anat dir>      directory containing the anatomical data. Can also be the regular project root
                      folder if you want fMRIprep do the surface reconstruction
      <derivatives>   output folder for fMRIprep; generally this will be \$DIR_DATA_DERIV
      <mode>          run anatomical workflow only with 'anat', or everything with 'func'
      <T2 dir>        if you have a T2w-file, but that is not in <anat dir> (because you preprocessed
                      the T1w-file, but not the T2w-file), you can specify the directory where it lives
                      here. Generally this will be the same as <func dir>
    
    Example:
      spinoza_fmriprep \$DIR_DATA_DERIV/masked_mp2rage \$DIR_DATA_DERIV \$DIR_DATA_HOME
      spinoza_fmriprep \\
        -s 001 \\
        -n 1 \\
        -f \$DIR_DATA_HOME \\
        \$DIR_DATA_DERIV/masked_mp2rage \$DIR_DATA_DERIV \$DIR_DATA_HOME
    
    Call with master:
      # vanilla (runs --anat-only)
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # include FUNC & run via master with singularity and 15 cores
      master -m $(get_module_nr $(basename ${0})) -s 01 --func -j 15 --sge
    
      # run via master with docker
      master -m $(get_module_nr $(basename ${0})) -s 01 --func --docker
    
      # remove single subject workflow folder
      master -m $(get_module_nr $(basename ${0})) -s 01 --func -j 15 --sge --remove-wf
    
      # remove surface workflow folder
      master -m $(get_module_nr $(basename ${0})) -s 01 --func -j 15 --sge --remove-surf-wf

spinoza_freesurfer_
====================================================================================================

.. code-block:: none

    spinoza_freesurfer
    
    Surface parcellation with FreeSurfer. We only need to specify where to look for the T1w-image which
    stage we should run (default is 'all'), and where to look for a T2w-image if there is one.
    
    Usage:
      spinoza_freesurfer [arguments] [options] <directory with anats> <stage> <T2-directory>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or n)
      -e <start>      start stage (maps to '-r' from 'call_freesurfer'). Must be one of 'pial',
                      cp', or 'wm' if <freesurfer stage> != 'all'
      -j <cpus>       number of cores to use (default is 2). As we parallellize over hemispheres
                      by default, the number of cores is divided by 2.
      -x <file>       use expert file
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -k <kwargs>     Extra arguments that will be directly passed to 'recon-all'. The format should
                      be as follows: different parameters comma-separated, and parameter-value pair
                      separated by '='):
    
                        "-x <parameter1>=<value1>,<parameter2>=<value2>,<parameterX>=<valueX>"
    
                      E.g.,:
                        "-k -mail,-deface"
    Options:
      -h|--help       print this help text
      -o|--ow         overwrite existing files
      --force-exec    Force execution even though directory exists already
      --local         Force local processing even though cluster is available
      --no-highres    Turn of highres mode by setting '-highres' flag empty
      --no-t2         Do not reuse T2 with autorecon3. Must be used in concert with '-e' and
                      '-r'. By default, we'll re-use the T2 if present. Same flag should be
                      used for not re-using FLAIR images
      --sge           Submit the script to a cluster using a template script
      --xopts-use     maps to '-xopts-use' for existing expert option file; use existing file
      --xopts-clean   maps to '-xopts-clean' for existing expert option file; delete existing file
      --xopts-overwrite maps to '-xopts-overwrite' for existing expert option file; use new file
    
    Positional arguments:
      <anat folder>   folder containing the T1w-file. In 'master', we'll look through various fol-
                      ders. In order of priority:
                        -'\$DIR_DATA_DERIV/masked_\${DATA_LWR}'
                        -'\$DIR_DATA_DERIV/denoised'
                        -'\$DIR_DATA_DERIV/pymp2rage'
                        -'\$DIR_DATA_HOME'
                      this ensures a level of agnosticity about anatomical preprocessing. I.e., you
                      don't have to run the full pipeline if you don't want to.
      <stage>         stage to run for FreeSurfer. By default 'all'
      <T2-folder>     if specified, we'll look for a '*T2w.nii.gz' or '*FLAIR.nii.gz' image to add
                      to the FreeSurfer reconstruction.
    
    General approach for segmentation:
      - Run autorecon1:   call_freesurfer -s <subj ID> -t <T1> -p <T2> -r 1)      ~an hour
      - Fix skullstrip:   call_freesurfer -s <subj ID> -o gcut                    ~10 minutes
      - Run autorecon2:   call_freesurfer -s <subj ID> -r 2                       ~few hours
      - Fix errors with:
        - norm; then run:
          # control points
          call_freesurfer -s sub-001 -r 23 -e cp
        - pia;  then run:
          # pial edits
          call_freesurfer -s sub-001 -r 23 -e pial
    
    You can specify in which directory to look for anatomical scans in the first argument. Usually,
    this is one of the following options: DIR_DATA_HOME if we should use the T1w in the project/
    sub-xxx/anat directory, or \$DIR_DATA_DERIV/pymp2rage to use T1w-images derived from
    pymp2rage, or \$DIR_DATA_DERIV/masked_mp2rage to use T1w-images where the dura and sagittal sinus
    are masked out (should be default!). In any case, it assumes that the file is in YOURINPUT/
    sub-xxx/ses-1/. If the input is equal to the \$DIR_DATA_HOME variable, this will
    be recognize and 'anat' will be appended to YOURINPUT/sub-xxx/ses-1/anat.
    
    You can also specify a directory where the T2-weighted image is located. Do this the same way as
    described above. To you path, sub-xxx/ses-x will be appended if the input path is
    not equal to \$DIR_DATA_HOME. Again, if it is, sub-xxx/ses-x/anat will be appended
    as well.
    
    Example:
      spinoza_freesurfer \$DIR_DATA_DERIV/masked_mp2rage "all" \$DIR_DATA_HOME
      spinoza_freesurfer -s 001 -n 1 \$DIR_DATA_HOME "all" \$DIR_DATA_HOME
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # submit
      master -m $(get_module_nr $(basename ${0})) -s 01 -j 15 --sge
    
      # exclude T2 if present but you don't want to use it (e.g., it is a slab)
      master -m $(get_module_nr $(basename ${0})) -s 01 --no-t2
    
      # turn off highres-mode
      master -m $(get_module_nr $(basename ${0})) -s 01 --func -j 15 --sge --no-highres
    
    Notes:
      When an expert options is passed, it will be copied to scripts/expert-options. Future calls to
      recon-all, the user MUST explicitly specify how to treat this file. Options are:
        (1) use the file ('--xopts-use')
        (2) delete it ('--xopts-clean'). If this file exsts and the user specifies another expert
            options file, then the user must also specify '--xopts-overwrite'.

spinoza_gdhpipeline_
====================================================================================================

.. code-block:: none

    spinoza_gdhpipeline
    
    this script contains the pipeline that mimics G. de Hollander's pipeline, wherein manual segmenta-
    tion are injected into fmriprep and MGDM to optimize the cortical reconstruction with FreeSurfer
    and CRUISE. It is run after completion of region extraction (spinoza_extractregions).
    
    It will open windows to view the reconstruction and the segmentation, after which user input is re-
    quired: if you're happy, it will run the remaining modules for cortical reconstruction using the
    same command as specified in the master script for that particular module. If you're not happy, you
    can make your edits to the files, save the files with a particular name, and re-run the pipeline
    with the following modules: fmriprep (spinoza_fmriprep > removes surface_recon_wf-directory first),
    skullstripping (spinoza_masking), and MGDM-tissue classification (spinoza_segmentmgdm). It will
    then open the window again to check the changes in reconstruction/classfication. That concludes the
    loop.
    
    The following arguments can be specified, but by default the script will read the variables from the
    spinoza_setup file, so if you have not changed any of the paths, you'll only need to specify the sub
    ID.
    
    Arguments:
      -s <subject ID>   subject ID
      -a <anat>         directory with skullstripped T1w & T1map images (default = 'skullstripped').
                        Files should be suffixed with "skullstrip_<T1w|T1map>", otherwise call_gdhmgdm
                        will fail
      -n <session nr>   session number (default is '1', specify 'n' for no session)
      -c <nighres dir>  root directory with MGDM-output (until <subject ID>)
      -t <prob seg dir> root directory with levelsets-output (until <subject ID>)
      -f <fmriprep dir> root directory with fmriprep-output (until <subject ID>). This flag also lets
                        you control whether you want to run or skip fMRIprep. Leave empty or specify
                        a directory to run it, enter '-f n' if want to go to fMRIprep directly. This
                        can be useful if you've encountered an error after you ran fMRIprep and don't
                        want to run it again.
      -r <freesurfer>   root directory with freesurfer-output (until <subject ID>). This flag also lets
                        you control whether you want to run or skip FreeSurfer. Leave empty or specify
                        a directory to run it, enter '-r n' if want to go to fMRIprep directly. This
                        can be useful if you've encountered an error after you ran FreeSurfer and don't
                        want to run it again.
      -m <mask dir>     root directory with the masks (until <subject ID>)
      -w <wf dir>       directory containing the fmriprep workflow folders
      -p <stage>        freesurfer stage to start off from (e.g., 'pial', 'wm' | default = 'wm')
      -i <inject>       inject manual edits in FreeSurfer (y|n; default="y", but can be set to 'n' if
                        you did manual edits to brainmask.mgz)
      -q <fprep type>   if you only want to run anatomical workflows again, enter '-q anat'. If you
                        also want to include functional, enter '-q func'. The latter is default for
                        most projects
      -y <run MGDM>     run MGDM after fMRIprep. Default = 'y', but can be turned of by specifying '-y
                        n'.
      -z <post MGDM>    after MGDM, we normally re-run denoising/pRF and later Nighres modules. If we
                        don't want this, specify 'n' (default = yes!)
    
    Usage:
      spinoza_gdhpipeline -s <sub ID> -t <mgdm dir> -f <fprep dir> -r <fs dir> -m <mask dir> -w <wf dir>
    
    Example:
      spinoza_gdhpipeline -s ${SUBJECT_PREFIX}001
      spinoza_gdhpipeline -s ${SUBJECT_PREFIX}001 -t /path/to/mdgm -p pial -i n (don't overwrite brainmask)
      spinoza_gdhpipeline -s ${SUBJECT_PREFIX}001 -r n -f n (skip FreeSurfer & fMRIprep)
      spinoza_gdhpipeline -s ${SUBJECT_PREFIX}001 -r n -f n -z n (run call_gdhmgdm only)
      spinoza_gdhpipeline -s ${SUBJECT_PREFIX}001 -f n -z n -y n (only inject manual edits and re-run FreeSurfer)

spinoza_install_
====================================================================================================

.. code-block:: none

    spinoza_install
    
    This script configures the fMRIproc repository environment by:
    
    - Adding 'spinoza_setup' sourcing to ~/.bash_profile (or ~/.zshrc if using Zsh)
    - Ensuring the correct path to the user's personal 'spinoza_config' is registered
    - Optionally adding 'conda activate <env>' to ~/.bash_profile if requested
    
    Usage:
      spinoza_install setup [add_conda] [config_path]
      spinoza_install help
    
    Options:
      no-conda        Do not add currently active conda environment to ~/.bash_profile (or ~/.zshrc).
                      Beware that the correct environment must be loaded for the scripts to be
                      available
      config_path     Path to a custom 'spinoza_config' file. If not provided, the default will be used.
    
    Examples:
      spinoza_install setup
      spinoza_install setup no-conda /home/user/my_spinoza_config
      spinoza_install help

spinoza_layering_
====================================================================================================

.. code-block:: none

    spinoza_layering
    
    Equivolumetric layering with either nighres or Wagstyl's surface_tools, as specified by the third
    argument. Surface_tools is based on FreeSurfer, so make sure that has run before it. This script is
    by default in overwrite mode, meaning that the files created earlier will be overwritten when
    re-ran. This doesn't take too long, so it doesn't really matter and prevents the need for an
    overwrite switch. To disable, you can specify a condition before running this particular script.
    
    Usage:
      spinoza_layering [arguments] [options] <input dir> <software>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -l <nr_layers>  number of layers to estimate (defaults: nighres=10; FreeSurfer=5)
      -x <kwargs>     Additional commands to be passed to 'volumetric_layering'. Format should
                      be comma-separated flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      This allows bash commands to be translated to python commands
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
    
    Positional:
      <input folder>  if software == 'nighres', then we need the nighres output folder (generally
                      \$DIR_DATA_DERIV/nighres). If software == 'freesurfer', then we need the \$SUB-
                      JECTS_DIR
      <software>      Possible inputs for software are:
                        - 'nighres': voxel-based layering [default]
                        - 'surface': surface-based layering with Wagstyl's method
    
    Example:
      spinoza_layering \$SUBJECTS_DIR surface
      spinoza_layering \$DIR_DATA_DERIV/nighres nighres
    
    Call with master:
      # vanilla (runs nighres)
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # use 20 depths
      master -m $(get_module_nr $(basename ${0})) -s 01 -l 20
    
      # layering kwargs
      master -m $(get_module_nr $(basename ${0})) -s 01 -x n_layers=20,layer_dir='inward'
    
      # run surface-based layering
      master -m $(get_module_nr $(basename ${0})) -s 01 --surface
    
    Notes:
      - The script will recognize any of the software inputs specified above, with these variations in
        capitalization.
      - The script will look for a surface_tools installation on the PATH and if it can't find it
        there, it will look for the first match in the HOME directory. To be sure, place the script
        either in the home directory or place it on the PATH.
      - If the script doesn't give an error before printing the starting time, it means it found the
        script.

spinoza_line2surface_
====================================================================================================

.. code-block:: none

    spinoza_line2surface
    
    This script contains the registration cascade from single slice/line > multi-slice (9 slice) > low
    resolution MP2RAGE from session 2 > high resolution MP2RAGE from session 1 > FreeSurfer anatomy.
    In spinoza_lineplanning, we have created a matrix mapping the low resolution anatomy to the high
    resolution anatomy from session 1. Because the single- and multislice images are basically in the
    same space (header-wise) as the low resolution anatomical scan, we can just apply this matrix to
    the single- and multi-slice. We then have everything in the space of the high resolution anatomy
    from session 1.
    
    Now we need a matrix mapping the high resolution anatomical scan from session 1 with the FreeSurfer
    anatomy. For this, we can use FreeSurfer's bbregister, which registers an input image to orig.mgz.
    We can transform both matrices to FSL-format, so we can create a composite transformation matrix
    that we can apply to everything from session 2 with flirt. Because we need all these transformed
    files for pycortex, we will try to store all the files in the pycortex directory, but you can
    specify this yourself (default is the pycortex directory).
    
    Easiest thing to do is run the "segmentation.ipynb" notebook to warp all segmentations to session
    1, then everything - HOP - to FreeSurfer and Pycortex space using the matrix created with spinoza_
    lineplanning (this matrix you should definitely have..).
    
    Usage:
      spinoza_line2surface -s <subject number> -y <anat session 2> -o <outputdir> -i <input dir>
    
    Arguments:
      -s <sub number> number of subject's FreeSurfer directory
      -y <anat ses 2> anatomical image from session 2 as outputted by spinoza_lineplanning
      -o <output dir> default is bids_root/derivatives/pycortex (easiest to set this to default other
                      make it the same as Pycortex' filestore) [<sub> will be appended]
      -i <warp dir>   input directory that we need to warp to the surface; I'm assuming a structure
                      like "<input dir>/<sub>/ses-2"
    
    Options:
      -h|--help       print this help text
    
    Example:
      spinoza_line2surface \\
        -s sub-01 \\
        -y \$DIR_DATA_HOME/sub-01/ses-2/anat/sub-01_ses-2_acq-MP2RAGE_T1w.nii.gz \\
        -o \$DIR_DATA_DERIV/pycortex \\
        -i \${NIGHRES/sub-01/ses-2
    
    Call with master:
      # vanilla (defaults to ses-2 for line-scanning)
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # set session to 3
      master -m $(get_module_nr $(basename ${0})) -s 01 -l 3

spinoza_lineplanning_
====================================================================================================

.. code-block:: none

    spinoza_lineplanning
    
    This is the main planning script that will print the translation and rotation values that should be
    entered in the MR console during a line-scanning session (ses-X). Prior to running this script, you
    should have generated a *desc-coords.csv-file with 'spinoza_bestvertex' [module 18]. This informa-
    tion is in "ses-1" space, so we need to translate this to the currently active session. We do so by
    acquiring a quick whole-brain anatomical scan. In case of surface coils, we use the 2 channels used
    for transmission also for receiving of the signal, allowing whole-brain coverage at a lower resolu-
    tion. In case of regular coils, we can acquire fast 3D T1-weighted scans. In any case, this script
    expects the PAR/RECs of these acquisitions to be placed in:
    
      \$DIR_DATA_SOURCE/<sub>/ses-<ses>/planning
    
      That should look like this:
      sourcedata/sub-022/ses-2/planning
      ├── sub-01_ses-2_WIP_-_MP2RAGE_2_4.PAR
      └── sub-01_ses-2_WIP_-_MP2RAGE_2_4.REC
    
    In this case, the acquisition was an MP2RAGE, so we can look for a trigger delay in the file:
    
      anat_session2=\$(
        find "\$DIR_DATA_SOURCE/<sub>/ses-<ses>/planning" \\
          -type f \\
          -name "*t\${ttime}*" \\
          -and -name "*.nii.gz" \\
          2>/dev/null
      )
    
    In any other case, we will look for these tags in the folder with converted files:
    
      anat_session2=\$(
        find "\$DIR_DATA_SOURCE/<sub>/ses-<ses>/planning \\
          -type f \\
          -name "*3DFFE*" \\
          -and -name "*.nii.gz" \\
          2>/dev/null
      )
    
    So make sure you sequence naming conforms to one of these schemes!
    
    These files will then be converted to nifti using 'call_dcm2niix' and registered to the FreeSurfer
    anatomy of that subject (orig.mgz). However, the coordinates are in "pycortex" space. Pycortex has
    an extra offset relative to FreeSurfer coordinates (see 'call_ctxsurfmove'). Internally, we will
    apply all these corrections and it also ensures the final angles are co-planar. This means that the
    angles with the x-/and y-axis of the magnet are calculated after correcting for the angle with the
    z-axis. If you do not apply this correction, you'll end up with slight inaccuracies, resulting in
    your line not being perpendicular to the cortex.
    
    The final output will look something like this:
    
      ENTER THE FOLLOWING VALUES IN THE MR-CONSOLE
    
      set orientation to coronal and foldover to FH
      FH: 18.69 deg
      AP: 37.14 deg
      RL: 0 deg
    
      set translation to:
      AP: 104.74 mm
      RL: 19.75 mm
      FH: -20.92 mm
      Targeted hemisphere: left
      Vertex number:       968
      Isocenter RAS:       [ -19.7527 -104.742   -20.923 ]
      Isocenter LPS:       [ 19.7527 104.742  -20.923 ]
    
    These values are to be entered in the console in the exact order as they are printed. This is be-
    cause angles will affect one another, so first the FH>AP>RL. As you really only need two angles to
    get the correct orientation, either AP or RL is set to 0, depending on what the orientation is. The
    target vertex' number is printed so you can compare the location live using FreeView on your local
    system.
    
    Usage:
      spinoza_lineplanning [options] [mandatory]
    
    Mandatory:
      -s <subject>    subject ID (e.g., sub-01)
      -n <session>    line-scanning session ID (>1)
      -i <anat>       path to PAR/RECs of anatomical file in line-scanning session. Typically, this is
                      \$DIR_DATA_SOURCE/<sub>/ses-<ses>/planning. Can also be a path directly pointing
                      to a nifti file for more custom inputs.
      -p <coords>     csv-file containing the coordinates/normal vectors indexed by hemisphere. This
                      is typically the output of 'spinoza_bestvertex'
                      E.g., "\${DIR_DATA_DERIV}/pycortex/<sub>/ses-<session/
                      <sub>_ses-<ses>_desc-coords.csv"
    
    Options:
      -h|--help       print this help text
      --lh            consider the left hemisphere for the line-scanning session [default due to better
                      signal homogeneity at this location of the coils]
      --rh            consider the right hemisphere for the line-scanning session
      --ident(ity)    debugging mode: sets the transformation matrix to the identity matrix so we can
                      verify if the workflow runs as planned.
    
    Example:
      # standard
      spinoza_lineplanning \\
        -s sub-001 \\
        -n 3 \\
        -i /path/to/raw/ses-2 \\
        -p /path/to/pycortex_file.csv \\
        --lh
    
      # specify custom input
        spinoza_lineplanning \\
        -s sub-01
        -n 2
        -i "/path/to/a/nifti_file.nii.gz"
        -p "\$DIR_DATA_DERIV/pycortex/sub-01/ses-2/sub-01_ses-2_desc-coords.csv"
    
      # test workflow
      spinoza_lineplanning \\
        -s sub-001 \\
        -n 1 \\
        -p /path/to/pycortex_file.csv \\
        --identity
    
    Notes:
      - You NEED ANTs for this to run
      - It also depends on python3; if something doesn't seem to work, try to update the package
        with python -m pip install <package> --upgrade
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01 -n 2 --lh
    
      # use session 3
      master -m $(get_module_nr $(basename ${0})) -s 001 -n 3 --lh # though --lh is default
    
      # use session 1 (uses identity matrix) for debugging purposes
      master -m $(get_module_nr $(basename ${0})) -s 001 --rh --identity

spinoza_linerecon_
====================================================================================================

.. code-block:: none

    spinoza_linerecon
    
    wrapper for call_linerecon that performs the reconstruction of the line data. Uses MRecon, so we
    can only run it on the spinoza cluster. It calls upon call_linerecon, which internally uses a
    template for the reconstruction with MRecon based on scripts provided by Luisa Raimondo.
    
    Usage:
      spinoza_linerecon [arguments] [options] <project root directory> <sourcedata>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or n)
      -m <n_echoes>   number of echoes in the acquisition (e.g., 5); by default we try to read it
                      from the PAR-file (field 'number of echoes')
      -r <runIDs>     specific runs to preproces; can be comma-separated list
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -c <comps>      percentage of components to remove using NORDIC (default is to use scree
                      plot to remove appropriae number of components)
      -f <suffix>     add custom suffix; overwrites default of "bold"
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --debug         don't submit job, just print inputs/outputs
      --no-nordic     turn off NORDIC denoising during reconstruction
      --sge           submit job to cluster (SoGE/SLURM)
    
    Positional:
      <project root>  base directory containing the derivatives and the subject's folders.
      <sourcedata>    base directory containing the raw data for reconstruction
    
    Example:
      # call the module
      spinoza_linerecon \$DIR_DATA_HOME \$DIR_DATA_SOURCE
    
    Call with master:
      # sub-01, ses-4, multi-echo (5) acquisition
      master -m $(get_module_nr $(basename ${0})) -s 01 -n 4 -e 5
    
      # sub-01, ses-4, single-echo acquisition
      master -m $(get_module_nr $(basename ${0})) -s 01 -n 4
    
      # submit to cluster
      master -m $(get_module_nr $(basename ${0})) -s --sge
    
      # turn off nordic (in case of surface coils)
      master -m $(get_module_nr $(basename ${0})) -s --sge --no-nordic
    
      # debug mode
      master -m $(get_module_nr $(basename ${0})) -s 01 --debug
    
    Notes:
      Runs by default NORDIC denoising, might be problematic with surface coils as the noise distri-
      bution is not uniform.

spinoza_lsprep_
====================================================================================================

.. code-block:: none

    spinoza_lsprep
    
    wrapper for call_lsprep that performs the reconstruction of the line data. Uses MRecon, so we can
    only run it on the spinoza cluster. It calls upon call_lsprep, which internally uses a template
    for the reconstruction with MRecon based on scripts provided by Luisa Raimondo.
    
    Usage:
      spinoza_lsprep [arguments] [options] <project root directory> <sourcedata>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., "2,3" or "3"). Defaults to '2'; specify multiple
                      sessions in a comma-separated list: "2,3,4"
      -j <n_cpus>     number of CPUs to use (default = 1)
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -x <kwargs>     Additional commands to be passed to 'call_lsprep'. Format should be comma-
                      separated flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      This allows bash commands to be translated to python commands
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      -c|--sge        submit job to cluster (SGE/SLURM)
    
    Positional:
      <project root>  base directory containing the derivatives and the subject's folders.
      <derivatives>   base directory to store the 'lsprep'-folder in
    
    Eample:
      spinoza_lsprep -s 01 -n 3 --sge \$DIR_DATA_SOURCE \$DIR_DATA_DERIV
      spinoza_lsprep -s 01 -n 3 -x --filter-pca=0.18,--verbose \$DIR_DATA_SOURCE \$DIR_DATA_DERIV
    
    Call with master:
      # use all defaults from call_lsprep
      master -m $(get_module_nr $(basename ${0})) -s 01 -n 3
    
      # use kwargs
      master -m $(get_module_nr $(basename ${0})) \\
        -s 01 \\
        -n 3 \\
        -x --filter-pca=0.18,--verbose,--no-button,--ow,--ica
    
      # submit to cluster+kwargs
      master -m $(get_module_nr $(basename ${0})) \\
        -s 01 \\
        -n 3 \\
        --sge \\
        -x --filter-pca=0.18,--verbose,--ica

spinoza_masking_
====================================================================================================

.. code-block:: none

    spinoza_masking
    
    Mask out the dura and skull from the T1-image to reduce noise. It follow Gilles' masking procedure,
    by setting the contents of dura ('outside') and other masks ('inside') to zero. The idea is to run
    this, run fMRIprep, check segmentations, manually edit it as "\<subject>_ses-1_acq-
    MP2RAGE_desc-manualwmseg" or something alike. These 'manualseg' will be taken as 'inside' to boost
    areas that were not counted as brain.
    
    Usage:
      spinoza_masking [arguments] [options] <anat dir> <output dir> <mask dir> <skullstrip dir>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -l <lower>      lower percentile (default = 0.01) for call_winsorize
      -u <upper>      upper percentile (default = 0.95) for call_winsorize. NOTE this is more ex-
                      treme than the default for call_winsorize.
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --no-manual     do not do any further manual editing; just combine all masks and apply
    
    Positional:
      <anat dir>      parent directory containing the sub-xxx folders for anatomies
      <output skull>  output folder for masked T1w-image (with skull)
      <mask dir>      folder containing a bunch of masks from previous modules. Should contains files
                      ending on;
                        -dura:   \"*dura_dil.nii.gz\", \"*cat_dura.nii.gz\", or \"*dura_orig.nii.gz\"
                        -brain:  \"*cat_mask.nii.gz\" or \"*gdh_mask.nii.gz\"
                        -inv2:   \"*spm_mask.nii.gz\"
                        -sinus:  \"*sinus\"
      <skullstr.>     output folder for brain-extracted output (generally the input for Nighres)
    
    Example:
      spinoza_masking \\
        \$DIR_DATA_DERIV/pymp2rage \\
        \$DIR_DATA_DERIV/masked_mp2rage \\
        \$DIR_DATA_DERIV/manual_masks \\
        \$DIR_DATA_DERIV/skullstripped
    
      spinoza_masking \\
        -s 01 \\
        -n 1 \\
        \$DIR_DATA_DERIV/pymp2rage \\
        \$DIR_DATA_DERIV/masked_mp2rage \\
        \$DIR_DATA_DERIV/manual_masks \\
        \$DIR_DATA_DERIV/skullstripped
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # skip ITK-snap
      master -m $(get_module_nr $(basename ${0})) -s 01 --no-manual
    
      # specify lower/upper bound for call_winsorize
      master -m $(get_module_nr $(basename ${0})) -s 01 --no-manual -l 0.05 -u 0.95

spinoza_mgdm_
====================================================================================================

.. code-block:: none

    spinoza_mgdm
    
    Tissue segmentation using nighres' MGDM. It assumes that you've run module from this pipeline
    before, so that you're directory structure is like derivatives/<process>/<subject>/ses-x. For this
    script, you need to give the path to the skullstripped directory up until <subject>, the output
    mgdm directory, and the directory containing masks that are used to filter out stuff in the MGDM
    segmentation.
    
    Usage:
      spinoza_mgdm [arguments] [options] <skullstripped> <mgdm> <masks>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -j <n_cpus>     number of CPUs to use (default = 1)
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in \$CONFIG_FILE.
      -p|--priors     The algorithm accepts 4 input files, each representing a different prior. In any
                      case, we need a T1w and T1map-file, which can come from different sources (e.g.,
                      field strength, atlases, or sequence). These sources include:
                      ['DWIFA3T', 'DWIMD3T', 'T1map9T', 'Mp2rage9T', 'T1map7T', 'Mp2rage7T', 'PV',
                      'Filters', 'T1pv', 'Mprage3T', 'T1map3T', 'Mp2rage3T', 'HCPT1w', 'HCPT2w',
                      'NormMPRAGE'].
    
                      For each input file, one of these sources must be specified. By default, the
                      priors are set to:
    
                      prior_list = [
                        "Mp2rage7T",
                        "T1map7T",
                        "Filters",
                        "Filters"
                      ]
    
                      where:
                        - T1w-file (-t|--t1w) comes from a 7T MP2RAGE sequence
                        - T1map-file (-m|--t1map) comes from a 7T MP2RAGE sequence
                        - Mask representing the skull (-s|--skull) is a "Filters"
                        - Mask representing the dura (-d|--dura) is a "Filters"
    
                      Format should be comma-separated list for the number of inputs used. For the
                      regular version, this means 4 (T1w, T1map, skull, and dura). For GdH-version,
                      this means 2 (T1w, T1map):
    
                        E.g., "-p Mprage3T,T1map3T,Filters,Filters"
    
      -x <kwargs>     Additional commands to be passed to 'mdgm_segmentation'. Format should be comma-
                      separated flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      This allows bash commands to be translated to python commands
    
    Options:
      -h|--help       print this help text
      -o|--ow         overwrite existing files
      --gdh           run GdH-pipeline version (call_gdhmgdm, default is call_nighresmgdm). This ver-
                      sion uses input from fMRIPrep and FreeSurfer as inputs for MGDM.
      --sge           submit job to cluster (SGE)
    
    Positional:
      <skullstr.>     path to skullstripped data
      <mgdm>          path to output directory
      <masks>         path to masks
    
    Example:
      spinoza_mgdm \$SKULLSTRIP \$NIGHRES/mgdm \$MASKS
      spinoza_mgdm -s 001 -n 1 \$SKULLSTRIP \$NIGHRES/mgdm \$MASKS
      spinoza_mgdm -s 001 -n 1 --gdh \$SKULLSTRIP \$NIGHRES/mgdm \$MASKS
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # run Gilles' version
      master -m $(get_module_nr $(basename ${0})) -s 01 --gdh
    
      # customize priors (default = Mp2rage7T,T1map7T,Filters,Filters)
      master -m $(get_module_nr $(basename ${0})) -s 01 -p Mprage3T,T1map3T,Filters,Filters
    
      # submit and specify kwargs
      master -m $(get_module_nr $(basename ${0})) -s 01 --sge -x diffuse_probabilities=True

spinoza_mriqc_
====================================================================================================

.. code-block:: none

    spinoza_mriqc
    
    Quality control using MRIqc. It uses the singularity container defined in the setup file (variable
    \$MRIQC_SIMG).
    
    Usage:
      spinoza_mriqc [arguments] [options] <project dir> <derivatives>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05. use 'group'
                      if you want group statistics
      -n <session>    session ID (e.g., 1, 2, or none); If set, only data from this session will be
                      used
      -j <cpus>       number of cores to use (default is 1)
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --local         don't submit to SGE, run locally
      --anat-only     only include anatomical images in the process (default is everything it can find)
      --func-only     only include functional images in the process (default is everything it can
                      find)
      --fd            only get FD-timecourse file without initializing MRIqc
    
    Positional:
      <project dir>   directory containing the anatomical data. Can also be the regular project root
                      folder if you want MRIqc do the surface reconstruction
      <derivatives>   output folder for MRIqc; generally this will be \$DIR_DATA_DERIV
    
    Example:
      spinoza_mriqc \$DIR_DATA_DERIV/masked_mp2rage \$DIR_DATA_DERIV anat
      spinoza_mriqc \\
        -s 001 \\
        -n 1 \\
        -f <project> \\
        \$DIR_DATA_DERIV/masked_mp2rage \$DIR_DATA_DERIV anat
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # retrieve Framewise Displacement files after MRIqc
      master -m $(get_module_nr $(basename ${0})) -s 01 --fd

spinoza_nordic_
====================================================================================================

.. code-block:: none

    spinoza_nordic
    
    Run NORDIC denoising on whole-brain functional data. Expects a BIDS-like folder structure with the
    magnitude data in 'func' and the phase data in 'phase'. If phase data is not present, we'll attempt
    a magnitude-only NORDIC process. If NORDIC is being run, we'll copy the 'func'-folder as 'no-
    nordic'-folder to denote that not preprocessing has taken place, while keeping the data close. The
    NORDIC'ed data will be placed in 'func', without any special tags to avoid that fMRIPrep gets
    confused. However, it's likely you've produced the phase output with 'spinoza_scanner2bids', in
    which case the files will be named properly. Thus, the folder structure is expected to be like:
    
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
      spinoza_nordic [arguments] [options] <bids folder>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none
      -r <run>        run ID (e.g., 1). Can also be comma-separated list: 1,3,4
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
    
    Options:
      -h|--help       print this help text
      -o|--ow         overwrite existing files even if "Nordic"-field is populated in json file
      --sge           submit individual NORDIC processes to the cluster for parallellization. If you
                      do this, it's advised to have identifiable 'run-' flags in your filenames so
                      that the template file is not overwritten; this can cause problems. If you do
                      not have run identifiers in your filenames, please run serially. This flag is
                      inherited from 'master', so calling it there will pass on the flag here.
      --mag           use magnitude only
      --no-tsnr       skip tSNR maps before/after NORDIC
    
    Positional:
      <bids folder> parent directory containing the sub-xxx folders for functional data. Generally,
                    this should be \$DIR_DATA_HOME
    
    Example:
      # run for all subjects
      spinoza_nordic \$DIR_DATA_HOME
    
      # run for specific subject/session
      spinoza_nordic -s 001 -n 1 \$DIR_DATA_HOME
    
      # submit to cluster
      spinoza_nordic --sge DIR_DATA_HOME
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0}))
    
      # submit
      master -m $(get_module_nr $(basename ${0})) -s 01,02 --sge
    
    Notes:
    - By default, tSNR maps from before/after NORDIC clipped to 100 will be produced and stored in the
      no-nordic folder as '*desc-tSNRpre_bold.nii.gz' and '*desc-tSNRpost_bold.nii.gz'

spinoza_profiling_
====================================================================================================

.. code-block:: none

    spinoza_profiling
    
    Sample the profile values of a particular image using call_nighresprofsamp. Here, we provide the
    boundaries-image from nighres.layering module and have the program sample values from a particular
    dataset (e.g., T1map) across depth. The first argument specifies where the nighres output is, used
    for both the layering and profile sampling. The second argument is the main directory where we will
    find the file the we want to sample. The last argument specifies a tag to look for the to-be-sampled
    file (e.g., T1map)
    
    Usage:
      spinoza_profiling [arguments] [options] <nighres input> <input folder> <extension for to-be-sampled file>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -i <image>      directly specify an image to sample the profile from. This assumes that the
                      image is in the same space as the specified input subjects. Generally, this is
                      not the case, as each subject has a slightly different space. However, in some
                      scenarios, I can see how this could be useful. E.g., with images in MNI space
                      (although I discourage layerifaction in MNI-space) or you only have 1 subject.
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
    
    Positional:
      <nighres>       parent directory containing the output files of Nighres
                        - \$DIR_DATA_DERIV/nighres/<subject>/<session>/layering/*boundaries*
    
                          # logic to find boundaries file (nighres_dir is compiled from input folder,
                          # subject ID and session ID)
                          boundaries=\$(
                            find "\${nighres_dir}/layering" \\
                            -type f \\
                            -name "*acq-\${DATA_UPR}*" \\
                            -and -name "*boundaries.nii.gz"
                          )
      <sample loc.>   directory where the to-be-sampled lives:
                        - If you want to sample T1-values that are reconstructed by the scanner, this
                          is \$DIR_DATA_HOME (output from 'spinoza_scanner2bids' [module $(get_module_nr spinoza_scanner2bids)]).
                        - If this is data from pymp2rage (output from 'spinoza_scanner2bids' [module
                          $(get_module_nr spinoza_qmrimaps)]), this is \$DIR_DATA_DERIV/pymp2rage
      <suffix>        suffix to use to look for to-be-sampled dataset (e.g., T1map)
    
    Example:
      spinoza_profiling \$DIR_DATA_DERIV/nighres \$DIR_DATA_HOME T1map
      spinoza_profiling -s 01 -n 2 \$DIR_DATA_DERIV/nighres \$DIR_DATA_DERIV/pymp2rage T1map
    
    Call with master:
      # vanilla (defaults to 'T2starmap')
      master -m $(get_module_nr $(basename ${0}))
    
      # use -x flag to change suffix
      master -m $(get_module_nr $(basename ${0})) -x T1map
    
      # directly specify image
      master -m $(get_module_nr $(basename ${0})) -i some_image_space-MNI152NLin6Asym_T1map.nii.gz

spinoza_qmrimaps_
====================================================================================================

.. code-block:: none

    spinoza_qmrimaps
    
    wrapper for estimation of T1 and other parametric maps from the (ME)MP2RAGE sequences by throwing
    the two inversion and phase images in Pymp2rage (https://github.com/Gilles86/pymp2rage).
    
    Usage:
      spinoza_qmrimaps [arguments] [options] <project root> <derivatives>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -p <pars file>  specify custom json-file with MP2RAGE(ME) parameters. See
                      \$REPO_DIR/misc for examples. Format should be like so (for mp2rage):
    
                        {
                            "TR": 5.5,
                            "inv_times": [0.8,2.7],
                            "fa": [6,6],
                            "nZ": 1000,
                            "FLASH_tr": [0.0062,0.0062]
                        }
    
      -q <queue>      submit jobs to a specific queue. Defaults to \$SGE_QUEUE_SHORT in spinoza_setup
      -l <lower>      lower percentile (default = 0.01) for call_winsorize
      -u <upper>      upper percentile (default = 0.99) for call_winsorize
      -x <kwargs>     Additional commands to be passed to 'N4BiasFieldCorrection'. Format should be
                      comma-separated flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      This allows bash commands to be translated to 'N4BiasFieldCorrection' commands
    
    Options:
      -h|--help       print this help text
      -o|--ow         overwrite existing files (T1w/T1map-files)
      -f|--full       overwrite all existing files (including masks)
      --verbose       echo command to terminal
      --ups           use settings for universal pulse (UP) [parameters are hardcoded]
      --no-reg        do not register separate T1map in case you have MPRAGE image
      --no-winsor     do not winsorize the image intensities of T1w (and T1map) from MPRAGE. Generally
                      recommend doing so, though..
      --spm           use SPM for bias correction instead of ANTs [call_mprage]
      --sge           submit job to cluster (called with 'master -m <module> --sge')
      --skip-bg       Do not create masks from INV2-image to remove noise from MP2RAGE
      --force-exec    Force the execution even if the files exist already
    
    Positional:
      <project root>  directory containing the T1w and T2w files; should generally be pymp2rage-folder
      <derivatives>   path to output mask directory
    
    Example:
      spinoza_qmrimaps \$DIR_DATA_HOME \$DIR_DATA_DERIV/pymp2rage
      spinoza_qmrimaps -s 01 -n 1 \$DIR_DATA_HOME \$DIR_DATA_DERIV/pymp2rage
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0}))
    
      # use UPs and submit
      master -m $(get_module_nr $(basename ${0})) --ups --sge
    
      # custom parameters
      master -m $(get_module_nr $(basename ${0})) -p some_file.json
    
      # specify kwargs
      master -m $(get_module_nr $(basename ${0})) -x -b=[1x1x1,3],-r=0

spinoza_registration_
====================================================================================================

.. code-block:: none

    spinoza_registration
    
    Wrapper for registration with ANTs. This script should be preceded by spinoza_qmri maps. It utili-
    zes the variable ACQ in the setup script to derive what should be registered to what. In theory,
    the first element of ACQ is taken as reference, and the second element will be registered to that.
    If ACQ has only one element and 'MNI' is specified, this first element is registered to the MNI
    template. This step is relatively obsolete given that we don't really need it in MNI space + we
    can do that step with fMRIprep, but can be useful if you need the registration file mapping
    T1w-to-MNI, without warping the actual 4D file to MNI-space (saves disk space).
    
    Scenarios:
      - MP2RAGE+MP2RAGEME [ACQ=("MP2RAGE" "MP2RAGEME")], 1st element is reference ('MP2RAGE'):
    
          # fixed
          The fixed image is the first element of \${ACQ[@]}. In this case, 'MP2RAGE'. We search for
          this file in \${input_dir}, which is given by the input directory to this function (see
          <anat folder>), combined with the subject ID (and session ID if given). Thus, this file
          must contain 'MP2RAGE' and 'T1w.nii.gz' and must be in native space (if the file is
          transformed, it will have a 'space-' tag, this must be absent!).
    
          fixed_file=\$(
            find -L "\${input_dir}" \\
            -type f \\
            -iname "*\${ACQ[0]^^}_*T1w.nii.gz" \\
            -not -name "*space-*"
          )
    
          # moving
          The moving file is the second element of \${ACQ[@]}. In this case, 'MP2RAGEME'. The same
          logic holds for this file.
    
          moving_files=\$(
            find -L "\${input_dir}" \\
            -type f \
            -iname "*\${ACQ[1]^^}_*T1w.nii.gz" \\
            -not -name "*space-*"
          )
    
      - Multiple MPRAGE(s) [ACQ=("MP2RAGE)]; ref should have 'run-1', subsequent files should have
        'run-[2-i]':
    
          # fixed
          If multple MPRAGEs are acquired, they must have a 'run-' identifier and \${ACQ[@]} should
          only contain 'MPRAGE'. In this scenario, 'run-1' will be taken as reference. Therefore, it
          should have 'MPRAGE', 'run-1', and 'T1w.nii.gz' in its filename.
    
          fixed_file=\$(
            find -L "\${input_dir}" \\
            -type f \\
            -iname "*\${ACQ[0]^^}_run-1*T1w.nii.gz" \\
            -not -name "*space-*"
          )
    
          # moving
          The moving files are found based on the same logic, other than a run-identifier greater
          than 1.
    
          moving_files=\$(
            find -L "\${input_dir}" \\
            -type f \\
            -iname "*\${ACQ[0]^^}*run-[2-9]*T1w.nii.gz" \\
            -not -name "*space-*"
          )
    
        - To MNI [acq=("MP2RAGE") | acq=("MP2RAGEME") | acq=("MPRAGE")]:
    
          # fixed
          The fixed file is the 1mm MNI template from FSL (MNI152NLin6Asym).
          fixed_file=\${FSLDIR}/data/standard/MNI152_T1_1mm.nii.gz
    
          # moving
          Moving files are all files containing the first element of \${ACQ[@]}.
    
          moving_files=\$(
            find -L "\${input_dir}" \\
            -type f \\
            -iname "*\${ACQ[0]^^}_*T1w.nii.gz" \\
            -not -name "._*"
          )
    
    Resulting transformation will be applied to files containing the suffixes in \$WARP_2_MP2RAGE-
    variable if the registration does NOT involve the MNI-template!. If nothing is
    specified in the \$CONFIG_FILE, it will be set to:
    
      WARP_2_MP2RAGE=("T1w" "T1map" "R2starmap")
    
    Usage:
      spinoza_registration [arguments] [options] <anat folder> <output folder> <registration type>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -j <cpus>       number of cores to use (default is 1), internally sets the ITK-variable:
                      'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS', which will be reset to 1 after the
                      process
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --affine        use affine-registration (12 parameters)
      --rigid         use rigid-body registration (6 parameters). Default if <registration type>
                      != 'mni' and no registration method is specified
      --syn           use SyN-diffeomorphic registration. Default if <registration type> == 'mni'
                      and no registration method is specified
      --fsl           also output the matrix in FSL-compatible format (not available for SyN, though
                      see: https://github.com/gjheij/fmriproc/blob/main/fmriproc/misc/ants2fsl.md)
    
    Positional:
      <anat folder>   folder containing images for registration. If \$DATA == "AVERAGE", we'll look
                      for T1w-images containing 'acq-MP2RAGE_' and 'acq-MP2RAGEME_', create a warp
                      file, and apply this file to MP2RAGEME-files with ('T1w' 'T1map' 'R2starmap
                      Files ending with something other than 'T1w' or 'T1map' will also be copied
                      to have 'acq-AVERAGE' in the filename, rather than 'space-MP2RAGE'. This en-
                      sures compatibility with 'spinoza_sagittalsinus' when \$DATA == AVERAGE. Regis-
                      tered files will end up in the <anat folder>, the warp file itself in <output
                      folder>
      <output folder> folder where warp files are stored. Registered files are stored in <anat folder>
      <reg type>      which registration should be carried out. If empty, we'll default to a regis-
                      tration between MP2RAGEME and MP2RAGE (assumes that \$DATA == AVERAGE). This
                      version is called as 'master -m 05a'. If 'mni', we'll register the T1w-file
                      in <anat folder> with FSL's 1mm template ('MNI152NLin6Asym'). This version is
                      called as 'master -m 05b'. If type == 'mni', we'll default to the first ele-
                      ment in \${ACQ[@]} to register to MNI. Generally, this will/should be
                      MP2RAGE
    
    Example:
      spinoza_registration \$DIR_DATA_DERIV/pymp2rage \$DIR_DATA_DERIV/ants mp2rage
      spinoza_registration -s 001 -n 1 \$DIR_DATA_DERIV/pymp2rage \$DIR_DATA_DERIV/ants
    
    Call with master:
      # anat to anat
      master -m 05a -s 01
    
      # also save transformations following FSL-convention
      master -m 05a -s 01 --fsl
    
      # anat to MNI with 10 jobs
      master -m 05b -s 01 -j 10

spinoza_sagittalsinus_
====================================================================================================

.. code-block:: none

    spinoza_sagittalsinus
    
    This script creates the sagittal sinus mask based on the R2*-map from pymp2rage. It requires the
    user to refine the mask a bit, because the R2*-map is imperfect especially around the putamen and
    other iron-rich regions inside the brain. It will start ITKsnap for the user to do the editing.
    If you have MEMP2RAGE-data, then the script will look for the R2*-file in the specified ANAT
    folder. If this is somewhere else, just copy it into that directory.
    
    Usage:
      spinoza_sagittalsinus [arguments] [options] <anat folder> <mask folder> <software [itk|fv]>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or n)
      -t <thresh>     threshold for R2*-file to generate sinus mask (default = 0.07). You can check
                      this first with e.g., ITK-Snap ('launch_itksnap'), then call this function
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --itk           use ITK-Snap for manual editing [default]
      --fsl           use FSLeyes for editing
      --freeview      use FreeView for editing
    
    Positional:
      <input dir>     folder where anatomical files live
      <skullstrip>    output folder for masks
    
    Example:
      spinoza_sagittalsinus --freeview \$DIR_DATA_DERIV/pymp2rage \$DIR_DATA_DERIV/manual_masks
      spinoza_sagittalsinus --itk -s 01 \$DIR_DATA_DERIV/pymp2rage \$DIR_DATA_DERIV/manual_masks
    
    Call with master:
      # vanilla (runs with ITK-Snap)
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # run with FSLeyes
      master -m $(get_module_nr $(basename ${0})) -s 01 --fsl

spinoza_scanner2bids_
====================================================================================================

.. code-block:: none

    spinoza_scanner2bids
    
    Convert raw data from the scanner to nifti format using 'call_dcm2niix'. This script can handle
    both PAR/RECs and DCM input. DCM files will be converted using 'dcm2niix', whereas PAR/RECs will be
    converted using 'parrec2nii' (wrapper in 'call_parrec2nii'). Complete json sidecars will be produ-
    ced and populated with relevant information for fMRIPrep, including:
      - SliceTiming (if BOLD files are 2D); see also 'call_slicetiming'. Important factors for this
        function are:
          - number of slices (read from PAR/DCM-file)
          - Multiband factor (either read from PAR-file or from \$MB_FACTOR-variable)
          - Assumes ascending slice ordering
      - PhaseEncodingDirection:
        - Read from the \$PE_DIR_BOLD-variable (priority)
        - Specified for BOLD through flags (--ap|--pa|--lr|--rl), reversed for FMAP
        - Either read from PAR (but is ambiguous) or DCM (via 'CSA')
        - Defaults to AP for BOLD, reversed for FMAP
      - RepetitionTime:
        - For DCMs:
            1.  Parse TR directly from the filename if present (TR2.9, TR=2.9, TR_2p9, _TR2p9_).
                This is the most reliable for modern Siemens 3D EPI.
            2.  For 3D acquisitions, trust RepetitionTime (0018,0080) from DICOM directly.
            3.  For 2D Mosaic acquisitions, calculate TR = NumSlices × SliceMeasurementDuration.
                This works for Siemens 2D-EPI (especially in fMRI).
            4.  For 2D multi-band sequences, apply multi-band correction (TR / MultiBandFactor).
        - For PAR/RECs:
            We can read the 'dtime' column and extra unique values between slices/volumes. This works
            well for 3D acquisitions.
        - Both:
            Specified through the '-t <tr' flag.
    
        The RepetitionTime-key from the json-file is used as reference. The TR in the header will be
        updated to this value if a mismatch is detected.
      - IntendedFor/B0FieldIdentifier): the script can deal and set the IntendedFor-key appropriately
        in the following scenarios:
          - 1 FMAP per BOLD [best/most stable]
          - 1 FMAP for every 2 BOLD [most likely case]
          - 1 FMAP for all BOLDs [iffy]
    
        Generally, it is best to have an FMAP per BOLD, in which case the filenaming will be matched,
        assuming the BOLD file ends with '_bold.nii.gz' and the FMAP with '_epi.nii.gz'. In a final
        attempt, the folder with converted nifti-files is scraped to search for "*_dir-*_epi.nii.gz"-
        files, which are then linked to BOLD files if possible.
    
        TIP: check 'call_replace'/'call_dcm' how to update PAR/DCM files so that this is set correctly.
        File are converted using %n_%p pattern (see -p flag), so you can update these fields in the
        PAR/DCM-files to help the BIDS-ification process (see also link in 'Notes').
    
    By default, all files will be converted to have the RAS+ (or LPI) coordinate system. This system
    is used by fMRIPrep and makes the output from that software compatible with 'older' files before
    fMRIPrep. This is especially handy if you want to combine multiple segmentations to boost surfa-
    ce reconstruction. If you do not want this, use '--no-lpi'.
    
    Usage:
      spinoza_scanner2bids [arguments] [options] <project root> <sourcedata>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -d <depth>      search depth for dcm2niix
      -q <queue>      submit jobs to a specific queue. Defaults to SGE_QUEUE_LONG in spinoza_setup
      -v <n_vols>     number of volumes to cut from the beginning of the timeseries (default = None)
                      For instance, you have acquired the actual data from dummy scans rather than
                      discard them. Will discard the first X volumes from both the FUNC and FMAP, un-
                      less '--skip-fmap' is specified, in which case the FMAPs are left alone.
      -p <pattern>    pattern for file-name reconstruction (default = %n_%p, representing Patient-
                      Name & Protocol Name). You can change this, but then I don't bear any respon-
                      sibilities over the consequences in later scripts.. This option is only avai-
                      lable for 'dcm2niix' (DCM-files), not 'parrec2nii' (PAR/REC-files).
      -a <suffixes>   use suffixes to store other anatomical files in the BIDS folder. This over-
                      writes the \$SEARCH_ANATOMICALS-variable in the setup-file. For instance, if
                      you have qMRI-data that did not come from MP2RAGEME, you can specify:
                      "-a T2star,QSM,T1map". Input must be comma-separated without spaces. *.nii.gz
                      will be added to the search. 'acq' and 'run' tags are derived from the file-
                      name.
      -x <kwargs>     Extra arguments that will be directly passed to 'dcm2niix'/'parrec2nii'. The
                      format should be as follows: different parameters comma-separated, and para-
                      meter-value pair separated by '='):
    
                        "-x <parameter1>=<value1>,<parameter2>=<value2>,<parameterX>=<valueX>"
    
                      E.g.,:
                        "-x -b=y=0.05,--ignore_trigger_times,-x=y"
    
                      The kwargs specified in this flag take precedent over the default args:
    
                      # dcm2niix
                      cmd_args=(
                        dcm2niix
                        -b y          # output JSON side cars
                        -f %n_%p      # file name pattern     (-p flag)
                        -z o          # compression           (-c flag)
                        -d 0          # search depth          (-d flag)
                        -o output_dir # output directory      (-o flag)
                        -v 1          # verbosity
                        input_dir     # input directory       (-i flag)
                      )
    
                      # parrec2nii
                      cmd_args=(
                        parrec2nii
                        --scaling fp  # floating point
                        --verbose     # make noise
                        --compressed  # make nii.gz, suppressed with --no-compress
                        --output-dir  # output directory      (-o flag)
                      )
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --full          Overwrite existing output + created nifti folder
      --lines         flag to tell we're dealing with a line-scanning session. By default 'regular',
                      which means standard whole-brain acquisitions.
      --inv           add individual inversion files from anatomies in 'anat' folder
      --take-avg-tr   Derive RepetitionTime by averaging the time differences between all slices.
                      Default behavior is to take the difference between the first and second volume.
                      Only works for PAR/REC-files!
      --ap            set the phase-encoding of the BOLD to AP (FMAP=PA)
      --pa            set the phase-encoding of the BOLD to PA (FMAP=AP)
      --lr            set the phase-encoding of the BOLD to LR (FMAP=RL)
      --rl            set the phase-encoding of the BOLD to RL (FMAP=LR)
      --no-lpi        do not reorient files to LPI. If you want to use NORDIC or use fMRIprep's out-
                      puts on more raw data, I'd advise you to reorient to LPI and to NOT use this
                      flag. This flag is mainly here because it can take some time with big files
                      which slows down debugging.
      --no-compress   create nii's instead of nii.gz's (default). Passes on '--no-compress' to call-
                      parrec2nii, and '-c n' to dcm2niix
      --sge           submit individual subjects to cluster as call_parrec2nii can take a while..
      --phys          run only physiology conversion
      --skip-tr       do not overwrite the TR in the header during call_bids. Generally not recom-
                      mended, but exists for debugging purposes.
      --skip-fmap     do not trim the time series from FMAPs. By default, it is assumed that all your
                      functional files have dummy-saving turned on.
    
    Positional:
      <project root>  directory to output BIDSified data to
      <sourcedata>    directory containing to be converted data
    
    Example:
      # regular
      spinoza_scanner2bids \$DIR_DATA_HOME \$DIR_DATA_HOME/sourcedata
    
      # regular whole-brain session
      spinoza_scanner2bids -s 01 \$DIR_DATA_HOME \$DIR_DATA_HOME/sourcedata
    
      # line-scanning session
      spinoza_scanner2bids --lines -n 2 \$DIR_DATA_HOME \$DIR_DATA_HOME/sourcedata
    
      # mixed with MP2RAGE (assumes BOLD files have 'acq-3DEPI' tag to unmix BOLD files)
      spinoza_scanner2bids --lines --inv -n 2 \$DIR_DATA_HOME \$DIR_DATA_HOME/sourcedata
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # fix TR
      master -m $(get_module_nr $(basename ${0})) -s 01 -t 1.32
    
      # fix PhaseEncodingDirection
      master -m $(get_module_nr $(basename ${0})) -s 01 --ap
    
      # cut volumes from BOLD, but not FMAP
      master -m $(get_module_nr $(basename ${0})) -s 01 -v 4 --skip-fmap
    
      # skip reorientation to LPI
      master -m $(get_module_nr $(basename ${0})) -s 01 --no-lpi
    
      # mixed line-scanning session
      master -m $(get_module_nr $(basename ${0})) -s 01 --lines --inv
    
      # run specific runs
      master -m $(get_module_nr $(basename ${0})) -s 01 -r 1,2,4
    
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
    
      see https://fmriproc.readthedocs.io/en/latest/pipeline_steps.html for more tips and tricks regar-
      ding filenaming

spinoza_segmentfast_
====================================================================================================

.. code-block:: none

    spinoza_segmentfast
    
    tissue segmentation with FAST using skullstripped inputs created during spinoza_maskaverages. It is
    important that the range of these images is set correctly, with T1w having a range of 0-4095, and
    the T1map having a range of (0,5050). This should automatically be the case if you have ran the py-
    mp2rage module in combination with the masking module prior to running this. If not, run
    call_rescale on these images.
    
    Usage:
      spinoza_segmentfast [arguments] [options] <skullstripped dir> <output dir> <overwrite>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -x <kwargs>     Additional commands to be passed to 'FAST'. Format should be comma-separated
                      flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      E.g,:
                        "-x -t=[0.25,0.005,250];-x=some_mask.nii.gz"
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
    
    Positional:
      <anat folder>   folder containing the files required for FAST. Input must be skullstripped
      <output>        output folder (<subject>/[<ses->] will be appended!)
    
    Example:
      spinoza_segmentfast \$DIR_DATA_DERIV/skullstripped \$DIR_DATA_DERIV/fast
      spinoza_segmentfast -s 001 -n 1 \$DIR_DATA_DERIV/skullstripped \$DIR_DATA_DERIV/fast
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # kwargs
      master -m $(get_module_nr $(basename ${0})) -s 01 -x -R=0.5,-S=3,--nopve

spinoza_setup_
====================================================================================================

.. code-block:: none

    (No help text found)

spinoza_sinusfrommni_
====================================================================================================

.. code-block:: none

    spinoza_sinusfrommni
    
    This script takes the registration matrix from MNI to subject space to warp the sagittal sinus mask
    in MNI-space to the subject space. We then multiply this image with the T1w/T2w ratio to get a de-
    cent initial estimate of the sagittal sinus
    
    Usage:
      spinoza_sinusfrommni [arguments] [options] <anat folder> <registration folder> <mask folder>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --itk           use ITK-Snap for manual editing [default]
      --fsl           use FSLeyes for editing
      --freeview      use FreeView for editing
    
    Positional:
      <anat dir>      directory containing the T1w and T2w files; should generally be pymp2rage-folder
      <reg dir>       path to directory where registration file is (output from spinoza_registration)
      <mask dir>      path to output mask directory (to put final 'sinus'-mask)
    
    Example:
      spinoza_sinusfrommni --freeview \$DIR_DATA_DERIV/pymp2rage \$DIR_DATA_DERIV/manual_masks
      spinoza_sinusfrommni --itk -s 01 \$DIR_DATA_DERIV/pymp2rage \$DIR_DATA_DERIV/manual_masks
    
    Call with master:
      # vanilla (runs with ITK-Snap)
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # run with FSLeyes
      master -m $(get_module_nr $(basename ${0})) -s 01 --fsl

spinoza_subcortex_
====================================================================================================

.. code-block:: none

    spinoza_subcortex
    
    Subcortex segmentation using Nighres' MASSP-algorithm. Calls on call_nighresmassp; see that file
    for more information on the required inputs.
    
    Usage:
      spinoza_subcortex [arguments] [options] <project root dir> <prob seg dir> <region> <overwrite>
    
    Arguments:
      -s <subject>    subject ID (e.g., 01). Can also be comma-separated list: 01,02,05
      -n <session>    session ID (e.g., 1, 2, or none)
      -j <cpus>       number of cores to use (default is 1)
      -q <queue>      submit jobs to a specific queue. Defaults to \$SGE_QUEUE_LONG in spinoza_setup
      -x <kwargs>     Additional commands to be passed to 'antsRegistration'. Format should be comma-
                      separated flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      This allows bash commands to be translated to python commands
    
      -p <kwargs>     Additional commands to be passed to 'MASSP'. Format should be comma-separated
                      flags as follows:
                        - if you specify a flag and values | <flag>=<value>
                        - if you specify a flag only | <flag>
    
                      combine as:
                        "-x <flag1>=<value>,<flag2>,<flag3>,<flag4>=<value>"
    
                      This allows bash commands to be translated to python commands
    
    Options:
      -h|--help       print this help text
      -o|--ow         Overwrite existing output
      --sge           submit job to cluster
    
    Positional:
      <anat folder>   folder containing the files required for MASSP. Files should end with:
                        -"*_R1.nii.gz"   > 1/T1map file
                        -"*_R2s.nii.gz"  > 1/T2* file
                        -"*_QSM.nii.gz"  > QSM file
      <output>        output folder (<subject>/[<ses->] will be appended!)
    
    Example:
      spinoza_subcortex \$DIR_DATA_HOME \$DIR_DATA_DERIV/nighres
      spinoza_subcortex -s 001 -n 1 \$DIR_DATA_HOME \$DIR_DATA_DERIV/nighres
    
    Call with master:
      # vanilla
      master -m $(get_module_nr $(basename ${0})) -s 01
    
      # kwargs for antsRegistration
      master -m $(get_module_nr $(basename ${0})) -s 01 -x rigid_iterations=250,affine_iterations=200
    
      # kwargs for MASSP
      master -m $(get_module_nr $(basename ${0})) -s 01 -p max_iterations=250,intensity_prior=0.45
    
    Notes:
      - embedded_antsreg_multi: https://nighres.readthedocs.io/en/latest/registration/embedded_antsreg_multi.html
      - MASSP: https://nighres.readthedocs.io/en/latest/auto_examples/example_07_massp_subcortex_parcellation.html
