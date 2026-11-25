"""编排:故障树、保修、估价与修换结论全在本地;模型只写诊断解释、风险与追问。

金额一律本地算:模型输出里的「N 元」会被 strip_money 换成「该费用」。
"""

from __future__ import annotations

import re

from . import llm, mock, rules

JSON_ONLY = "只输出 JSON,不要输出解释或多余文字。"
MONEY_RE = re.compile(r"(¥|￥)?\s*\d+(?:\.\d+)?\s*(?:元|块)(?:左右|上下)?")


def _use_model(config, force_mock):
    if force_mock:
        return False
    return bool({**llm.default_config(), **(config or {})}.get("api_key"))


def _cfg(config):
    return {**llm.default_config(), **(config or {})}


def strip_money(text):
    return MONEY_RE.sub("该费用", text).replace("该费用该费用", "该费用")


def verdict(r):
    d = r["decision"]
    war = r["warranty"]
    head = "%s:%s。" % (d["verdict"], d["why"])
    if war["age"] is None:
        return head + " 保修情况未知,补购机年份。"
    live = [i["name"] for i in war["items"] if i["active"] and i["name"] != "压缩机/电机"]
    if live:
        return head + " 整机/主要部件仍在保(%s),先走官方售后,别自己找人修。" % "、".join(live)
    return head + " 整机与主要部件已过保(%d 年),报价前先问清上门费与配件费。" % war["age"]


def _model_advice(r, config):
    causes = "\n".join("- [%s] %s:%s" % (c["level"], c["cause"], c["check"]) for c in r["causes"])
    raw = llm.chat([{
        "role": "system",
        "content": ("你是家电维修顾问。只根据给定的故障树、保修与本地估价说话;不要写金额数字,"
                    "不要建议用户自行拆燃气、制冷、高压部件;不确定就让他报修。"),
    }, {
        "role": "user",
        "content": ("家电:%s 现象:%s\n可能原因:\n%s\n保修:%s\n修换结论:%s\n安全禁忌:%s\n%s\n输出格式:"
                    '{"summary":"三句话内说清最可能原因与先做什么",'
                    '"risks":["继续使用的安全风险或被加价的坑"],'
                    '"questions":["上门前还要问师傅/客服的问题"]}'
                    % (r["fault"]["name"], "、".join(r["symptoms"]) or "未明确", causes,
                       "在保" if not r["warranty"]["expired"] else "过保",
                       r["decision"]["verdict"], "、".join(r["safety"]), JSON_ONLY)),
    }], config=_cfg(config), temperature=0.2, max_tokens=1800)
    d = llm.extract_json(raw)
    return {"summary": strip_money(str(d.get("summary") or "")),
            "risks": [strip_money(str(x)) for x in d.get("risks", [])][:6],
            "questions": [strip_money(str(x)) for x in d.get("questions", [])][:6]}


def diagnose(text, buy_year=None, config=None, db=None, force_mock=False, save=False):
    r = rules.analyze(text, buy_year=buy_year)
    r["text"] = text
    if _use_model(config, force_mock):
        layers = _model_advice(r, config)
        mode = "model"
    else:
        layers = mock.offline(r)
        mode = "offline"
    r.update({"verdict": verdict(r), "mode": mode, "saved_id": None, **layers})
    if db is not None and save:
        r["saved_id"] = db.save(r)
    return r
