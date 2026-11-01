#!/usr/bin/env bash
# ============================================================
# 量化工作台 · 云服务器一键部署（Ubuntu 20.04+ / Debian 11+）
# 用法：把整个项目上传到服务器后，在项目目录执行：
#       bash deploy/deploy.sh
# 完成后直接访问 http://<服务器IP> 即可
# ============================================================
set -e

APP_DIR=/opt/quant-app
PORT=8000

echo "==> [1/6] 更新系统并安装依赖（python3 / nginx）…"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip nginx ufw

echo "==> [2/6] 部署应用到 ${APP_DIR} …"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -f "$SRC_DIR/app.py" ]; then
    echo "[错误] 未找到 app.py，请把整个项目目录上传到服务器后重试"
    exit 1
fi
mkdir -p "$APP_DIR"
# 复制应用代码（排除无关目录）
rsync -a --delete \
    --exclude 'data/market.db' --exclude '__pycache__' \
    --exclude 'tools' --exclude 'deploy' \
    "$SRC_DIR/" "$APP_DIR/" 2>/dev/null || \
    cp -r "$SRC_DIR"/. "$APP_DIR/"

echo "==> [3/6] 创建虚拟环境并安装 numpy / pandas …"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/venv/bin/pip" install numpy pandas

echo "==> [4/6] 注册 systemd 服务（开机自启 + 崩溃自动拉起）…"
cp "$SRC_DIR/deploy/quant.service" /etc/systemd/system/quant.service
systemctl daemon-reload
systemctl enable quant
systemctl restart quant

echo "==> [5/6] 配置 nginx 反向代理 …"
sed "s/quant.example.com/_/g" "$SRC_DIR/deploy/nginx.conf" > /etc/nginx/conf.d/quant.conf
nginx -t
systemctl reload nginx

echo "==> [6/6] 放行防火墙端口（80/443）…"
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw allow OpenSSH || true
ufw --force enable || true

echo ""
echo "============================================================"
echo "  🎉 部署完成！"
echo "  立即访问：http://$(hostname -I | awk '{print $1}')"
echo "  服务状态：systemctl status quant"
echo "  查看日志：journalctl -u quant -f"
echo ""
echo "  绑定域名 + 免费 HTTPS："
echo "    1) 域名解析到本服务器 IP"
echo "    2) 编辑 /etc/nginx/conf.d/quant.conf 的 server_name 为你的域名"
echo "    3) apt install certbot python3-certbot-nginx"
echo "    4) certbot --nginx -d 你的域名"
echo "============================================================"
