#!/usr/bin/env bash
set -euo pipefail
APP=" /opt/futures-ai/futures_ai_app_v0.2.4"
if [ "$#" -gt 0 ]; then APP="$1"; else APP="/opt/futures-ai/futures_ai_app_v0.2.4"; fi
PY="/opt/futures-ai/venv/bin/python"
HERE="$(cd "$(dirname "$0")" && pwd)"
test -f "$APP/main.py" && test -f "$APP/monitor_v052.py" || {
  echo "请先安装V0.5.2及其后端";exit 1;
}
BACKUP="$APP/main.py.backup-v055-$(date +%Y%m%d-%H%M%S)"
cp -p "$APP/main.py" "$BACKUP"
install -m 644 "$HERE/cross_engine_v055.py" "$APP/cross_engine_v055.py"
"$PY" -m py_compile "$APP/cross_engine_v055.py"
python3 - "$APP/main.py" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding="utf-8")
anchor="@app.post('/analyze')"
if "@app.get('/v055/signals')" not in s:
    if anchor not in s: raise SystemExit("找不到原始路由，停止安装")
    block='''@app.get('/v055/signals')
def v055_signals():
    from cross_engine_v055 import read_status
    return read_status('/var/lib/futures-ai/cross-research-v055.sqlite3')

'''
    s=s.replace(anchor,block+anchor,1)
    compile(s,str(p),'exec')
    p.write_text(s,encoding="utf-8")
PY
"$PY" -m py_compile "$APP/main.py"
systemctl restart futures-ai.service
healthy=0
for i in $(seq 1 25); do
  if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1 &&
     curl -fsS --max-time 2 http://127.0.0.1:8000/v055/signals >/dev/null 2>&1; then
    healthy=1;break
  fi
  sleep 1
done
if [ "$healthy" -ne 1 ]; then
    cp -p "$BACKUP" "$APP/main.py"
    systemctl restart futures-ai.service || true
    echo "V0.5.5安装检查失败，已回滚main.py";exit 1
fi
echo "安装完成。该版本只提供研究信号读取接口，未启动实时监测或手机通知。"
echo "检查: curl -sS http://127.0.0.1:8000/v055/signals"
echo "备份: $BACKUP"
