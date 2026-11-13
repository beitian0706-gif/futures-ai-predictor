#!/usr/bin/env bash
# Optional research-only monitor, push and trading are disabled.
set -euo pipefail
APP_DIR="/opt/futures-ai/futures_ai_app_v0.2.4"
if [ "$#" -gt 0 ]; then APP_DIR="$1"; fi
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
MAIN="$APP_DIR/main.py"
test -f "$MAIN" && test -f "$APP_DIR/ma144_60m.py" || { echo "缺少旧版后端或MA144模块"; exit 1; }
test -f "$SOURCE_DIR/monitor_v052.py" || exit 1
PYTHON="/opt/futures-ai/venv/bin/python"
test -x "$PYTHON" || { echo "原虚拟环境不存在"; exit 1; }
DATA_DIR="/var/lib/futures-ai"
CFG="/etc/futures-ai/v052_watchlist.json"
BACKUP="$MAIN.backup-v052-$(date +%Y%m%d-%H%M%S)"
cp -p "$MAIN" "$BACKUP"
cp -p "$SOURCE_DIR/monitor_v052.py" "$APP_DIR/monitor_v052.py"
cp -p "$SOURCE_DIR/main_candidates_v052.py" "$APP_DIR/main_candidates_v052.py"
python3 - "$MAIN" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding="utf-8")
if "@app.get('/monitor/v052')" not in s:
    anchor="@app.post('/analyze')"
    if anchor not in s:raise SystemExit("后端API结构不符，拒绝更新")
    block='''@app.get('/monitor/v052')
def monitor_v052():
    from monitor_v052 import read_latest
    return read_latest('/var/lib/futures-ai/monitor-v052.sqlite3')

'''
    s=s.replace(anchor,block+anchor,1)
    compile(s,str(p),'exec')
    p.write_text(s,encoding="utf-8")
PY
"$PYTHON" -m py_compile "$MAIN" "$APP_DIR/monitor_v052.py" "$APP_DIR/main_candidates_v052.py"
mkdir -p /etc/futures-ai "$DATA_DIR"
if [ ! -e "$CFG" ]; then printf '[]\n' > "$CFG"; fi
chmod 644 "$CFG"
chown ubuntu:ubuntu "$DATA_DIR"
chmod 750 "$DATA_DIR"
cat > /etc/systemd/system/futures-v052-scan.service <<EOF
[Unit]
Description=V0.5.2 Historical research poller (no notifications)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON $APP_DIR/monitor_v052.py --watchlist $CFG --database $DATA_DIR/monitor-v052.sqlite3 --once
TimeoutStartSec=180
NoNewPrivileges=true
EOF
cat > /etc/systemd/system/futures-v052-scan.timer <<'EOF'
[Unit]
Description=Historical research scan every minute (NOT realtime verified)

[Timer]
OnCalendar=*-*-* *:*:00
Persistent=false
AccuracySec=2s
Unit=futures-v052-scan.service

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl disable --now futures-v052-scan.timer >/dev/null 2>&1 || true
systemctl restart futures-ai.service
ok=0
for i in $(seq 1 25); do
  if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then ok=1;break;fi
  sleep 1
done
if [ "$ok" -ne 1 ]; then
 echo "健康检查失败，恢复原main.py并重启"
 cp -p "$BACKUP" "$MAIN"
 systemctl restart futures-ai.service || true
 exit 1
fi
echo "研究接口安装成功。原main.py备份：$BACKUP"
echo "测试：curl -sS http://127.0.0.1:8000/monitor/v052"
echo "扫描定时器默认关闭，人工建立明确合约观察池后才可启用。"
echo "合约池配置：$CFG"
echo "人工启用：sudo systemctl enable --now futures-v052-scan.timer"
