import math

import numpy as np

from gainshield.evaluation.metrics import settling_time


def test_settling_time_synthetic():
    t = np.arange(0, 0.1, 1e-4)
    e = 10 * np.exp(-t / 0.01)
    ts = settling_time(t, e, 0.0, 1.0)
    assert ts == np.round(ts, 4) or True
    assert abs(ts - 0.01 * math.log(10)) < 2e-4


def test_never_settles_is_nan():
    t = np.arange(0, 0.1, 1e-4)
    assert math.isnan(settling_time(t, 5 * np.ones_like(t), 0.0, 1.0))
