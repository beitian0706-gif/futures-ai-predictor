#!/usr/bin/env bash
# Research-only discovery; preserves installed V0.5.2 scanner.
set -euo pipefail
APP_DIR="/opt/futures-ai/futures_ai_app_v0.2.4"
if [ "$#" -gt 0 ];then APP_DIR="$1";fi
HERE="$(cd "$(dirname "$0")" && pwd)"
MAIN="$APP_DIR/main.py"
PY="/opt/futures-ai/venv/bin/python"
test -f "$MAIN" && test -f "$APP_DIR/monitor_v052.py" && test -x "$PY" || { echo "必须先安装V0.5.2及依赖";exit 1; }
BACKUP="$MAIN.backup-v053-$(date +%Y%m%d-%H%M%S)"
cp -p "$MAIN" "$BACKUP"
cp -p "$HERE/discovery_v053.py" "$APP_DIR/discovery_v053.py"
cp -p "$HERE/close_gate_v053.py" "$APP_DIR/close_gate_v053.py"
"$PY" -m py_compile "$APP_DIR/discovery_v053.py" "$APP_DIR/close_gate_v053.py"
python3 - "$MAIN" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding="utf-8")
anchor="@app.post('/analyze')"
if "@app.get('/v053/status')" not in s:
    if anchor not in s:raise SystemExit("后端路由格式与预期不符")
    block='''@app.get('/v053/status')
def v053_status():
    import json
    from pathlib import Path
    from close_gate_v053 import close_policy_summary
    p = Path('/var/lib/futures-ai/main-candidates-v053.json')
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError, PermissionError):
        doc = {'candidates': [], 'updated_at': None}
    return {'version': '0.5.3', 'main_candidates': doc.get('candidates', []),
            'candidate_updated_at': doc.get('updated_at'),
            'close_policy': close_policy_summary(),
            'notification_enabled': False, 'trading_enabled': False}

'''
    s=s.replace(anchor,block+anchor,1)
    compile(s,str(p),'exec')
    p.write_text(s,encoding="utf-8")
PY
"$PY" -m py_compile "$MAIN"
install -d -m 755 /etc/futures-ai
install -d -o ubuntu -g ubuntu -m 755 /var/lib/futures-ai
CFG="/etc/futures-ai/v053_products.json"
if [ ! -e "$CFG" ];then
  printf '%s\n' '{"products":[{"name":"螺纹钢","product":"RB"}]}' > "$CFG"
fi
chmod 644 "$CFG"
cat > /etc/systemd/system/futures-v053-discover.service <<EOF
[Unit]
Description=V0.5.3 research-only futures candidate discovery
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=$APP_DIR
ExecStart=$PY $APP_DIR/discovery_v053.py --config $CFG --status /var/lib/futures-ai/main-candidates-v053.json
TimeoutStartSec=120
NoNewPrivileges=true
EOF
cat > /etc/systemd/system/futures-v053-discover.timer <<'EOF'
[Unit]
Description=V0.5.3 optional historical candidate snapshots

[Timer]
OnCalendar=*-*-* *:0/15:00
AccuracySec=5s
Persistent=false
Unit=futures-v053-discover.service

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl disable --now futures-v053-discover.timer >/dev/null 2>&1 || true
systemctl restart futures-ai.service
ok=0
for i in $(seq 1 25);do
 if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1;then ok=1;break;fi
 sleep 1
done
if [ "$ok" != 1 ];then
 cp -p "$BACKUP" "$MAIN"
 systemctl restart futures-ai.service || true
 echo "健康检查失败，已恢复主程序";exit 1
fi
if ! curl -fsS --max-time 3 http://127.0.0.1:8000/v053/status >/dev/null;then
 cp -p "$BACKUP" "$MAIN"
 systemctl restart futures-ai.service || true
 echo "V0.5.3接口检查失败，已恢复主程序";exit 1
fi
echo "V0.5.3安装成功，保留原V0.5.2后台扫描"
echo "备份：$BACKUP"
echo "查看：curl -sS http://127.0.0.1:8000/v053/status"
echo "单次候选发现：sudo systemctl start futures-v053-discover.service"
echo "日志：sudo journalctl -u futures-v053-discover.service -n 40 --no-pager"
echo "定时器默认关闭，数据验证后再启用"
