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
        "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt", 
        "https://raw.githubusercontent.com/WLget/V2Ray_configs_64/refs/heads/master/ConfigSub_list.txt",
        "https://raw.githubusercontent.com/ermaozi/get_subscribe/refs/heads/main/subscribe/v2ray.txt",
        "https://raw.githubusercontent.com/free18/v2ray/refs/heads/main/v.txt",
        "https://gist.githubusercontent.com/shuaidaoya/9e5cf2749c0ce79932dd9229d9b4162b/raw/base64.txt"
    ],
    # 目标国家：仅保留美国、香港、日本
    "target_countries": ["US", "HK", "JP"],
    "global_dns": "1.1.1.1",
    "china_dns": "223.5.5.5",
    "timeout": 5.0,
    "max_workers": 80
}

def safe_decode(data: str) -> str:
    if not data: return ""
    data = re.sub(r'[^A-Za-z0-9+/=]', '', data.replace("-", "+").replace("_", "/"))
    missing_padding = len(data) % 4
    if missing_padding: data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except: return ""

def get_ip_country(ip):
    """请求 IP 地理位置 API"""
    try:
        # 使用 ip-api.com 获取国家代码
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode", timeout=2)
        data = response.json()
        if data.get("status") == "success":
            return data.get("countryCode")
    except:
        pass
    return None

def test_node(link: str):
    """DNS 解析 -> 地理位置校验 -> TCP 测速"""
    try:
        host, port = None, None
        if link.startswith("vmess://"):
            p = json.loads(safe_decode(link[8:]))
            host, port = p.get("add"), int(p.get("port"))
        elif "://" in link:
            o = urlparse(link)
            host, port = o.hostname, o.port or 443
        
        if not host or not port: return None

        # 1. DNS 解析逻辑
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            # 阿里 DNS 预检国内可达性
            try:
                res_ali = dns.resolver.Resolver(); res_ali.nameservers = [CONFIG['china_dns']]
                res_ali.timeout = 2; res_ali.resolve(host, 'A')
            except: return None

            # 1.1.1.1 真实解析
            res_cf = dns.resolver.Resolver(); res_cf.nameservers = [CONFIG['global_dns']]
            res_cf.timeout = 2
            ip_to_test = str(res_cf.resolve(host, 'A')[0])
        else:
            ip_to_test = host

        # 2. 地理位置二次筛选
        country = get_ip_country(ip_to_test)
        if country not in CONFIG["target_countries"]:
            return None

        # 3. 实际 TCP 测速
        start = time.perf_counter()
        with socket.create_connection((ip_to_test, port), timeout=CONFIG["timeout"]):
            latency = (time.perf_counter() - start) * 1000
            return (link, latency)
    except:
        return None

def main():
    print(f"🚀 任务启动 | 目标地区: {CONFIG['target_countries']}")
    raw_all = []
    with requests.Session() as s:
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        for url in CONFIG["sources"]:
            try:
                r = s.get(url, timeout=10)
                content = r.text
                if "://" not in content[:100]: content = safe_decode(content)
                raw_all.extend(re.findall(r'(?:vmess|vless|ss|ssr|trojan)://[^\s|<>"]+', content))
            except: pass

    unique_nodes = list(dict.fromkeys(raw_all))
    print(f"💎 提取到去重节点: {len(unique_nodes)}，开始地理位置过滤与测速...")

    valid_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
        results = list(executor.map(test_node, unique_nodes))
        valid_list = [r for r in results if r]

    # 按延迟排序
    valid_list.sort(key=lambda x: x[1])
    final_nodes = [item[0] for item in valid_list]

    # 导出为 Base64 订阅格式
    out_b64 = base64.b64encode("\n".join(final_nodes).encode()).decode()
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(out_b64)
    
    print(f"🎉 任务完成！保留 {len(final_nodes)} 个符合要求的节点 (US/HK/JP)")

if __name__ == "__main__":
    main()
