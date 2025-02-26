from setuptools import setup, find_packages
import glob

# Collect all scripts in bin/ and shell/
bin_scripts = glob.glob("bin/*")  # All files in bin/
shell_scripts = glob.glob("shell/*")  # All files in shell/

setup(
    name="fmriproc",
    version="0.1",
    packages=find_packages(),
    install_requires=[],
    include_package_data=True,
    scripts=bin_scripts+shell_scripts
)
