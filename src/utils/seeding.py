"""Seed control so experiments are reproducible."""

import os
import random

import numpy as np
import torch


def set_seed(seed: int) -> None:
    """Seed Python, NumPy and PyTorch RNGs, and force deterministic cuDNN.

    Deterministic cuDNN trades some speed for exact reproducibility, which
    matters more here than training throughput given the small debug runs
    and Colab's limited free-tier GPU time.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
