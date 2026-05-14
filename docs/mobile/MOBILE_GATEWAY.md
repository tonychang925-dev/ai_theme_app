# 移动端远程访问指南

> iOS HTML5 投资驾驶舱 — Tailscale Serve 部署方案

---

## 1. 前提条件

- 电脑端已安装 Tailscale 并登录
- iPhone 已安装 Tailscale 并登录同一账号
- 项目已构建完成：`npm run build`

---

## 2. 启动服务

```bash
# 1. 启动后端服务栈
./scripts/start_new_chain_stack.sh --restart --with-frontend

# 2. （可选）设置移动端访问密钥
export MOBILE_ACCESS_TOKEN="your-secret-token-here"

# 3. 启动 Tailscale Serve
tailscale serve --bg 8000
```

服务映射：
```
localhost:8000  →  web_app_service (API)
localhost:5173  →  Vite dev server (开发)
localhost:8090  →  stock_processing_service (不对外暴露)
```

---

## 3. iPhone 访问

### 3.1 获取 Tailscale 域名

```bash
tailscale status
# 找到本机 MagicDNS 名称，例如：my-macbook.tailxxxxx.ts.net
```

### 3.2 iPhone Safari 打开

```
https://<your-tailnet-name>.ts.net/mobile
```

### 3.3 添加到主屏幕

1. Safari 打开 `/mobile` 页面
2. 点击底部 **分享** 按钮（方框+箭头）
3. 选择 **添加到主屏幕**
4. 命名为「AI 投资」
5. 点击 **添加**

---

## 4. 安全配置

### 4.1 启用访问密钥（推荐）

```bash
# 在启动服务前设置
export MOBILE_ACCESS_TOKEN="your-64-char-random-token"
```

iPhone 访问时需在 URL 后附加 `?token=xxx`，或使用快捷指令注入 Header：
```
X-Mobile-Access-Token: your-64-char-random-token
```

### 4.2 未设置 Token

如果 `MOBILE_ACCESS_TOKEN` 未设置或为空，则移动端路由不校验，允许本地开发模式访问。

### 4.3 Tailscale ACL（可选）

在 Tailscale Admin Console 中限制端口访问：
```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["tag:iphone"],
      "dst": ["tag:macbook:8000"]
    }
  ]
}
```

---

## 5. 不对外暴露的端口

以下端口**绝不**通过 Tailscale Serve 暴露：

| 端口 | 服务 | 原因 |
|---|---|---|
| 5432 | PostgreSQL | 数据库直连 |
| 6379 | Redis | 缓存/消息队列 |
| 8090 | stock_processing_service | 内部计算服务 |
| 8095 | JYHF CDP Service | CDP 采集 |
| 9223 | CDP DevTools | 浏览器调试端口 |

以上端口仅绑定 `127.0.0.1`，Tailscale 无法路由。

---

## 6. Cloudflare Tunnel 方案（品牌域名）

如需自有域名 `https://ai.yourdomain.com/mobile`：

```bash
# 安装 cloudflared
brew install cloudflared

# 登录
cloudflared tunnel login

# 创建隧道
cloudflared tunnel create ai-theme-mobile

# 配置 DNS
cloudflared tunnel route dns ai-theme-mobile ai.yourdomain.com

# 启动
cloudflared tunnel run --url http://localhost:8000 ai-theme-mobile
```

配合 Cloudflare Access 可增加 Google/GitHub OAuth 登录。

---

## 7. 故障排查

### 7.1 iPhone 无法打开页面
```bash
# 检查 Tailscale 连接
tailscale status

# 检查服务是否在监听
curl http://127.0.0.1:8000/healthz

# 检查 Tailscale Serve
tailscale serve status
```

### 7.2 API 返回 401
```bash
# 检查 Token 是否设置
echo $MOBILE_ACCESS_TOKEN

# 临时关闭 Token 校验
unset MOBILE_ACCESS_TOKEN
# 重启 web_app_service
```

### 7.3 页面空白
```bash
# 确认构建产物存在
ls dist/assets/MobileHomePage-*.js

# 重新构建
npm run build
```
