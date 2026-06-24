import socket
import ssl
import datetime
import asyncio
import sys

def log(msg: str):
    """
    显式带时间戳和换行 flush 的日志输出，确保在 Docker 容器 PM2 中 100% 实时落盘。
    """
    tz_bj = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz_bj).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [SSL-CHECKER] {msg}", file=sys.stdout, flush=True)


async def trigger_caddy_renew():
    """
    通过 SSH 连云服务器，删除 Caddy 中指定域名的证书缓存并重启 Caddy 以立即重新申请。
    """
    log("⚠️ 正在触发远程 Caddy 清理旧证书缓存并重启...")
    cmd = (
        "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null sy_frp_server "
        "\"find /var/lib/caddy/.local/share/caddy/ -type d -name 'rag.liukun.com' -exec rm -rf {} + && systemctl restart caddy\""
    )
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        log("✅ 远程 Caddy 证书清空并重启成功，Caddy 已启动自动重新申请证书进程")
    else:
        log(f"❌ 远程 Caddy 证书重置失败: {stderr.decode().strip()}")


async def check_and_renew_ssl():
    """
    启动后延迟 1 分钟检查远程 rag.liukun.com 的 SSL 证书状态。
    若剩余天数少于 30 天（或证书已过期），则立刻触发远程 Caddy 重新申请。
    """
    log("⏳ SSL 证书有效期检查将在 60 秒后触发...")
    await asyncio.sleep(60)
    log("⏳ 开始执行 rag.liukun.com SSL 证书有效期检查...")

    hostname = "rag.liukun.com"
    port = 443
    try:
        # 使用默认的安全上下文（必须校验证书链，才能获取详细的 peercert 字典）
        context = ssl.create_default_context()
        
        # 建立连接
        reader, writer = await asyncio.open_connection(hostname, port, ssl=context, server_hostname=hostname)
        ssock = writer.get_extra_info('ssl_object')
        cert = ssock.getpeercert(binary_form=False)
        writer.close()
        await writer.wait_closed()

        if not cert:
            log("⚠️ 握手成功但未能获取到证书详情")
            return

        expire_str = cert.get('notAfter')
        if not expire_str:
            log("⚠️ 证书详情中未能找到过期时间 notAfter 字段")
            return

        # 示例 expire_str: 'Aug 31 16:42:47 2026 GMT'
        expire_date = datetime.datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z")
        remain_days = (expire_date - datetime.datetime.utcnow()).days
        log(f"📅 证书 rag.liukun.com 过期时间: {expire_str}，剩余有效期: {remain_days} 天")

        if remain_days < 30:
            log(f"⚠️ 证书有效期剩余 {remain_days} 天（少于 30 天），触发更新！")
            await trigger_caddy_renew()
        else:
            log("✅ 证书有效期充足，无需更新")

    except (ssl.SSLCertVerificationError, ssl.SSLError) as cert_err:
        # 如果抛出了 SSL 验证错误或过期错误，表明证书可能已经彻底过期或无效，同样需要触发重新申请
        log(f"⚠️ 证书连接发生安全异常，证书可能已过期或损坏: {cert_err}。将强制触发更新！")
        await trigger_caddy_renew()
    except Exception as e:
        log(f"❌ 检查或更新 SSL 证书失败: {e}")
