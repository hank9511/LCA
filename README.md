# Agentic life cycle assessment

**Provider selecting by the pedigree-matrix method**, as used for the paper’s main results, is **not included**. After publication it will be available for academic, non-commercial use upon email request. See [CODE_AVAILABILITY.md](CODE_AVAILABILITY.md).

---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Starting the openLCA IPC server](#starting-the-openlca-ipc-server)
- [Command-line usage](#command-line-usage)
- [Web application](#web-application)
- [Excel input format](#excel-input-format)
- [Repository structure](#repository-structure)
- [License](#license)

---

## Requirements

| Dependency | Notes |
|------------|-------|
| Python 3.9+ | 3.10 / 3.11 recommended |
| [openLCA 2.x](https://www.openlca.org/) | IPC Server must be enabled (default port **8080**) |
| ecoinvent or a compatible database | Opened in openLCA, or loaded by the headless scripts |
| Optional LLM | Only used for translating Chinese flow names and for geographic hints; semantic matching works without it |

**Note:** the openLCA graphical interface and the headless IPC server **cannot open the same database at the same time** (Derby allows a single process only).

Default database name (can be changed in `lca_automation/config.py`):

```
ecoinvent 3.12 Cutoff Unit 2025-12-19
```

Default LCIA method: `EF v3.1`

---

## Installation

From the repository root:

```bash
git clone https://github.com/hank9511/LCA.git
cd LCA

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r lca_website/requirements.txt   # only needed for the web app

cp .env.example .env               # optional: LLM / website secrets
```

Common `.env` entries:

```env
GROK_API_KEY=                      # optional, e.g. flow name translation
GROK_BASE_URL=https://openrouter.ai/api/v1
SECRET_KEY=change-me               # web app
DATABASE_URL=sqlite:///lca_website.db
LCA_IPC_PORTS=8080                 # comma-separated for multiple openLCA instances
```

Do not commit `.env` to Git.

---

## Starting the openLCA IPC server

Python must be able to reach openLCA before any analysis can run. Choose either option.

### Option A: graphical interface (cross-platform)

1. Open openLCA and load the ecoinvent (or compatible) database
2. **Window → Developer tools → IPC Server → Run** (port `8080`)

### Option B: headless scripts (macOS)

```bash
chmod +x lca_automation/server/*.command
./lca_automation/server/start_olca_ipc.command

# Pass a database name (the folder name under the openLCA workspace "databases" directory)
./lca_automation/server/start_olca_ipc.command "ecoinvent 3.12 Cutoff Unit 2025-12-19"

# Stop the server and release the database
./lca_automation/server/stop_olca_ipc.command
```

Optional environment variables: `OLCA_APP`, `OLCA_DATA_DIR`, `OLCA_DB`, `OLCA_PORT`, `OLCA_XMX`. See [`lca_automation/server/README.md`](lca_automation/server/README.md) for details.

Windows users should use Option A.

---

## Command-line usage

Run from the **repository root** (make sure the IPC server is listening on port 8080):

```bash
python -m lca_automation.main path/to/inventory.xlsx --ablation-variant semantic_only
```

Or from Python:

```python
from lca_automation import run_automated_lca_workflow

results = run_automated_lca_workflow(
    excel_path="path/to/inventory.xlsx",
    database_path="ecoinvent 3.12 Cutoff Unit 2025-12-19",
)
```

Accepted values for `--ablation-variant`:

| Value | Meaning |
|-------|---------|
| `config` | Use `lca_automation/config.py` (default) |
| `semantic_only` | Semantic name matching only (recommended for this snapshot) |
| `full` | Pedigree-matrix provider screening (falls back to semantic matching in this snapshot) |
| `unconstrained_candidate` | Relaxed candidate filters |
| `no_stage_classification` | Disable life-cycle stage classification |

In this snapshot, `PROVIDER_SELECTION_MODE = "semantic_only"`.

### Batch processing (macOS)

```bash
export LCA_PYTHON="$(which python)"
./lca_automation/server/run_batch.command path/to/case1.xlsx path/to/case2.xlsx
```

Point the `LCA_PYTHON` environment variable at an interpreter that has `olca-ipc` installed.

---

## Web application

```bash
# Start the openLCA IPC server first (see above), then:
cd lca_website
python app.py
```

Open **http://127.0.0.1:8087** in a browser.

You can register an account on first visit, or, if you have run `python init_db.py`, sign in with the default administrator `admin` / `admin123` (change the password immediately; never use these credentials in production).

Feature overview: create a project → upload an Excel inventory → automated modelling and calculation → inspect contributions / generate a report.

To run several instances in parallel, set the following in the `.env` file at the repository root:

```env
LCA_IPC_PORTS=8080,8081,8082
LCA_MAX_CONCURRENT_TASKS=3
```

Each port corresponds to a separate openLCA process, and they **cannot share the same database connection**.

---

## Excel input format

The inventory workbook must be parsable by `lca_automation/excel_parser.py`, and typically contains:

- Process names and, optionally, life-cycle stages
- Input / output flows, amounts and units
- Optionally: explicitly specified background providers and locations

`.xlsx` files are ignored by `.gitignore` by default. Keep case files locally and do not commit proprietary inventories.

The database name must match the database actually opened in openLCA. If your database name differs from the default, change `DATABASE_PATH` in `lca_automation/config.py`, or pass it via `run_automated_lca_workflow(..., database_path=...)`.

---

## Repository structure

```
LCA/
├── lca_automation/          # Modelling and calculation core
│   ├── main.py              # CLI: python -m lca_automation.main
│   ├── main_workflow.py     # Excel → product system → LCIA
│   ├── excel_parser.py
│   ├── provider_selector.py # this snapshot: semantic matching
│   ├── model_builder.py
│   ├── result_calculator.py
│   └── server/              # headless IPC startup scripts (macOS)
├── lca_website/             # Flask web UI (port 8087)
├── LCA_report/              # Sample LCA PDF reports generated by the pipeline
├── requirements.txt
├── .env.example
└── LICENSE                  # MIT (pedigree-matrix provider screening not included)
```

| Included | Not in this snapshot |
|----------|----------------------|
| Excel parsing, model building, upstream merge, LCIA | Provider screening by the pedigree-matrix method (paper’s main results) |
| Semantic provider matching | Pedigree-matrix indicators, prompts, arbitration workflow, and calibrated constants |
| Geographic / market candidate filters | |

---

## License

Public snapshot: [MIT](LICENSE).

Provider screening by the pedigree-matrix method is **not** licensed under MIT. Academic, non-commercial access will be offered after publication upon request.
