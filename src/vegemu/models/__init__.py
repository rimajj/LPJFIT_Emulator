"""The learned map from a climate summary to a forest state.

    emulator   the state predictor: one head per scored quantity, fitted per spatial fold
"""

from __future__ import annotations

from vegemu.models.emulator import (
    LOG_TARGETS,
    Emulator,
    EmulatorConfig,
    fit_out_of_fold,
)

__all__ = ["LOG_TARGETS", "Emulator", "EmulatorConfig", "fit_out_of_fold"]
