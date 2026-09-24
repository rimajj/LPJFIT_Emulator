### Added
- `binfmt.restart.assemble_restart` and `Segment`: stitch shards (each a valid restart file for a
  contiguous block) and ranges of the template into one restart file, by byte-range copies with a
  rebased offset table. Refuses a gap, an overlap, or a shard written under different headers.
- `scripts/synth_global.py`: the global emulated restart as a task farm over cell blocks
  (`plan --out <file> --predictions <parquet> [--template] [--block-size]` -> `shards` ->
  `assemble` -> `verify`, or `run` for all of it in one job, `finish` for the last three). The
  template defaults to `ground_truth.restart_spinup_end`. Blocks with nothing to synthesise write
  no shard and are copied straight from the template. `verify` reads every record back, checks
  pass-through cells byte for byte against the template and each shard against its hash, and
  re-derives from the written records the litter-index condition the model aborts on and the
  count of stems of a type their cell never holds. `t0` streams a block or the whole file through
  the writer and `cmp`s it against the source.
- Shard writing is restartable: `shards --task I --ntasks N` owns a fixed, disjoint block set, a
  shard counts as written only if its body and report agree in size and plan hash, and `status`
  names the task to re-run. `farm` prints the multi-job submission.
- Two plug points: the donor rule (`--donor-rule module:factory`; default `synth_restart.py`'s,
  imported from it) and the per-cell synthesis (`--cell-rule module:factory`; default
  `current-api`, which calls `synthesise_cell` exactly as it stands today). The second is where
  predicted type shares, a recomputed climate buffer and a climate-derived type rule get wired in.
- `plan` and `assemble` refuse to start without the free disk they will use, plus 10 %.
- `plan` refuses, before any work: prediction files with duplicate cells; files whose median
  prediction/template ratio over 48 forested cells falls outside 4x for any quantity the
  synthesiser reads (a log1p or cm column; `--skip-scale-check` overrides and is recorded); files
  whose `lon`/`lat` are not the grid's own (another cell ordering); a census of another template;
  a template not framed from cell 0. `plan`, `assemble`, `census` and `t0` refuse an output that
  is the template itself (`t0` would have deleted it after comparing it with itself).
- `census`: the tree-stem count of every template record. On `restart_1999`: 56,986 cells with a
  stem, 10,434 without, in 36 s on 32 workers. `plan --census` then says before any work exactly
  how many cells it will synthesise, and the cost projection prices only those.
- Measured on the real 67,420-cell `restart_1999` (127,588,235,786 B): streamed through the writer
  in 42 s at 3.0 GB/s with 428 MB peak memory, `cmp` identical to the source; every record decoded,
  re-encoded, sharded, stitched and `cmp`'d identical to the source by the farm in identity mode.

### Changed
- `RestartWriter` streams: each record goes to disk as it is appended and only the offsets are
  held, the offset table is fixed up in place at `close()`, and the file is built as
  `<name>.partial` and renamed only by a successful close. Same API and the same bytes as the old
  in-memory writer, which the new tests keep as their oracle.
- A cell the prediction marks treeless (`pred_treeless`) is written with no tree rather than
  passed through with its present-day forest. A template that holds no tree passes through
  whatever is predicted for it, so the synthesised set is the predicted cells with any stem.
