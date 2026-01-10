import requests
import base64
import socket
import concurrent.futures
import re
from datetime import datetime

# --- 配置区：在此添加你的订阅链接或单节点 ---
SOURCES = [
    "https://raw.githubusercontent.com/free-nodes/nodes/main/sub", # 示例订阅1
    "https://example.com/another_sub",                             # 示例订阅2
    "vmess://xxxxxx",                                              # 示例单节点
]

TIMEOUT = 3       # 测速超时时间（秒），超过此时间认为不可用
MAX_WORKERS = 50  # 并发线程数，提高处理速度

def decode_base64(data):
    """解码 Base64 订阅内容"""
    data = data.replace('-', '+').replace('_', '/')
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)
    try:
        return base64.b64decode(data).decode('utf-8')
    except:
        return ""

def check_node_alive(node_link):
    """通过 TCP 握手简单测试节点是否存活"""
    try:
        # 提取主机和端口
        # 兼容 vmess, vless, ss, trojan 等
        pattern = r'@([^:]+):(\d+)'
        match = re.search(pattern, node_link)
        if not match:
            # 兼容不带@符号的格式（如部分旧版 SS）
            pattern_alt = r'://([^:]+):(\d+)'
            match = re.search(pattern_alt, node_link)
            
        if match:
            host = match.group(1)
            port = int(match.group(2))
            # 尝试建立 TCP 连接
            with socket.create_connection((host, port), timeout=TIMEOUT):
                return node_link
    except:
        pass
    return None

def get_nodes():
    all_raw_nodes = []
    headers = {'User-Agent': 'v2rayNG/1.8.5'}

    for url in SOURCES:
        url = url.strip()
        if not url: continue
        try:
            if url.startswith('http'):
                print(f"正在抓取: {url}")
                resp = requests.get(url, headers=headers, timeout=10).text.strip()
                decoded = decode_base64(resp)
                # 如果解码成功且包含节点协议，说明是 Base64 加密的订阅
                lines = decoded.splitlines() if "://" in decoded else resp.splitlines()
                all_raw_nodes.extend([l.strip() for l in lines if "://" in l])
            else:
                all_raw_nodes.append(url)
        except Exception as e:
            print(f"抓取失败 {url}: {e}")

    # 1. 基础去重（通过配置主体去重，防止改名重复）
    unique_dict = {}
    for node in all_raw_nodes:
        config_part = node.split('#')[0] # 去掉备注部分进行比对
        if config_part not in unique_dict:
            unique_dict[config_part] = node
    
    unique_nodes = list(unique_dict.values())
    print(f"去重后节点数: {len(unique_nodes)}")

    # 2. 并发测速过滤
    print("开始测速过滤...")
    alive_nodes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(check_node_alive, unique_nodes))
        alive_nodes = [r for r in results if r is not None]

    print(f"最终存活节点数: {len(alive_nodes)}")
    return alive_nodes

if __name__ == "__main__":
    nodes = get_nodes()
    if not nodes:
        print("未发现有效节点，跳过写入。")
    else:
        # 重新组合并 Base64 编码
        content = "\n".join(nodes)
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        with open("subscribe.txt", "w") as f:
            f.write(encoded_content)
        
        # 生成一个给人看的清单（可选）
        with open("list.txt", "w") as f:
            f.write(f"更新时间: {datetime.now()}\n")
            f.write(content)
