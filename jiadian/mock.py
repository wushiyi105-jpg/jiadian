"""离线模式:诊断摘要、风险与追问,结构与模型模式一致。"""

from __future__ import annotations


def offline(r):
    fault = r["fault"]
    ok = [c for c in r["causes"] if c["level"] == "可自查"]
    must = [c for c in r["causes"] if c["level"] == "必须报修"]
    summary = "%s 的「%s」,先做 %d 项自查" % (fault["name"], "、".join(r["symptoms"]) or "故障", len(ok))
    if ok:
        summary += "(%s)" % "、".join(c["cause"] for c in ok[:2])
    if must:
        summary += ";仍不正常则大概率是「%s」,需要报修" % must[0]["cause"]
    summary += "。"
    if not r["warranty"]["expired"]:
        summary += "仍在保修期,优先官方售后。"
    else:
        summary += "已过保,先问清上门费再约。"

    risks = []
    if "燃气" in r["text"]:
        risks.append("燃气类故障严禁自行拆装,闻到燃气味先关阀开窗、到室外打电话。")
    risks.append("过保机被「先修后报价」:上门只查不报,修完才给总价,极易被加价。")
    risks.append("非官方维修点换件后,原厂保修通常直接失效。")
    if r["new_price"] and r["decision"]["verdict"] in ("换新", "倾向换新"):
        risks.append("继续修可能越修越贵:这台已接近残值,维修费容易超过机器本身价值。")
    risks.append("同一故障修两次仍不好,按三包可主张换货或退货(保修期内)。")
    for s in fault["safety"][:2]:
        risks.append("安全:" + s)

    questions = ["上门费多少?检测不修收不收?", "配件是原厂还是通用件?报价含不含税?",
                 "修完这部分保多久?", "能不能先给总价区间再动手?", "旧机能不能折抵新机?"]
    if must:
        questions.append("是不是「%s」?需要带什么配件?" % must[0]["cause"])
    return {"summary": summary, "risks": risks[:6], "questions": questions[:6]}
