import torch

state_dict = torch.load('/Users/nbourke/GD/atom/unity/fw-gears/fw-GAMBAS/app/gpu/previous_net_G.pth')
# state_dict = torch.load('/Users/nbourke/GD/atom/unity/fw-gears/fw-GAMBAS/app/gpu/latest_net_G.pth')
print(state_dict.keys())