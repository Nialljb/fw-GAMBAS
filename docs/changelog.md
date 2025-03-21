# Changelog

0.2.4 (2025-03-21) NJB
- Refactoring to run at the project level

0.1.8 (2025-03-12) NJB  
- Updated bottleneck_5 in residual_transformers3D.py  
- Refactored input for ants  


12/3/2025  
Version 0.1.6 NJB  
- update netG and model selection based on cpu/gpu selection

6/3/2025
Updated outfile naming to be cleaner in BIDs format


26/02/2025

Version 0.0.5 NJB
- Successfully tested on Flywheel

To Do:
clean output filename

Version 0.0.2 NJB
- refactoring the parser code

To Do:
** base_options needs to be updated to handle gpu selection rather than cpu default
** need to rebuild base image to handle GPU selection
** To run on GPU should batch process to save costs of loading Docker container each time


20/02/2025
Version 0.0.2 NJB, LB
- updates to run on CPU
- Not pushed to FW, need to rebuild from CUDA Docker image to ensure compatibility to run on GPU
- Current default is to run on CPU, need to check option to run on GPU
    This is currently set as condition if CUDA is available, then run on GPU, else run on CPU

14/02/2025
Version 0.0.1

Refactoring for Flywheel gear