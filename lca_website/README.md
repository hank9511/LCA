# LCA service website

A web application for life cycle assessment (LCA), supporting Excel file upload, AI-assisted analysis and project management.

## 🚀 Quick start

Run these from the repository root, with the openLCA IPC server already running (see the root `README.md`):

1. **Install dependencies**: `pip install -r lca_website/requirements.txt`
2. **Start the site**: `cd lca_website && python app.py`
3. **Open the site**: browse to `http://127.0.0.1:8087`

On Windows you can also use the helper scripts in this directory, e.g. `start.bat`.

## ✨ Main features

- User registration and login
- Project management (create, edit, delete)
- Excel file upload and analysis
- AI-driven evaluation of LCA data
- Viewing and downloading analysis results
- File management and history

## 🔧 Tech stack

- **Backend**: Python Flask
- **Database**: SQLite
- **AI service**: OpenAI-compatible API (configured via `GROK_API_KEY` / `GROK_BASE_URL`, defaults to OpenRouter)
- **Frontend**: HTML + CSS + JavaScript

## 📖 Further documentation

See the repository root `README.md` for installation, openLCA IPC setup and the Excel input format.

## ⚙️ Configuring multiple parallel openLCA instances

Configure this in the `.env` file at the repository root:

```env
LCA_IPC_PORTS=8080,8081,8082,8083,8084,8085
# Optional: defaults to the number of ports when left empty
LCA_MAX_CONCURRENT_TASKS=6
```

Notes:
- `LCA_IPC_PORTS` is the port pool this service actually uses for task scheduling; it does not automatically read the current settings of the openLCA GUI.
- You must start a separate openLCA instance for each port, and make sure each instance's IPC port matches the configuration above.
- After starting `python lca_website/app.py`, the log prints `ipc_ports=[...]`, which you can use to confirm the configuration took effect.

---
*A simple, easy-to-use LCA service website* 🎯
