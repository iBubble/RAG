FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# Mac Studio 是 ARM64 架构，其 Ubuntu 包源地址是 ports.ubuntu.com
# 构建时通过 --build-arg 传入 root 密码，避免硬编码
ARG ROOT_PASSWORD

RUN apt-get update && \
    apt-get install -y python3 python3-pip curl vim sudo git ca-certificates openssh-server \
        poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
        fonts-noto-cjk fonts-wqy-zenhei dotnet-sdk-8.0 ffmpeg golang-go && \
    fc-cache -fv && \
    mkdir -p /run/sshd && \
    mkdir -p /root/.ssh && chmod 700 /root/.ssh && \
    chmod 600 /root/.ssh/authorized_keys 2>/dev/null || true && \
    echo "root:${ROOT_PASSWORD}" | chpasswd && \
    sed -i '1iPermitRootLogin yes' /etc/ssh/sshd_config && \
    sed -i '1iPasswordAuthentication yes' /etc/ssh/sshd_config && \
    sed -i '1iPubkeyAuthentication yes' /etc/ssh/sshd_config && \
    echo "PubkeyAcceptedAlgorithms +ssh-rsa" >> /etc/ssh/sshd_config && \
    echo 'ClientAliveInterval 30' >> /etc/ssh/sshd_config && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pm2 && \
    curl -L -k "https://ghproxy.net/https://github.com/fatedier/frp/releases/download/v0.56.0/frp_0.56.0_linux_arm64.tar.gz" -o frp.tar.gz && \
    tar -zxvf frp.tar.gz && mv frp_0.56.0_linux_arm64/frpc /usr/local/bin/ && chmod +x /usr/local/bin/frpc && rm -rf frp* && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/
# 使用国内 PyPI 镜像源加速下载
RUN cd /app/backend && pip3 install --no-cache-dir --default-timeout=120 -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt


COPY frontend/package.json /app/frontend/
RUN cd /app/frontend && npm install

CMD ["bash", "start.sh"]
