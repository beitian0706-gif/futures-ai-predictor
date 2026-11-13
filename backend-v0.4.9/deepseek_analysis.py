"""DeepSeek historical report: bounded input, explicit completion checks."""
import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"

def generate_report(contract, quant_result):
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("服务端未配置 DEEPSEEK_API_KEY")
    allowed = ("symbol", "last_price", "combined_score", "bias", "factor_scores",
               "ma20", "ema12", "ema26", "volume_ratio", "open_interest_change",
               "data_completeness", "weight_coverage", "factor_provenance",
               "source", "retrieved_at", "timeframe", "scenario_ranges", "missing_factors")
    evidence = {k: quant_result.get(k) for k in allowed if k in quant_result}
    prompt = (
        "请用简洁中文制作期货历史日线研究报告，只引用如下JSON已提供数据。"
        "报告分为：一、核心结论（最多3句话）；二、技术与量价证据（3至5条）；"
        "三、参考均线和情景边界；四、判断失效条件；五、数据局限与风险。"
        "全文尽量在700至1000个汉字内，不生成Markdown表格，不重复免责声明。"
        "价格与均线必须注明日线周期，技术面与资金面有矛盾应标明信号分歧。"
        "未验证的主力身份、实时价格、60分钟MA144、基差、库存和情绪不能声称已知。"
        "情景区间不是统计置信区间或预测概率，不能编造支撑阻力和胜率。"
        "不得给出确定性交易建议。数据："
        + json.dumps(evidence, ensure_ascii=False, default=str)
    )
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是严谨的金融研究报告撰写助手。不要捏造事实。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1900,
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json"
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("DeepSeek 接口返回 HTTP " + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("DeepSeek 网络请求失败或超时") from None
    try:
        choice = result["choices"][0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("DeepSeek 报告被截断，请重试或缩短研究要求")
        report = choice["message"]["content"]
        if not isinstance(report, str) or not report.strip():
            raise ValueError("empty report")
        return report.strip()
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError("DeepSeek 返回内容格式异常") from None
