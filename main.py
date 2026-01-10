import requests
import base64
import socket
import concurrent.futures
import re
import time
from datetime import datetime

# --- 配置区 ---
SOURCES = [
    "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt", # 示例订阅1
    "https://raw.githubusercontent.com/WLget/V2Ray_configs_64/refs/heads/master/ConfigSub_list.txt",                             # 示例订阅2
    "https://github.com/ermaozi/get_subscribe/blob/main/subscribe/v2ray.txt",                                              # 示例单节点
    "https://github.com/free18/v2ray/blob/main/v.txt",
    "https://gist.githubusercontent.com/shuaidaoya/9e5cf2749c0ce79932dd9229d9b4162b/raw/base64.txt"
]

MAX_LATENCY = 0.5   # 延迟阈值：500ms
ALI_DNS_URL = "https://223.5.5.5/resolve?name="  # 阿里 DoH 接口
TIMEOUT = 3         # 测速超时
MAX_WORKERS = 40    # 并发数

def get_ip_from_alidns(host):
    """使用阿里 DNS 接口解析域名"""
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', host):
        return host  # 已经是 IP 地址则直接返回
    try:
        # 使用轻量级的 HTTP DNS 接口避免 UDP 限制
        resp = requests.get(f"{ALI_DNS_URL}{host}&type=A", timeout=2)
        data = resp.json()
        if "Answer" in data:
            return data["Answer"][0]["data"]
    except:
        pass
    return host # 解析失败则尝试原始 Host

def check_node_performance(node_link):
    """结合 DNS 解析与 TCP 测速"""
    try:
        # 1. 提取 Host 和 Port
        match = re.search(r'@([^:]+):(\d+)', node_link)
        if not match:
            match = re.search(r'://([^:]+):(\d+)', node_link)
        if not match: return None
        
        raw_host, port = match.group(1), int(match.group(2))

        # 2. 模拟国内 DNS 解析
        resolved_host = get_ip_from_alidns(raw_host)

        # 3. 高精度延迟测试
        start_time = time.perf_counter()
        with socket.create_connection((resolved_host, port), timeout=TIMEOUT):
            latency = (time.perf_counter() - start_time) * 1000 # 转为 ms
            
            if latency <= (MAX_LATENCY * 1000):
                # 在节点名后加上测得的延迟，方便 v2rayNG 查看
                name_suffix = f" | {int(latency)}ms"
                if "#" in node_link:
                    return node_link + name_suffix
                else:
                    return f"{node_link}#{name_suffix}"
    except:
        pass
    return None

if __name__ == "__main__":
    print(f"[{datetime.now()}] 启动：阿里 DNS 预解析 + {int(MAX_LATENCY*1000)}ms 延迟过滤")
    all_raw_nodes = []
    
    # 抓取逻辑
    headers = {'User-Agent': 'v2rayNG/1.8.12'}
    for url in SOURCES:
        try:
            resp = requests.get(url, headers=headers, timeout=10).text.strip()
            # 自动识别 Base64
            try:
                if "://" not in resp:
                    resp = base64.b64decode(resp).decode('utf-8')
            except: pass
            
            nodes = [l.strip() for l in resp.splitlines() if "://" in l]
            all_raw_nodes.extend(nodes)
        except: continue

    unique_nodes = list(set(all_raw_nodes))
    print(f"去重后待测节点: {len(unique_nodes)}")

    # 并发执行
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(check_node_performance, unique_nodes))
        alive_nodes = [r for r in results if r is not None]

    print(f"筛选完成！保留节点: {len(alive_nodes)}")

    if alive_nodes:
        final_b64 = base64.b64encode("\n".join(alive_nodes).encode()).decode()
        with open("subscribe.txt", "w") as f:
            f.write(final_b64)
