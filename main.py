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
import maxminddb  # 用于读取离线数据库
from urllib.parse import urlparse, quote

# --- 核心配置 ---
CONFIG = {
    "sources": [
        "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt", 
        "https://raw.githubusercontent.com/WLget/V2Ray_configs_64/refs/heads/master/ConfigSub_list.txt",
        "https://raw.githubusercontent.com/ermaozi/get_subscribe/refs/heads/main/subscribe/v2ray.txt",
        "https://raw.githubusercontent.com/free18/v2ray/refs/heads/main/v.txt",
        "https://gist.githubusercontent.com/shuaidaoya/9e5cf2749c0ce79932dd9229d9b4162b/raw/base64.txt"
    ],
    "mmdb_path": "Country.mmdb", # 离线数据库路径
    "global_dns": "1.1.1.1",
    "china_dns": "223.5.5.5",
    "timeout": 0.4,
    "max_workers": 100, # 离线查询极快，可以大幅提高并发
    "max_node_count": 100
}

# 扩展国家对照表
COUNTRY_NAMES = {
    "CN": "中国", "HK": "香港", "TW": "台湾", "US": "美国", "JP": "日本", 
    "KR": "韩国", "SG": "新加坡", "FR": "法国", "DE": "德国", "GB": "英国",
    "RU": "俄罗斯", "CA": "加拿大", "AU": "澳大利亚", "NL": "荷兰", "IN": "印度",
    "TR": "土耳其", "BR": "巴西", "TH": "泰国", "VN": "越南", "MY": "马来西亚"
}

def safe_decode(data: str) -> str:
    if not data: return ""
    data = re.sub(r'[^A-Za-z0-9+/=]', '', data.replace("-", "+").replace("_", "/"))
    missing_padding = len(data) % 4
    if missing_padding: data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except: return ""

def get_country_offline(ip, reader):
    """从离线数据库获取国家名称"""
    try:
        res = reader.get(ip)
        if res:
            code = res.get('country', {}).get('iso_code') or res.get('registered_country', {}).get('iso_code')
            return COUNTRY_NAMES.get(code, code)
    except: pass
    return "未知"

def rename_node(link, country, latency):
    new_name = f"{country} | {int(latency)}ms"
    try:
        if link.startswith("vmess://"):
            data = json.loads(safe_decode(link[8:]))
            data['ps'] = new_name
            return "vmess://" + base64.b64encode(json.dumps(data).encode()).decode()
        elif "://" in link:
            base_url = link.split("#")[0]
            return f"{base_url}#{quote(new_name)}"
    except: pass
    return link

def test_node(link: str, reader):
    try:
        host, port = None, None
        if link.startswith("vmess://"):
            p = json.loads(safe_decode(link[8:]))
            host, port = p.get("add"), int(p.get("port"))
        elif "://" in link:
            o = urlparse(link)
            host, port = o.hostname, o.port or 443
        
        if not host or not port: return None

        # 1.1.1.1 解析
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
            
            # 离线获取国家 (reader 已通过参数传入)
            country = get_country_offline(ip_to_test, reader)
            return (rename_node(link, country, latency), latency)
    except: return None

def main():
    print("🚀 启动【离线数据库版】全量精选任务...")
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
    print(f"💎 原始节点: {len(unique_nodes)} 个")

    # 初始化离线数据库读取器
    with maxminddb.open_database(CONFIG["mmdb_path"]) as reader:
        valid_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
            # 将 reader 传递给每个线程
            futures = [executor.submit(test_node, n, reader) for n in unique_nodes]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res: valid_list.append(res)

    valid_list.sort(key=lambda x: x[1])
    final_nodes = [item[0] for item in valid_list[:CONFIG["max_node_count"]]]

    out_b64 = base64.b64encode("\n".join(final_nodes).encode()).decode()
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(out_b64)
    print(f"🎉 离线验证完成！共精选 {len(final_nodes)} 个节点。")

if __name__ == "__main__":
    main()
