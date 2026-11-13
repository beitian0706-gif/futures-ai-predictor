#!/usr/bin/env bash
# Opt-in server-side deployment; DOES NOT run as part of GitHub Actions.
set -euo pipefail
APP_DIR="${1:-/opt/futures-ai/futures_ai_app_v0.2.4}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
test -f "$APP_DIR/main.py" || { echo "找不到main.py"; exit 1; }
test -f "$SCRIPT_DIR/ma144_60m.py" || { echo "缺少MA144模块"; exit 1; }
BACKUP="$APP_DIR/main.py.backup-v050-$(date +%Y%m%d-%H%M%S)"
cp -p "$APP_DIR/main.py" "$BACKUP"
cp "$SCRIPT_DIR/ma144_60m.py" "$APP_DIR/ma144_60m.py"
python3 - "$APP_DIR/main.py" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text(encoding='utf-8')
if "@app.get('/signals/ma144/{contract}')" not in text:
    anchor="@app.post('/analyze')"
    if anchor not in text: raise SystemExit("缺少原有/analyze路由，停止安装")
    route='''@app.get('/signals/ma144/{contract}')
def ma144_signals(contract: str):
    from ma144_60m import query_sina_60m, Market60mError
    try:
        return query_sina_60m(contract)
    except Market60mError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(503, '服务器缺少AKShare依赖') from exc
    except Exception as exc:
        raise HTTPException(502, f'60分钟行情源失败（{type(exc).__name__}），未生成MA144信号') from exc

'''
    text=text.replace(anchor,route+anchor,1)
    compile(text,str(path),'exec')
    path.write_text(text,encoding='utf-8')
PY
python3 -m py_compile "$APP_DIR/main.py" "$APP_DIR/ma144_60m.py"
if command -v systemctl >/dev/null; then
    systemctl restart futures-ai.service
    if ! systemctl is-active --quiet futures-ai.service; then
        cp -p "$BACKUP" "$APP_DIR/main.py"
        systemctl restart futures-ai.service || true
        echo "服务无法启动，已回滚main.py"
        exit 1
    fi
fi
echo "接口安装完成。示例: curl http://127.0.0.1:8000/signals/ma144/RB2701"
echo "警告：仅历史研究，不支持实时推送。"
