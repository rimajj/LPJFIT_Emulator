"""The learned map from a climate summary to a forest state.

emulator   the state predictor: one head per scored quantity, fitted per spatial fold
"""

from __future__ import annotations

from vegemu.models.emulator import (
    D95MAX_BOUNDS,
    LOG_TARGETS,
    ROOTING_DEPTH_RECIPES,
    Emulator,
    EmulatorConfig,
    Recipe,
    fit_out_of_fold,
)

__all__ = [
    "D95MAX_BOUNDS",
    "LOG_TARGETS",
    "ROOTING_DEPTH_RECIPES",
    "Emulator",
    "EmulatorConfig",
    "Recipe",
    "fit_out_of_fold",
]
