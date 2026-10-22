"""A dirty script: every rule fires at least once."""

import random

import numpy as np
import torch
import tensorflow as tf

from sklearn.model_selection import train_test_split
from sklearn.utils import shuffle


def unseeded_sample() -> list:
    # SEED-001: stdlib random without a seed in scope.
    a = random.random()
    # SEED-002: numpy.random without a seed in scope.
    b = np.random.rand(5)
    # SEED-003: torch without manual_seed in scope.
    c = torch.randn(5)
    # SEED-004: tf.random without set_seed in scope.
    d = tf.random.uniform([5])
    return [a, b, c, d]


def unseeded_split(X, y):
    # SEED-005: scikit-learn split without random_state.
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    X_train, y_train = shuffle(X_train, y_train)
    return X_train, X_test, y_train, y_test


def reseed_in_fn():
    # SEED-006: reseed inside a function.
    np.random.seed(1)
    a = np.random.rand()
    np.random.seed(2)
    b = np.random.rand()
    return a, b
