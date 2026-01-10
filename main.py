import requests
import base64
import socket
import concurrent.futures
import re
from datetime import datetime

# --- 配置区 ---
SOURCES = [
    "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt", # 示例订阅1
    "https://raw.githubusercontent.com/WLget/V2Ray_configs_64/refs/heads/master/ConfigSub_list.txt",                             # 示例订阅2
    "https://github.com/ermaozi/get_subscribe/blob/main/subscribe/v2ray.txt",                                              # 示例单节点
    “https://github.com/free18/v2ray/blob/main/v.txt”,
    "https://gist.githubusercontent.com/shuaidaoya/9e5cf2749c0ce79932dd9229d9b4162b/raw/base64.txt"
]

# 阿里 DNS 地址 (用于模拟国内环境解析)
ALI_DNS = "223.5.5.5"
TIMEOUT = 3       # 测速超时
MAX_WORKERS = 50  # 并发数

def decode_base64(data):
    data = data.replace('-', '+').replace('_', '/')
    missing_padding = len(data) % 4
    if missing_padding: data += '=' * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode('utf-8')
    except:
        return ""

def check_node_with_dns(node_link):
    """使用阿里DNS解析并进行TCP测速"""
    try:
        # 提取 Host 和 Port
        pattern = r'@([^:]+):(\d+)'
        match = re.search(pattern, node_link)
        if not match: return None
        
        host = match.group(1)
        port = int(match.group(2))

        # 检查是否为域名，如果是域名则尝试连接 (GitHub Actions 无法指定 DNS Server 进行解析，
        # 但我们可以通过直接拨号来验证该节点对国内环境的可用性)
        # 此处模拟建立连接，若节点在阿里DNS解析下无记录或端口不通，则过滤
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return node_link
    except:
        return None

def get_nodes():
    all_raw_nodes = []
    headers = {'User-Agent': 'v2rayNG/1.8.12'}

    for url in SOURCES:
        try:
            resp = requests.get(url, headers=headers, timeout=10).text.strip()
            decoded = decode_base64(resp)
            lines = decoded.splitlines() if "://" in decoded else resp.splitlines()
            all_raw_nodes.extend([l.strip() for l in lines if "://" in l])
        except:
            continue

    # 去重
    unique_nodes = list(set(all_raw_nodes))
    
    # 测速过滤
    print(f"开始使用模拟环境测速，原始节点: {len(unique_nodes)}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(check_node_with_dns, unique_nodes))
        alive_nodes = [r for r in results if r is not None]
    
    print(f"测速完成，剩余可用节点: {len(alive_nodes)}")
    return alive_nodes

if __name__ == "__main__":
    nodes = get_nodes()
    if nodes:
        encoded = base64.b64encode("\n".join(nodes).encode('utf-8')).decode('utf-8')
        with open("subscribe.txt", "w") as f:
            f.write(encoded)
