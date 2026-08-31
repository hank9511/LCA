# lca_automation

Excel → openLCA 产品系统 → LCIA。

本公开版本按以下优先级选择背景过程（provider）：

1. Excel 中显式指定的 provider  
2. 同一 Excel 文件中的前景过程  
3. 数据库候选：按名称语义相似度排序（可选 market / 地理过滤）

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

见 `config.py`。本公开版本默认：

- `PROVIDER_SELECTION_MODE = "semantic_only"`
- `USE_LLM_FOR_PROVIDER_SELECTION = False`（LLM 仍可用于流名称翻译 / 地理辅助）

```python
from lca_automation import run_automated_lca_workflow

results = run_automated_lca_workflow(
    excel_path="case.xlsx",
    database_path="ecoinvent 3.12 Cutoff Unit 2025-12-19",
)
```

If `full` is requested (pedigree-matrix provider screening), this public snapshot falls back to semantic matching.

## Upstream expansion

为上游 provider 构建临时产品系统，再合并过程与链接（原系统优先），类似 openLCA 的 “Update Process Links”。
