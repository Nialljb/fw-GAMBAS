import argparse
import os
from utils.utils import *
import torch
import models


class BaseOptions():
    def __init__(self):
        self.initialized = False

    def initialize(self, parser):
        parser.add_argument('--data_path', type=str, default='/flywheel/v0/Combined_data/train', help='Train images path (paired)')
        parser.add_argument('--data_path_2', type=str, default='/flywheel/v0/GANs/unpaired/train', help='Train images path (unpaired)')
        parser.add_argument('--val_path', type=str, default='/flywheel/v0/Combined_data/val', help='Validation images path')
        parser.add_argument('--batch_size', type=int, default=1, help='input batch size')
        parser.add_argument('--patch_size', default=[128, 128, 128], help='Size of the patches extracted from the image (default is 32, 256, 256)')
        parser.add_argument('--input_nc', type=int, default=1, help='# of input image channels')
        parser.add_argument('--output_nc', type=int, default=1, help='# of output image channels')
        parser.add_argument('--resample', default=False, help='Decide or not to rescale the images to a new resolution')
        parser.add_argument('--new_resolution', default=(0.45, 0.45, 0.45), help='New resolution (if you want to resample the data again during training')
        parser.add_argument('--min_pixel', default=0.1, help='Percentage of minimum non-zero pixels in the cropped label')
        parser.add_argument('--drop_ratio', default=0, help='Probability to drop a cropped area if the label is empty. All empty patches will be dropped for 0 and accept all cropped patches if set to 1')

        parser.add_argument('--ngf', type=int, default=64, help='# of gen filters in first conv layer (default is 64)')
        parser.add_argument('--ndf', type=int, default=64, help='# of discrim filters in first conv layer')
        parser.add_argument('--netD', type=str, default='n_layers', help='selects model to use for netD')
        parser.add_argument('--n_layers_D', type=int, default=3, help='only used if netD==n_layers')
        parser.add_argument('--netG', type=str, default='res_cnn', help='selects model to use for netG. Look on Networks3D to see the whole list (i2i_mamba = gpu (to be renamed gambas); res_cnn = cpu)')

        parser.add_argument('--gpu_ids', default=-1, help='gpu ids: e.g. 0  0,1,2, 0,2. use -1 for CPU')

        parser.add_argument('--name', type=str, default='cpu', help='name of the experiment. It decides where to store samples and models')
        parser.add_argument('--model', type=str, default='i2i_mamba_one', help='chooses which model to use: cycle_gan|pix2pix|ea_gan|resvit_one|i2i_mamba_one')

        parser.add_argument('--which_direction', type=str, default='AtoB', help='AtoB or BtoA (keep it AtoB)')
        parser.add_argument('--checkpoints_dir', type=str, default='/flywheel/v0/app', help='models are saved here')
        parser.add_argument('--workers', default=8, type=int, help='number of data loading workers')
        parser.add_argument('--norm', type=str, default='instance', help='instance normalization or batch normalization')

        parser.add_argument('--no_dropout', action='store_true', help='no dropout for the generator')
        parser.add_argument('--init_type', type=str, default='normal', help='network initialization [normal|xavier|kaiming|orthogonal]')
        parser.add_argument('--init_gain', type=float, default=0.02, help='scaling factor for normal, xavier and orthogonal.')
        parser.add_argument('--verbose', action='store_true', help='if specified, print more debugging information')
        parser.add_argument('--suffix', default='', type=str, help='customized suffix: opt.name = opt.name + suffix: e.g., {model}_{netG}_size{loadSize}')
        self.initialized = True

        return parser

    def gather_options(self):
        # initialize parser with basic options
        if not self.initialized:
            parser = argparse.ArgumentParser(
                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
            parser = self.initialize(parser)

        # get the basic options
        opt, _ = parser.parse_known_args()

        # modify model-related parser options
        model_name = opt.model
        model_option_setter = models.get_option_setter(model_name)
        parser = model_option_setter(parser, self.isTrain)
        opt, _ = parser.parse_known_args()  # parse again with the new defaults

        self.parser = parser

        return parser.parse_args()

    def print_options(self, opt):
        message = ''
        message += '----------------- Options ---------------\n'
        for k, v in sorted(vars(opt).items()):
            comment = ''
            default = self.parser.get_default(k)
            if v != default:
                comment = '\t[default: %s]' % str(default)
            message += '{:>25}: {:<30}{}\n'.format(str(k), str(v), comment)
        message += '----------------- End -------------------'
        print(message)

        # save to the disk
        expr_dir = os.path.join(opt.checkpoints_dir, opt.name)
        mkdirs(expr_dir)
        file_name = os.path.join(expr_dir, 'opt.txt')
        with open(file_name, 'wt') as opt_file:
            opt_file.write(message)
            opt_file.write('\n')

    def parse(self):

        opt = self.gather_options()
        opt.isTrain = self.isTrain  # train or test

        # process opt.suffix
        if opt.suffix:
            suffix = ('_' + opt.suffix.format(**vars(opt))) if opt.suffix != '' else ''
            opt.name = opt.name + suffix

        self.print_options(opt)

        # set gpu ids
        if opt.gpu_ids == '-1':
            str_ids = ['-1']
        else:
            str_ids = list(opt.gpu_ids)
        # str_ids.remove(',')
        opt.gpu_ids = []
        for str_id in str_ids:
            id = int(str_id)
            if id >= 0:
                opt.gpu_ids.append(id)
        if len(opt.gpu_ids) > 0:
            torch.cuda.set_device(opt.gpu_ids[0])
        
        #device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


        self.opt = opt
        return self.opt

