# openLCA headless IPC 服务器（方案 A）

不打开 openLCA 图形界面，直接以「无界面服务器」方式连接指定数据库，在 **8080** 端口
对外提供 JSON-RPC 接口，供 `lca_automation`（`olca_ipc.Client(8080)`）或任意程序调用。

替代了原本「手动打开 openLCA → 开发者工具 → IPC Server → 点 run」的全部步骤。

## 文件

| 文件 | 作用 |
|------|------|
| `start_olca_ipc.command` | 一键启动 headless IPC 服务器 |
| `stop_olca_ipc.command`  | 一键停止服务器并释放数据库 |

> macOS 上可在「访达 Finder」中**双击**运行；也可在终端执行。

## 使用

```bash
# 启动（默认数据库：ecoinvent 3.12 Cutoff Unit 2025-12-19）
./start_olca_ipc.command

# 启动并指定数据库（databases 目录下的文件夹名）
./start_olca_ipc.command "ecoinvent 3.12-中石化"

# 停止
./stop_olca_ipc.command
```

启动成功后会显示地址 `http://localhost:8080`、进程 PID 和日志路径。
随后即可直接运行你的分析，例如：

```bash
python -m lca_automation.main your_case.xlsx
```

## 可配置项（环境变量，可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OLCA_APP`      | `/Applications/openLCA.app` | openLCA 安装路径 |
| `OLCA_DATA_DIR` | `~/openLCA-data-1.4`        | 工作区数据目录 |
| `OLCA_DB`       | `ecoinvent 3.12 Cutoff Unit 2025-12-19` | 数据库名 |
| `OLCA_PORT`     | `8080`                      | 端口 |
| `OLCA_XMX`      | `16G`                       | JVM 最大堆内存 |
| `OLCA_THREADS`  | `4`                         | 计算线程数 |

示例：`OLCA_PORT=8090 OLCA_XMX=24G ./start_olca_ipc.command`

## 运行文件位置

- 日志：`~/.olca-ipc/ipc-<端口>.log`
- PID：`~/.olca-ipc/ipc-<端口>.pid`

## 重要注意事项

1. **不能与图形界面同时打开同一数据库。**
   headless 服务器与 openLCA GUI 不能同时连接同一个数据库（Derby 单进程独占）。
   - 启动前若 GUI 正打开该库，脚本会提示先关闭。
   - 用脚本建好产品系统、算完后，运行 `stop_olca_ipc.command` 释放数据库，
     再在 GUI 中打开该库即可看到全部结果（数据是同一份，完全同步）。

2. **数据同步是「串行交接」而非实时双向刷新。** 谁用完关掉，另一个再打开。

3. **MKL 高性能求解器（已启用）：** 默认情况下 openLCA 的 headless 模式
   不会加载原生计算库（加载入口仅在图形界面启动时调用）。本方案通过一个
   极小的启动壳 `OlcaIpcServer` 在启动服务器前显式加载 MKL，使计算走原生
   加速（实测完整 ecoinvent 关联系统单次计算约数秒）。
   - 启动成功后会显示「⚡ 已启用 MKL 高性能求解器」。
   - 若提示回退到纯 Java 求解器，请确认 `lib/OlcaIpcServer.class` 与 openLCA
     安装目录下的 `Contents/Eclipse/olca-mkl-*` 目录存在。

## 启动壳（MKL 加载器）说明

- 源码：`src/OlcaIpcServer.java`
- 已编译产物：`lib/OlcaIpcServer.class`（随仓库提供，运行时仅用 openLCA 内置 JRE，无需额外 JDK）
- 仅当 openLCA 升级且类名/接口变化导致失效时才需重新编译：

```bash
# 需要一个 JDK 21（仅编译用），CP 指向 openLCA 的 libs
JDK=/path/to/jdk-21/Contents/Home
CP="/Applications/openLCA.app/Contents/Eclipse/plugins/olca-app_*/libs/*"
"$JDK/bin/javac" -classpath "$CP" -d lib src/OlcaIpcServer.java
```
