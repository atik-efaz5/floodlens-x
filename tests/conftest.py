"""Shared pytest configuration for FloodLens-X regression tests."""

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _suppress_expected_numerical_warnings():
    """Notebook kernel divides by h in dry cells; suppress benign float warnings."""
    with np.errstate(divide="ignore", invalid="ignore"):
        yield
