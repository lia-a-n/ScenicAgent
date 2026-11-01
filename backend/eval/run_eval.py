"""离线评测脚本

指标:
1. 意图准确率        全量(忽略标记 ignore_intent 的用例)
2. 检索命中率        知识类: RAG 是否命中 + 命中文档是否包含期望来源
3. 办事成功率        票务类: 回答是否包含期望关键字(订单号/金额等)
4. 行程约束满足率    规划类: 程序化复检(检修/身高) + 人群标签 + 最少步数
5. 转人工成功率      投诉/求助类: 是否生成工单

运行: python eval/run_eval.py
"""
import asyncio
import json
import sys
from pathlib import Path

# 允许直接 python eval/run_eval.py 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

import app.agents.planner_node as planner_node
from app.agents.graph import chat_graph
from app.agents.planner_node import _gather_facts, _validate
from app.agents.state import Itinerary
from app.utils.dates import fmt_date, normalize_date

QA_FILE = Path(__file__).parent / "qa.jsonl"


# 评测固定天气,不访问外网:保证可复现,且生成与校验两次调用口径一致
async def _fixed_weather(query_date: str) -> str:
    return json.dumps({
        "日期": fmt_date(normalize_date(query_date)),
        "天气": "晴",
        "温度": "20~28℃",
        "风力": "2 级",
        "出行建议": "适合全项目",
    }, ensure_ascii=False)


planner_node._get_weather = _fixed_weather

# 每个评测会话独立,避免未命中计数互相干扰
results: list[dict] = []


def _kw_hit(answer: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if kw not in answer]


async def _eval_plan(case: dict, final: dict) -> tuple[bool, str]:
    """规划类:结构化行程存在性 + 复用规划节点的程序化校验"""
    raw = final.get("itinerary")
    if not raw:
        return False, "未生成行程"
    it = Itinerary(**raw)

    facts, _ = await _gather_facts(normalize_date(case.get("date", "明天")))
    err, _ = _validate(it, facts, [])
    if err:
        return False, f"约束违规: {'；'.join(err)}"

    if case.get("has_elder") is not None and it.has_elder != case["has_elder"]:
        return False, f"老人标签错误: 期望 {case['has_elder']} 实际 {it.has_elder}"
    if "child_ages" in case and sorted(it.child_ages) != sorted(case["child_ages"]):
        return False, f"儿童年龄错误: 期望 {case['child_ages']} 实际 {it.child_ages}"
    return True, f"{len(it.steps)} 步,校验通过"


async def check(case: dict, final: dict) -> dict:
    ctype = case["type"]
    answer = final.get("answer", "") or ""
    alt_intents = case.get("alt_intent", [])
    if isinstance(alt_intents, str):
        alt_intents = [alt_intents]
    intent_ok = (
        case.get("ignore_intent")
        or final.get("intent") == case["intent"]
        or final.get("intent") in alt_intents
    )
    checks: dict[str, object] = {"intent": intent_ok}
    detail = ""

    if ctype == "knowledge":
        sources = final.get("sources") or []
        expect_srcs = case.get("sources") or ([case["source"]] if case.get("source") else [])
        src_ok = (not expect_srcs) or any(s["source"] in expect_srcs for s in sources)
        missed_kw = _kw_hit(answer, case.get("keywords", []))
        checks.update(retrieval=bool(sources), source=src_ok, keywords=not missed_kw)
        detail = f"来源 {len(sources)} 条" + ("" if not missed_kw else f",缺词 {missed_kw}")

    elif ctype == "order":
        missed_kw = _kw_hit(answer, case.get("keywords", []))
        checks["keywords"] = not missed_kw
        detail = "关键字齐全" if not missed_kw else f"缺词 {missed_kw}"

    elif ctype == "plan":
        plan_ok, plan_detail = await _eval_plan(case, final)
        checks["plan"] = plan_ok
        detail = plan_detail

    elif ctype == "handoff":
        has_ticket = bool(final.get("handoff"))
        missed_kw = _kw_hit(answer, case.get("keywords", []))
        checks.update(handoff=has_ticket, keywords=not missed_kw)
        detail = "工单已建" if has_ticket else "未转人工"

    elif ctype == "miss":
        # 首轮温和兜底或直接转人工都算正确处理
        checks["handled"] = "人工" in answer
        detail = answer[:30]

    elif ctype == "chitchat":
        missed_kw = _kw_hit(answer, case.get("keywords", []))
        checks["keywords"] = not missed_kw
        detail = "闲聊已回应" if not missed_kw else f"缺词 {missed_kw}"

    passed = all(checks.values())
    return {"id": case["id"], "type": ctype, "pass": passed, "checks": checks, "detail": detail}


async def run_one(case: dict) -> dict:
    try:
        final = await chat_graph.ainvoke({
            "session_id": "eval-" + case["id"],
            "user_input": case["q"],
            "history_text": "",
        })
        return await check(case, final)
    except Exception as e:
        return {"id": case["id"], "type": case["type"], "pass": False, "checks": {}, "detail": f"异常: {e}"}


def _rate(items: list[dict], key: str) -> str:
    total = [r for r in items if key in r["checks"]]
    if not total:
        return "N/A"
    ok = sum(1 for r in total if r["checks"][key])
    return f"{ok}/{len(total)} = {ok / len(total) * 100:.1f}%"


async def main():
    cases = [json.loads(line) for line in QA_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    # 支持按用例 id 过滤: python eval/run_eval.py K14 K23
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        cases = [c for c in cases if c["id"] in wanted]
    logger.info(f"开始评测,共 {len(cases)} 条用例")

    for i, case in enumerate(cases, 1):
        r = await run_one(case)
        results.append(r)
        mark = "PASS" if r["pass"] else "FAIL"
        logger.info(f"[{i}/{len(cases)}] {r['id']} {r['type']:<9} {mark}  {r['detail']}")
        print(f"[{i:>2}/{len(cases)}] {r['id']} {r['type']:<9} {mark}  {r['detail']}", flush=True)
        # 控制请求速率,避免触发 DashScope RPM 限流(qwen-turbo 限流更严)
        await asyncio.sleep(1)

    passed = sum(1 for r in results if r["pass"])
    print("\n========== 评测汇总 ==========")
    print(f"整体通过率:        {passed}/{len(results)} = {passed / len(results) * 100:.1f}%")
    print(f"意图准确率:        {_rate(results, 'intent')}")
    print(f"RAG 命中(有参考):  {_rate(results, 'retrieval')}")
    print(f"期望文档命中:      {_rate(results, 'source')}")
    print(f"办事成功率:        {_rate(results, 'keywords')}")
    print(f"行程约束满足率:    {_rate(results, 'plan')}")
    print(f"转人工成功率:      {_rate(results, 'handoff')}")

    fails = [r for r in results if not r["pass"]]
    if fails:
        print("\n失败用例:")
        for r in fails:
            print(f"  {r['id']} ({r['type']}): {r['detail']} | checks={json.dumps(r['checks'], ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main())
