Troubleshooting & Common Issues
===============================

Issue: fMRIprep Cannot Find License File
----------------------------------------

Ensure the `license.txt` is correctly placed:

.. code-block:: bash

    export FS_LICENSE="/path/to/license.txt"

Issue: Error with Cluster Submission
------------------------------------

Check if your system supports **SGE or SLURM**:

.. code-block:: bash

    if command -v qsub >/dev/null 2>&1; then
        echo "SGE detected"
    elif command -v sbatch >/dev/null 2>&1; then
        echo "SLURM detected"
    else
        echo "No supported scheduler found"
    fi

Issue: Incorrect Phase-Encoding Direction
-----------------------------------------

Verify your `spinoza_config` settings:

.. code-block:: bash

    export PE_DIR_BOLD="AP" # Ensure correct phase encoding
