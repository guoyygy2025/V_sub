#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

# --- 核心配置 ---
CONFIG = {
    "sources": [
        "https://raw.githubusercontent.com/freefq/free/master/v2",
        "https://raw.githubusercontent.com/vfarid/v2ray-worker-sub/master/Single",
        "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt",
        "https://raw.githubusercontent.com/v2ray-free/v2ray/master/v2ray"
    ],
    "timeout": 5.0,                  # 增加超时到 5 秒，防止 Action 服务器网络波动
    "max_workers": 100,
    "filter_keywords": ["官网", "到期", "流量", "网站"],
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def safe_decode(data: str) -> str:
    if not data: return ""
    data = data.replace("-", "+").replace("_", "/")
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except:
        return ""

def extract_node_info(node_link: str):
    """解析节点返回 host 和 port"""
    try:
        link = node_link.strip()
        if link.startswith("vmess://"):
            data = json.loads(safe_decode(link[8:]))
            return data.get("add"), int(data.get("port"))
        elif link.startswith(("vless://", "trojan://", "ss://")):
            parsed = urlparse(link)
            host = parsed.hostname
            port = parsed.port or 443
            return host, port
    except:
        pass
    return None, None

def test_node(node_link):
    host, port = extract_node_info(node_link)
    if not host or not port: return None
    
    # 关键词简单过滤
    for kw in CONFIG["filter_keywords"]:
        if kw in node_link: return None

    try:
        # 使用系统默认解析，移除强制指定的 DNS 提高兼容性
        start_time = time.perf_counter()
        with socket.create_connection((host, port), timeout=CONFIG["timeout"]):
            latency = (time.perf_counter() - start_time) * 1000
            return (node_link, latency)
    except:
        return None

def main():
    print("开始抓取订阅源...")
    all_raw_nodes = []
    
    with requests.Session() as s:
        s.headers.update({"User-Agent": CONFIG["user_agent"]})
        for url in CONFIG["sources"]:
            try:
                r = s.get(url, timeout=15)
                content = r.text.strip()
                if not content: continue
                
                # 自动判定并解码
                if not re.search(r'://', content[:50]):
                    content = safe_decode(content)
                
                found = re.findall(r'(vmess|vless|ss|ssr|trojan)://[^\s]+', content)
                all_raw_nodes.extend(found)
                print(f"成功从 {url[:30]}... 抓取 {len(found)} 个节点")
            except Exception as e:
                print(f"抓取失败 {url[:30]}: {e}")

    unique_nodes = list(set(all_raw_nodes))
    print(f"去重后总数: {len(unique_nodes)}")

    if not unique_nodes:
        print("警告: 未抓取到任何节点！")
        return

    print("开始并发测速...")
    valid_nodes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['max_workers']) as executor:
        futures = {executor.submit(test_node, n): n for n in unique_nodes}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                valid_nodes.append(res)

    valid_nodes.sort(key=lambda x: x[1])
    final_links = [n[0] for n in valid_nodes]

    # 强制逻辑：如果测速后一个可用的都没有，保留前 5 个原始节点防止文件为空
    if not final_links and unique_nodes:
        print("测速全部失败，保留原始前 5 个节点作为占位")
        final_links = unique_nodes[:5]

    # 保存 Base64
    b64_content = base64.b64encode("\n".join(final_links).encode()).decode()
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(b64_content)
    
    print(f"任务完成，有效节点: {len(final_links)}")

if __name__ == "__main__":
    main()
