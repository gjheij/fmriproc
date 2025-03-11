import os
import pytest

@pytest.fixture(scope="session")
def examples_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fmriproc", "examples"))
