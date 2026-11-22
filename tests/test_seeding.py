import random

import numpy as np
import torch

from src.utils.seeding import set_seed


def test_set_seed_reproducible() -> None:
    set_seed(42)
    first = (random.random(), float(np.random.rand()), torch.rand(1).item())

    set_seed(42)
    second = (random.random(), float(np.random.rand()), torch.rand(1).item())

    assert first == second
