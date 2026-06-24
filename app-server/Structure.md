# GenRAG 容器化架构白皮书 (Phase 1 完结版)

## 一、架构基底拓扑
本系统于 2026/04/06 完成微服务容器化剥离。核心生产环境由纯物理机执行脚本的方式，无缝飞升为挂载在 Docker (基于 OrbStack 引擎) 底座的微服务编排网格。

所有的运行规则，受控于统一环境入口：`/Users/gemini/Projects/Own/RAG/docker-compose.yml`。

### 1. 容器分布视图
- **🐳 RAG-Server (Container A)**：核心中枢脑。基于 Ubuntu 22.04 LTS (ARM64)。
  - 内嵌组件：Python 3、Node 20.x、PM2
  - 承载服务：FastAPI 后端引擎、Vite 前端、FRPC 云端隧穿节点、OpenSSH 守护神。
  - 热挂载卷：直接映射 Mac 宿主的 `./app-server` 目录至容器的 `/app`，在此修改代码即产生“超导热刷联动”。
- **🐳 RAG-Redis**：高速缓存军火库。基于 alpine。负责提供强安全的键值通信中转。
- **🐳 RAG-Database**：Qdrant 向量存储基地。现处于预发空载状态（等候 Phase 2 演进计划）。

---

## 二、网络路由与外挂隧道全解剖
系统目前拥有**两条绝对安全的平行跨网出海隧道**。

### 1. 业务展示舱通道（前端应用发布）
* **远端穿透**：HTTP 监听 `https://rag.liukun.com`
* **链路过程**：云端 FRPS (47.103.55.200) -> 深入容器 A 内置的 `frpc` (2028端口) -> 无缝连接到 Vite 的侦测板 (2028)。
* **配置阵列地**：`/Users/gemini/Projects/Own/RAG/frpc.toml` 中的 `[[proxies]]`。

### 2. DevOps 全境开发通道
我们为您定制了两种隔离维度的终极操控特权：

**【视角一：统帅上帝舱】** (针对管理编排)
* 功能：调控整套 `docker-compose` 编排生杀大权。
* 访问：使用外网 Antigravity 打开直连 `ssh -p 50022 gemini@...`
* 工作地标：`/Users/gemini/Projects/Own/RAG`

**【视角二：绝对开发舱】** (针对业务代码编写)
* 功能：屏蔽底层操作系统杂音，全身心浸入纯粹的 Linux (/app) 代码编写室。不受宿主环境牵绊，热插拔起效。
* 访问：使用外网 Antigravity 打开直连 **`ssh -p 60022 root@47.103.55.200`**
* 工作地标：`/app` 目录。

---

## 三、加密守卫指引 (Credential Keys)
目前全机最高守卫系统的密文清单如下：
- **RAG-Redis**：密码已锁死为 `Sy2026@sy`。
- **RAG-Server** (2222 SSH 盲区入口/60022 隧穿入口)：
  * 用户名：`root`
  * 根密码：`Sy2026@sy`
  * 密钥特征库：免密通行证书 (`kiro-ssh-key` 对应的特权公钥，存放于 `/root/.ssh/authorized_keys`)。

---

## 四、核心底层增强插件（附言）
**🔥 全局环境代理增强**
RAG-Server 全体组员（Node 及 Python 组件）目前已全量强制挂载指向了位于局域网 Mac 宿主上的翻越前哨：**Clash Verge (Port: 7897)**。
- 这意味着 RAG 后端所有针对 OpenAI 或境外数据库的大规模爬取，全部都会在底层黑盒中遁入 `host.docker.internal:7897` 绕关出海，不会有任何超时死锁。
