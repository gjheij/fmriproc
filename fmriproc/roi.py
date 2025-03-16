from lazyfmri import (
    fitting,
    plotting,
    utils,
    dataset
)
import numpy as np
import pandas as pd
import os
import nibabel as nb
from joblib import Parallel,delayed
import datetime
import matplotlib.pyplot as plt
import json

opj = os.path.join

# subclass JSONEncoder
class DateTimeEncoder(json.JSONEncoder):
    #Override the default method
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()

class ExtractFromROIs():

    """ExtractFromROIs

    Extract timecourses given a list of ROIs from functional files. Assumes the ROI and functional files are in the same space,
    e.g., both in native functional space (in case of single-subject processing), or all in MNI-space (in which case multi-
    subject processing is permitted). If the ROIs represent float data (e.g., zstat/tstat), it will extract the 15 highest
    voxels within that ROI. If ROI is binary, all voxels will be used. See also :func:`fmriproc.roi.ExtractFromROIs.extract_data`.

    Parameters
    ----------
    func: str, nibabel.Nifti1Image, nibabel.GiftiImage, np.ndarray
        Input functional data, either a string representing a path, a nibabel.Nifti1Image-object, a nibabel.GiftiImage-object,
        or a numpy array
    rois: list, str, optional
        List of ROIs, either strings representing a path, nibabel.Nifti1Image-objects, or a numpy arrays or a directory con-
        taining a bunch of ROIs. Use the "filters="-flag to further specify the input.
    filters: str, list, optional
        additional filters to search for ROI files. For instance, you have specified a directory with "--rois /path/to/ROIs",
        but that directory contains a bunch of ROIs that you're not necessarily interested in. If you're only interested in
        the files starting with "conv-\*", you can specify that here.        
    roi_names, list, str, optional
        If empty, we will try to derive the ROI name from the filename (if they are strings).
        E.g., from "bin.thr.ACC_L.nii.gz", it would extract the last elements after ".", so "ACC_L".
        If the inputs are not strings, we will default to "roi_{}", so it's highly encouraged to use the *roi_names*-input
        for non-string functional files.
    ses: int, optional
        Specify session ID; will be read from filename if possible using :func:`lazyfmri.utils.split_bids_components`
    task: str, optional
        Specify task ID; will be read from filename if possible using :func:`lazyfmri.utils.split_bids_components`
    TR: int, optional
        Repetition time to use for the dataframe formation, by default 2
    subject: int, optional
        Subject ID to use for the dataframe formation, by default 1
    verbose: bool, optional
        Make some noise, by default False
    **kwargs: dict
        Same as :func:`fmriproc.roi.ExtractFromROIs.extract_data`

    Example
    ----------

    .. code-block:: python

        from fmriproc import roi
        obj = roi.ExtractFromROIs(
            "/path/to/fmriprep/sub-01/ses-1/func/sub-01_ses-1_task-task1_space-MNI152NLin6Asym_bold.nii.gz",
            rois=[
                "/path/to/rois/bin.thr.space-MNI152NLin6Asym.ACC_L.nii.gz,
                "/path/to/rois/bin.thr.space-MNI152NLin6Asym.ACC_R.nii.gz
                "/path/to/rois/bin.thr.space-MNI152NLin6Asym.PCC_L.nii.gz
                "/path/to/rois/bin.thr.space-MNI152NLin6Asym.PCC_R.nii.gz
            ],
            TR=1.5,
            subject="01"
        )

    """

    def __init__(
        self, 
        func, 
        rois=None,
        filters=None,
        roi_names=None,
        ses=None,
        task=None,
        TR=2,
        subject=1,
        verbose=False,
        **kwargs
        ):

        self.func = func
        self.rois = rois
        self.filters = filters
        self.TR = TR
        self.subject = subject
        self.verbose = verbose
        self.roi_names = roi_names
        self.ses = ses
        self.task = task

        if isinstance(self.func, (str,nb.Nifti1Image,np.ndarray,nb.GiftiImage)):
            self.func = [self.func]

        if isinstance(self.filters, str):
            self.filters = [self.filters]

        if isinstance(self.roi_names, str):
            self.roi_names = [self.roi_names]

        # decide input of ROIs
        self.set_rois_input()

        # check if roi_names == rois
        if isinstance(self.roi_names, list):
            if len(self.roi_names) != len(self.roi_list):
                raise ValueError(f"Number of specified ROI names ({len(self.roi_names)}) does not match number of supplied ROI-files ({len(self.roi_list)})")

        # run extractor
        self.extracted_data = self.main_extractor(**kwargs)
    
    def set_rois_input(self):

        if isinstance(self.rois, (nb.GiftiImage, nb.Nifti1Image, np.ndarray)):
            self.roi_list = [self.rois]
        elif isinstance(self.rois, str):
            # input is directory
            if os.path.isdir(self.rois):
                self.roi_list = utils.FindFiles(
                    self.rois,
                    extension="nii.gz",
                    exclude="._"
                ).files

                if isinstance(self.filters, list):
                    self.roi_list = utils.get_file_from_substring(
                        self.filters,
                        self.rois
                    )

            elif os.path.isfile(self.rois):
                # input is a file
                self.roi_list = [self.rois]
            else:
                # input is invalid
                raise TypeError(f"rois must be a directory or filepath, not {type(self.rois)}")
        elif isinstance(self.rois, list):
            self.roi_list = self.rois
        else:
            raise ValueError(f"rois must be a directory, filepath, or list of files, not {type(self.rois)}")
                
    def main_extractor(
        self, 
        sep="_",
        **kwargs
        ):

        """Loop through functional files to extract data using :func:`fmriproc.roi.ExtractFromROIs.extract_data`"""
        df = []
        # loop through functionals
        for ix,func in enumerate(self.func):
            
            # try to read subject/run info from file
            subject = self.subject
            self.run = ix+1

            # load data
            if isinstance(func, str):
                utils.verbose(f"Func #{ix+1}: {func}", self.verbose)
            else:
                utils.verbose(f"Func #{ix+1}: input={type(func)}", self.verbose)

            # load functional file
            data = self.load_file(func)

            # loop through ROIs
            roi_df = []
            for ix, roi in enumerate(self.roi_list):
                
                # use specified ROI names
                roi_name = self.extract_run_identifier(
                    roi,
                    ix,
                    sep=sep
                )

                # load file and extract
                roi_data = self.load_file(roi)
                extr_data = self.extract_data(
                    data,
                    roi_data,
                    **kwargs
                )

                tmp_df = pd.DataFrame(extr_data, columns=[roi_name])
                roi_df.append(tmp_df)

            roi_df = pd.concat(roi_df, axis=1)
            roi_df["subject"], roi_df["run"], roi_df["t"] = subject, self.run, list(np.arange(0,roi_df.shape[0], dtype=float)*self.TR)

            for k in ["ses", "task"]:
                if hasattr(self, k):
                    el = getattr(self, k)
                    if el is not None:
                        roi_df[k] = el

            df.append(roi_df)

        df = pd.concat(df)
        utils.verbose(f"Done", self.verbose)
        return df

    def extract_run_identifier(
        self,
        roi,
        ix,
        sep="_",
        ):

        roi_name = None
        if isinstance(self.roi_names, list):
            roi_name = self.roi_names[ix]

        # extract ROI name from file
        if roi_name is None:
            if isinstance(roi, str):
                utils.verbose(f" Dealing with roi: {roi}", self.verbose)
    
                roi_name = os.path.basename(roi)
                if roi_name.endswith("gz"):
                    roi_name = sep.join(roi_name.split(".")[:-2])
                elif roi_name.endswith("nii"):
                    roi_name = sep.join(roi_name.split(".")[:-1])
                else:
                    raise NotImplementedError()
                
                try:
                    bids_comps = utils.split_bids_components(roi)
                    for key in ["ses", "task", "run"]:
                        if key in list(bids_comps.keys()):
                            setattr(self, key, bids_comps[key])
                except Exception:
                    pass

        else:
            roi_name = f"roi_{ix+1}"

        return roi_name
    
    @staticmethod
    def extract_data(
        func,
        roi,
        nr=15,
        bsl=15,
        highest=True,
        psc=True,
        zscore=False
        ):
        
        """extract_data

        Extractor function depending on ROI input. If the ROI represents a zstat/tstat file (or file with float) values,
        we will select by default the 15 highest values within the roi. To select the 15 lowest, set *highest=False*.
        To change the number of voxels to extract, use the *nr*-input.

        Parameters
        ----------
        func: np.ndarray
            4D timeseries representing the functional data
        roi: np.ndarray
            int/float np.ndarray representing the ROI data
        nr: int, optional
            number of voxels to extract from data in case the input is float, by default 15.
            if the input is binary, we will take the entire ROI.
        bsl: int, optional
            amount of time to use to calculate baseline for percent signal change conversion, by default 15s.
        highest: bool, optional
            If True, we select *nr* HIGHEST voxels from roi. If False, we select the *nr* LOWEST. By default True
        psc: bool, optional
            Normalize to percent signal change. Default is True.
        zscore: bool, optional
            Normalize using z-scoring. Default = False

        Returns
        ----------
        np.ndarray
            extracted data (either normalized or not) 

        """
        # deal with binary data
        if 0 <= roi.max() <= 1:
            tm = func[roi>0]
            tc = tm.mean(axis=0)
        else:
            # find max values in 
            max_val = np.sort(roi.ravel())

            if highest:
                search_vals = max_val[-nr:]
            else:
                search_vals = max_val[:nr]

            vox = []
            for i in search_vals:
                vox.append(func[np.where(roi == i)])

            tc = np.concatenate(vox, axis=0).mean(axis=0)[...,np.newaxis]            

        if zscore:
            psc = False

        if psc:
            psc = utils.percent_change(
                tc,
                0,
                baseline=bsl
            )
            return psc
        else:
            if zscore:
                sd = tc.std()
                m_ = tc.mean()
                z = (tc-m_)/sd
                return z
            else:
                return tc

    @staticmethod
    def load_file(file):
        """Load file based on whether it is a string, numpy array, or nibabel.Nifti1Image object"""
        if isinstance(file, str):
            if file.endswith(".nii.gz"):
                data = nb.load(file).get_fdata()
            elif file.endswith(".gii"):
                data = dataset.ParseGiftiFile(file).data
            else:
                raise NotImplementedError(f"{file} is not supported. Must be .nii.gz, or .gii")
        elif isinstance(file, np.ndarray):
            data = file.copy()
        elif isinstance(file, nb.Nifti1Image):
            data = file.get_fdata()
        elif isinstance(file, nb.GiftiImage):
            data = np.vstack([arr.data for arr in file.f_gif.darrays])
        else:
            raise TypeError(f"Input {file} is of type {type(file)}. Must be a string pointing to an existing file path, an numpy array, nb.Nifti1Image-object, or nb.GiftiImage-object")

        return data

class ExtractSubjects(ExtractFromROIs):

    """ExtractSubjects

    Loop through all subjects in a FEAT-directory to extract timecourses from a set of ROIs using
    :class:`fmriproc.roi.ExtractFromROIs()`.

    Parameters
    ----------
    ft_dir: str
        path to 1st level FEAT, fMRIprep, or Pybest directory. For FEAT, We're explicitly searching for the
        "filtered_func_data" files; for fMRIprep, we will look for "\*desc-preproc_bold.nii.gz" using the
        native functional files as default. Use e.g., `space=MNI152NLin6Asym` to select FSL's MNI files.
        For Pybest, we will either look in the "unzscored"-folder if you want surface-based files (e.g.,
        'fsnative' or 'fsaverage') for "\*desc-denoised_bold.npy". For volumetric files, we will look in
        the "masked" folder for "\*desc-denoised_bold.nii.gz". For both fMRIprep and Pybest, you can select
        specific tasks with *task=["task1", "task3"]*. Otherwise all files will be considered. This can be
        particularly problematic for surface-based files from Pybest, as there's extra files being outputted
        by Pybest that make selection using these criteria difficult. For instance, if you have multiple runs,
        it saves out an average without "run"-identifier. However, it outputs the same file if you only have
        a single runs..
    func: str, list, optional
        Reuse existing csv-file (<output_dir>/<base_name>/<base_name>_desc-tcs.csv)
    excl_subjs: list, optional
        Exclude particular subjects present in the *ft_dir*, by default None
    incl_subjs: str, optional
        Include particular subjects present in the *ft_dir*, by default None
    n_jobs: int, optional
        Number of jobs to use for the extraction, by default set to the number of subjects present
    verbose: bool, optional
        Make some noise, by default False
    **kwargs: dict
        Same as :func:`fmriproc.roi.ExtractFromROIs.extract_data`
    """

    def __init__(
        self, 
        ft_dir, 
        func=None,
        space=None,
        task=None,
        excl_subjs=[],
        incl_subjs=None,
        n_jobs=None,
        verbose=False,
        **kwargs
        ):
        self.ft_dir = ft_dir
        self.excl_subjs = excl_subjs
        self.incl_subjs = incl_subjs
        self.n_jobs = n_jobs
        self.verbose = verbose
        self.func = func
        self.space = space
        self.task = task

        if not isinstance(self.func, str):
            
            # check for incl/excl subjects
            self.set_subjects()

            # set number of jobs
            if not isinstance(self.n_jobs, int):
                self.n_jobs = len(self.subjects)

            # search files
            self.search_for_files()

            # extract
            self.df_func = self.extract_subjects(**kwargs)
        else:
            self.read_tcs_file()

    def search_for_files(self):

        # check if input if fmriprep
        utils.verbose(f"Looking for files in '{self.ft_dir}'", self.verbose)
        if os.path.basename(self.ft_dir) == "fmriprep":
            self.all_files = self.find_fmriprep_files(self.ft_dir, space=self.space, task=self.task)
        elif os.path.basename(self.ft_dir) == "pybest":
            self.all_files = self.find_pybest_files(self.ft_dir, space=self.space, task=self.task)
        else:
            self.all_files = self.find_feat_files(self.ft_dir)

        if isinstance(self.all_files, str):
            self.all_files = [self.all_files]
            
        utils.verbose(f"Found {len(self.all_files)} file(s)", self.verbose)

    def read_tcs_file(self):

        utils.verbose(f"Reading file: {self.func}", self.verbose)
        self.df_func = pd.read_csv(self.func, dtype={"subject": str}) # bit dodgy..
        self.df_func.set_index(["subject","run","t"], inplace=True)

        # read subject IDs from dataframe
        self.subj = utils.get_unique_ids(self.df_func, id="subject")
        self.subjects = [f"sub-{i}" for i in self.subj]

    def set_subjects(self):
        if not isinstance(self.incl_subjs, (str,list)):

            self.subjects = utils.get_file_from_substring(["sub-"], os.listdir(self.ft_dir))
            if isinstance(self.subjects, str):
                self.subjects = [self.subjects]

            self.subjects = sorted([i for i in self.subjects if i not in self.excl_subjs])
        else:
            if isinstance(self.incl_subjs, str):
                self.incl_subjs = [self.incl_subjs]
                
            self.subjects = [i for i in self.incl_subjs if i not in self.excl_subjs]
        
        utils.verbose(f"Including following subjects: {self.subjects}", self.verbose)

    @staticmethod
    def find_feat_files(input_dir):
        # assuming input is FEAT
        ft_files = utils.FindFiles(input_dir, extension="filtered_func_data.nii.gz", exclude="._").files

        if not isinstance(ft_files, (str, list)):
            raise ValueError(f"Could not find files with 'filtered_func_data.nii.gz' in '{input_dir}'")
        
        return ft_files

    @staticmethod
    def find_fmriprep_files(input_dir, space="func", task=None):

        all_files = utils.FindFiles(input_dir, extension="desc-preproc_bold.nii.gz", exclude="._").files
        if isinstance(space, str):
            if space == "func":
                fprep_files = utils.get_file_from_substring(
                    ["desc-preproc_bold.nii.gz"],
                    all_files,
                    exclude="space-"
                )                
            else:
                fprep_files = utils.get_file_from_substring(
                    [f"space-{space}"],
                    all_files
                )

            if not isinstance(fprep_files, (str, list)):
                raise ValueError(f"Could not find files with 'desc-preproc_bold.nii.gz' in '{input_dir}'")
        else:
            raise ValueError(f"space- tag required for fmriprep input, otherwise I don't know which files to take..")
    
        if isinstance(task, (str)):
            task = [task]

        if isinstance(task, list):
            task_files = []
            for t in task:
                tmp = utils.get_file_from_substring(
                        [f"task-{t}"],
                        fprep_files
                    )
                task_files += tmp

            return task_files
        else:
            return fprep_files

    @staticmethod
    def find_pybest_files(input_dir, space=None, task=None):
        if isinstance(space, str):
            if space in ["fsaverage", "fsnative"]:
                ext = "desc-denoised_bold.npy"
                pyb_files = utils.FindFiles(
                    input_dir,
                    extension=ext,
                    exclude="._"
                ).files

                pyb_files = utils.get_file_from_substring(
                    ["unzscored"],
                    pyb_files
                )
            else:
                ext = "desc-denoised_bold.nii.gz"
                all_files = utils.FindFiles(
                    input_dir,
                    extension=ext,
                    exclude="._"
                ).files

                if space == "func":
                    pyb_files = utils.get_file_from_substring(
                        ["masked"],
                        all_files,
                        exclude="space-"
                    )
                else:
                    pyb_files = utils.get_file_from_substring(
                        ["masked", f"space-{space}"],
                        all_files
                    )
            
            if not isinstance(pyb_files, (str, list)):
                raise ValueError(f"Could not find files with '{ext}' in '{input_dir}'")
            
            if isinstance(task, (str)):
                task = [task]

            if isinstance(task, list):
                task_files = []
                for t in task:
                    tmp = utils.get_file_from_substring(
                        [f"task-{t}"],
                        pyb_files
                    )
                    task_files += tmp

                return task_files
            else:
                return pyb_files
        else:
            raise ValueError(f"space- tag required for pybest input, otherwise I don't know which files to take..")
        
    def extract_subjects(
        self, 
        **kwargs
        ):
        """Wrapper around :func:`fmriproc.roi.ExtractSubjects.extract_single_subject` to loop through subjects"""
        output = Parallel(n_jobs=self.n_jobs, verbose=True)(
            delayed(self.extract_single_subject)(
                utils.get_file_from_substring([sub], self.all_files),
                subject=sub.split("-")[-1],
                verbose=self.verbose,
                **kwargs
            )
            for sub in self.subjects
        )

        # concat
        df = pd.concat(output)

        # set indices
        idx_list = ["subject", "run", "t"]
        for k in ["task", "ses"]:
            if k in list(df.columns):
                idx_list.insert(1, k)

        df.set_index(idx_list, inplace=True)

        return df

    def extract_single_subject(
        self, 
        files,
        **kwargs):
        """Wrapper around :class:`fmriproc.roi.ExtractFromROIs` to extract data from a single subject"""
        super().__init__(
            files,
            **kwargs
        )

        return self.extracted_data.copy()


def format_onsets(
    subject_list, 
    project_dir
    ):

    onset = []
    for ix,subject in enumerate(subject_list):

        subj = subject.split("-")[-1]
        onset_dir = opj(project_dir, subject, "ses-1")
        if not os.path.exists(onset_dir):
            raise FileNotFoundError(f"Directory '{onset_dir}' does not exist; is 'proj_dir' set correctly?")

        tsv_files = utils.FindFiles(
            onset_dir,
            extension="tsv"
        ).files

        if len(tsv_files) == 0:
            raise ValueError(f"Could not find tsv-files in '{onset_dir}'")
        
        # sort onset time
        tmp_onset = []
        for tsv in tsv_files:

            # read runID from bids components
            comps = utils.split_bids_components(tsv)
            run = comps["run"]

            onset_df = pd.read_csv(tsv, sep='\t')
            selected_columns = onset_df[["onset", "trial_type"]]
            onset_df = selected_columns.copy()
            onset_df['subject'], onset_df['run'] =  subj, int(run)
            onset_df = onset_df.rename(columns={"trial_type": "event_type"})
            onset_df['onset'] = onset_df['onset'].astype(float)
            onset_df['event_type'] = onset_df['event_type'].astype(str)  
            tmp_onset.append(onset_df)

        subj_onset = pd.concat(tmp_onset)
        onset.append(subj_onset)

    return pd.concat(onset).set_index(['subject', 'run', 'event_type'])

class FullExtractionPipeline(ExtractSubjects):

    """FullExtractionPipeline

    Given a list of ROIs, extract the timecourses from all subjects' preprocessed data in a level1 feat folder. If these ROIs
    are binary, the timecourses will be averaged across this entire area. If the ROIs are values (e.g., z-stat values), the n
    (default = 15) highest (default) /lowest (--lowest) values will be selected and averaged. These timecourses are entered in
    a deconvolution model using the canonical HRF and its derivatives as basis sets (default). From this model, parameters are
    extracted from the individual basis sets as well as the full HRF. Results are plotted and stored in a figure where the
    rows denote EVs (stimulus conditions. There's a couple of default settings that you can generally leave alone, but there's
    flags to changed them nonetheless.

    Parameters
    ----------
    proj_dir: str, optional
        Root of the project folder, defaults to os.environ.get("DIR_DATA_HOME"). Mainly necessary for fetching onset files.
    order: list, optional
        If performing deconvolution, a plot can be generated. This flag sets the order (rows). By default, we'll take the order
        in the onset dataframe (unsorted).
    peak: int, optional
        Deconvolution can sometimes cause exotic HRF shapes. This flag specifically tells the algorithm to select the first
        peak while extracting parameters.
    dec_kws: dict, optional
        Extra parameters for the deconvolution, by default:

        .. code-block:: python

            dec_defaults = {
                "interval": [-2,25],
                "basis_sets": "canonical_hrf_with_time_derivative_dispersion",
                "TR": 2
            }

        The format should be as follows (different parameters comma-separated, and parameter-value pair separated by '='):
        "--dec <parameter1>=<value1>,<parameter2>=<value2>,<parameterX>=<valueX>"
        In case you want to change the interval over which the profiles are deconvolved, use "interval=t1>t2" (separated by '>').

    plot_kws: dict, optional
        Set parameters for plotting. The idea is similar to the "--dec" flag. The defaults are set to:

        .. code-block:: python

            plot_defaults = {
                "line_width": 3,    # thickness of the lines of profiles
                "y_dec": 2,         # number of decimals on y-axes (ensures correct spacing)
                "add_hline": 0,     # horizontal line at 0
                "sns_offset": 4,    # distance between y-axis and first bar in bar plot
                "error": "se",      # error type (standard error of mean) for bar plot
                "cmap": "Set1"      # colormap Set1
            }

    output_dir: str, optional
        path to output directory (default = $DIR_DATA_DERIV/roi_extract)
    output_base: str, optional
        basename for output. Will also be used to create a subfolder in <output_dir>. "_desc-<description>" will
        be appended automatically. Defaults to "roi_extract" (very insightful, I know..)
    verbose: bool, optional
        print progress to the terminal
    pos_neg: bool, optional
        Switch to different plotting function, by default False.
    do_fit: bool, optional
        If False, we'll only extract the data and will not perform deconvolution, by default True
    """
    def __init__(
        self, 
        proj_dir=None,
        order=None,
        peak=1,
        dec_kws={},
        plot_kws={},
        output_dir=None,
        output_base="roi_extract",
        verbose=False,
        pos_neg=False,
        do_fit=True,
        **kwargs
        ):
        self.proj_dir = proj_dir
        self.dec_kws = dec_kws
        self.plot_kws = plot_kws
        self.peak = peak
        self.order = order
        self.output_dir = output_dir
        self.output_base = output_base
        self.verbose = verbose
        self.pos_neg = pos_neg
        self.do_fit = do_fit

        if not isinstance(self.proj_dir, str):
            self.proj_dir = os.environ.get("DIR_DATA_HOME")

        if not isinstance(self.output_dir, str):
            self.output_dir = opj(self.proj_dir, "derivatives", "roi_extract", self.output_base)

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        # initiate ExtractSubjects class
        super().__init__(
            verbose=self.verbose,
            **kwargs
        )

        # check whether to do fit
        if self.do_fit:
            
            # parse onsets in a dataframe
            self.df_onsets = format_onsets(
                self.subjects,
                self.proj_dir
            )

            # check order
            if not isinstance(self.order, list):
                self.order = utils.get_unique_ids(
                    self.df_onsets,
                    id="event_type",
                    sort=False
                )

            # derive TR from functional dataframe
            self.t = utils.get_unique_ids(self.df_func, id="t")
            self.TR = np.diff(self.t)[0]
            
            # define default deconvolution parameters
            dec_defaults = {
                "interval": [-2,25],
                "basis_sets": "canonical_hrf_with_time_derivative",
                "verbose": self.verbose,
                "TR": self.TR
            }

            for key,val in dec_defaults.items():
                self.dec_kws = utils.update_kwargs(
                    self.dec_kws,
                    key,
                    val
                )

            ## fit
            self.run_fitter(**self.dec_kws)

            # plot
            if not self.pos_neg:
                self.generate_plot(**self.plot_kws)
            else:
                self.generate_plot2(**self.plot_kws)

        ## write output files
        self.write_csv_files()
        self.write_settings()

        ## done
        utils.verbose("Done", self.verbose)

    def run_fitter(
        self,
        **kwargs
        ):

        self.fitter = fitting.NideconvFitter(
            self.df_func,
            self.df_onsets,
            **kwargs
        )

        # get deconvolved timecourses
        self.fitter.timecourses_condition()

        # get subject-specific parameters
        self.fitter.parameters_for_tc_subjects(col_name="roi")

        # get condition-specific parameters
        self.fitter.parameters_for_tc_condition(col_name="roi")        

    def sort_rois(
        self, 
        ddict,
        base_color="#ffffff",
        fc=1
        ):

        # enforce int
        fc = int(fc)

        # get columns
        cols = list(self.fitter.tc_condition.columns)

        # cols 2 list
        cdict = {}
        color_list = []
        roi_list = []
        idx_list = []
        for key,val in ddict.items():
            cdict[key] = []
            for c in cols:
                if key in c:
                    cdict[key].append(c)

            roi_list += cdict[key]

            # create colormaps
            color_list += utils.make_between_cm(
                base_color,
                val,
                N=len(cdict[key])+fc,
                as_list=True
            )[fc:]

        for r in roi_list:
            idx_list.append(cols.index(r))

        return idx_list,roi_list,color_list

    def sort_dataframe(
        self, 
        df, 
        idx=None, 
        cols=None
        ):

        # sort columns or rows
        if isinstance(cols, (list,str)):
            return df[cols]
        else:
            subjs = utils.get_unique_ids(df, id="subject")
            new = []
            for subj in subjs:
                
                subj_df = utils.select_from_df(df, expression=f"subject = {subj}")
                evs = utils.get_unique_ids(subj_df, id="event_type")
                for ev in evs:
                    ev_df = utils.select_from_df(subj_df, expression=f"event_type = {ev}")
                    if "run" in list(subj_df.columns):
                        run_ids = utils.get_unique_ids(subj_df, id="run")

                        for run in run_ids:
                            run_df = utils.select_from_df(ev_df, expression=f"run = {run}")

                            tmp = run_df.reset_index()
                            new_df = tmp.iloc[:,idx]
                            new_df.set_index(list(subj_df.index.names), inplace=True)
                            new.append(new_df)
                    else:
                        tmp = ev_df.reset_index()
                        new_df = tmp.iloc[idx,:]
                        new_df.set_index(list(subj_df.index.names), inplace=True)

                        new.append(new_df)

            return pd.concat(new)

    def generate_plot(
        self, 
        include_pars=[
            "magnitude",
            "time_to_peak",
            "1st_deriv_time_to_peak",
            "2nd_deriv_time_to_peak",
            "rise_slope",
            "positive_area"
        ],
        time_col="time",
        write_files=True,
        cdict={},
        subjects=False,
        fc=1,
        **kwargs
        ):

        y_size = 4
        nrows = 1
        if isinstance(include_pars, (str,list)):
            if isinstance(include_pars, str):
                include_pars = [include_pars]

            nrows += len(include_pars)
            y_size = 4*(1+len(include_pars))

        fig = plt.figure(
            figsize=(len(self.order)*4,y_size),
            constrained_layout=True,
        )

        utils.verbose(f"Generating plot..", self.verbose)

        sfs = fig.subfigures(nrows=nrows)
        
        axs = {}
        for f_ix in range(nrows):
            if nrows<2:
                sf = sfs
            else:
                sf = sfs[f_ix]

            axs[f"ax{f_ix}"] = sf.subplots(ncols=4, sharey=True)

        for e,ev in enumerate(self.order):

            utils.verbose(f" ev-{e} | {ev}", self.verbose)
            expr = f"event_type = {ev}"
            ev_regr = utils.select_from_df(self.fitter.tc_condition, expression=expr)
            
            if subjects:
                use_df = self.fitter.avg_pars_subjects
            else:
                use_df = self.fitter.pars_condition

            ev_pars = utils.select_from_df(use_df, expression=expr)

            ax = axs["ax0"][e]

            # default cmap
            if len(cdict)<1:
                if not "color" in list(kwargs.keys()):
                    kwargs = utils.update_kwargs(
                        kwargs,
                        "cmap",
                        "Set1"
                    )
                else:
                    kwargs = utils.update_kwargs(
                        kwargs,
                        "palette",
                        kwargs["color"]
                    )

            else:

                # get information on how to sort dataframe
                t = self.sort_rois(cdict, fc=fc)

                # sort rows of parameter dataframe
                ev_pars = self.sort_dataframe(
                    ev_pars,
                    idx=t[0]
                )

                # sort columns or profile dataframe
                ev_regr = self.sort_dataframe(
                    ev_regr,
                    cols=t[1]
                )

                # add colors to kwargs
                kwargs = utils.update_kwargs(
                    kwargs,
                    "color",
                    t[2]
                )
                
            # set plotting defaults
            plot_defaults = {
                "line_width": 1,
                "y_dec": 2,
                "add_hline": 0,
                "error": "se",
                "font_size": 24,
                "add_points": False,
                "points_color": "k"
            }

            plot_defaults["title_size"] = plot_defaults["font_size"]*1.1

            for key,val in plot_defaults.items():
                kwargs = utils.update_kwargs(
                    kwargs,
                    key,
                    val
                )
            
            bar_lbl = None
            y_lbl = None
            if e == 0:
                y_lbl = "magnitude (%)"

            bs = plotting.LazyPlot(
                list(ev_regr.T.values),
                xx=utils.get_unique_ids(ev_regr, id=time_col),
                axs=ax,
                title = {
                    "title": ev.replace("_", " "),
                    "fontweight": "bold"
                },
                y_label=y_lbl,
                **kwargs
            )

            if isinstance(include_pars, list):

                for p_ix,par in enumerate(include_pars):

                    if e == 0:  
                        unit = "s"
                        par_lbl = par
                        if par == "magnitude":
                            unit = "%"
                        elif par in ["positive_area","undershoot"]:
                            unit = "au"
                        elif "1st_deriv" in par:
                            unit = "%/s"
                            par_lbl = "rate of change"
                        elif "2nd_deriv" in par:
                            unit = "%/s$^2$"
                            par_lbl = "acceleration"          

                        bar_lbl = f"{par_lbl.replace('_', ' ')} ({unit})"

                    b_ax = axs[f"ax{p_ix+1}"][e]
                    allowed_inputs = [
                        'magnitude', 
                        'fwhm', 
                        'time_to_peak', 
                        'half_rise_time', 
                        'half_max',	
                        'rise_slope', 
                        'rise_slope_t', 
                        'positive_area', 
                        'undershoot',
                        '1st_deriv_magnitude',
                        '1st_deriv_time_to_peak',
                        '2nd_deriv_magnitude',
                        '2nd_deriv_time_to_peak',
                    ]

                    if par not in allowed_inputs:
                        raise ValueError(f"Specified parameter '{par}' cannot be used. Must be one of {allowed_inputs}")
                    
                    # copy kwargs, but slight reduce fontsize
                    bar_kws = {}
                    for key,val in kwargs.items():
                        bar_kws[key] = val
                        
                    for key,val in zip(["font_size","label_size","sns_offset"],[bs.font_size,bs.label_size,4]):
                        bar_kws = utils.update_kwargs(
                            bar_kws,
                            key,
                            val,
                            force=True
                        )

                    n_rois = utils.get_unique_ids(ev_pars, id="roi", sort=False)
                    _ = plotting.LazyBar(
                        ev_pars,
                        x="roi",
                        y=par,
                        axs=b_ax,
                        y_label=bar_lbl,
                        **bar_kws
                    )
            else:

                n_rois = list(ev_regr.columns)

            if nrows>1:
                prof_sf = sfs[0]
            else:
                prof_sf = sfs

            prof_sf.supxlabel("time (s)", fontsize=bs.title_size)

            if nrows>1:
                sfs[-1].supxlabel("ROIs", fontsize=bs.title_size)

        fig.legend(
            labels=n_rois,
            bbox_to_anchor=(1.01,1),
            loc="upper left",
            frameon=False,
            fontsize=bs.label_size
        )

        # save figure
        if write_files:
            fname = opj(self.output_dir, f"{self.output_base}_desc-plot")
            utils.verbose(f"Writing plot files: {fname}", self.verbose)
            for ext in ["pdf","png","svg"]:
                fig.savefig(
                    f"{fname}.{ext}",
                    bbox_inches="tight",
                    facecolor="white",
                    dpi=300
                )

    def generate_plot2(
        self, 
        use_colors=["#D97F75","#9ABDD4"],
        time_col="time",
        write_files=True,
        cdict={},
        subjects=False,
        fc=1,
        **kwargs
        ):

        y_size = 4
        nrows = 1
        if isinstance(include_pars, (str,list)):
            if isinstance(include_pars, str):
                include_pars = [include_pars]

            nrows += len(include_pars)
            y_size = 4*(1+len(include_pars))

        fig = plt.figure(
            figsize=(len(self.order)*4,y_size),
            constrained_layout=True,
        )

        utils.verbose(f"Generating plot..", self.verbose)

        sfs = fig.subfigures(nrows=nrows)
        
        axs = {}
        for f_ix in range(nrows):
            if nrows<2:
                sf = sfs
            else:
                sf = sfs[f_ix]

            axs[f"ax{f_ix}"] = sf.subplots(ncols=4, sharey=True)

        for e,ev in enumerate(self.order):

            utils.verbose(f" ev-{e} | {ev}", self.verbose)
            expr = f"event_type = {ev}"
            
            ev_regr = utils.select_from_df(self.fitter.tc_condition, expression=expr)
            if subjects:
                subjs_df = utils.select_from_df(self.fitter.tc_subjects, expression=expr)
                subjs_df = ev_regr.groupby(["subject","event_type","t"]).mean()

            # set plotting defaults
            ax = axs["ax0"][e]
            plot_defaults = {
                "line_width": 3,
                "y_dec": 2,
                "add_hline": 0,
                "error": "se",
                "font_size": 24
            }

            plot_defaults["title_size"] = plot_defaults["font_size"]*1.1

            for key,val in plot_defaults.items():
                kwargs = utils.update_kwargs(
                    kwargs,
                    key,
                    val
                )
            
            y_lbl = None
            if e == 0:
                y_lbl = "magnitude (%)"

            bs = plotting.LazyPlot(
                list(ev_regr.T.values),
                xx=utils.get_unique_ids(ev_regr, id=time_col),
                axs=ax,
                title = {
                    "title": ev.replace("_", " "),
                    "fontweight": "bold"
                },
                y_label=y_lbl,
                **kwargs
            )

            if nrows>1:
                prof_sf = sfs[0]
            else:
                prof_sf = sfs

            prof_sf.supxlabel("time (s)", fontsize=bs.title_size)

        # save figure
        if write_files:
            fname = opj(self.output_dir, f"{self.output_base}_desc-plot")
            utils.verbose(f"Writing plot files: {fname}", self.verbose)
            for ext in ["pdf","png","svg"]:
                fig.savefig(
                    f"{fname}.{ext}",
                    bbox_inches="tight",
                    facecolor="white",
                    dpi=300
                )

    def write_csv_files(self):

        utils.verbose(f"Writing csv-files to {self.output_dir}..", self.verbose)

        if self.do_fit:
            out_dict = {
                "hrfs": getattr(self.fitter, "hrfs"),
                "pars_run": getattr(self.fitter, "pars_subjects"),
                "pars_avg": getattr(self.fitter, "avg_pars_subjects"),
                "tcs": getattr(self, "df_func"),
                "pars_evs": getattr(self, "df_onsets"),
                "pars_evs": getattr(self, "pars_condition"),
            }
        else:
            out_dict = {
                "tcs": getattr(self, "df_func")
            }

        for key,val in out_dict.items():
            val.to_csv(opj(self.output_dir, f"{self.output_base}_desc-{key}.csv"))

    def write_settings(self):

        utils.verbose(f"Generating settings file", self.verbose)

        if self.do_fit:
            settings = {
                "date": datetime.datetime.now(),
                "subject": self.subjects,
                "rois": self.roi_list,
                "fit": self.do_fit,
                "TR": self.fitter.TR,
                "unit": "seconds",
                "basis_sets": self.fitter.basis_sets,
                "interval": self.fitter.interval,
                "project_dir": self.proj_dir,
                "input_dir": self.ft_dir,
                "output_dir": self.output_dir,
                "output_base": self.output_base
            }
        else:
            settings = {
                "date": datetime.datetime.now(),
                "subject": self.subjects,
                "rois": self.roi_list,
                "fit": self.do_fit,
                "TR": self.TR,
                "unit": "seconds",
                "project_dir": self.proj_dir,
                "input_dir": self.ft_dir,
                "output_dir": self.output_dir,
                "output_base": self.output_base
            }

        settings_for_json = json.dumps(
            settings, 
            indent=4, 
            cls=DateTimeEncoder
        )

        fname = opj(self.output_dir, f"{self.output_base}_desc-settings.json")
        with open(fname, "w") as outfile:
            outfile.write(settings_for_json)
