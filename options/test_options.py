import flywheel
from pathlib import Path
from options.base_options import BaseOptions  # BaseOptions is defined elsewhere
from utils.parser import parse_config

class TestOptions(BaseOptions):
    def __init__(self, which_model, config):
        super().__init__()  # Initialize parent class
        self.which_model = which_model  # Store which_model as an instance variable
        self.config = config

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

        # Define default input and output directories
        parser.add_argument("--input_dir", type=str, default="/flywheel/v0/input/input", help="Path to input directory")
        parser.add_argument("--output_dir", type=str, default="/flywheel/v0/output", help="Path to output directory")

        # Find the first available NIfTI file in input directory
        input_files = list(Path(parser.get_default("input_dir")).glob("*.nii.gz"))
        if not input_files:
            raise FileNotFoundError("No NIfTI image found in the input directory.")

        parser.add_argument("--image", type=str, default=str(input_files[0]), help="Path to input NIfTI image")
        parser.add_argument("--reference", type=str, default="/flywheel/v0/app/TemplateKhula.nii", help="Path to reference NIfTI image")
        # parser.add_argument("--result_gambas", type=str, default=str(Path(parser.get_default("output_dir")) / f"{input_files[0].stem}_gambas.nii.gz"), help="Path to save the result NIfTI file")
        parser.add_argument("--result_sr", type=str, default=str(Path(parser.get_default("output_dir")) / output_label), help="Path to save the result NIfTI file")
        
        # Parse additional configuration arguments
        parser.add_argument("--phase", type=str, default=self.config.get("phase", "test"), help="Test phase")
        parser.add_argument("--which_epoch", type=str, default=self.config.get("which_epoch", "latest"), help="Epoch to load")
        parser.add_argument("--stride_inplane", type=int, default=int(self.config.get("stride_inplane", 32)), help="Stride size in 2D plane")
        parser.add_argument("--stride_layer", type=int, default=int(self.config.get("stride_layer", 32)), help="Stride size in Z direction")
        

        parser.set_defaults(model='test')
        self.isTrain = False

        return parser
