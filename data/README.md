# Data layout

- `data/seed/` contains curated, sanitized demo content that is safe to publish.
- Runtime state such as SQLite databases, traces, feedback, costs, and temporary files should be created under ignored runtime paths and must not be committed.

Use `python -m src.cli seed-demo` to copy the published seed knowledge into the active runtime knowledge directory.
