# Agentic life cycle assessment

**Provider selecting by the pedigree-matrix method**, as used for the paper’s main results, is **not included**. After publication it will be available for academic, non-commercial use upon email request. See [CODE_AVAILABILITY.md](CODE_AVAILABILITY.md).

---

## 目录 / Contents

- [环境要求](#环境要求)
- [安装](#安装)
- [启动 openLCA IPC](#启动-openlca-ipc)
- [命令行运行](#命令行运行)
- [Web 应用](#web-应用)
- [Excel 输入说明](#excel-输入说明)
- [仓库结构](#仓库结构)
- [License](#license)

---

## 环境要求

| 依赖 | 说明 |
|------|------|
| Python 3.9+ | 推荐 3.10 / 3.11 |
| [openLCA 2.x](https://www.openlca.org/) | 需启用 IPC Server（默认端口 **8080**） |
| ecoinvent 或兼容数据库 | 已在 openLCA 中打开 / 由 headless 脚本加载 |
| 可选 LLM | 仅用于中文流名称翻译、地理辅助；不填也能跑语义匹配 |

**注意：** openLCA 图形界面与 headless IPC **不能同时打开同一个数据库**（Derby 单进程独占）。

默认数据库名（可在 `lca_automation/config.py` 中修改）：

```
ecoinvent 3.12 Cutoff Unit 2025-12-19
```

默认 LCIA 方法：`EF v3.1`

---

## 安装

在仓库根目录：

```bash
git clone https://github.com/hank9511/LCA.git
cd LCA

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r lca_website/requirements.txt   # 若要跑 Web

cp .env.example .env               # 可选：填 LLM / 网站密钥
```

`.env` 常用项：

```env
GROK_API_KEY=                      # 可选，流名称翻译等
GROK_BASE_URL=https://openrouter.ai/api/v1
SECRET_KEY=change-me               # Web
DATABASE_URL=sqlite:///lca_website.db
LCA_IPC_PORTS=8080                 # 多个 openLCA 实例时用逗号分隔
```

不要把 `.env` 提交到 Git。

---

## 启动 openLCA IPC

分析前必须先让 Python 连上 openLCA。两种方式任选其一。

### 方式 A：图形界面（跨平台）

1. 打开 openLCA，加载 ecoinvent（或兼容）数据库  
2. **Window → Developer tools → IPC Server → Run**（端口 `8080`）

### 方式 B：无界面脚本（macOS）

```bash
chmod +x lca_automation/server/*.command
./lca_automation/server/start_olca_ipc.command

# 指定数据库名（openLCA 工作区 databases 下的文件夹名）
./lca_automation/server/start_olca_ipc.command "ecoinvent 3.12 Cutoff Unit 2025-12-19"

# 停止并释放数据库
./lca_automation/server/stop_olca_ipc.command
```

可选环境变量：`OLCA_APP`、`OLCA_DATA_DIR`、`OLCA_DB`、`OLCA_PORT`、`OLCA_XMX`。详见 [`lca_automation/server/README.md`](lca_automation/server/README.md)。

Windows 用户请用方式 A。

---

## 命令行运行

在**仓库根目录**执行（确保 IPC 已在 8080 监听）：

```bash
python -m lca_automation.main path/to/inventory.xlsx --ablation-variant semantic_only
```

或在 Python 中：

```python
from lca_automation import run_automated_lca_workflow

results = run_automated_lca_workflow(
    excel_path="path/to/inventory.xlsx",
    database_path="ecoinvent 3.12 Cutoff Unit 2025-12-19",
)
```

`--ablation-variant` 可选值：

| 值 | 含义 |
|----|------|
| `config` | 使用 `lca_automation/config.py`（默认） |
| `semantic_only` | Semantic name matching only (recommended for this snapshot) |
| `full` | Pedigree-matrix provider screening (falls back to semantic matching in this snapshot) |
| `unconstrained_candidate` | Relaxed candidate filters |
| `no_stage_classification` | Disable life-cycle stage classification |

本快照中 `PROVIDER_SELECTION_MODE = "semantic_only"`。

### 批处理（macOS）

```bash
export LCA_PYTHON="$(which python)"
./lca_automation/server/run_batch.command path/to/case1.xlsx path/to/case2.xlsx
```

请用环境变量 `LCA_PYTHON` 指向已安装 `olca-ipc` 的解释器。

---

## Web 应用

```bash
# 先启动 openLCA IPC（见上文），再：
cd lca_website
python app.py
```

浏览器打开：**http://127.0.0.1:8087**

首次访问可注册账号，或若你运行过 `python init_db.py`，默认管理员为 `admin` / `admin123`（请立刻改密，切勿用于生产）。

功能概览：项目创建 → 上传 Excel 清单 → 自动建模与计算 → 查看贡献 / 生成报告。

多实例并行时，在仓库根 `.env` 中设置：

```env
LCA_IPC_PORTS=8080,8081,8082
LCA_MAX_CONCURRENT_TASKS=3
```

每个端口对应一个独立的 openLCA 进程，且**不能共用同一数据库连接**。

---

## Excel 输入说明

清单表需能被 `lca_automation/excel_parser.py` 解析，通常包含：

- 过程（process）名称与生命周期阶段（可选）
- 输入 / 输出流、数量、单位
- 可选：显式指定的背景过程 provider、地理位置

`.xlsx` 文件默认被 `.gitignore` 忽略，请把案例文件放在本地，不要提交专有清单。

数据库名需与 openLCA 中实际打开的库一致。若你的库名不是默认值，请改 `lca_automation/config.py` 中的 `DATABASE_PATH`，或在调用 `run_automated_lca_workflow(..., database_path=...)` 时传入。

---

## 仓库结构

```
LCA/
├── lca_automation/          # 建模与计算核心
│   ├── main.py              # CLI: python -m lca_automation.main
│   ├── main_workflow.py     # Excel → 产品系统 → LCIA
│   ├── excel_parser.py
│   ├── provider_selector.py # this snapshot: semantic matching
│   ├── model_builder.py
│   ├── result_calculator.py
│   └── server/              # headless IPC 启动脚本（macOS）
├── lca_website/             # Flask Web UI（端口 8087）
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
