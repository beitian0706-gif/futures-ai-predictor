#!/usr/bin/env bash
set -euo pipefail
APP="/opt/futures-ai/futures_ai_app_v0.2.4"
if [ "$#" -gt 0 ];then APP="$1";fi
PY="/opt/futures-ai/venv/bin/python"
HERE="$(cd "$(dirname "$0")" && pwd)"
test -f "$APP/main.py" && test -f "$APP/discovery_v053.py" && test -f "$APP/monitor_v052.py" || { echo "请先安装V0.5.3和V0.5.2";exit 1; }
BACKUP="$APP/main.py.backup-v054-$(date +%Y%m%d-%H%M%S)"
cp -p "$APP/main.py" "$BACKUP"
cp "$HERE/session_audit_v054.py" "$APP/session_audit_v054.py"
"$PY" -m py_compile "$APP/session_audit_v054.py"
python3 - "$APP/main.py" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text(encoding="utf-8")
anchor="@app.post('/analyze')"
if "@app.get('/v054/audit')" not in s:
    if anchor not in s:raise SystemExit("无法定位后端路由，停止修改")
    block='''@app.get('/v054/audit')
def v054_audit():
    from pathlib import Path
    import json
    from session_audit_v054 import monitor_audit
    from monitor_v052 import read_latest
    try:
        candidates=json.loads(Path('/var/lib/futures-ai/main-candidates-v053.json').read_text(
            encoding='utf-8')).get('candidates',[])
    except (FileNotFoundError,PermissionError,ValueError):
        candidates=[]
    try:
        scans=read_latest('/var/lib/futures-ai/monitor-v052.sqlite3').get('latest_scans',[])
    except (OSError,ValueError):
        scans=[]
    return monitor_audit(data={'main_candidates':candidates,'latest_scans':scans})

'''
    s=s.replace(anchor,block+anchor,1)
    compile(s,str(p),'exec')
    p.write_text(s,encoding="utf-8")
PY
"$PY" -m py_compile "$APP/main.py"
systemctl restart futures-ai.service
healthy=0
for i in $(seq 1 25);do
 if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1 &&
    curl -fsS --max-time 2 http://127.0.0.1:8000/v054/audit >/dev/null 2>&1;then
    healthy=1;break
 fi
 sleep 1
done
if [ "$healthy" -ne 1 ];then
 cp -p "$BACKUP" "$APP/main.py"
 systemctl restart futures-ai.service || true
 echo "接口验证失败，已恢复主程序";exit 1
fi
echo "V0.5.4 诊断接口安装完成，备份：$BACKUP"
echo "curl -sS http://127.0.0.1:8000/v054/audit"
echo "原V0.5.2/V0.5.3定时器配置均未修改。无实时推送和下单。"
