#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import base64
import socket
import concurrent.futures
import re
import json
import time
import dns.resolver  # 需要 pip install dnspython
from urllib.parse import urlparse

# --- 核心配置 ---
CONFIG = {
    "sources": [
        "https://raw.githubusercontent.com/freefq/free/master/v2",
        "https://raw.githubusercontent.com/vfarid/v2ray-worker-sub/master/Single",
        "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt"
    ],
    "dns_server": "223.5.5.5",  # 阿里公共 DNS
    "timeout": 5.0,
    "max_workers": 50
}

def safe_decode(data: str) -> str:
    if not data: return ""
    data = re.sub(r'[^A-Za-z0-9+/=]', '', data.replace("-", "+").replace("_", "/"))
    missing_padding = len(data) % 4
    if missing_padding: data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except: return ""

def resolve_by_ali(hostname: str) -> str:
    """使用阿里 DNS 解析域名"""
    # 如果本身就是 IP，直接返回
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", hostname):
        return hostname
    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [CONFIG["dns_server"]]
        resolver.timeout = 2.0
        resolver.lifetime = 2.0
        answers = resolver.resolve(hostname, 'A')
        return str(answers[0])
    except Exception:
        return None

def extract_node_info(link: str):
    try:
        if link.startswith("vmess://"):
            p = json.loads(safe_decode(link[8:]))
            return p.get("add"), int(p.get("port"))
        elif "://" in link:
            o = urlparse(link)
            if o.hostname and o.port:
                return o.hostname, int(o.port)
    except: pass
    return None, None

def test_node(link: str):
    """阿里 DNS 解析 + TCP 握手双重验证"""
    host, port = extract_node_info(link)
    if not host or not port: return None
    
    # 步骤 1: 阿里 DNS 解析验证
    resolved_ip = resolve_by_ali(host)
    if not resolved_ip:
        return None  # DNS 无法解析，直接弃用

    # 步骤 2: TCP 连接验证 (使用解析后的 IP 速度更快)
    try:
        start = time.perf_counter()
        with socket.create_connection((resolved_ip, port), timeout=CONFIG["timeout"]):
            latency = (time.perf_counter() - start) * 1000
            return (link, latency)
    except:
        return None

def main():
    print(f"🚀 开始任务，使用 DNS: {CONFIG['dns_server']}")
    raw_all = []
    with requests.Session() as s:
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        for url in CONFIG["sources"]:
            try:
                r = s.get(url, timeout=10)
                content = r.text
                if "://" not in content[:50]: content = safe_decode(content)
                found = re.findall(r'(?:vmess|vless|ss|ssr|trojan)://[^\s|<>"]+', content)
                raw_all.extend(found)
                print(f"✅ 从源提取到 {len(found)} 个节点")
            except: pass

    unique_nodes = list(dict.fromkeys(raw_all))
    print(f"💎 去重后 {len(unique_nodes)} 个，开始双重验证...")

    valid_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
        futures = {executor.submit(test_node, n): n for n in unique_nodes}
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res: valid_list.append(res)

    valid_list.sort(key=lambda x: x[1])
    final_nodes = [item[0] for item in valid_list]

    # 保底
    if not final_nodes: final_nodes = unique_nodes[:5]

    out_content = base64.b64encode("\n".join(final_nodes).encode()).decode()
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(out_content)
    
    print(f"🎉 验证完成！最终保留 {len(final_nodes)} 个节点")

if __name__ == "__main__":
    main()
