Installation Guide
==================

Installing **fMRIproc** requires a **Python environment** and several external software dependencies.

Setting Up the Environment
---------------------------

1. **Create a Conda Environment (optional but recommended):**

   .. code-block:: bash

      conda create --name fmriproc python=3.11

2. **Install fMRIproc via GitHub:**

   .. code-block:: bash

      pip install git+https://github.com/gjheij/fmriproc

3. **Install ANTs via conda:**

   .. code-block:: bash

      conda install -c conda-forge ants

This installs the core Python package and scripts.

---

Configuring the Environment
---------------------------

To ensure smooth execution, **fMRIproc** uses a `spinoza_config` file for paths and settings (see :doc:`configuration`).

After installation, run:

.. code-block:: bash

   spinoza_install setup

This will:

- Add `spinoza_setup` sourcing to `~/.bash_profile` or `~/.zshrc`.
- Register the correct path for `spinoza_config`.
- Optionally add `conda activate fmriproc` for auto-activation.

For a custom configuration location:

.. code-block:: bash

   spinoza_install setup /path/to/custom_config

