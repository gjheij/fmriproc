Running fMRIproc on HPC Clusters
================================

fMRIproc supports **SGE (Sun Grid Engine) and SLURM** for cluster execution.

Check Scheduler Type
--------------------

.. code-block:: bash

   if command -v qsub >/dev/null 2>&1; then
       echo "Using SGE"
   elif command -v sbatch >/dev/null 2>&1; then
       echo "Using SLURM"
   else
       echo "No scheduler detected."
   fi

Submitting Jobs
---------------

For both **SGE**/ **SLURM**, the command is the same. The command is configured properly depending on the system.

.. code-block:: bash

   master -m 02a -s <subjectID> -n <sessionID> --sge
