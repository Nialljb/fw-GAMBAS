#!/usr/bin/env python
"""The run script."""
import logging
import os
import sys
import bids
import warnings
from datetime import datetime

# import flywheel functions
from flywheel_gear_toolkit import GearToolkitContext
import flywheel

from utils.parser import parse_config
from utils.parser import download_dataset
from options.test_options import TestOptions
from models import create_model
from app.main import inference
from app.main import Registration
import utils.bids as gb

# Add top-level package directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Verify sys.path
print("sys.path:", sys.path)
os.environ["PATH"] += os.pathsep + "/opt/ants-2.5.4/bin"

# The gear is split up into 2 main components. The run.py file which is executed
# when the container runs. The run.py file then imports the rest of the gear as a
# module.

log = logging.getLogger(__name__)


def main(context: GearToolkitContext) -> None:
    # """Parses config and runs."""

    print('Parsing config')
    # Initialize Flywheel context and configuration
    context = flywheel.GearContext()
    config = context.config
    input_container, config, manifest, which_model = parse_config(context)
    
    # Download the dataset 
    subses = download_dataset(context, input_container, config)
    print(f"subses: {subses}")

    # Initialize BIDS layout
    layout = bids.BIDSLayout(root=f'{config["work_dir"]}/rawdata', derivatives=f'{config["work_dir"]}/derivatives')
    
    # Process each subject and create a new analysis container for each
    for sub in subses.keys():
            for ses in subses[sub].keys():
                raw_fnames, deriv_fnames = fw_process_subject(layout, sub, ses, which_model, config)
        
                out_files = []
                out_files.extend(raw_fnames)
                out_files.extend(deriv_fnames)

                # Create a new analysis
                gversion = manifest["version"]
                gname = manifest["name"]
                gdate = datetime.now().strftime("%Y%M%d_%H:%M:%S")
                image = manifest["custom"]["gear-builder"]["image"]
                session_container = context.client.get(subses[sub][ses])
                
                analysis = session_container.add_analysis(label=f'{gname}/{gversion}/{gdate}')
                analysis.update_info({"gear":gname,
                                    "version":gversion, 
                                    "image":image,
                                    "Date":gdate,
                                    **config})


                for file in out_files:
                    gb._logprint(f"Uploading output file: {os.path.basename(file)}")
                    analysis.upload_output(file)

            gb._logprint("Copying output files")

            if not os.path.exists(config['output_dir']):
                os.makedirs(config['output_dir'])



def parse_input_files(layout, sub, ses, show_summary=True):

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

        else:
            if len(files) == 1:
                my_files[ax] = files
            elif len(files) > 1:
                my_files[ax] = [files[0]]
            else:
                warnings.warn(f"Found no {ax} scans")
    
    if show_summary:
        print(f"--- SUB: {sub}, SES: {ses} ---")
        print(f"Axial: {len(my_files['axi'])} scans")
        # print(f"Cor: {len(my_files['cor'])} scans")
        # print(f"Sag: {len(my_files['sag'])} scans")

    return my_files


def fw_process_subject(layout, sub, ses, which_model, config):
    """
    Process the Unity QA data for a subject.

    Args:
        layout (Layout): The BIDS Layout object.
        sub (str): The subject ID.
        ses (str): The session ID.

    Returns:
        None
    """

    print('Parsing input files')
    print(f"sub: {sub}, ses: {ses}")
    
    my_files = parse_input_files(layout, sub, ses)
    print(my_files)
    
    gb._logprint(f'Starting for {sub}-{ses}')


    all_t2 = [*my_files['axi'], *my_files['sag'], *my_files['cor']]

    deriv_fnames = []
    raw_fnames = [x.path for x in all_t2]

    print('Setting up options for model')
    # NOTE: Need to pass input, output dirs here!!
    opt = TestOptions(which_model=which_model, config=config, sub=sub, ses=ses).parse()

    print('Registering images')
    input_image = Registration(opt.image, opt.reference, sub, ses)
    # sitk.WriteImage(image, outPath)

    print('Creating model')
    model = create_model(opt)
    model.setup(opt)

    print('Running inference')
    fname = inference(model, input_image, opt.result_sr, opt.resample, opt.new_resolution, opt.patch_size[0],
              opt.patch_size[1], opt.patch_size[2], opt.stride_inplane, opt.stride_layer, 1)
    
    deriv_fnames.append(fname)

    return raw_fnames, deriv_fnames

# Only execute if file is run as main, not when imported by another module
if __name__ == "__main__":  # pragma: no cover
    # Get access to gear config, inputs, and sdk client if enabled.
    with GearToolkitContext() as gear_context:

        # Initialize logging, set logging level based on `debug` configuration
        # key in gear config.
        gear_context.init_logging()

        # Pass the gear context into main function defined above.
        main(gear_context)
