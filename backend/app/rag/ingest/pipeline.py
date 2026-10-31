"""知识库入库流水线:把 md / docx 统一转成分块,并产出入库质检统计

md 直接按二级标题切块;docx 先解析成页面块再渲染成 markdown,复用同一套切块规则。
检索链路只认最终分块,不感知源文件格式。
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from loguru import logger

from app.rag.ingest.docx_parser import parse_docx
from app.rag.ingest.page_merge import PageTextPreparation
from app.rag.ingest.splitter import doc_title_of, split_markdown

MIN_CHUNK_CHARS = 20  # 低于该长度的块在质检报告里单独计数
TRUST_DEFAULT = 1.0   # 内部知识库文档默认可信度


@dataclass
class Chunk:
    id: str
    text: str        # 原文:写入 Chroma documents,检索返回与前端溯源用
    embed_text: str  # 送 embedding/rerank 的文本:文档标题/块标题 + 原文
    source: str
    title: str
    doc_title: str
    trust: float = TRUST_DEFAULT

    def metadata(self) -> Dict:
        """Chroma metadata 只支持 str/int/float/bool"""
        return {
            "source": self.source,
            "title": self.title,
            "doc_title": self.doc_title,
            "trust": self.trust,
        }


def _docx_to_markdown(path: Path) -> str:
    """docx -> 按页渲染的 markdown 文本"""
    report = parse_docx(path)
    prep = PageTextPreparation(report)
    pages = [prep.page_text(p) for p in report["content"]]
    return "\n\n".join(p for p in pages if p.strip())


def build_chunks(kb_dir: Path) -> Tuple[List[Chunk], Dict]:
    """遍历知识库目录,返回 (分块列表, 质检报告)"""
    md_files = sorted(kb_dir.rglob("*.md"))
    docx_files = sorted(kb_dir.rglob("*.docx"))

    chunks: List[Chunk] = []
    per_file: List[Dict] = []
    duplicates: List[Dict] = []
    short_chunks: List[Dict] = []
    failed: List[Dict] = []
    seen: Dict[str, Chunk] = {}

    for path in md_files + docx_files:
        fmt = "docx" if path.suffix.lower() == ".docx" else "md"
        try:
            text = _docx_to_markdown(path) if fmt == "docx" else path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error(f"解析失败 {path.name}: {exc}")
            failed.append({"file": path.name, "format": fmt, "error": str(exc)})
            continue

        doc_title = doc_title_of(text) or path.stem  # 没有 H1 时用文件名
        file_chunks = 0
        file_chars = 0
        for idx, (title, body) in enumerate(split_markdown(text)):
            title = title or path.stem
            digest = hashlib.md5(body.encode("utf-8")).hexdigest()
            if digest in seen:
                duplicates.append({
                    "source": path.name,
                    "title": title,
                    "duplicate_of": seen[digest].source,
                })
                continue

            chunk = Chunk(
                id=hashlib.md5(f"{path.name}-{idx}-{title}".encode("utf-8")).hexdigest(),
                text=body,
                embed_text=f"{doc_title} / {title}\n{body}",
                source=path.name,
                title=title,
                doc_title=doc_title,
            )
            seen[digest] = chunk
            chunks.append(chunk)
            file_chunks += 1
            file_chars += len(body)
            if len(body) < MIN_CHUNK_CHARS:
                short_chunks.append({"source": path.name, "title": title, "chars": len(body)})

        per_file.append({
            "file": path.name,
            "format": fmt,
            "chunks": file_chunks,
            "chars": file_chars,
        })

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": {
            "total": len(md_files) + len(docx_files),
            "md": len(md_files),
            "docx": len(docx_files),
            "failed": len(failed),
        },
        "chunks": {
            "total": len(chunks),
            "avg_chars": round(sum(len(c.text) for c in chunks) / len(chunks), 1) if chunks else 0,
            "max_chars": max((len(c.text) for c in chunks), default=0),
            "short_chunks": len(short_chunks),
            "duplicate_skipped": len(duplicates),
        },
        "per_file": per_file,
        "short_chunks_detail": short_chunks,
        "duplicates": duplicates,
        "failed": failed,
    }
    return chunks, report


def write_report(report: Dict, path: Path) -> None:
    """质检报告落盘"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
