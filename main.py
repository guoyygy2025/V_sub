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
from urllib.parse import urlparse

# --- 核心配置 ---
CONFIG = {
    "sources": [
        "https://raw.githubusercontent.com/freefq/free/master/v2",
        "https://raw.githubusercontent.com/vfarid/v2ray-worker-sub/master/Single",
        "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt",
        "https://raw.githubusercontent.com/v2ray-free/v2ray/master/v2ray"
    ],
    "timeout": 5.0,
    "max_workers": 100,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def safe_decode(data: str) -> str:
    if not data: return ""
    data = re.sub(r'[^A-Za-z0-9+/=]', '', data.replace("-", "+").replace("_", "/"))
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except:
        return ""

def extract_node_info(node_link: str):
    try:
        if node_link.startswith("vmess://"):
            v_json = safe_decode(node_link[8:])
            data = json.loads(v_json)
            return data.get("add"), int(data.get("port"))
        elif "://" in node_link:
            parsed = urlparse(node_link)
            if parsed.hostname and parsed.port:
                return parsed.hostname, int(parsed.port)
            # 处理 ss://base64 格式
            host_part = parsed.netloc if "@" in parsed.netloc else safe_decode(parsed.netloc)
            if ":" in host_part:
                h, p = host_part.split(":")[-2:]
                return h, int(p)
    except:
        pass
    return None, None

def test_node(node_link):
    host, port = extract_node_info(node_link)
    if not host or not port: return None
    try:
        start_time = time.perf_counter()
        with socket.create_connection((host, port), timeout=CONFIG["timeout"]):
            latency = (time.perf_counter() - start_time) * 1000
            return (node_link, latency)
    except:
        return None

def main():
    all_raw_nodes = []
    with requests.Session() as s:
        s.headers.update({"User-Agent": CONFIG["user_agent"]})
        for url in CONFIG["sources"]:
            try:
                r = s.get(url, timeout=15)
                content = r.text.strip()
                if not content: continue
                # 尝试解码整个订阅包
                decoded_content = safe_decode(content)
                if "://" in decoded_content:
                    content = decoded_content
                
                # 改进后的正则表达式：匹配 :// 及其后的非空白字符，且长度至少大于 10 (防止只抓到协议头)
                found = re.findall(r'(?:vmess|vless|ss|ssr|trojan)://[^\s\u4e00-\u9fa5]{10,}', content)
                all_raw_nodes.extend(found)
                print(f"源 {url[:20]}... 提取到 {len(found)} 个节点")
            except Exception as e:
                print(f"抓取错误: {e}")

    unique_nodes = list(dict.fromkeys(all_raw_nodes))
    print(f"去重后总数: {len(unique_nodes)}")

    if not unique_nodes:
        print("未发现有效节点内容，请检查源。")
        return

    valid_nodes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['max_workers']) as executor:
        futures = {executor.submit(test_node, n): n for n in unique_nodes}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                valid_nodes.append(res)

    valid_nodes.sort(key=lambda x: x[1])
    # 如果测速一个没过，保底保留 10 个节点供手动尝试
    final_output = [n[0] for n in valid_nodes] if valid_nodes else unique_nodes[:10]

    b64_content = base64.b64encode("\n".join(final_output).encode()).decode()
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(b64_content)
    print(f"任务结束，最终生成节点数: {len(final_output)}")

if __name__ == "__main__":
    main()
