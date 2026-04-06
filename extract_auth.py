import json
from mitmproxy import http

AUTH_FILE = "/tmp/jyhf_auth_token.json"

def response(flow: http.HTTPFlow) -> None:
    # 拦截目标主机（可根据需要修改）
    if "app.txcfgl.com" in flow.request.pretty_host:
        auth = flow.request.headers.get("Authorization")
        if auth:
            data = {
                "token": auth,
                "timestamp": flow.request.timestamp_start,
                "host": flow.request.pretty_host
            }
            with open(AUTH_FILE, "w") as f:
                json.dump(data, f)
            print(f"[mitmproxy] Extracted token: {auth[:20]}...")