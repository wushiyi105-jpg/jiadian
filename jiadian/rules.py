"""家电维修本地规则:故障树、保修判定、维修估价与修/换结论、报修话术。"""

import json
import os
import re

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
YEAR_RE = re.compile(r"(20\d{2})\s*年?[买购入]")
NEW_PRICE_RE = re.compile(r"(?:新机价|原价|买时价|买时|售价)\s*(\d{3,6})")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def detect(text):
    faults = load("faults.json")["faults"]
    low = (text or "").lower()
    best, best_hits = None, []
    for f in faults:
        hits = [s for s in f["symptoms"] if s in low]
        if len(hits) > len(best_hits):
            best, best_hits = f, hits
    return best, best_hits


def causes_for(fault, symptoms):
    causes = list(fault["causes"])
    causes.sort(key=lambda c: 0 if c["level"] == "可自查" else 1)
    return [{"cause": c["cause"], "check": c["check"], "level": c["level"],
             "cost": c["cost"], "matched": any(s in c["cause"] for s in symptoms)} for c in causes]


def purchase_year(text, this_year=2026):
    m = YEAR_RE.search(text or "")
    if m:
        return int(m.group(1))
    if "去年" in (text or ""):
        return this_year - 1
    if "前年" in (text or ""):
        return this_year - 2
    return None


def warranty(purchase_year, this_year=2026, months=0):
    if purchase_year is None:
        return {"age": None, "items": [], "expired": None,
                "note": "没写购机年份,判不了保修;用 --buy-year 指定或补一句「2023年买的」"}
    age = this_year - purchase_year
    items = []
    for w in load("faults.json")["warranty"]:
        limit = age <= w["years"]
        items.append({"name": w["name"], "years": w["years"], "basis": w["basis"],
                      "active": bool(limit), "remain_years": max(0, w["years"] - age)})
    return {"age": age, "items": items, "expired": not any(i["active"] for i in items),
            "note": "保修按发票/签收起算;无发票按出厂日期+90 天,可能已经过保"}


def new_price(text, fault):
    m = NEW_PRICE_RE.search(text or "")
    if m:
        return float(m.group(1))
    return None


def estimate(causes):
    live = [c for c in causes if c["level"] == "必须报修"]
    pool = live or causes
    lo = min(c["cost"][0] for c in pool)
    hi = max(c["cost"][1] for c in pool)
    return {"low": lo, "high": hi,
            "items": [{"cause": c["cause"], "low": c["cost"][0], "high": c["cost"][1]}
                      for c in pool]}


def residual(new_price, age):
    if not new_price or age is None:
        return None
    value = new_price * (0.55 ** max(1, age))
    return round(max(value, new_price * 0.05))


def decision(est, res, new_price, war=None):
    if war and war.get("age") is not None:
        core = [i["name"] for i in war["items"] if i["active"] and i["name"] != "压缩机/电机"]
        if core and est["high"] > 0:
            return {"verdict": "先走保修", "why": "仍在 %s 范围内,先让官方检测,过保与否以发票为准" % "、".join(core),
                    "ratio": None}
    if not new_price:
        return {"verdict": "先补新机价", "why": "没有新机价,算不出维修费占比,也判断不了换新划不划算",
                "ratio": None}
    ratio = est["high"] / new_price
    if res and est["high"] >= res:
        return {"verdict": "换新", "why": "维修上限 %d 元已超过残值 %d 元,修完也不值" % (est["high"], res),
                "ratio": round(ratio, 2)}
    if ratio >= 0.35:
        return {"verdict": "倾向换新", "why": "维修上限占新机价 %.0f%%,超过 35%% 这条线" % (ratio * 100),
                "ratio": round(ratio, 2)}
    if ratio <= 0.15:
        return {"verdict": "修", "why": "维修上限占新机价 %.0f%%,低于 15%%,修了继续用" % (ratio * 100),
                "ratio": round(ratio, 2)}
    return {"verdict": "看情况", "why": "维修费占新机价 %.0f%%,先比价再定:超过残值一半就换" % (ratio * 100),
            "ratio": round(ratio, 2)}


def talk_script(fault, causes):
    must = [c for c in causes if c["level"] == "必须报修"]
    lines = ["师傅您好,%s 出现「%s」,想先问清楚再约上门。" % (fault["name"], "、".join(fault["symptoms"][:3])),
             "1. 上门费多少?检测后不修是否收费?",
             "2. 配件费大概多少?是原厂件还是通用件?",
             "3. 报价是否含税、含拆装与清运?",
             "4. 修完这部分保修多久?",
             "5. 如果判断不值得修,旧机能否折抵?"]
    if must:
        lines.append("6. 我怀疑是「%s」,请带对应配件上门。" % must[0]["cause"])
    return "\n".join(lines)


def checklist(text):
    checks = [
        ("品牌型号", ["型号", "品牌", "kg", "匹", "升"], "铭牌在机身侧面/门内侧,拍照留存"),
        ("购机年份/发票", ["年", "发票", "保修卡"], "决定是否在保,过保报价差别很大"),
        ("故障现象", ["不", "异响", "漏水", "黑屏", "报错"], "什么时候开始、什么情况下出现、有无异味"),
        ("已自查项", ["滤网", "断电", "重启", "插头"], "先做断电重启与滤网清理,能省一次上门费"),
        ("是否拆过", ["拆", "修过", "非官方"], "私拆会失去保修,报修时要如实说"),
        ("安装环境", ["高层", "壁挂", "嵌入式", "燃气"], "高层/燃气类需专业资质,不能找散工"),
    ]
    return [{"item": n, "ok": any(k in (text or "").lower() for k in keys), "how": how}
            for n, keys, how in checks]


def analyze(text, buy_year=None, this_year=2026):
    fault, hits = detect(text)
    notes = []
    if fault is None:
        fault = load("faults.json")["faults"][0]
        notes.append("没识别到具体家电,按冰箱估;用「空调不制冷」这类说法更准")
    causes = causes_for(fault, hits)
    py = buy_year or purchase_year(text, this_year)
    war = warranty(py, this_year)
    newp = new_price(text, fault)
    est = estimate(causes)
    res = residual(newp, war["age"])
    dec = decision(est, res, newp, war)
    return {"fault": fault, "symptoms": hits, "causes": causes, "purchase_year": py,
            "warranty": war, "new_price": newp, "residual": res,
            "estimate": est, "decision": dec, "talk": talk_script(fault, causes),
            "checklist": checklist(text), "safety": fault["safety"], "notes": notes}

