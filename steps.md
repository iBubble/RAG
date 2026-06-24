markdown
# Local Deployment Task Checklist (steps.md)
# 目标：在本地 MacBook Pro (M4 Max) 上重现并运行 ShengyaoRAG 系统
## 📋 上下文信息与背景知识
1. **系统架构**：这是一个基于 Docker 容器化的微服务系统，包含核心应用服务（RAG-Server：React 前端 + FastAPI 后端 + Celery 任务队列）、Redis 缓存，以及 Qdrant 向量数据库。
2. **大模型部署策略**：为了发挥本地 M4 Max 的 GPU 推理性能，大模型（Qwen3.6-35B-A3B 量化版）需部署在 Mac 宿主机本地的 Ollama 上，应用容器通过 `host.docker.internal` 访问宿主机 Ollama。
3. **只读保护避坑限制**：系统内置了 `watchdog.py`，会定期检查容器内 `/Volumes/SYRAID/RAG_Files` 目录是否存在。若不存在，系统会强制进入“只读保护模式 (Read-Only)”，导致所有写入/生成请求报 503 错误。因此，必须在本地将 `/Volumes/macData/RAG_Files` 挂载到容器内该对应路径。
---
## 🛠️ 任务清单 (Tasks)
### [x] 任务 1：从远程服务器拉取项目代码与资料文件
在本地 Mac 终端中运行以下命令，完成项目代码与历史资料的拉取：
1. **同步项目源码**：
   ```bash
   # 新建本地项目根目录
   mkdir -p /Users/gemini/Projects/Own/RAG/app-server
   
   # 从远程开发舱同步源码（开发舱 SSH 端口为 60022，密码为 Sy2026@sy）
   rsync -avzP -e "ssh -p 60022" root@47.103.55.200:/app/ /Users/gemini/Projects/Own/RAG/app-server/
同步资料卷数据：
bash
# 新建本地挂载资料目录
mkdir -p /Volumes/macData/RAG_Files
# 从远程宿主机管理口同步资料（管理口 SSH 端口为 50022，用户名为 shengyao）
rsync -avzP -e "ssh -p 50022" shengyao@47.103.55.200:/Volumes/SYRAID/RAG_Files/ /Volumes/macData/RAG_Files/
[x] 任务 2：创建本地 docker-compose.yml 配置文件
在本地项目根目录 /Users/gemini/Projects/Own/RAG/ 下（即与拉取下来的 app-server 文件夹同级）创建 docker-compose.yml，用于微服务容器编排：

文件内容：

yaml
version: '3.8'
services:
  # 1. 向量数据库 (Qdrant)
  rag-database:
    image: qdrant/qdrant:latest
    container_name: rag-database
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./data/qdrant_storage:/qdrant/storage
    restart: always
  # 2. 高速缓存与消息队列 (Redis)
  rag-redis:
    image: redis:alpine
    container_name: rag-redis
    ports:
      - "6379:6379"
    command: redis-server --requirepass Sy2026@sy
    volumes:
      - ./data/redis_data:/data
    restart: always
  # 3. 核心应用中枢 (React 前端 + FastAPI 后端 + Celery 异步队列)
  rag-server:
    build:
      context: ./app-server
      dockerfile: Dockerfile
    container_name: rag-server
    extra_hosts:
      - "host.docker.internal:host-gateway" # 支持容器访问宿主机的 Ollama 接口
    ports:
      - "2026:2026"  # 前端网页服务映射端口
      - "8001:8001"  # 后端 API 服务映射端口
      - "60022:22"   # SSH 调试端口
    volumes:
      - ./app-server:/app
      # 将 Mac 本地资料卷映射为系统心跳检测的路径，规避只读熔断
      - /Volumes/macData/RAG_Files:/Volumes/SYRAID/RAG_Files
    environment:
      - TZ=Asia/Shanghai
    depends_on:
      - rag-database
      - rag-redis
    restart: always
[x] 任务 3：创建后端环境变量配置文件
在本地 /Users/gemini/Projects/Own/RAG/app-server/backend/ 目录下创建 .env 文件。

文件内容：

ini
OLLAMA_BASE_URL="http://host.docker.internal:11434"
FRONTEND_URL="http://localhost:2026"
ALLOW_ORIGINS="http://localhost:2026,http://localhost:8001"
# 鉴权凭据密钥（建议与您从服务器拉取下来的数据库一致，或自定义）
JWT_SECRET="CHANGE_ME_use_openssl_rand_hex_32"
ADMIN_INIT_PASSWORD="CHANGE_ME_admin_initial_password"
[x] 任务 4：在 Mac 本地部署并运行 Qwen3.6-35B-A3B 大模型
从魔搭下载 4-bit 量化权重文件：

魔搭社区（ModelScope）合集：https://www.modelscope.cn/collections/Qwen/Qwen36
进入仓库：Qwen/Qwen3.6-35B-A3B-GGUF
下载文件：qwen3.6-35b-a3b-q4_k_m.gguf （约 20-22 GB）
提示：可以使用魔搭命令行快速下载：
bash
pip install modelscope
python3 -c "from modelscope import model_file_download; model_file_download(model_id='Qwen/Qwen3.6-35B-A3B-GGUF', file_path='qwen3.6-35b-a3b-q4_k_m.gguf', cache_dir='./')"
在本地 Ollama 中注册该模型： 在权重文件同级目录下，创建文本文件 Modelfile，输入以下内容：

dockerfile
FROM ./qwen3.6-35b-a3b-q4_k_m.gguf
在终端运行命令创建模型：

bash
ollama create qwen3.6:35b-q4 -f Modelfile
开启 Ollama 外部网络监听： 在 Mac 本地终端配置环境变量（以允许 Docker 容器连接宿主机的 Ollama 端口），并重启 Ollama 客户端：

bash
export OLLAMA_HOST="0.0.0.0"
[x] 任务 5：OrbStack 容器起锚与测试验证
一键构建与运行服务： 启动本地 OrbStack，在 /Users/gemini/Projects/Own/RAG/ 目录下执行：

bash
docker-compose up -d --build
注意：首次启动构建时，镜像会自动预载 BGE-M3 (568M) 和 Reranker (300M) 两个模型（共约 2.2GB），这可能会耗时数分钟。

服务健康验证：

访问前端：http://localhost:2026
访问后端 API Docs：http://localhost:8001/docs
测试在前端“Document Studio”上传文档、配置范文，并执行流式生成，确认本地 M4 Max 的推理速度与稳定性。