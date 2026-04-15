# AI Theme App - 生产环境部署

## 概述

本目录包含AI主题分析应用的生产环境部署脚本和配置文件。系统支持两种部署方式：
1. **传统部署**：直接在服务器上运行Python和Node.js服务
2. **容器化部署**：使用Docker Compose运行所有服务

## 部署架构

### 服务组件
1. **PostgreSQL** (5432): 主数据库
2. **Redis** (6379): 缓存和消息队列
3. **Backend API** (8000): 后端API服务
4. **Frontend BFF** (8001): 前端BFF服务
5. **Model Service** (8002): AI模型服务
6. **Frontend Web** (8080): 前端Web界面
7. **Monitoring** (9090): Prometheus监控
8. **Logstash** (5000): 日志收集

### 网络架构
```
用户请求 → Frontend (8080) → Frontend BFF (8001) → Backend API (8000)
                                  ↓
                            Model Service (8002)
                                  ↓
                            PostgreSQL + Redis
```

## 部署方式

### 1. 传统部署

#### 环境要求
- Python 3.9+
- Node.js 18+ (仅前端部署需要)
- PostgreSQL 13+
- Redis 6+

#### 部署步骤
```bash
# 1. 设置环境变量
cp .env.example .env
# 编辑 .env 文件，填写实际配置

# 2. 运行部署脚本
./deployment/deploy_production.sh

# 3. 可选：不部署前端
./deployment/deploy_production.sh --no-frontend
```

#### 服务管理
```bash
# 停止所有服务
./deployment/stop_services.sh

# 重启所有服务
./deployment/restart_services.sh
```

### 2. 容器化部署 (Docker)

#### 环境要求
- Docker 20.10+
- Docker Compose 2.0+

#### 部署步骤
```bash
# 1. 设置环境变量
cp .env.example .env
# 编辑 .env 文件，填写实际配置

# 2. 使用Docker部署
./deployment/deploy_production.sh --docker

# 3. 或者直接使用docker-compose
docker-compose up -d
```

#### Docker服务管理
```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart
```

## 配置文件说明

### 1. docker-compose.yml
主Docker Compose配置文件，定义所有服务及其依赖关系。

### 2. 部署脚本
- `deploy_production.sh`: 主部署脚本
- `stop_services.sh`: 停止服务脚本
- `restart_services.sh`: 重启服务脚本

### 3. Dockerfiles
- `Dockerfile.backend`: 后端服务Dockerfile
- `Dockerfile.frontend-bff`: 前端BFF服务Dockerfile
- `Dockerfile.model-service`: AI模型服务Dockerfile
- `frontend/Dockerfile.frontend`: 前端Web服务Dockerfile

### 4. 监控配置
- `deployment/prometheus.yml`: Prometheus监控配置
- `deployment/logstash.conf`: Logstash日志收集配置

### 5. 前端配置
- `frontend/nginx.conf`: Nginx反向代理配置

## 环境变量配置

### 必需配置
1. **数据库配置**: `POSTGRES_PASSWORD`, `DATABASE_URL`
2. **Redis配置**: `REDIS_URL`
3. **AI服务配置**: `OPENAI_API_KEY`
4. **应用配置**: `APP_SECRET_KEY`

### 可选配置
1. **监控配置**: `SENTRY_DSN`, `LOG_LEVEL`
2. **通知配置**: SMTP和Slack配置
3. **安全配置**: JWT相关配置
4. **功能开关**: 各种功能标志

## 健康检查

所有服务都配置了健康检查端点：

- 后端API: `http://localhost:8000/health`
- 前端BFF: `http://localhost:8001/health`
- 模型服务: `http://localhost:8002/health`
- 前端Web: `http://localhost:8080/health`

## 监控和日志

### 监控仪表板
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (需要单独部署)

### 日志收集
- 应用日志: `logs/` 目录
- 容器日志: `docker-compose logs`
- 结构化日志: 通过Logstash收集到Elasticsearch

## 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查PostgreSQL服务是否运行
   - 验证DATABASE_URL配置
   - 检查网络连接

2. **Redis连接失败**
   - 检查Redis服务是否运行
   - 验证REDIS_URL配置

3. **服务启动失败**
   - 检查端口是否被占用
   - 查看服务日志: `logs/*.log`
   - 检查环境变量配置

4. **前端无法访问**
   - 检查前端构建是否成功
   - 验证Nginx配置
   - 检查网络代理设置

### 日志位置
- 传统部署: `logs/` 目录下的 `*.log` 文件
- 容器部署: `docker-compose logs <service-name>`

## 安全建议

1. **生产环境必须修改的配置**
   - `APP_SECRET_KEY`: 使用强随机字符串
   - `POSTGRES_PASSWORD`: 使用强密码
   - `JWT_SECRET_KEY`: 使用强随机字符串

2. **网络安全**
   - 配置防火墙规则
   - 启用SSL/TLS加密
   - 限制不必要的端口访问

3. **数据安全**
   - 定期数据库备份
   - 启用数据库加密
   - 保护敏感环境变量

## 备份和恢复

### 数据库备份
```bash
# PostgreSQL备份
docker exec ai-theme-postgres pg_dump -U ai_theme_user ai_theme_app > backup.sql

# Redis备份
docker exec ai-theme-redis redis-cli save
```

### 恢复数据库
```bash
# PostgreSQL恢复
docker exec -i ai-theme-postgres psql -U ai_theme_user ai_theme_app < backup.sql
```

## 更新和升级

### 代码更新
```bash
# 1. 拉取最新代码
git pull origin main

# 2. 传统部署: 重启服务
./deployment/restart_services.sh

# 3. 容器部署: 重建并重启
docker-compose down
docker-compose up -d --build
```

### 依赖更新
```bash
# 更新Python依赖
pip install -r requirements.txt --upgrade

# 更新Node.js依赖
cd frontend && npm update
```

## 性能优化建议

1. **数据库优化**
   - 添加适当的索引
   - 配置连接池
   - 定期清理旧数据

2. **缓存优化**
   - 合理设置缓存TTL
   - 使用Redis集群提高可用性
   - 监控缓存命中率

3. **前端优化**
   - 启用CDN加速
   - 配置资源压缩
   - 实现懒加载

## 联系和支持

如有问题，请参考：
1. 项目文档: `docs/` 目录
2. 部署检查清单: `deployment/production_checklist.md`
3. GitHub Issues: 提交问题和反馈

---

**最后更新**: 2026-04-11  
**版本**: 1.0