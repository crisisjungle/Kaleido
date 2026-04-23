# Kaleido 阿里云部署记录

## DNS

1. 在域名注册控制台把 `kaleido.asia` 的 NS 改成阿里云 DNS 分配的：
   - `dns11.hichina.com`
   - `dns12.hichina.com`
2. 等 NS 生效后，在阿里云云解析 DNS 添加记录：
   - 主机记录：`@`
   - 记录类型：`A`
   - 记录值：`8.135.60.155`
   - TTL：默认
3. 可选添加 `www`：
   - 主机记录：`www`
   - 记录类型：`A`
   - 记录值：`8.135.60.155`

## ECS

安全组只需要开放：

- `80/tcp`
- `443/tcp`
- SSH 管理端口

不要直接开放 Kaleido 的后端端口。

## 部署文件

生产编排使用：

```bash
docker compose -f docker-compose.prod.yml up -d
```

前端容器只监听宿主机本地：

```text
127.0.0.1:8088
```

宿主机 Nginx 把 `kaleido.asia` 反代到这个端口。

## 服务器 `.env`

在服务器项目目录创建 `.env`，至少包含：

```env
FLASK_DEBUG=False
SECRET_KEY=replace-with-a-long-random-secret

LLM_API_KEY=replace-with-your-key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

ZEP_API_KEY=replace-with-your-zep-key
```

线上前端入口由镜像构建参数控制为 `space_only`，不需要写进服务器 `.env`。

## Nginx

把 `deploy/nginx/kaleido.asia.conf` 放到服务器 Nginx 配置目录，例如：

```bash
sudo cp deploy/nginx/kaleido.asia.conf /etc/nginx/sites-available/kaleido.asia
sudo ln -s /etc/nginx/sites-available/kaleido.asia /etc/nginx/sites-enabled/kaleido.asia
sudo nginx -t
sudo systemctl reload nginx
```

证书申请：

```bash
sudo certbot --nginx -d kaleido.asia -d www.kaleido.asia
```

如果服务器不是 Debian/Ubuntu 的 `sites-available` 布局，就把同一份 server block 放进当前 Nginx 的 `conf.d`。

## 验证

```bash
curl -I https://kaleido.asia
curl https://kaleido.asia/health
docker compose -f docker-compose.prod.yml ps
docker stats
```

网页验证：

- 首页可以打开。
- 首页只显示太空碰撞模拟入口，不显示推演和历史入口。
- `/space-forecast` 可以运行模拟。
- Synapse 原服务不受影响。
