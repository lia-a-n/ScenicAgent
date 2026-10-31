"""DOCX 解析:按逻辑页把 word 文档拆成块序列

docx 没有物理页码,用内容量加标题作为换页依据,产出的块类型
(section_header / text / list_item / page_header / page_footer / table)
与 page_merge 的渲染规则一一对应。
"""
from pathlib import Path
from typing import Dict, Iterator, List, Union

from docx import Document
from docx.document import Document as _Document
from docx.table import Table as _Table
from docx.text.paragraph import Paragraph as _Paragraph

# 单个逻辑页的目标字符数,超过则换页
_PAGE_TARGET_CHARS = 3000


def _iter_block_items(doc: _Document) -> Iterator[Union[_Paragraph, _Table]]:
    """按文档顺序遍历段落与表格,保证表格不被排到所有段落之后"""
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield _Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield _Table(child, doc)


def _table_to_markdown(table: _Table) -> str:
    """把 python-docx 的 Table 转成 markdown 表格"""
    rows: List[List[str]] = []
    for row in table.rows:
        cells = [c.text.strip().replace("\n", " ").replace("|", "\\|") for c in row.cells]
        rows.append(cells)

    if not rows:
        return ""

    ncols = max(len(r) for r in rows)
    lines = []
    for i, row in enumerate(rows):
        padded = row + [""] * (ncols - len(row))
        lines.append("| " + " | ".join(padded) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * ncols) + " |")
    return "\n".join(lines)


def _classify_paragraph(paragraph: _Paragraph) -> str:
    """按段落样式判断块类型"""
    style_name = (paragraph.style.name or "").lower()
    if not paragraph.text.strip():
        return "text"
    # 中文版 Word / WPS 的样式名可能是"标题 1""项目符号列表"等
    if (
        style_name.startswith("heading")
        or style_name.startswith("title")
        or style_name.startswith("标题")
    ):
        return "section_header"
    if (
        "list" in style_name
        or "bullet" in style_name
        or "number" in style_name
        or "列表" in style_name
        or "项目符号" in style_name
    ):
        return "list_item"
    # 内置样式的内部名是 Header/Footer,但 WPS 等工具生成的文档可能直接写"页眉"/"页脚"
    if "header" in style_name or "页眉" in style_name:
        return "page_header"
    if "footer" in style_name or "页脚" in style_name:
        return "page_footer"
    return "text"


def _split_into_pages(blocks: List[Dict], tables: List[Dict]) -> List[Dict]:
    """按逻辑页切分块,遇到大标题或超长内容时换页,同时回填表格所在页"""
    pages: List[Dict] = []
    current_blocks: List[Dict] = []
    current_chars = 0

    for block in blocks:
        is_header = block["type"] == "section_header"
        block_len = len(block.get("text", ""))

        should_split = bool(current_blocks) and (
            (is_header and current_chars > 500)
            or current_chars + block_len > _PAGE_TARGET_CHARS * 1.5
        )

        if should_split:
            pages.append(_finalize_page(current_blocks, len(pages) + 1, tables))
            current_blocks = []
            current_chars = 0

        current_blocks.append(block)
        current_chars += block_len

    if current_blocks:
        pages.append(_finalize_page(current_blocks, len(pages) + 1, tables))

    return pages


def _finalize_page(page_blocks: List[Dict], page_no: int, tables: List[Dict]) -> Dict:
    """给页面块标记页号,并回填该页表格的 page"""
    for block in page_blocks:
        if block["type"] == "table":
            tid = block["table_id"]
            tables[tid]["page"] = page_no
    return {"page": page_no, "content": page_blocks}


def parse_docx(docx_path: Path) -> Dict:
    """解析单个 docx,返回 {"content": 按页分组的块, "tables": 表格对象}"""
    doc = Document(str(docx_path))

    blocks: List[Dict] = []
    tables: List[Dict] = []
    table_id = 0

    for item in _iter_block_items(doc):
        if isinstance(item, _Table):
            tables.append({
                "table_id": table_id,
                "page": 0,
                "markdown": _table_to_markdown(item),
            })
            blocks.append({"type": "table", "table_id": table_id})
            table_id += 1
            continue

        text = item.text.strip()
        if not text:
            continue
        blocks.append({"text": text, "type": _classify_paragraph(item), "text_id": len(blocks)})

    if not blocks:
        raise ValueError(f"文档 {docx_path.name} 解析后没有内容")

    return {"content": _split_into_pages(blocks, tables), "tables": tables}
