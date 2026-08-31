# LCA服务网站

一个用于生命周期评估(LCA)的Web应用，支持Excel文件上传、AI分析和项目管理。

## 🚀 快速开始

1. **安装依赖**: 双击 `安装依赖.bat`
2. **启动网站**: 双击 `启动网站.bat`
3. **访问网站**: 浏览器打开 `http://localhost:8080`

## ✨ 主要功能

- 用户注册和登录
- 项目管理（创建、编辑、删除）
- Excel文件上传和分析
- AI驱动的LCA数据评估
- 分析结果查看和下载
- 文件管理和历史记录

## 🔧 技术栈

- **后端**: Python Flask
- **数据库**: SQLite
- **AI服务**: DeepSeek API
- **前端**: HTML + CSS + JavaScript

## 📖 详细说明

更多详细信息请查看 `部署说明.md`

## ⚙️ 多 openLCA 并行配置

在项目根目录 `.env` 中配置：

```env
LCA_IPC_PORTS=8080,8081,8082,8083,8084,8085
# 可选：不填时默认等于端口数量
LCA_MAX_CONCURRENT_TASKS=6
```

说明：
- `LCA_IPC_PORTS` 是本服务真正用于任务调度的端口池，不会自动读取 openLCA GUI 当前设置。
- 需要分别启动多个 openLCA 实例，并确保每个实例的 IPC 端口与上面配置一致。
- 启动 `python lca_website/app.py` 后，日志中会打印 `ipc_ports=[...]`，用于确认是否生效。

---
*简单易用的LCA服务网站* 🎯