.. include:: links.rst

------------
Installation
------------

Install the **fmriproc**-repository as follows:

.. code:: bash

   $ # installs the main package
   $ pip install git+https://github.com/gjheij/fmriproc

   $ # run setup
   $ spinoza_setup setup

   $ # run source
   $ source ~/.bash_profile

I futher recommend a folder structure where `logs` and `projects` are separated. In the former, we store all the custom
installed packages (i.e., `git clone`), fMRIprep_'s workflow folders, and other stuff that we might need for multiple
projects. Inside the `projects` folder, you then store your project data according to the BIDS-format (as much as possible).
That would look something like this  (see **TIP** below on what ``<some directory>`` for more information):

.. code:: bash

    <your directory>
    ├── logs
    │   ├── fmriprep                # created automatically when running fMRIPrep
    │   │   ├── name_1              # matches project name in 'projects' folder
    │   │   │   ├── fmriprep_wf
    │   │   └── name_2              # matches project name in 'projects' folder
    │   │       └── fmriprep_wf    
    │   └── fmriproc            # this repository
    └── projects
        ├── name_1
        │   ├── derivatives
        │   ├── sourcedata
        │   ├── sub-01
        │   └── dataset_description.json
        └── name_2
            ├── derivatives
            ├── sourcedata
            ├── sub-01
            └── dataset_description.json        

Test the installation with:

.. code:: bash

   $ python -c "import fmriproc"

If no error was given, the installation was successful. To test the ``bash`` environment, enter the following:

.. code:: bash

   $ master

This should give the help menu of the master script.

External Dependencies
---------------------

Installations of ANTs_, FSL_, SPM_ (+CAT12_-toolbox), fMRIprep_ and FreeSurfer_ are expected to exist on your system.
  
.. code:: bash
   
   export FREESURFER_HOME=<path to FreeSurfer installation>
   export FS_LICENSE=$FREESURFER_HOME/license.txt
   source $FREESURFER_HOME/SetUpFreeSurfer.sh

.. attention:: 
   FreeSurfer_ requires a ``SUBJECTS_DIR``, and upon installation this is set to ``FREESURFER_HOME``. However, this variable is overwritten in ``spinoza_setup``! It is possible that in some cases this might lead to undesirable effects. For instance, if you use this package alongside your own scripts. If you wish to overwrite the variable in ``spinoza_setup``, comment out that line and set a ``SUBJECTS_DIR`` in your ``~/.bash_profile``.
      