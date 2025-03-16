Pipeline Steps
==============

Below is a **step-by-step guide** on how to execute the preprocessing pipeline.

1. **Convert Raw Data to NIfTI**

   .. code-block:: bash

      master -m 02a -s <subjectID> -n <sessionID>

2. **Run Quality Control with MRIQC**

   .. code-block:: bash

      master -m 02b -s <subjectID> -n <sessionID>

3. **Apply NORDIC Denoising (Optional)**

   .. code-block:: bash

      master -m 10 -s <subjectID> -n <sessionID> --sge

4. **Run FreeSurfer Surface Reconstruction**

   .. code-block:: bash

      master -m 14 -s <subjectID> -n <sessionID>

5. **Run fMRIprep**

   .. code-block:: bash

      master -m 15 -s <subjectID> -n <sessionID> --func

6. **Denoise Functional Data with Pybest**

   .. code-block:: bash

      master -m 16 -s <subjectID> -n <sessionID> --sge

