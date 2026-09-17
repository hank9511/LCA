# openLCA headless IPC server (Option A)

Connects to a given database as a “headless server”, without opening the openLCA graphical
interface, and exposes a JSON-RPC interface on port **8080** for `lca_automation`
(`olca_ipc.Client(8080)`) or any other program.

This replaces the whole manual sequence of “open openLCA → Developer tools → IPC Server → click run”.

## Files

| File | Purpose |
|------|---------|
| `start_olca_ipc.command` | Start the headless IPC server in one step |
| `stop_olca_ipc.command`  | Stop the server and release the database in one step |

> On macOS these can be run by **double-clicking** them in Finder, or from a terminal.

## Usage

```bash
# Start (default database: ecoinvent 3.12 Cutoff Unit 2025-12-19)
./start_olca_ipc.command

# Start with a specific database (the folder name under the "databases" directory)
./start_olca_ipc.command "ecoinvent 3.12-sinopec"

# Stop
./stop_olca_ipc.command
```

Once started, the script prints the address `http://localhost:8080`, the process PID and the log path.
You can then run your analysis directly, for example:

```bash
python -m lca_automation.main your_case.xlsx
```

## Configuration (environment variables, optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLCA_APP`      | `/Applications/openLCA.app` | openLCA installation path |
| `OLCA_DATA_DIR` | `~/openLCA-data-1.4`        | Workspace data directory |
| `OLCA_DB`       | `ecoinvent 3.12 Cutoff Unit 2025-12-19` | Database name |
| `OLCA_PORT`     | `8080`                      | Port |
| `OLCA_XMX`      | `16G`                       | JVM maximum heap size |
| `OLCA_THREADS`  | `4`                         | Number of computation threads |

Example: `OLCA_PORT=8090 OLCA_XMX=24G ./start_olca_ipc.command`

## Runtime file locations

- Log: `~/.olca-ipc/ipc-<port>.log`
- PID: `~/.olca-ipc/ipc-<port>.pid`

## Important notes

1. **The same database cannot be open in the graphical interface at the same time.**
   The headless server and the openLCA GUI cannot connect to the same database simultaneously
   (Derby allows a single process only).
   - If the GUI currently has the database open, the script will ask you to close it first.
   - After building the product system and finishing the calculation with the scripts, run
     `stop_olca_ipc.command` to release the database; opening it in the GUI then shows all
     results (it is the same data, fully in sync).

2. **Data is handed over sequentially, not refreshed bidirectionally in real time.** Whoever is
   finished closes it, then the other side can open it.

3. **MKL high-performance solver (enabled):** by default openLCA’s headless mode does not load
   the native computation libraries (the loading entry point is only invoked when the graphical
   interface starts). This setup uses a minimal launcher shell, `OlcaIpcServer`, to load MKL
   explicitly before starting the server, so calculations use native acceleration (measured: a
   single calculation on a fully linked ecoinvent system takes a few seconds).
   - On successful startup it prints “⚡ MKL high-performance solver enabled”.
   - If it reports a fallback to the pure Java solver, check that `lib/OlcaIpcServer.class` and
     the `Contents/Eclipse/olca-mkl-*` directory inside the openLCA installation both exist.

## About the launcher shell (MKL loader)

- Source: `src/OlcaIpcServer.java`
- Compiled artifact: `lib/OlcaIpcServer.class` (shipped with the repository; at runtime only
  openLCA’s bundled JRE is used, no extra JDK required)
- Recompilation is only needed if an openLCA upgrade changes class names or interfaces and
  breaks it:

```bash
# Requires a JDK 21 (for compilation only); CP points at openLCA's libs
JDK=/path/to/jdk-21/Contents/Home
CP="/Applications/openLCA.app/Contents/Eclipse/plugins/olca-app_*/libs/*"
"$JDK/bin/javac" -classpath "$CP" -d lib src/OlcaIpcServer.java
```
