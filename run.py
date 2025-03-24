#!/usr/bin/env python
"""The run script."""
import logging
import os
import sys
import bids
from datetime import datetime
from io import StringIO

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
from utils.parser import parse_input_files

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
    """
    Steps in main:
    1. Parse the config and other options from the context, both gear and app options.
    2. Download the dataset.
    3. Initialize BIDS layout.
    4. Process each subject and create a new analysis container for each.
    5. Upload the output files to the analysis container.
    """

    print('Step 1: Parsing config')
    # Initialize Flywheel context and configuration
    context = flywheel.GearContext()
    config = context.config
    input_container, config, manifest, which_model = parse_config(context)
    
    # Download the dataset 
    print('Step 2: Downloading dataset')
    subses = download_dataset(context, input_container, config)
    print(f"subses: {subses}")

    # Initialize BIDS layout
    print('Step 3: Initializing BIDS layout')
    layout = bids.BIDSLayout(root=f'{config["work_dir"]}/rawdata', derivatives=f'{config["work_dir"]}/derivatives')
    
    # Process each subject and create a new analysis container for each
    print('Step 4: Processing each subject')
    for sub in subses.keys():
            for ses in subses[sub].keys():
                raw_fnames, deriv_fnames, logs = fw_process_subject(layout, sub, ses, which_model, config)
        
                # Check for missing input or output
                if not raw_fnames:
                    gb._logprint(f"[SKIPPING] No input files for {sub}/{ses}.")
                    continue
                if not deriv_fnames:
                    gb._logprint(f"[ERROR] Processing failed for {sub}/{ses}: No derived output.")
                    # Delete files in raw_fnames because derived output is missing
                    for file_path in raw_fnames:
                        try:
                            os.remove(file_path)
                            gb._logprint(f"Deleted raw file: {file_path}")
                        except Exception as e:
                            gb._logprint(f"Error deleting {file_path}: {e}")
                    continue

                out_files = []
                out_files.extend(raw_fnames)
                out_files.extend(deriv_fnames)
                out_files.extend(logs)

                # Create a new analysis
                gversion = manifest["version"]
                gname = manifest["name"]
                gdate = datetime.now().strftime("%Y%M%d_%H:%M:%S")
                image = manifest["custom"]["gear-builder"]["image"]
                session_container = context.client.get(subses[sub][ses])
                
                analysis = session_container.add_analysis(label=f'{gname}/{gversion} {gdate}')
                analysis.update_info({"gear":gname,
                                    "version":gversion, 
                                    "image":image,
                                    "Date":gdate,
                                    "status": "failed" if not deriv_fnames else "success",
                                    "note": "No derived outputs, processing may have failed." if not deriv_fnames else "",
                                    **config})

                for file in out_files:
                    gb._logprint(f"Uploading output file: {os.path.basename(file)}")
                    analysis.upload_output(file)


            # if not os.path.exists(config['output_dir']):
            #     os.makedirs(config['output_dir'])

# The main function for processing a subject
def fw_process_subject(layout, sub, ses, which_model, config):
    """
    Run the model on the input files for a subject and session.

    Args:
        layout (Layout): The BIDS Layout object.
        sub (str): The subject ID.
        ses (str): The session ID.
        which_model (str): The model to use.
        config (dict): The configuration dictionary.

    Returns:
        list: The list of raw filenames.
        list: The list of derivative filenames.
    """

    # Set up in-memory log capture for this subject
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Attach handler to root logger
    logger = logging.getLogger()
    logger.addHandler(handler)
    logs = []

    try:
        logging.info(f"Processing subject {sub} session {ses}")

        print('Parsing input files')
        print(f"sub: {sub}, ses: {ses}")
        
        my_files = parse_input_files(layout, sub, ses)
        print(my_files)
        
        gb._logprint(f'Starting for {sub}-{ses}')


        all_t2 = [*my_files['axi'], *my_files['sag'], *my_files['cor']]

        deriv_fnames = []
        raw_fnames = [x.path for x in all_t2]

        for f in raw_fnames:
            try:
                gb._logprint(f"Input file: {f}")

                print('Setting up options for model')
                logging.info(f"Setting up options for model {which_model}")
                # Pass the current file to TestOptions if needed.
                opt = TestOptions(which_model=which_model, config=config, sub=sub, ses=ses, image=f).parse()
                
                print('Registering images')
                logging.info(f"Registering images for {sub}-{ses}")
                input_image = Registration(opt.image, opt.reference, sub, ses)

                if input_image is None:
                    logging.warning(f"Registration failed for subject {sub} session {ses}. Skipping this iteration.")
                    continue  # Skip to the next iteration if registration fails

                print('Creating model')
                logging.info(f"Creating model for {sub}-{ses}")
                model = create_model(opt)
                model.setup(opt)

                print('Running inference')
                logging.info(f"Running inference for {sub}-{ses}")
                fname = inference(model, input_image, opt.result_sr, opt.resample, opt.new_resolution,
                                opt.patch_size[0], opt.patch_size[1], opt.patch_size[2],
                                opt.stride_inplane, opt.stride_layer, 1)
                
                if fname:
                    deriv_fnames.append(fname)
                    logging.info("Inference completed")
                    logging.info(f"Output file: {fname}")
                else:
                    logging.error("Inference failed")
                    logging.error("No output file generated")
            except Exception as e:
                # Log the error for this file and continue with the next one.
                logging.error(f"Error processing file {f} for subject {sub} session {ses}: {e}")
                continue  # Continue with the next file

        # for f in raw_fnames:
        #     gb._logprint(f"Input file: {f}")

        #     print('Setting up options for model')
        #     logging.info(f"Setting up options for model {which_model}")
        #     # NOTE: Need to pass input, output dirs here!!
        #     opt = TestOptions(which_model=which_model, config=config, sub=sub, ses=ses, image = f).parse()
            
        #     print('Registering images')
        #     logging.info(f"Registering images for {sub}-{ses}")
        #     input_image = Registration(opt.image, opt.reference, sub, ses)

        #     if input_image is None:
        #         logging.warning(f"Registration failed for subject {sub} session {ses}. Skipping this iteration.")
        #         continue  # Skip to the next iteration of the loop

        #     print('Creating model')
        #     logging.info(f"Creating model for {sub}-{ses}")
        #     model = create_model(opt)
        #     model.setup(opt)

        #     print('Running inference')
        #     logging.info(f"Running inference for {sub}-{ses}")
        #     fname = inference(model, input_image, opt.result_sr, opt.resample, opt.new_resolution, opt.patch_size[0],
        #             opt.patch_size[1], opt.patch_size[2], opt.stride_inplane, opt.stride_layer, 1)
            
            if fname:
                deriv_fnames.append(fname)
                logging.info(f"Inference completed")
                logging.info(f"Output file: {fname}")
            else:
                logging.error(f"Inference failed")
                logging.error(f"No output file generated")

    except Exception as e:
        logging.error(f"Error processing subject {sub} session {ses}: {e}")
        # raise e

    finally:
        # Write captured log to file
        log_contents = log_stream.getvalue()
        # log_filename = os.path.join(gear_context.output_dir, f"sub-{sub}_ses-{ses}_log.txt")
        log_filename = os.path.join(gear_context.work_dir, f"sub-{sub}_ses-{ses}_log.txt")
        with open(log_filename, 'w') as f:
            f.write(log_contents)

        # Clean up
        logger.removeHandler(handler)
        log_stream.close()

        # Append log filename to logs list
        logs.append(log_filename)

    return raw_fnames, deriv_fnames, logs

# Only execute if file is run as main, not when imported by another module
if __name__ == "__main__":  # pragma: no cover
    # Get access to gear config, inputs, and sdk client if enabled.
    with GearToolkitContext() as gear_context:

        # Initialize logging, set logging level based on `debug` configuration
        # key in gear config.
        gear_context.init_logging()

        # Pass the gear context into main function defined above.
        main(gear_context)
