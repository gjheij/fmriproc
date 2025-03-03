# fmriproc/__init__.py

import os
import warnings
import platform
from importlib.metadata import version

def set_mkl_threading_layer():
    """
    Set MKL_THREADING_LAYER automatically based on platform.
    This helps avoid OpenMP conflicts (like the threadpoolctl warning).
    """
    if platform.system() == "Darwin":
        os.environ["MKL_THREADING_LAYER"] = "TBB"
    elif platform.system() == "Linux":
        os.environ["MKL_THREADING_LAYER"] = "INTEL"
    else:
        os.environ["MKL_THREADING_LAYER"] = "TBB"  # Default safe option

def suppress_threadpoolctl_warning():
    """
    Suppress the threadpoolctl RuntimeWarning about multiple OpenMP libraries.
    This doesn't fix the root cause, but avoids scaring users.
    """
    warnings.filterwarnings("ignore", category=RuntimeWarning, module="threadpoolctl")

# Apply fixes immediately when package loads
set_mkl_threading_layer()
suppress_threadpoolctl_warning()

__version__ = version("fmriproc")

# Now import core functionality (optional, but typical in __init__.py)
from . import image
from . import planning
from . import prf
from . import scanner
from . import simulate
from . import transform

__all__ = ["image", "planning", "prf", "scanner", "simulate", "transform"]
