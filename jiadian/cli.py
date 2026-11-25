"""命令行入口:python -m jiadian <命令>。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, agent, llm, rules
from . import db as dbmod
from .llm import LLMError

BANNER = ("⚠️  当前为离线模式(未配置 LLM_API_KEY):故障树、保修、估价与修换结论由本地给出。\n"
          "   填入 LLM_API_KEY 后,诊断解释与追问由模型撰写(金额仍以本地估价为准)。\n")


def render(r):
    mode = "模型" if r["mode"] == "model" else "离线模式"
    lines = ["🔧 家电报修诊断  [%s]" % mode, "", "📌 " + r["verdict"], ""]
    if r["notes"]:
        for n in r["notes"]:
            lines.append("注:" + n)
        lines.append("")

    lines.append("🧾 故障定位")
    lines.append("  家电:%s  现象:%s" % (r["fault"]["name"], "、".join(r["symptoms"]) or "未明确"))
    for c in r["causes"]:
        mark = "🟢" if c["level"] == "可自查" else "🔴"
        lines.append("  %s [%s] %s" % (mark, c["level"], c["cause"]))
        lines.append("      怎么查:%s" % c["check"])
    lines.append("")

    lines.append("📅 保修")
    w = r["warranty"]
    if w["age"] is None:
        lines.append("  " + w["note"])
    else:
        lines.append("  购机 %s 年,已用 %d 年" % (r["purchase_year"], w["age"]))
        for i in w["items"]:
            lines.append("  %s %s(%d 年)" % ("✅ 在保" if i["active"] else "❌ 过保", i["name"], i["years"]))
        lines.append("  注:" + w["note"])
    lines.append("")

    e = r["estimate"]
    lines.append("💰 维修估价(配件+人工的常见区间)")
    for i in e["items"]:
        lines.append("  · %s:%d–%d 元" % (i["cause"], i["low"], i["high"]))
    lines.append("  合计参考:%d–%d 元" % (e["low"], e["high"]))
    if r["new_price"]:
        lines.append("  新机价 %d 元,残值约 %s 元" % (r["new_price"], r["residual"]))
    lines.append("")

    d = r["decision"]
    lines.append("🤔 修还是换:%s" % d["verdict"])
    lines.append("  " + d["why"])
    if d["ratio"] is not None:
        lines.append("  维修上限占新机价 %.0f%%" % (d["ratio"] * 100))
    lines.append("")

    lines.append("⚠️  安全禁忌")
    for s in r["safety"]:
        lines.append("  · " + s)
    lines.append("")
    lines.append("📞 报修话术")
    for x in r["talk"].splitlines():
        lines.append("  " + x)
    lines.append("")

    if r["summary"]:
        lines.append("🧭 判断")
        lines.append("  " + r["summary"])
        lines.append("")
    if r["risks"]:
        lines.append("🚩 风险与坑")
        for x in r["risks"]:
            lines.append("  · " + x)
        lines.append("")
    if r["questions"]:
        lines.append("❓ 还要问")
        for x in r["questions"]:
            lines.append("  · " + x)
        lines.append("")
    lines.append("📋 报修前体检")
    for c in r["checklist"]:
        lines.append("  %s %s —— %s" % ("✅" if c["ok"] else "❌", c["item"], c["how"]))
    return "\n".join(lines)


def _text(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return f.read()
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def cmd_diagnose(args):
    text = _text(args)
    if not text.strip():
        print("❌ 没有描述:用 --text、--file 或管道输入。", file=sys.stderr)
        sys.exit(2)
    db = dbmod.Database(args.db) if args.db else dbmod.Database()
    r = agent.diagnose(text, buy_year=args.buy_year, config=llm.config_from_args(args),
                       db=db, force_mock=args.mock, save=args.save)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(render(r))
    if r.get("saved_id"):
        print("\n已入库(#%d),`python -m jiadian history` 可回看。" % r["saved_id"])


def cmd_faults(args):
    faults = rules.load("faults.json")["faults"]
    if args.grep:
        faults = [f for f in faults if args.grep in f["name"]]
    print("🧰 故障树(%d 类家电)" % len(faults))
    for f in faults:
        print("\n【%s】现象:%s" % (f["name"], "、".join(f["symptoms"])))
        for c in f["causes"]:
            print("  %s %s(%d–%d 元)" % ("🟢" if c["level"] == "可自查" else "🔴", c["cause"],
                                          c["cost"][0], c["cost"][1]))


def cmd_warranty(args):
    rows = rules.load("faults.json")["warranty"]
    print("📅 保修口径")
    for w in rows:
        print("  · %s:%d 年(%s)" % (w["name"], w["years"], w["basis"]))
    for n in rules.load("faults.json")["warranty_notes"]:
        print("  ⚠ " + n)


def cmd_history(args):
    rows = dbmod.Database(args.db).latest(args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("还没有记录。`python -m jiadian diagnose --text \"空调不制冷\" --save` 存一条。")
        return
    print("🔧 报修记录")
    for r in rows:
        print("  #%d  %s  %s  %s  维修上限 %s 元  %s"
              % (r["id"], r["appliance"], r["symptoms"] or "—", r["verdict"],
                 r["estimate"] or "—", r["created_at"]))


def cmd_web(args):
    from . import web
    web.serve(host=args.host, port=args.port, db_path=args.db, force_mock=args.mock)


def build_parser():
    p = argparse.ArgumentParser(prog="jiadian", description="家电 · 报修诊断:先自查,再估价,决定修还是换。")
    p.add_argument("--version", action="version", version="jiadian %s" % __version__)
    p.add_argument("--mock", action="store_true", help="强制离线模式")
    p.add_argument("--json", action="store_true", help="输出原始 JSON")
    p.add_argument("--model", help="覆盖 LLM_MODEL")
    p.add_argument("--base-url", help="覆盖 LLM_BASE_URL")
    p.add_argument("--api-key", help="覆盖 LLM_API_KEY")
    p.add_argument("--db", help="SQLite 路径")
    sub = p.add_subparsers(dest="command", required=True)

    dp = sub.add_parser("diagnose", help="诊断一台家电")
    dp.add_argument("--text", help="现象描述:家电、故障、购机年份、新机价")
    dp.add_argument("--file", help="从文件读")
    dp.add_argument("--buy-year", type=int, help="购机年份,如 2021")
    dp.add_argument("--save", action="store_true")
    dp.set_defaults(func=cmd_diagnose)

    fp = sub.add_parser("faults", help="故障树")
    fp.add_argument("--grep", help="按家电名过滤")
    fp.set_defaults(func=cmd_faults)

    wp = sub.add_parser("warranty", help="保修口径")
    wp.set_defaults(func=cmd_warranty)

    hp = sub.add_parser("history", help="历史记录")
    hp.add_argument("--limit", type=int, default=10)
    hp.set_defaults(func=cmd_history)

    webp = sub.add_parser("web", help="启动 Web 界面")
    webp.add_argument("--host", default="127.0.0.1")
    webp.add_argument("--port", type=int, default=8000)
    webp.add_argument("--mock", action="store_true", default=argparse.SUPPRESS)
    webp.set_defaults(func=cmd_web)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.mock and args.command == "diagnose" and not llm.config_from_args(args).get("api_key"):
        print(BANNER, file=sys.stderr)
    try:
        args.func(args)
    except LLMError as e:
        print("❌ %s" % e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
