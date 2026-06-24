FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# Mac Studio 是 ARM64 架构，其 Ubuntu 包源地址是 ports.ubuntu.com
RUN apt-get update && \
    apt-get install -y python3 python3-pip curl vim sudo git ca-certificates openssh-server \
        poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
        fonts-noto-cjk fonts-wqy-zenhei dotnet-sdk-8.0 ffmpeg golang-go && \
    fc-cache -fv && \
    mkdir -p /run/sshd && \
    mkdir -p /root/.ssh && chmod 700 /root/.ssh && \
    echo 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDNuNL4c45/5NHVELswRacN5eeBxzk90RYK0fja1uYqeAOLkROTLx8MrDhBm5ZpxDOICQiAWEoGFOvvrwOIjHx/YH+koST11+BeFonNOhqp5VLW1sxvmDPuLR2WjPwlhfWD1OPmuMBYGqJklntLODBJjV8AGH3ZEyqNT/SmMWwMPKYPvh0MbS9V1i5meiZircZ9bbY0dXFwl3COPfEs6p3Q87CGZYahP/XwRKNDz1oiX74+VPmxaI2PE6JJpvUQ6Ew7Z1lPxfEBY8urVDAODLnKxgMDsrcUYDwNiMITVV/Kzw4tCg6/SNJjTznMOcwXHy3wgCBxHQ8QtiQ+PmAZnCR7kSuD93y9xzKB9IVlZLVJdVVBZF8PARQ4kPcbd4EqwdKlkaDTKOevc7+WyTSX4JKyqb3ijKHYo3o4CT5e1hjODb2jjuOTzjyTjks6LCY9Bu02gkgh5l7BD3/04gQM5sax0XmjeFwVpCCPfhg9yxegwUERs/clOsfHnaUUMHqoIGRoT6tVsHVpRfglZSYdRMV+kiy50YpvHB8E4D/dbQPgjQaHxGP7wjkQjNuEFaWg+/KvmV4A0xqYAIv4HYqOHdQY5XR9wmaMpc5GgmlF++FEMZi8WP3D6i75togVuCgcKJ9Fj94oTxdgmlQLhVsBptA+0iI41Y605J9lc11NnZnkKw== kiro-ssh-key' > /root/.ssh/authorized_keys && \
    chmod 600 /root/.ssh/authorized_keys && \
    echo 'root:Sy2026@sy' | chpasswd && \
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
