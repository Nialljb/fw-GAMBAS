"""Parser module to parse gear config.json."""

from typing import Tuple
import os
import re
from flywheel_gear_toolkit import GearToolkitContext
import flywheel
import json
import os
import subprocess
from string import ascii_lowercase as alc
import warnings
from datetime import datetime
import logging

from utils.bids import import_dicom_folder, setup_bids_directories

def check_gpu():
    """Check if the container has access to a GPU."""
    try:
        # Check if NVIDIA GPUs are available
        result = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print("GPU detected!")
            return True
        else:
            print("No GPU detected.")
            return False
    except FileNotFoundError:
        print("nvidia-smi not found. No GPU available.")
        return False


def parse_config(context):
    """Parse the config and other options from the context, both gear and app options.

    Returns:
        file output label
        model name
    """

    # Check if the container has access to a GPU
    is_gpu = check_gpu()
    if is_gpu:
        print("Running on GPU")
        model = 'GAMBAS'
    else:
        print("Running on CPU")
        model = 'ResCNN'
    
    base_dir = '/flywheel/v0'
    input_dir = base_dir + '/input/'
    work_dir = base_dir + '/work/'
    output_dir = base_dir + '/output/'
    # Get the input file id
    input_container = context.client.get_analysis(context.destination["id"])
    
    input_id = input_container.parent.id
    container = context.client.get(input_id)
    # print(f"Container type: {container.container_type}")

    # Read config.json file
    with open(base_dir + '/config.json') as f:
        config = json.load(f)

    # Read manifest.json file
    with open(base_dir + '/manifest.json') as f:
        manifest = json.load(f)
    
    inputs = config['inputs']
    
    config = config['config']
    config['input_dir'] = input_dir
    config['work_dir'] = work_dir
    config['output_dir'] = output_dir
    config['bids_config_file'] = base_dir + '/utils/dcm2bids_config.json'
    
    return container, config, manifest, model


def download_dataset(gear_context: GearToolkitContext, container, config):
    
    work_dir = config['work_dir']
    force_run = config['force_run']

    setup_bids_directories(work_dir)
    import_options = {'config': config['bids_config_file'], 'projdir': work_dir, 'skip_dcm2niix': True}

    source_data_dir = os.path.join(work_dir, 'sourcedata')
    os.makedirs(source_data_dir, exist_ok=True)
    
    print(f"Downloading {container.label}...")
    print(f"Container type: {container.container_type}" )

    if container.container_type == 'file':
        ses_container = gear_context.client.get(container.parents.session)
        sub_label = make_subject_label(gear_context.client.get(container.parents.subject))
        ses_label = make_session_label(ses_container)
        ses_id = ses_container.id

        for acq in ses_container.acquisitions.iter():
            for file in acq.files:
                if container.id == file.id:
                    download_file(file, ses_dir, dry_run=False)
        return {sub_label: {ses_label: ses_id}}

    # Need to have a condition to check if a single file has been uploaded. If so this means there may have been multiple in a session and this is the file to process
    # If this is the case should copy it to the same directory as the other files and then process as normal without going through the download process

    elif container.container_type == 'project':
        proj_label, subjects = download_project(container, source_data_dir, force_run, dry_run=False)
        print(f"Downlaoded project data, moving on to making BIDS structure...")

        output = {}
        for sub in subjects.keys():
            output[sub] = {}
            sessions = subjects[sub]

            for ses in sessions.keys():
                print(f"Importing {sub} {ses}...")
                import_dicom_folder(dicom_dir=subjects[sub][ses]['folder'], sub_name=sub, ses_name=ses, **import_options)
                output[sub][ses] = subjects[sub][ses]['id']

        return output

    elif container.container_type == 'subject':
        proj_label = gear_context.client.get(container.parents.project).label
        source_data_dir = os.path.join(source_data_dir, proj_label)
        
        sub_label, sessions = download_subject(container, source_data_dir, force_run, dry_run=False)
        
        output = {sub_label:{}}

        for ses in sessions.keys():
            import_dicom_folder(dicom_dir=sessions[ses]['folder'], sub_name=sub_label, ses_name=ses, **import_options)
            output[sub_label][ses] = sessions[ses]['id']
        
        return output

    elif container.container_type == 'session':
        proj_label = gear_context.client.get(container.parents.project).label
        sub_label = make_subject_label(gear_context.client.get(container.parents.subject))
        source_data_dir = os.path.join(source_data_dir, proj_label, sub_label)
        
        ses_label, ses_dir, ses_id = download_session(container, source_data_dir, force_run, dry_run=False)
        import_dicom_folder(dicom_dir=ses_dir, sub_name=sub_label, ses_name=ses_label, **import_options)

        return {sub_label: {ses_label: ses_id}}


def make_session_label(ses) -> str:
    return ses.label.split()[0].replace("-",'').replace("_", "")

# Forcing BIDS compliance by removing spaces and dashes in subject labels
def make_subject_label(sub) -> str:
    return sub.label.replace("-", '').replace(" ", '').replace("_", "") #'P'+sub.label.split('-')[1]

def make_project_label(proj) -> str:
    return proj.replace("-", '_').replace(" ", '')

def download_file(file, my_dir, dry_run=False) -> str:
    do_download = False

    # Convert file name to lowercase for case-insensitive checks
    file_name_lower = file.name.lower()

    # Check for required substrings and exclusions
    if file['type'] in ['source code', 'nifti']:
        if 'T2' in file.name and ('axi' in file_name_lower or 'AXI' in file.name):
            if not any(excluded in file_name_lower for excluded in ['mapping', 'align', 'brain']): # 'diagnostic', 
                do_download = True
    
    if do_download:
        download_dir = my_dir
        os.makedirs(download_dir, exist_ok=True)
        
        try:
            if dry_run:
                print(f"[DRY RUN] Would have downloaded: {file.name}")
            else:
                fpath = os.path.join(download_dir, file.name)
                if not os.path.exists(fpath):
                    file.download(fpath)
                else:
                    print("File already downloaded")

        except Exception as e:
            print(f"Error downloading {file.name}: {e}")

        print(f"Downloaded file: {file.name}")

    return file.name


def download_session(ses_container, sub_dir, force_run, dry_run=False) -> Tuple[str, str]:
    print("--- Downloading session ---")
    print(f"Session label: {ses_container.label}")
    print(f"Acquisitions: {len(ses_container.acquisitions())}")
    print(f"force_run: {force_run}")

    ses_label = make_session_label(ses_container)
    ses_dir = os.path.join(sub_dir, ses_label)
    ses_id = ses_container.id

    if force_run:
        print(f"[FORCE RUN] Skipping age check and saving data into: {ses_dir}")
        proceed = True
        age = "unknown"  # Optional, if you still want to log age
    else:
        age_check, age = check_age(ses_id)
        if not age_check:
            print(f"Age {age} is not within the model range 3 months - 3 years")
            proceed = False
        else:
            print(f"Saving data into: {ses_dir}")
            proceed = True

    if proceed:
        for acq in ses_container.acquisitions.iter():
            for file in acq.files:
                download_file(file, ses_dir, dry_run=dry_run)

    return ses_label, ses_dir, ses_id


def download_subject(sub_container, proj_dir, force_run, dry_run=False):
    print("--- Downloading subject ---")
    print(f"Label: {sub_container.label}")
    print(f"Sessions: {len(sub_container.sessions())}")
    
    sub_label = make_subject_label(sub_container)
    sub_dir = os.path.join(proj_dir, sub_label)
    # print(f"Saving data into: {sub_dir}")
    
    sessions_out = {}

    for ses in sub_container.sessions.iter():
        ses_label0, ses_dir, ses_id = download_session(ses, sub_dir, force_run, dry_run=dry_run)

        # Check for duplicate session labels
        ses_label = ses_label0; i = 0
        
        while ses_label in sessions_out:
            ses_label = ses_label0 + alc[i]
            i += 1
        

        sessions_out[ses_label] = {'folder':ses_dir, 'id':ses_id}

    return sub_label, sessions_out


def download_project(project, my_dir, force_run, dry_run=False):
    print("--- Downloading project ---")
    print(f"Label: {project.label}")
    print(f"Subjects: {project.stats.number_of.subjects}")
    print(f"Sessions: {project.stats.number_of.sessions}")
    print(f"Acquisitions: {project.stats.number_of.acquisitions}")
    
    proj_name = make_project_label(project.label)
    my_dir = os.path.join(my_dir, proj_name)
    # print(f"Saving data into: {my_dir}")
    
    subjects_out = {}
    for sub in project.subjects.iter():
        sub_lab, sessions_dict = download_subject(sub, my_dir, force_run, dry_run=dry_run)
        subjects_out[sub_lab] = sessions_dict

    return proj_name, subjects_out


def parse_input_files(layout, sub, ses, show_summary=True):
    logger = logging.getLogger(__name__)

    try:
        # Example: Validate input layout
        if not layout:
            logger.error("No layout provided. Exiting parse_input_files.")
            raise ValueError("Empty layout provided")
        else:
            my_files = {'axi':[], 'sag':[], 'cor':[]}

            for ax in my_files.keys():
                files = layout.get(scope='raw', extension='.nii.gz', subject=sub, reconstruction=ax, session=ses)
                
                if ax == 'axi':

                    if len(files)==2:
                        axi1 = layout.get(scope='raw', extension='.nii.gz', subject=sub, reconstruction='axi', session=ses, run=1)[0]
                        axi2 = layout.get(scope='raw', extension='.nii.gz', subject=sub, reconstruction='axi', session=ses, run=2)[0]
                        my_files['axi'] = [axi1, axi2]

                    elif len(files)==1:
                        my_files['axi'] = layout.get(scope='raw', extension='.nii.gz', subject=sub, reconstruction='axi', session=ses)
                    
                    else:
                        warnings.warn(f'Expected to find 1 or 2 axial scans. Found {len(files)} axial scans')
                        logging.info(f'Expected to find 1 or 2 axial scans. Found {len(files)} axial scans')
                else:
                    if len(files) == 1:
                        my_files[ax] = files
                    elif len(files) > 1:
                        my_files[ax] = [files[0]]
                    else:
                        warnings.warn(f"Found no {ax} scans")
    except Exception as e:
        logger.exception(f"Exception encountered in parse_input_files: {e}")
        raise

    if show_summary:
        print(f"--- SUB: {sub}, SES: {ses} ---")
        print(f"Axial: {len(my_files['axi'])} scans")
        # print(f"Cor: {len(my_files['cor'])} scans")
        # print(f"Sag: {len(my_files['sag'])} scans")

    return my_files

def check_age(ses_id):
    """Check if the age is within the model range 3months - 3 years"""
    # check custom fields for age, then check Age field, then check dicom headers
    context = flywheel.GearContext()
    ses = context.client.get(ses_id)

    # Read config.json file
    p = open('/flywheel/v0/config.json')
    config = json.loads(p.read())
    # Read API key in config file
    api_key = (config['inputs']['api-key']['key'])
    fw = flywheel.Client(api_key=api_key)

    print(f"Checking age in session demographic sync...")
    age_in_months = 0
    if 'age_at_scan_months' in ses.info and ses.info['age_at_scan_months'] not in (0, None): 
        age_in_months = ses.info['age_at_scan_months']
        print(f"Age in months in session demographic sync: {age_in_months}")
    else:
        print("No age in session demographic sync...")
        print("Checking age in dicom header...")
        for acq in ses.acquisitions.iter():
            acq = acq.reload()
            if 'T2' in acq.label and 'AXI' in acq.label and 'Segmentation' not in acq.label and 'Align' not in acq.label: 
                for file_obj in acq.files: # get the files in the acquisition
                    # Screen file object information & download the desired file
                    if file_obj['type'] == 'dicom':
                        dicom_header = fw._fw.get_acquisition_file_info(acq.id, file_obj.name)
                        print(f"Acquisition label: {acq.label}")
                        if 'PatientBirthDate' in dicom_header.info:
                            print("Checking DOB in dicom header...")
                            try:
                                dob = dicom_header.info['PatientBirthDate']
                                seriesDate = dicom_header.info['SeriesDate']
                                # Validate date format and presence of SeriesDate
                                if not seriesDate:
                                    raise ValueError("SeriesDate is missing")
                                    
                                # Calculate age at scan
                                age = (datetime.strptime(seriesDate, '%Y%m%d')) - (datetime.strptime(dob, '%Y%m%d'))
                                age_in_days = age.days
                                age_in_months = int(age_in_days / 30.44)
                                print(f"Age in months in dicom header: {age_in_months}")

                                # Sanity check for negative ages or unreasonable values
                                if age_in_days < 0:
                                    raise ValueError(f"Invalid age calculation: {age_in_days} days")
                                        
                            except ValueError as e:
                                print(f"Error processing dates: {e}")
                                raise

                        elif 'PatientAge' in dicom_header.info:
                            print("No DOB in dicom header or age in session info! Trying PatientAge from dicom...")
                            try:
                                age = dicom_header.info['PatientAge']
                                if not age:
                                    raise ValueError("PatientAge is empty")
                                    
                                if age.endswith('M'):
                                    # Remove leading zeros and 'M', then convert to int
                                    age_in_months = int(age.rstrip('M').lstrip('0'))
                                    if age_in_months == 0:
                                        raise ValueError("Age cannot be 0 months")
                                    age_in_days = int(age_in_months * 30.44)
                                else:
                                    # Original case for days ('D')
                                    age = re.sub('\D', '', age)
                                    age_in_days = int(age)
                                    age_in_months = int(age_in_days / 30.44)
                                    
                                # Sanity check
                                if age_in_days < 0 or age_in_days > 36500:
                                    raise ValueError(f"Unreasonable age value: {age_in_days} days")
                                    
                            except (ValueError, TypeError) as e:
                                print(f"Error processing DICOM age: {e}")
                                raise
                        else:
                            print("No age at scan in session info label! Ask PI...")
                            raise ValueError("No valid age information found")
        
    # accept age in months between 1 and 42 months (3.5 years)
    if age_in_months > 1 and age_in_months < 42:
        return True, age_in_months
    else:
        return False, age_in_months



