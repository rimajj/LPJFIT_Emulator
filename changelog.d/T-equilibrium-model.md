### Added

- **The model that predicts the settled forest from climate and soil alone is now a saved, reusable
  model, and it has been applied to every land cell.** The earlier test that it works (61 % of the
  variation explained at places it never saw) built its models, scored them and threw them away.
  They are now built once from all 6,000 pilot simulations, saved to disk as plain files with a
  record of exactly what went into them, and can be loaded again anywhere; a loaded copy gives
  exactly the same predictions, to the last digit. The saved model was then run on all 67,420
  land cells for three 30-year climates: 1970-1999, and 2071-2100 under a low-emission and a
  high-emission scenario.

  **The recorded result was reproduced exactly.** Rebuilding the test from the saved model's own
  code, on the same data and the same held-out regions, gives the recorded 61 % (0.6075822) to the
  last digit for every one of the 22 measured quantities, and the same for the second, finer way of
  holding regions out. Running the same fit twice gives identical answers, and so does running it
  on 16 processor cores instead of the one the original test had, so the number is exactly
  repeatable on this cluster. How far it would move if the learner drew its random row and column
  samples differently was not measured.

  **What else the saved model predicts, not yet tested in advance.** Beyond the 22 measured
  quantities it also predicts litter carbon, two more points of each trait distribution, and the
  share of each of the seven tree types. These are marked as development work: how well they do
  was looked at, but not against a bar written down beforehand, so it is not a result. On the
  same held-out regions the tree-type shares look promising (65 % of their variation, against 28 %
  for copying the most similar climate), though that copy lands close to the exact mix more often.
  A proper registered test of them is proposed; because these numbers have now been seen, a fair
  test needs places the model has not already been scored on.

  **Where the predictions are guesses beyond what the model has seen.** For each cell and climate
  the prediction files say how far that climate is from anything in the 200 pilot locations. Among
  cells that hold trees today, 3 % (1970-1999), 3 % (high emissions) and 4 % (low emissions) have
  at least one climate or soil input outside the range the model was built on, rising to 11-16 %
  for the future climates between the equator and 15° S. By overall distance, almost every cell is
  closer to a pilot simulation than the held-out pilot locations were to the rest during the test,
  so most predictions are interpolations of the kind the 61 % was measured on. That does not show
  that the 61 % holds there: being near a pilot simulation is needed for the comparison to be fair,
  not enough to make it true, and 200 locations cannot show every combination of climate and soil a
  real place has.

  **What is still wrong.** The model is fitted to average behaviour, so it pulls every quantity
  towards the middle: the sparsest forests are over-predicted and the densest under-predicted, most
  strongly for rooting depth. The part that matters most for climate change is weaker than the
  headline: how each location changes across its 30 climates is captured at 10-57 % depending on
  the quantity, against 61 % for the overall level. And it has seen few places without trees, so it
  predicts trees in about two thirds of the 10,434 cells that hold none in the original model's
  1970-1999 run (a run with a different CO2 history, so a rough check only). Where it extrapolates
  it can predict impossible negative trait values: leaf longevity in about 430 of the 67,420 cells
  for 1970-1999, and rooting depth in a few. The saved predictions set those to zero. That removes
  the impossible number but does not make the prediction right. Tested on 200 of the 54,020 forest
  cells; the acceptance test is untouched.
