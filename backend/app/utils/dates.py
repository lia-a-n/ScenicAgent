"""日期归一化:支持 YYYY-MM-DD 与中文相对日期(今天/明天/后天/大后天)"""
from datetime import date, datetime, timedelta

_RELATIVE = {
    "今天": 0, "今日": 0, "今晚": 0,
    "明天": 1, "明日": 1,
    "后天": 2,
    "大后天": 3,
}


def normalize_date(value: str) -> date:
    """把模型给出的日期参数转为 date;无法解析时默认今天"""
    value = (value or "").strip()
    for word, offset in _RELATIVE.items():
        if word in value:
            return date.today() + timedelta(days=offset)
    # 尝试直接解析标准日期
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%m月%d日"):
        try:
            d = datetime.strptime(value, fmt)
            if fmt == "%m月%d日":
                d = d.replace(year=date.today().year)
            return d.date()
        except ValueError:
            continue
    return date.today()


def fmt_date(d: date) -> str:
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    return f"{d.isoformat()}(周{weekdays[d.weekday()]})"


def relative_label(d: date) -> str:
    """把绝对日期换算成相对今天的说法,给口语化 prompt 做锚点

    LLM 不知道今天几号,只给绝对日期时容易把"明天"说成"今天"。
    """
    offset = (d - date.today()).days
    return {0: "今天", 1: "明天", 2: "后天", 3: "大后天"}.get(offset, f"{offset}天后")
