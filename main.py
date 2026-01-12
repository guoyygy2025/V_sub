#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import base64
import socket
import concurrent.futures
import re
import json
import time
import dns.resolver
from urllib.parse import urlparse

# --- 核心配置 ---
CONFIG = {
    "sources": [
        "https://raw.githubusercontent.com/freefq/free/master/v2",
        "https://raw.githubusercontent.com/vfarid/v2ray-worker-sub/master/Single",
        "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt",
        "https://raw.githubusercontent.com/v2ray-free/v2ray/master/v2ray"
    ],
    "global_dns": "1.1.1.1",      # Cloudflare DNS: 用于 GitHub 环境极速解析
    "china_dns": "223.5.5.5",     # 阿里 DNS: 用于模拟国内解析环境，过滤污染节点
    "timeout": 0.4,               # 测速超时
    "max_workers": 80             # 并发数
}

def safe_decode(data: str) -> str:
    """标准 Base64 解码"""
    if not data: return ""
    data = re.sub(r'[^A-Za-z0-9+/=]', '', data.replace("-", "+").replace("_", "/"))
    missing_padding = len(data) % 4
    if missing_padding: data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except: return ""

def get_resolver(nameserver: str):
    """配置 DNS 解析器"""
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [nameserver]
    resolver.timeout = 2.0
    resolver.lifetime = 2.0
    return resolver

def test_node(link: str):
    """双重 DNS 校验 + TCP 测速"""
    try:
        host, port = None, None
        if link.startswith("vmess://"):
            p = json.loads(safe_decode(link[8:]))
            host, port = p.get("add"), int(p.get("port"))
        elif "://" in link:
            o = urlparse(link)
            host, port = o.hostname, o.port or 443
        
        if not host or not port: return None

        # 如果是 IP 则直接测试，如果是域名则进行双重解析
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            # 1. 阿里 DNS 校验 (检查国内解析是否正常)
            try:
                get_resolver(CONFIG["china_dns"]).resolve(host, 'A')
            except:
                return None # 阿里解析失败，说明国内大概率不可用

            # 2. 1.1.1.1 获取解析后的实际 IP
            answers = get_resolver(CONFIG["global_dns"]).resolve(host, 'A')
            ip_to_test = str(answers[0])
        else:
            ip_to_test = host

        # 3. TCP 握手测速
        start = time.perf_counter()
        with socket.create_connection((ip_to_test, port), timeout=CONFIG["timeout"]):
            latency = (time.perf_counter() - start) * 1000
            return (link, latency)
    except:
        return None

def main():
    print(f"🚀 启动测速优化方案: 1.1.1.1 (海外解析) + {CONFIG['china_dns']} (国内校验)")
    raw_all = []
    
    with requests.Session() as s:
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        for url in CONFIG["sources"]:
            try:
                r = s.get(url, timeout=15)
                content = r.text
                if "://" not in content[:100]: content = safe_decode(content)
                found = re.findall(r'(?:vmess|vless|ss|ssr|trojan)://[^\s|<>"]+', content)
                raw_all.extend(found)
                print(f"✅ 源 {url[:25]}... 提取到 {len(found)} 个节点")
            except: pass

    unique_nodes = list(dict.fromkeys(raw_all))
    print(f"💎 待测节点总数: {len(unique_nodes)}，开始验证...")

    valid_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
        results = list(executor.map(test_node, unique_nodes))
        valid_list = [r for r in results if r]

    # 按延迟排序
    valid_list.sort(key=lambda x: x[1])
    final_nodes = [item[0] for item in valid_list]

    # 保底输出（如果全部不通，保留前5个原始节点）
    if not final_nodes: final_nodes = unique_nodes[:5]

    # 结果转为 Base64 写入文件
    out_b64 = base64.b64encode("\n".join(final_nodes).encode()).decode()
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(out_b64)
    
    print(f"🎉 任务完成！最终保留有效节点: {len(final_nodes)} 个")

if __name__ == "__main__":
    main()
