"""A healthy script: every RNG call is either in a scope that saw a
seeding call, or explicitly carries a seed/random_state kwarg.
"""

import random

import numpy as np

from sklearn.model_selection import train_test_split


random.seed(42)
np.random.seed(42)


def sample() -> list:
    out = []
    for _ in range(5):
        out.append(random.random())
        out.append(np.random.rand())
    return out


def split(X, y):
    return train_test_split(X, y, test_size=0.2, random_state=42)


if __name__ == "__main__":
    sample()
