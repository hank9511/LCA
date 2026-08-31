# lca_automation

Excel → openLCA product system → LCIA workflow.

This public snapshot selects background providers by **semantic name matching** (after Excel-specified providers and market/geography filters). The paper’s provider quality-scoring module is not included; see the repository root `README.md` and `CODE_AVAILABILITY.md`.

## Layout

```
Excel
  → data_parser.py
  → model_builder.py
  → provider_selector.py   (semantic matching in this snapshot)
  → upstream_merger.py
  → result_calculator.py
```

## Provider priority

1. Provider named in Excel  
2. Foreground process in the same Excel file  
3. Database candidates ranked by name similarity (optional market / geography filters)

## Config

See `config.py`. Defaults in this snapshot:

- `PROVIDER_SELECTION_MODE = "semantic_only"`
- `USE_LLM_FOR_PROVIDER_SELECTION = False` (LLM may still be used for flow-name translation / geography helpers)

```python
from lca_automation import run_automated_lca_workflow

results = run_automated_lca_workflow(
    excel_path="case.xlsx",
    database_path="ecoinvent 3.12 Cutoff Unit 2025-12-19",
)
```

## Upstream expansion

Temporary product systems are built for upstream providers, then processes and links are merged (original system preferred), similar to openLCA “Update Process Links”.
