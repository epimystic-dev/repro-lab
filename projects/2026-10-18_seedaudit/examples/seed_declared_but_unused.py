"""SEED-007: a seed is declared, but no RNG sampling call exists."""

import numpy as np


np.random.seed(42)


def unrelated_function(x):
    return x + 1
