import flywheel
from pathlib import Path
from options.base_options import BaseOptions  # BaseOptions is defined elsewhere
from utils.parser import parse_config

def get_gambas_basename(in_dir, which_model):
    """
    Given an input directory and model name, returns a modified NIfTI basename
    with '_gambas' or '_ResCNN' inserted before the extension.

    Parameters:
        in_dir (Path): Path to the input directory
        which_model (str): 'GAMBAS' or other (e.g. 'ResCNN')

    Returns:
        str: Modified NIfTI filename
    """
    
    print(in_dir)

    # Find .nii or .nii.gz files
    nii_files = list(in_dir.glob("*.nii.gz"))

    if not nii_files:
        raise FileNotFoundError("No NIfTI files found in the anat directory.")

    # Use the first file found
    original_file = nii_files[0]
    base = original_file.name

    suffix = "_gambas.nii.gz" if which_model == 'GAMBAS' else "_ResCNN.nii.gz"

    # Append '_gambas' before extension
    if base.endswith(".nii.gz"):
        gambas_basename = base.replace(".nii.gz", suffix)
    else:
        raise ValueError("Unsupported file type")

    print(f"Using {gambas_basename} as the output basename.")
    return gambas_basename


class TestOptions(BaseOptions):
    def __init__(self, which_model, config, sub, ses):
        super().__init__()  # Initialize parent class
        self.which_model = which_model  # Store which_model as an instance variable
        self.config = config
        self.sub = sub
        self.ses = ses

    def initialize(self, parser):
        # Initialize parser from BaseOptions
        parser = BaseOptions.initialize(self, parser)
        
        # Determine GPU setting based on model
        gpu_index = '0' if self.which_model == 'GAMBAS' else '-1'
        gpu_setting = 'gpu' if self.which_model == 'GAMBAS' else 'cpu'
        netG = 'i2i_mamba' if self.which_model == 'GAMBAS' else 'res_cnn'

        # Update gpu_ids argument in base options
        parser.set_defaults(gpu_ids=gpu_index)
        parser.set_defaults(name=gpu_setting)
        parser.set_defaults(netG=netG)

        in_dir = Path(f"/flywheel/v0/work/rawdata/sub-{self.sub}/ses-{self.ses}/anat")
        output_path = Path(f"/flywheel/v0/work/derivatives/sub-{self.sub}/ses-{self.ses}/anat")
        output_path.mkdir(parents=True, exist_ok=True)

        m = self.which_model
        output_label = get_gambas_basename(in_dir, m)

        # Define default input and output directories
        parser.add_argument("--input_dir", type=str, default=in_dir, help="Path to input directory")
        parser.add_argument("--output_dir", type=str, default=output_path, help="Path to output directory")

        # Find the first available NIfTI file in input directory
        input_files = list(Path(parser.get_default("input_dir")).glob("*.nii.gz"))
        if not input_files:
            raise FileNotFoundError("No NIfTI image found in the input directory.")

        parser.add_argument("--image", type=str, default=str(input_files[0]), help="Path to input NIfTI image")
        parser.add_argument("--reference", type=str, default="/flywheel/v0/app/TemplateKhula.nii", help="Path to reference NIfTI image")
        parser.add_argument("--result_sr", type=str, default=str(Path(parser.get_default("output_dir")) / output_label), help="Path to save the result NIfTI file")
        
        # Parse additional configuration arguments
        parser.add_argument("--phase", type=str, default=self.config.get("phase", "test"), help="Test phase")
        parser.add_argument("--which_epoch", type=str, default=self.config.get("which_epoch", "latest"), help="Epoch to load")
        parser.add_argument("--stride_inplane", type=int, default=int(self.config.get("stride_inplane", 32)), help="Stride size in 2D plane")
        parser.add_argument("--stride_layer", type=int, default=int(self.config.get("stride_layer", 32)), help="Stride size in Z direction")
        

        parser.set_defaults(model='test')
        self.isTrain = False

        return parser
