"""知识库灌库:读取 kb 下的 md / docx,统一切块后写入 Chroma

用法: python scripts/ingest_kb.py        # 增量写入
      python scripts/ingest_kb.py --reset # 清空后重建
"""
import asyncio
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.chroma_store import ChromaStore  # noqa: E402
from app.rag.ingest.pipeline import build_chunks, write_report  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
KB_DIR = BACKEND_DIR / "kb"
REPORT_PATH = BACKEND_DIR / "data" / "ingest_report.json"


async def main(reset: bool) -> None:
    store = ChromaStore()
    if reset:
        store.reset()
        logger.info("已清空旧集合")

    chunks, report = build_chunks(KB_DIR)
    await store.add(
        [c.id for c in chunks],
        [c.text for c in chunks],
        [c.embed_text for c in chunks],
        [c.metadata() for c in chunks],
    )
    write_report(report, REPORT_PATH)
    logger.info(
        f"灌库完成: {report['files']['total']} 个文件 -> {len(chunks)} 个分块,"
        f"集合现有 {store.collection.count()} 条,质检报告 {REPORT_PATH}"
    )


if __name__ == "__main__":
    asyncio.run(main(reset="--reset" in sys.argv))
