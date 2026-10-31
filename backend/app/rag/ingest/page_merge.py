"""把 docx 解析出的页面块渲染成 markdown 文本

页面渲染规则:
标题分级、列表转 `-`、表格取 markdown 原样嵌入。
渲染后每页首个标题写成 `#`,其余标题写成 `##`,便于后续按 `##` 切块。
"""
from typing import Dict, List


class PageTextPreparation:
    """单份 docx 报告的页面文本规整"""

    def __init__(self, report: Dict):
        self.report = report
        self._tables = {t["table_id"]: t.get("markdown", "") for t in report.get("tables", [])}

    def page_text(self, page: Dict) -> str:
        """渲染单页文本;只有第一页的首个标题写成 H1,其余页的标题一律 H2

        多页文本拼接后由同一套规则按 `##` 切块,若每页都产生 H1,
        后一页的 H1 会被并入上一块的正文。
        """
        blocks = [b for b in page["content"] if b["type"] != "page_footer"]
        parts = self._apply_formatting_rules(blocks, page["page"] == 1)
        if parts:
            parts[0] = parts[0].lstrip()
            parts[-1] = parts[-1].rstrip()
        return "\n".join(parts)

    def _apply_formatting_rules(self, blocks: List[Dict], first_page: bool) -> List[str]:
        """按块类型逐组渲染,返回渲染后的文本片段列表"""
        header_in_first_3 = any(b["type"] == "page_header" for b in blocks[:3])
        final_blocks: List[str] = []
        first_header_index = 0

        i = 0
        n = len(blocks)
        while i < n:
            block = blocks[i]
            block_type = block["type"]
            text = block.get("text", "").strip()

            if block_type == "page_header":
                final_blocks.append(f"\n{'#' if first_page else '##'} {text}\n")
                i += 1
                continue

            if block_type == "section_header":
                first_header_index += 1
                if first_page and first_header_index == 1 and i < 3 and not header_in_first_3:
                    prefix = "\n# "
                else:
                    prefix = "\n## "
                final_blocks.append(f"{prefix}{text}\n")
                i += 1
                continue

            if block_type == "table":
                final_blocks.append(f"\n{self._tables.get(block['table_id'], '')}\n")
                i += 1
                continue

            if block_type == "list_item":
                group = []
                while i < n and blocks[i]["type"] == "list_item":
                    group.append(blocks[i].get("text", "").strip())
                    i += 1
                final_blocks.append("\n" + "".join(f"- {item}\n" for item in group) + "\n")
                continue

            if block_type == "text":
                if text:
                    final_blocks.append(f"{text}\n")
                i += 1
                continue

            raise ValueError(f"未知的块类型: {block_type}")

        return final_blocks
