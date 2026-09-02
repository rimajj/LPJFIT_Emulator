"""vegemu — a purely data-driven emulator of the LPJmL-FIT dynamic global vegetation model.

Given a climate, predict the vegetation state, and write it out as a byte-loadable LPJmL-FIT restart
file plus the model's own output files -- so the model's 1000-year spin-up can be skipped and the
equilibrium forest under any climate obtained directly.

Layout (see PLAN.md for the rung ladder and CLAUDE.md for the protocol):

    binfmt/   LPJmL-FIT's own file formats: the restart file, .clm forcing, NetCDF output   [line D]
    corpus/   the spin-up perturbation ensemble and its provenance                          [line D]
    models/   the learned state predictor                                                   [line T]
    train/    training and inference                                                        [line T]
"""

__version__ = "0.0.1"
