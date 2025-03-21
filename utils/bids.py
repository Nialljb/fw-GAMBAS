import subprocess as sp
import os
import json
import shlex
from datetime import datetime

### Helper functions ###

def _logprint(s):
    t = datetime.now().strftime("%H:%M:%S")
    print(f"[{t}] {s}", flush=True)

### Tools to use ###
def import_dicom_folder(dicom_dir, sub_name, ses_name, config, projdir, skip_dcm2niix=False):
    """
    Imports DICOM files from a specified directory into the BIDS format.

    Args:
        dicom_dir (str): The path to the directory containing the DICOM files.
        sub_name (str): The subject name for the BIDS dataset.
        ses_name (str): The session name for the BIDS dataset.
        config (str): The path to the configuration file for dcm2bids.
        projdir (str): The path to the project directory where the BIDS dataset will be created.

    Returns:
        None
    """

    cmd = f'dcm2bids --force_dcm2bids -d {shlex.quote(dicom_dir)} -p {sub_name} -s {ses_name} -c {config} -o {projdir}/rawdata -l DEBUG'
    if skip_dcm2niix:
        cmd += ' --skip_dcm2niix'
    sp.Popen(shlex.split(cmd)).communicate()


def setup_bids_directories(projdir):
    """
    Set up the necessary BIDS directories and files for a project.

    Args:
        projdir (str): The path to the project directory.

    Returns:
        None
    """

    # Check for basic folders
    for f in ['rawdata', 'sourcedata', 'derivatives']:
        if not os.path.exists(f'{projdir}/{f}'):
            os.makedirs(f'{projdir}/{f}')
    
    def dump_description(fname, D):
        if not os.path.exists(fname):
            with open(fname, 'w') as f:
                json.dump(D,f,indent=4)

    # Check for dataset description    
    dump_description(fname=f'{projdir}/rawdata/dataset_description.json',
                     D={"Name": "GAMBAS rawdata", "BIDSVersion": "1.0.2"})
    
    dump_description(fname=f'{projdir}/sourcedata/dataset_description.json',
                     D={"Name": "GAMBAS sourcedata dataset", "BIDSVersion": "1.0.2", "GeneratedBy": [{"Name":"GAMBAS"}]})
    
    dump_description(fname=f'{projdir}/derivatives/dataset_description.json',
                     D={"Name": "GAMBAS derivatives dataset", "BIDSVersion": "1.0.2", "GeneratedBy": [{"Name":"GAMBAS"}]})

    dump_description(fname = f'{projdir}/dataset_description.json',
                     D={"Name": "UNITY example dataset", "BIDSVersion": "1.0.2"})
    