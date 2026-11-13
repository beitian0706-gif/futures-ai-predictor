#!/usr/bin/env bash
set -euo pipefail
APP="/opt/futures-ai/futures_ai_app_v0.2.4"
if [ "$#" -gt 0 ];then APP="$1";fi
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="/opt/futures-ai/venv/bin/python"
MAIN="$APP/main.py"
test -f "$MAIN" && test -x "$PY" || { echo "未发现后端程序或虚拟环境";exit 1; }
BACKUP="$MAIN.backup-v056-$(date +%Y%m%d-%H%M%S)"
cp -p "$MAIN" "$BACKUP"
cp "$HERE/strategy_v056.py" "$APP/strategy_v056.py"
cp "$HERE/research_runner_v056.py" "$APP/research_runner_v056.py"
"$PY" -m py_compile "$APP/strategy_v056.py" "$APP/research_runner_v056.py"
python3 - "$MAIN" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding="utf-8")
anchor="@app.post('/analyze')"
if "@app.get('/v056/strategy')" not in s:
    if anchor not in s:raise SystemExit("主程序版本不匹配，未插入路由")
    block='''@app.get('/v056/strategy')
def v056_strategy_report():
    from pathlib import Path
    import json
    report=Path('/var/lib/futures-ai/strategy-v056.json')
    fallback={"version":"0.5.6","ready":False,"research_only":True,
              "push_enabled":False,"order_enabled":False,
              "warning":"尚未提供经检验的历史60分钟CSV，不能生成回测或入场建议"}
    try:
        obj=json.loads(report.read_text(encoding='utf-8'))
        if not isinstance(obj,dict) or obj.get("version")!="0.5.6" or obj.get("research_only") is not True:
            return fallback
        return {**obj,"ready":True,"push_enabled":False,"order_enabled":False}
    except (OSError,ValueError,TypeError):
        return fallback

'''
    s=s.replace(anchor,block+anchor,1)
    compile(s,str(p),'exec')
    p.write_text(s,encoding="utf-8")
PY
"$PY" -m py_compile "$MAIN"
if ! systemctl restart futures-ai.service;then
    cp -p "$BACKUP" "$MAIN"
    systemctl restart futures-ai.service || true
    exit 1
fi
ok=0
for i in $(seq 1 25);do
    if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1 &&
       curl -fsS --max-time 2 http://127.0.0.1:8000/v056/strategy >/dev/null 2>&1;then
        ok=1;break
    fi
    sleep 1
done
if [ "$ok" -ne 1 ];then
    cp -p "$BACKUP" "$MAIN"
    systemctl restart futures-ai.service || true
    echo "检查未通过，已恢复main.py";exit 1
fi
echo "V0.5.6历史策略研究接口已安装；未接入实盘，不发送通知，不下单。"
echo "检查：curl -sS http://127.0.0.1:8000/v056/strategy"
echo "备份：$BACKUP"
