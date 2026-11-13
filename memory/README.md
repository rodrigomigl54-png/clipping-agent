# Machine memory (committed on purpose)

Durable copy of what the clipping machine has learned and produced, so a new session continues where
the last one stopped. Written by `python main.py memory save` and the research commands; loaded automatically.

- `research/` — trend snapshots (`snapshot_YYYY-MM-DD.json`), `summary_latest.json`, video stats cache,
  creators discovered from captions.
- `plans/` — the daily content plans.
- `export_registry.json`, `clips_index.json` — what was already made/exported (duplicate prevention).
- `performance.json`, `recommendations.json`, `config_changes.json`, `format_assignments.json` — results and learning.

The style library (learned formats from example clips) lives in `config/style_examples/`.
