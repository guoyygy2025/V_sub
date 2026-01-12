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
from urllib.parse import urlparse, quote, unquote

# --- 核心配置 ---
CONFIG = {
    "sources": [
        "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt", 
        "https://raw.githubusercontent.com/WLget/V2Ray_configs_64/refs/heads/master/ConfigSub_list.txt",
        "https://raw.githubusercontent.com/ermaozi/get_subscribe/refs/heads/main/subscribe/v2ray.txt",
        "https://raw.githubusercontent.com/free18/v2ray/refs/heads/main/v.txt",
        "https://gist.githubusercontent.com/shuaidaoya/9e5cf2749c0ce79932dd9229d9b4162b/raw/base64.txt"
    ],
    "global_dns": "1.1.1.1",
    "china_dns": "223.5.5.5",
    "timeout": 0.4,
    "max_workers": 80,
    "max_node_count": 100
}

# 国家代码对应中文名字典
COUNTRY_NAMES = {
    "CN": "中国", "HK": "香港", "TW": "台湾", "US": "美国", "JP": "日本", 
    "KR": "韩国", "SG": "新加坡", "FR": "法国", "DE": "德国", "GB": "英国",
    "RU": "俄罗斯", "CA": "加拿大", "AU": "澳大利亚", "NL": "荷兰"
}

def safe_decode(data: str) -> str:
    if not data: return ""
    data = re.sub(r'[^A-Za-z0-9+/=]', '', data.replace("-", "+").replace("_", "/"))
    missing_padding = len(data) % 4
    if missing_padding: data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except: return ""

def get_ip_info(ip):
    """获取 IP 的国家代码"""
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode", timeout=2)
        data = r.json()
        if data.get("status") == "success":
            code = data.get("countryCode")
            return COUNTRY_NAMES.get(code, code) # 优先返回中文名
    except: pass
    return "未知"

def rename_node(link, country, latency):
    """根据国家和延迟重命名节点"""
    new_name = f"{country} | {int(latency)}ms"
    try:
        if link.startswith("vmess://"):
            data = json.loads(safe_decode(link[8:]))
            data['ps'] = new_name
            return "vmess://" + base64.b64encode(json.dumps(data).encode()).decode()
        elif "://" in link:
            # 处理 SS/SSR/Trojan 等通过 # 命名的情况
            base_url = link.split("#")[0]
            return f"{base_url}#{quote(new_name)}"
    except: pass
    return link

def test_node(link: str):
    """核心逻辑：解析 -> 测速 -> 获取地理位置 -> 重命名"""
    try:
        host, port = None, None
        if link.startswith("vmess://"):
            p = json.loads(safe_decode(link[8:]))
            host, port = p.get("add"), int(p.get("port"))
        elif "://" in link:
            o = urlparse(link)
            host, port = o.hostname, o.port or 443
        
        if not host or not port: return None

        # DNS 解析
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            res_cf = dns.resolver.Resolver(); res_cf.nameservers = [CONFIG['global_dns']]
            res_cf.timeout = 2
            ip_to_test = str(res_cf.resolve(host, 'A')[0])
        else:
            ip_to_test = host

        # TCP 测速
        start = time.perf_counter()
        with socket.create_connection((ip_to_test, port), timeout=CONFIG["timeout"]):
            latency = (time.perf_counter() - start) * 1000
            
            # 获取地理位置
            country = get_ip_info(ip_to_test)
            
            # 执行重命名
            new_link = rename_node(link, country, latency)
            return (new_link, latency)
    except: return None

def main():
    print("🚀 启动重命名模式：[国家 + 延迟]")
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
    print(f"💎 原始节点: {len(unique_nodes)} 个，开始测速与重命名...")

    valid_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
        results = list(executor.map(test_node, unique_nodes))
        valid_list = [r for r in results if r]

    # 排序并截取
    valid_list.sort(key=lambda x: x[1])
    final_nodes = [item[0] for item in valid_list[:CONFIG["max_node_count"]]]

    # 写入文件
    out_b64 = base64.b64encode("\n".join(final_nodes).encode()).decode()
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(out_b64)
    
    print(f"🎉 任务完成！已生成 {len(final_nodes)} 个重命名后的节点。")

if __name__ == "__main__":
    main()
