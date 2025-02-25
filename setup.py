from setuptools import setup, find_packages
import glob
import os

# Collect all scripts in bin/ and shell/
bin_scripts = glob.glob("bin/*")  # All files in bin/
shell_scripts = glob.glob("shell/*")  # All files in shell/

setup(
    name="fmriproc",
    version="0.1",
    packages=find_packages(),
    install_requires=[],
    include_package_data=True,
    data_files=[
        ("bin", bin_scripts),
        ("shell", shell_scripts),
    ],
)

# Ensure scripts are executable
for script in bin_scripts + shell_scripts:
    os.chmod(script, 0o775)  # rwxr-xr-x
