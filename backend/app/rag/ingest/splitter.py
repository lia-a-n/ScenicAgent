"""按二级标题切块

md 与 docx 渲染后的文本共用同一套规则。
"""
import re

MAX_CHUNK_CHARS = 400  # 单块最长字符,超出按段落继续切
_DOC_TITLE_RE = re.compile(r"^#\s+(.+)$", flags=re.MULTILINE)


def doc_title_of(text: str) -> str:
    """取文档首个 H1 作为总标题,没有则返回空串"""
    match = _DOC_TITLE_RE.search(text)
    return match.group(1).strip() if match else ""


def split_markdown(text: str) -> list[tuple[str, str]]:
    """
    按二级标题切块,返回 [(块标题, 块内容), ...]
    超过 MAX_CHUNK_CHARS 的块按段落再切
    """
    # H1 作为文档总标题
    doc_title = doc_title_of(text)

    # 按 ## 标题切分
    sections = re.split(r"^##\s+(.+)$", text, flags=re.MULTILINE)
    # sections: [开头, 标题1, 内容1, 标题2, 内容2, ...]
    chunks: list[tuple[str, str]] = []
    if len(sections) == 1:
        body = re.sub(r"^#\s+.+$", "", sections[0].strip(), count=1, flags=re.MULTILINE).strip()
        if body:
            chunks.append((doc_title, body))
    else:
        # 首个 H2 之前的部分:H1 单独出现时不单独成块,避免产生只有标题的碎片
        opening = re.sub(r"^#\s+.+$", "", sections[0].strip(), count=1, flags=re.MULTILINE).strip()
        if opening:
            chunks.append((doc_title, opening))
        for i in range(1, len(sections) - 1, 2):
            heading = sections[i].strip()
            body = sections[i + 1].strip()
            if not body:
                continue
            chunks.append((heading, body))

    # 超长块按段落二次切分
    final: list[tuple[str, str]] = []
    for title, body in chunks:
        if len(body) <= MAX_CHUNK_CHARS:
            final.append((title, body))
            continue
        buf = ""
        for para in re.split(r"\n\n+", body):
            if len(buf) + len(para) > MAX_CHUNK_CHARS and buf:
                final.append((title, buf.strip()))
                buf = para
            else:
                buf = f"{buf}\n\n{para}" if buf else para
        if buf.strip():
            final.append((title, buf.strip()))
    return final
