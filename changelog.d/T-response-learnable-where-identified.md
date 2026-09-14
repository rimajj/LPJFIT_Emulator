### Added

- **The warming response is learnable where it is identified, and not from the scenario legs.**
  Both sealed model arms were run. On the designed perturbation ensemble the emulator explains
  0.545 of the squared change against a best null of 0.146 and a required 0.226, beating that null
  at all 29 perturbation levels — 63 % of the attainable ceiling of 0.870, not of 1.0. The same
  model, asked for the year-2100 forest of a low-emissions leg it had never seen, placed all 22
  quantities inside the band in 0.5 % of cells against persistence's 3.4 %: below the do-nothing
  competitor, the worst of the three pre-named outcomes.
- **The two results are one fact, not a contradiction.** The ensemble spins the same cell up under
  30 climates, so the response is identified by construction; the scenario legs hold one climate per
  place, so climate and geography are collinear and no response is separately identified. Response
  work moves to the ensemble, and no warmed climate may be quoted from the scenario-leg map.
- **A disclosure that must travel with the 0.545.** A model blinded to which of the 29 perturbations
  it is being asked about still scores 0.349 — 64 % of the headline, and itself above the bar. Only
  the remaining +0.196 is forcing-attributable, and that is the number any future improvement has to
  move. No pre-registered null covers this competitor, because every null there is information-free
  by construction and none of them is a learned-but-treatment-blind model.
- Falsification arms for the pilot model: blind, per-cell-scrambled forcing, and a collapse
  decomposition. Scrambling drops the score to 0.308, below blind, so the model does genuinely use
  the forcing; collapse is not what is being scored (0.549 on surviving pairs alone).
- `vegemu.results.append_result_block`, so a job emits the flat `arms` block and the
  `prereg_sha256` that `append_result.py` requires, read from inside the job where it can prove
  which pre-registration governed the run.

### Fixed

- A falsification arm that could not fail. The scramble originally used one permutation for all 200
  cells, which — because the 29 design points are identical at every cell — is a relabelling the
  model relearns under new names rather than a scramble. It scored 0.495 against the model's 0.545
  and read as a near-miss while falsifying nothing. Permutations are now drawn per cell.

### Changed

- The apparatus is validated rather than asserted: the held-out-leg run also scored the map on the
  leg it was fitted on and returned 0.036067, reproducing the 0.0361 recorded for the earlier map
  experiment. Every null in both experiments reproduced its sealed value exactly.
