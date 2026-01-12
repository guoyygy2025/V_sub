#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
V2Ray 节点自动抓取、解析、去重与测速工具 (GitHub Actions 适配版)
"""

import requests
import base64
import socket
import concurrent.futures
import re
import sys
import time
import json
import os
import threading
from urllib.parse import urlparse, unquote
from functools import lru_cache
import dns.resolver

# --- 核心配置 ---
CONFIG = {
    "sources": [
        "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt",
        "https://raw.githubusercontent.com/WLget/V2Ray_configs_64/master/ConfigSub_list.txt",
        "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt",
        "https://raw.githubusercontent.com/free18/v2ray/main/v.txt",
        "https://gist.githubusercontent.com/shuaidaoya/9e5cf2749c0ce79932dd9229d9b4162b/raw/base64.txt"
    ],
    "dns_server": "223.5.5.5",       # 阿里 DNS
    "timeout": 2.0,                  # TCP 连接超时 (秒)
    "max_workers": 100,              # 最大并发线程
    "filter_keywords": ["官网", "剩余", "到期", "流量", "时间", "群", "TG", "教程"],
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# --- 辅助工具 ---

def safe_decode(data: str) -> str:
    """鲁棒的 Base64 解码"""
    if not data: return ""
    data = data.replace("-", "+").replace("_", "/")
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except:
        return ""

@lru_cache(maxsize=2048)
def resolve_domain(hostname: str) -> str:
    """带缓存的 DNS 解析"""
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", hostname):
        return hostname
    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [CONFIG["dns_server"]]
        resolver.lifetime = 2.0 
        answer = resolver.resolve(hostname, "A")
        return str(answer[0])
    except:
        return None

class NodeParser:
    @staticmethod
    def parse(node_link: str):
        link = node_link.strip()
        try:
            if link.startswith("vmess://"):
                return NodeParser._parse_vmess(link)
            elif link.startswith("ss://"):
                return NodeParser._parse_ss(link)
            elif link.startswith("ssr://"):
                return NodeParser._parse_ssr(link)
            elif link.startswith(("vless://", "trojan://")):
                return NodeParser._parse_url_standard(link)
        except:
            pass
        return None, None, None

    @staticmethod
    def _parse_vmess(link):
        try:
            data = json.loads(safe_decode(link[8:]))
            return data.get("add"), int(data.get("port")), data.get("ps", "")
        except:
            return None, None, None

    @staticmethod
    def _parse_ss(link):
        try:
            body = link[5:].split("#")[0]
            if "@" in body and ":" not in body.split("@")[0]:
                # ss://base64(method:pass)@host:port
                decoded_user = safe_decode(body.split("@")[0])
                host_part = body.split("@")[1]
            else:
                # ss://base64(method:pass@host:port)
                decoded = safe_decode(body)
                if "@" in decoded:
                    host_part = decoded.split("@")[1]
                else:
                    return None, None, None
            
            if ":" in host_part:
                host, port = host_part.split(":")
                return host, int(port), ""
        except:
            pass
        return None, None, None

    @staticmethod
    def _parse_ssr(link):
        try:
            decoded = safe_decode(link[6:])
            parts = decoded.split(":")
            if len(parts) >= 2:
                return parts[0], int(parts[1]), ""
        except:
            pass
        return None, None, None

    @staticmethod
    def _parse_url_standard(link):
        parsed = urlparse(link)
        return parsed.hostname, parsed.port, unquote(parsed.fragment or "")

# --- 核心逻辑 ---

def fetch_subscriptions():
    print("🔍 [1/3] 正在抓取订阅源...")
    nodes = []
    
    def _fetch(url):
        try:
            resp = requests.get(url, headers={"User-Agent": CONFIG["user_agent"]}, timeout=15)
            if resp.status_code != 200: return []
            content = resp.text.strip()
            
            # 检测是否需要整体解码
            if not re.search(r'://', content[:100]):
                content = safe_decode(content)
            
            found = re.findall(r'(vmess|vless|ss|ssr|trojan)://[a-zA-Z0-9\+\-\=_/%\.\:\@\#]+', content)
            return found
        except Exception:
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_fetch, url) for url in CONFIG["sources"]]
        for future in concurrent.futures.as_completed(futures):
            nodes.extend(future.result())
            
    return list(set(nodes))

def check_node(node_link):
    host, port, remarks = NodeParser.parse(node_link)
    
    if not host or not port: return None
    
    # 关键词过滤
    if remarks:
        for kw in CONFIG["filter_keywords"]:
            if kw in remarks: return None

    # DNS 解析
    ip = resolve_domain(host)
    if not ip: return None

    # TCP 测速
    try:
        start_time = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONFIG["timeout"])
        result = sock.connect_ex((ip, port))
        sock.close()
        
        if result == 0:
            latency = (time.perf_counter() - start_time) * 1000
            return (node_link, latency, f"{ip}:{port}")
    except:
        pass
    return None

def main():
    # 1. 获取
    raw_nodes = fetch_subscriptions()
    print(f"📦 获取到 {len(raw_nodes)} 个原始节点")
    
    if not raw_nodes:
        print("❌ 未获取到节点")
        sys.exit(0)

    # 2. 测速
    print(f"⚡ [2/3] 开始并发测速 (Timeout: {CONFIG['timeout']}s)...")
    
    valid_nodes = []
    seen_host_port = set()
    total = len(raw_nodes)
    completed = 0
    is_ci = os.getenv('GITHUB_ACTIONS') == 'true'
    lock = threading.Lock()

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['max_workers']) as executor:
        futures = {executor.submit(check_node, node): node for node in raw_nodes}
        
        for future in concurrent.futures.as_completed(futures):
            with lock:
                completed += 1
                # 仅在本地运行时显示动态进度条，CI 环境每 10% 打印一次日志
                if not is_ci:
                    percent = (completed / total) * 100
                    bar = '█' * int(percent / 2) + '-' * (50 - int(percent / 2))
                    sys.stdout.write(f"\r|{bar}| {percent:.1f}%")
                    sys.stdout.flush()
                elif completed % (total // 10 + 1) == 0:
                    print(f"   ...进度: {int(completed/total*100)}%")

            res = future.result()
            if res:
                link, latency, unique_id = res
                # 逻辑去重
                if unique_id not in seen_host_port:
                    seen_host_port.add(unique_id)
                    valid_nodes.append((link, latency))

    print("\n")

    # 3. 保存
    print("💾 [3/3] 正在保存结果...")
    valid_nodes.sort(key=lambda x: x[1])
    final_links = [n[0] for n in valid_nodes]
    
    # 写入文件
    with open("subscribe_plain.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(final_links))
        
    b64_content = base64.b64encode("\n".join(final_links).encode("utf-8")).decode()
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(b64_content)

    print(f"🎉 完成！有效节点: {len(valid_nodes)} 个")
    if valid_nodes:
        print(f"   平均延迟: {sum(n[1] for n in valid_nodes)/len(valid_nodes):.1f} ms")

if __name__ == "__main__":
    main()
