import sys
import os
from unittest.mock import MagicMock
import importlib

sys.path.insert(0, os.path.abspath(".."))
try:
    version_module = importlib.import_module("fmriproc.version")
    release = version = version_module.__version__  # Use the dynamic version
except (ImportError, AttributeError):
    release = version = "unknown"  # Fallback version if import fails


# List of modules to mock (DO NOT mock NumPy)
MOCK_MODULES = [
    "nibabel", "nipype", "nipype.interfaces", "nipype.interfaces.freesurfer", "lazyfmri",
    "pandas", "joblib",
]

# Create MagicMock objects for each module
mocked_modules = {mod: MagicMock() for mod in MOCK_MODULES}

# Update sys.modules with mocked modules
sys.modules.update(mocked_modules)

# -- Sphinx Configuration --
project = "fMRIproc Documentation"
author = "Jurjen Heij"
release = "1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "nbsphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
