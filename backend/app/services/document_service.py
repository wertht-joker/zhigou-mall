"""文档管理服务：编排「上传 → 解析 → 切分 → 向量化 → 入库」全流程

失败统一抛 AppError 子类：
- 用户侧问题（格式不支持、解析为空）→ BadRequestError
- 服务侧问题（向量库写入失败等）→ AppServiceError
路由层不再需要 try/except。
"""
import os

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.errors import AppError, AppServiceError, BadRequestError, NotFoundError
from app.models.document import Document
from app.rag import embedding, loader, splitter, vector_store
from app.repositories.document_repository import DocumentRepository

# 上传文件保存目录（相对 backend 运行目录）
UPLOAD_DIR = "uploads"

# 支持的文件类型
SUPPORTED_TYPES = {"pdf", "docx", "xlsx", "md", "txt"}


def _file_type(filename: str) -> str:
    """根据扩展名返回文件类型"""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _save_file(file: UploadFile) -> tuple[str, int]:
    """保存上传文件，返回 (路径, 大小)"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, file.filename)
    content = file.file.read()
    with open(path, "wb") as f:
        f.write(content)
    return path, len(content)


def upload_document(db: Session, file: UploadFile, tenant_id: int | None = None) -> Document:
    """完整入库流程"""
    file_type = _file_type(file.filename)
    if file_type not in SUPPORTED_TYPES:
        raise BadRequestError(
            f"不支持的文件格式: {file_type}，仅支持 {sorted(SUPPORTED_TYPES)}"
        )

    # 1. 先写元数据（状态 processing）
    repo = DocumentRepository(db)
    doc = repo.create(file.filename, file_type, tenant_id)

    try:
        # 2. 保存文件
        path, size = _save_file(file)
        doc.size = size
        repo.save(doc)

        # 3. 解析 → 文本
        text = loader.load_document(path, file_type)
        if not text.strip():
            raise BadRequestError("文档解析结果为空，无法入库")

        # 4. 切分 → 块
        chunks = splitter.split_text(text)
        if not chunks:
            raise BadRequestError("文档切分后没有内容")

        # 5. 向量化
        vectors = embedding.embed(chunks)

        # 6. 插入 Milvus（block 带租户分区键，检索时可按租户隔离）
        vector_store.insert_chunks(doc.id, chunks, vectors, tenant_id)

        # 7. 更新元数据为完成态
        doc.chunk_count = len(chunks)
        doc.status = "done"
        repo.save(doc)
    except AppError:
        doc.status = "failed"
        repo.save(doc)
        raise
    except Exception as exc:
        # 未预期的失败：标记状态并转成统一的服务异常
        doc.status = "failed"
        repo.save(doc)
        raise AppServiceError(f"文档入库失败：{exc}") from exc

    return doc


def list_documents(db: Session, keyword: str | None = None,
                   tenant_id: int | None = None) -> list[Document]:
    """文档列表（按上传时间倒序，支持按名称关键词搜索）"""
    return DocumentRepository(db).list(keyword, tenant_id)


def delete_document(db: Session, doc_id: int, tenant_id: int | None = None) -> None:
    """删除文档（元数据 + Milvus 向量）"""
    repo = DocumentRepository(db)
    doc = repo.get(doc_id, tenant_id)
    if not doc:
        raise NotFoundError("文档不存在")

    # 先删 Milvus 向量（Milvus 不可用时仍要能删元数据），限定本租户
    try:
        vector_store.delete_by_doc_id(doc_id, tenant_id)
    except Exception:
        pass

    repo.delete(doc)
