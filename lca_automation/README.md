# lca_automation

Excel → openLCA product system → LCIA.

This public version selects background processes (providers) in the following order of priority:

1. Providers explicitly specified in the Excel file
2. Foreground processes within the same Excel file
3. Database candidates, ranked by semantic similarity of the name (optional market / geographic filters)

**Provider screening by the pedigree-matrix method**, as used for the paper’s main results, is not included; see the repository root `README.md` and `CODE_AVAILABILITY.md`.

## Layout

```
Excel
  → data_parser.py
  → model_builder.py
  → provider_selector.py   # this snapshot: semantic matching
  → upstream_merger.py
  → result_calculator.py
```

## Config

See `config.py`. Defaults in this public version:

- `PROVIDER_SELECTION_MODE = "semantic_only"`
- `USE_LLM_FOR_PROVIDER_SELECTION = False` (an LLM can still be used for flow name translation and geographic hints)

```python
from lca_automation import run_automated_lca_workflow

results = run_automated_lca_workflow(
    excel_path="case.xlsx",
    database_path="ecoinvent 3.12 Cutoff Unit 2025-12-19",
)
```

If `full` is requested (pedigree-matrix provider screening), this public snapshot falls back to semantic matching.

## Upstream expansion

A temporary product system is built for each upstream provider, then its processes and links are merged into the main system (the original system takes precedence), similar to openLCA’s “Update Process Links”.
