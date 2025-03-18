import numpy as np
from fmriproc import prf
import os

def test_load_design_matrix(examples_dir):
    """Test that design matrix can be loaded correctly."""
    mat_file = os.path.join(examples_dir, "design_task-2R.mat")
    design = prf.read_par_file(mat_file)
    assert design.shape[-1] == 225, "design should have 225 volumes"

def test_fit_prf_with_example(examples_dir):
    """Test PRF fitting using example timecourse and design."""
    mat_file = os.path.join(examples_dir, "design_task-2R.mat")
    prf_file = os.path.join(examples_dir, "prf.npy")

    design = prf.read_par_file(mat_file)
    timecourse = np.load(prf_file)

    # Use the actual pRFmodelFitting from fmriproc.prf
    model_fitter = prf.pRFmodelFitting(
        timecourse.T, 
        design,
        TR=1.5,
        model="gauss",
        constraints="bgfs",
        verbose=True
    )
    model_fitter.fit()

    result = model_fitter.gauss_iter  # Assuming `results` holds the fitting results.

    assert isinstance(result, np.ndarray), "fit_prf should return a numpy array"
    assert 0 <= result[0,-1] <= 1, "r2 should be between 0 and 1"
