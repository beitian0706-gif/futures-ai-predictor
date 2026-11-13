#!/usr/bin/env bash
# V0.5.1 optional backend deployment. Does not enable trading/notifications.
set -euo pipefail
APP_DIR="${1:-/opt/futures-ai/futures_ai_app_v0.2.4}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN="$APP_DIR/main.py"
test -f "$MAIN" || { echo "未找到 $MAIN"; exit 1; }
test -f "$APP_DIR/ma144_60m.py" || { echo "缺少V0.5.0行情模块"; exit 1; }
test -f "$SCRIPT_DIR/opportunity_engine.py" || { echo "缺少机会研究模块"; exit 1; }
BACKUP="$MAIN.backup-v051-$(date +%Y%m%d-%H%M%S)"
cp -p "$MAIN" "$BACKUP"
cp "$SCRIPT_DIR/opportunity_engine.py" "$APP_DIR/opportunity_engine.py"
rollback() {
  cp -p "$BACKUP" "$MAIN"
  systemctl restart futures-ai.service || true
}
python3 - "$MAIN" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text(encoding="utf-8")
route_name="@app.get('/opportunities/{contract}')"
if route_name not in text:
    anchor="@app.post('/analyze')"
    if anchor not in text:
        raise SystemExit("旧版接口结构不符，未覆盖main.py")
    route='''@app.get('/opportunities/{contract}')
def research_opportunities(contract: str):
    from opportunity_engine import query_opportunity
    from ma144_60m import Market60mError
    try:
        return query_opportunity(contract)
    except Market60mError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(503, f'机会研究依赖缺失：{type(exc).__name__}') from exc
    except Exception as exc:
        raise HTTPException(502, f'历史机会研究行情源暂不可用（{type(exc).__name__}）') from exc

'''
    text=text.replace(anchor,route+anchor,1)
    compile(text,str(path),'exec')
    path.write_text(text,encoding="utf-8")
PY
PYTHON="/opt/futures-ai/venv/bin/python"
test -x "$PYTHON" || PYTHON=python3
"$PYTHON" -m py_compile "$MAIN" "$APP_DIR/opportunity_engine.py"
"$PYTHON" -c "import sys;sys.path.insert(0,'$APP_DIR');import opportunity_engine"
if ! systemctl restart futures-ai.service || ! systemctl is-active --quiet futures-ai.service; then
  echo "服务启动失败，开始恢复原main.py"
  rollback
  exit 1
fi
if ! curl -fsS --max-time 8 http://127.0.0.1:8000/health >/dev/null; then
  echo "健康检查失败，开始恢复原main.py"
  rollback
  exit 1
fi
echo "接口更新成功，备份在 $BACKUP"
echo "检查：curl -sS http://127.0.0.1:8000/opportunities/RB2701"
echo "历史研究接口，不发送入场提醒，也不自动交易。"
