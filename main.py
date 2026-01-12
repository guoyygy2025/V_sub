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
import maxminddb
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
    "mmdb_path": "Country.mmdb",
    "global_dns": "1.1.1.1",
    "timeout": 0.5,
    "max_workers": 100,
    "max_node_count": 100
}

COUNTRY_NAMES = {
    "CN": "中国", "HK": "香港", "TW": "台湾", "US": "美国", "JP": "日本", 
    "KR": "韩国", "SG": "新加坡", "FR": "法国", "DE": "德国", "GB": "英国",
    "RU": "俄罗斯", "CA": "加拿大", "AU": "澳大利亚", "NL": "荷兰", "IN": "印度"
}

def safe_decode(data: str) -> str:
    if not data: return ""
    data = re.sub(r'[^A-Za-z0-9+/=]', '', data.replace("-", "+").replace("_", "/"))
    missing_padding = len(data) % 4
    if missing_padding: data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except: return ""

def get_node_fingerprint(link: str) -> str:
    """
    生成节点指纹，用于深度去重。
    原理：提取 [协议, 服务器, 端口, 关键ID/用户] 作为唯一标识，忽略节点名称。
    """
    try:
        if link.startswith("vmess://"):
            data = json.loads(safe_decode(link[8:]))
            return f"vmess|{data.get('add')}|{data.get('port')}|{data.get('id')}"
        elif "://" in link:
            o = urlparse(link)
            protocol = o.scheme
            netloc = o.netloc.split('@')[-1] # 去掉 user:pass 部分
            path = o.path
            return f"{protocol}|{netloc}|{path}"
    except:
        return link
    return link

def get_country_offline(ip, reader):
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
            # 清除原有的备注并附加新备注
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

        # DNS 解析获取真实 IP
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            res_cf = dns.resolver.Resolver(); res_cf.nameservers = [CONFIG['global_dns']]
            res_cf.timeout = 1.5
            ip_to_test = str(res_cf.resolve(host, 'A')[0])
        else:
            ip_to_test = host

        # TCP 测速
        start = time.perf_counter()
        with socket.create_connection((ip_to_test, port), timeout=CONFIG["timeout"]):
            latency = (time.perf_counter() - start) * 1000
            country = get_country_offline(ip_to_test, reader)
            return (rename_node(link, country, latency), latency)
    except: return None

def main():
    print("🚀 启动自动化精选与深度去重任务...")
    raw_all = []
    
    with requests.Session() as s:
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        for url in CONFIG["sources"]:
            try:
                r = s.get(url, timeout=10)
                content = r.text
                if "://" not in content[:100]: content = safe_decode(content)
                found = re.findall(r'(?:vmess|vless|ss|ssr|trojan)://[^\s|<>"]+', content)
                raw_all.extend(found)
            except: pass

    # --- 深度去重逻辑 ---
    seen_fingerprints = set()
    unique_links = []
    
    for link in raw_all:
        fp = get_node_fingerprint(link)
        if fp not in seen_fingerprints:
            seen_fingerprints.add(fp)
            unique_links.append(link)

    print(f"💎 采集原始连接: {len(raw_all)} 个")
    print(f"🛡️ 深度去重后剩余: {len(unique_links)} 个")

    # 验证过程
    with maxminddb.open_database(CONFIG["mmdb_path"]) as reader:
        valid_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:
            futures = [executor.submit(test_node, n, reader) for n in unique_links]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res: valid_list.append(res)

    # 排序与截断
    valid_list.sort(key=lambda x: x[1])
    final_nodes = [item[0] for item in valid_list[:CONFIG["max_node_count"]]]

    # 输出结果
    out_content = "\n".join(final_nodes)
    out_b64 = base64.b64encode(out_content.encode()).decode()
    
    with open("subscribe.txt", "w", encoding="utf-8") as f:
        f.write(out_b64)
    
    print(f"🎉 任务完成！有效且唯一的节点: {len(final_nodes)} 个已保存。")

if __name__ == "__main__":
    main()
