import subprocess
import json
from pathlib import Path
import os

# 目标 URL 和参数配置
BASE_URL = "https://app.txcfgl.com/api/app/subject"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

def get_auth_from_user():
    """从用户输入获取 Authorization 信息"""
    print("\n" + "="*60)
    print("请输入 Authorization 信息（从浏览器复制）")
    print("="*60)
    print("格式示例: Bearer eyJhbGciOiJIUzUxMiJ9...")
    print("="*60)
    
    auth = input("\nAuthorization: ").strip()
    return auth

def fetch_with_auth(endpoint, params=None, auth_token=None):
    """使用 Authorization 头获取数据"""
    url = f"https://app.txcfgl.com/api/app/subject/{endpoint}"
    
    if params:
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        url = f"{url}?{query_string}"
    
    print(f"\nFetching: {url}")
    
    # 构建 curl 命令
    cmd = [
        'curl',
        '-s',
        '-L',
        '--compressed',
        '-H', f'User-Agent: {HEADERS["User-Agent"]}',
        '-H', f'Accept: {HEADERS["Accept"]}',
        '-H', f'Accept-Language: {HEADERS["Accept-Language"]}',
        '-H', 'Connection: keep-alive',
        '-H', 'Referer: https://app.txcfgl.com/',
        '-H', 'Origin: https://app.txcfgl.com',
        '--cacert', '/etc/ssl/cert.pem',
    ]
    
    # 添加 Authorization 头
    if auth_token:
        cmd.extend(['-H', f'Authorization: {auth_token}'])
        token_preview = auth_token[:20] + "..." if len(auth_token) > 20 else auth_token
        print(f"使用 Authorization: {token_preview}")
    
    cmd.append(url)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        if result.stdout:
            try:
                data = json.loads(result.stdout)
                
                # 检查响应状态
                if isinstance(data, dict):
                    code = data.get('code')
                    if code == 200:
                        print(f"✅ 成功获取数据!")
                    elif code == 401:
                        print(f"⚠️  认证失败: {data.get('msg', 'Unknown error')}")
                    elif 'status' in data and data['status'] == 404:
                        print(f"⚠️  接口不存在 (404)")
                    elif code:
                        print(f"响应码: {code} - {data.get('msg', '')}")
                
                return data
                
            except json.JSONDecodeError:
                print(f"❌ 响应不是有效的 JSON")
                return None
        else:
            print("❌ 空响应")
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Curl 错误: {e}")
        return None

def get_theme_history(subject_id: int, auth_token: str, page_num: int = 1, page_size: int = 20):
    """获取主题历史数据"""
    params = {"subjectId": subject_id, "pageNum": page_num, "pageSize": page_size}
    return fetch_with_auth("top-history", params, auth_token)

def get_theme_children(subject_id: int, auth_token: str):
    """获取主题子树数据 - 这个接口可能不存在，我们暂时禁用"""
    print(f"\n⚠️  跳过 child-stock-tree 接口（可能不存在）")
    return None

def get_theme_details(subject_id: int, auth_token: str):
    """获取主题详情数据"""
    return fetch_with_auth(f"query/{subject_id}", None, auth_token)

def save_data_safe(data, output_file: Path, data_type: str):
    """安全保存数据"""
    if data is None:
        print(f"⚠️  没有 {data_type} 数据可保存")
        return
    
    try:
        items = []
        
        # 处理不同类型的响应
        if isinstance(data, dict):
            # 如果是错误响应，不保存
            if data.get('status') == 404:
                print(f"⚠️  接口返回 404，不保存 {data_type} 数据")
                return
            
            # 检查是否有 data 字段
            if 'data' in data:
                data_field = data['data']
                if isinstance(data_field, list):
                    items = data_field
                    print(f"📊 找到 {len(items)} 条记录在 data 字段中")
                elif data_field is not None:
                    # 如果 data 字段存在但不是列表，将其作为单条记录
                    items = [data_field]
                    print(f"📊 data 字段是单个对象")
            elif 'rows' in data:
                # 有些接口可能用 rows 字段
                items = data['rows'] if isinstance(data['rows'], list) else [data['rows']]
                print(f"📊 找到 {len(items)} 条记录在 rows 字段中")
            else:
                # 如果没有标准字段，保存整个响应
                items = [data]
                print(f"📊 保存整个响应作为单条记录")
        
        elif isinstance(data, list):
            items = data
            print(f"📊 直接保存列表，包含 {len(items)} 条记录")
        
        if not items:
            print(f"⚠️  {data_type} 数据为空")
            return
        
        # 保存到文件
        with open(output_file, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        
        print(f"✅ 已保存 {len(items)} 条 {data_type} 记录到 {output_file}")
        
        # 显示第一条记录的预览
        if items and len(items) > 0:
            preview = json.dumps(items[0], ensure_ascii=False)
            print(f"📝 预览: {preview[:150]}...")
        
    except Exception as e:
        print(f"❌ 保存 {data_type} 数据时出错: {e}")
        import traceback
        traceback.print_exc()

def check_output_files(output_dir: Path, subject_id: int):
    """检查输出的文件"""
    print("\n" + "="*50)
    print("输出文件检查:")
    print("="*50)
    
    files = list(output_dir.glob(f"{subject_id}_*.jsonl"))
    
    if not files:
        print("❌ 没有找到输出文件")
        return
    
    for file in files:
        size = file.stat().st_size
        print(f"\n📄 {file.name}")
        print(f"   大小: {size} 字节")
        
        # 显示前几行
        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                print(f"   记录数: {len(lines)}")
                if lines:
                    print(f"   第一行预览: {lines[0][:150]}...")
        except Exception as e:
            print(f"   读取错误: {e}")

def main(subject_id: int, output_dir: Path):
    print("\n" + "="*50)
    print("Starting ETL with Authorization...")
    print("="*50)
    
    # 获取 Authorization token
    auth_token = get_auth_from_user()
    
    if not auth_token:
        print("❌ 未提供 Authorization，退出")
        return
    
    # 获取数据
    print(f"\n开始获取主题 ID {subject_id} 的数据...")
    
    history_data = get_theme_history(subject_id, auth_token)
    children_data = get_theme_children(subject_id, auth_token)  # 这个现在返回 None
    details_data = get_theme_details(subject_id, auth_token)
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存数据
    print("\n保存数据...")
    save_data_safe(history_data, output_dir / f"{subject_id}_history.jsonl", "history")
    save_data_safe(children_data, output_dir / f"{subject_id}_children.jsonl", "children")
    save_data_safe(details_data, output_dir / f"{subject_id}_details.jsonl", "details")
    
    # 检查输出文件
    check_output_files(output_dir, subject_id)
    
    print("\n" + "="*50)
    print("ETL process completed!")
    print("="*50)

if __name__ == "__main__":
    subject_id = 9011398
    output_dir = Path("output")
    main(subject_id, output_dir)