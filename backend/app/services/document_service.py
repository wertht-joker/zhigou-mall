"""文档管理服务：编排「上传 → 解析 → 切分 → 向量化 → 入库」全流程

失败统一抛 AppError 子类：
- 用户侧问题（格式不支持、解析为空）→ BadRequestError
- 服务侧问题（向量库写入失败等）→ AppServiceError
路由层不再需要 try/except。
"""
import glob
import os
import shutil
from datetime import datetime

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, AppServiceError, BadRequestError, NotFoundError
from app.core.redis import bump_kb_version
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


def _save_file(file: UploadFile, doc_id: int) -> tuple[str, int]:
    """保存上传文件，按文档 ID 命名，避免新版本覆盖旧版本源文件"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = os.path.basename(file.filename or "document")
    path = os.path.join(UPLOAD_DIR, f"{doc_id}_{filename}")
    content = file.file.read()
    with open(path, "wb") as f:
        f.write(content)
    return path, len(content)


def _samples_dir() -> str:
    return os.path.normpath(
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..", settings.samples_dir
        )
    )


def _resolve_source_path(doc: Document) -> str | None:
    """定位文档原始文件：新上传（id_文件名）→ 旧上传（文件名）→ 种子文档"""
    name = os.path.basename(doc.name)
    candidates = sorted(glob.glob(os.path.join(UPLOAD_DIR, f"{doc.id}_*")))
    candidates += [
        os.path.join(UPLOAD_DIR, name),
        os.path.join(_samples_dir(), doc.name),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def upload_document(db: Session, file: UploadFile, tenant_id: int | None = None,
                    category_id: int | None = None,
                    policy_key: str | None = None, version: int | None = None,
                    effective_from: datetime | None = None,
                    effective_to: datetime | None = None) -> Document:
    """完整入库流程（可选政策版本元数据）

    policy_key 相同视为同一政策的不同版本：
    - version 为空时自动 +1；
    - 旧 active 版本标记为 superseded 并补上 effective_to；
    - 历史版本不物理删除，历史订单仍可按当时版本检索。
    """
    file_type = _file_type(file.filename)
    if file_type not in SUPPORTED_TYPES:
        raise BadRequestError(
            f"不支持的文件格式: {file_type}，仅支持 {sorted(SUPPORTED_TYPES)}"
        )

    # 1. 先写元数据（状态 processing）
    repo = DocumentRepository(db)
    policy_key = (policy_key or "").strip() or None
    supersedes_id = None
    if policy_key:
        latest = repo.latest_by_policy(policy_key, tenant_id)
        if latest and version is not None and version <= latest.version:
            raise BadRequestError(
                f"版本号必须大于当前最新版本 v{latest.version}"
            )
        if version is None:
            version = (latest.version + 1) if latest else 1
        # 新版本未指定生效时间时默认“从现在开始”，避免新旧版本同时生效
        if version > 1 and effective_from is None:
            effective_from = datetime.now()
        supersedes_id = latest.id if latest else None
    else:
        version = version or 1

    doc = repo.create(
        file.filename, file_type, tenant_id,
        category_id=category_id,
        policy_key=policy_key,
        version=version,
        effective_from=effective_from,
        effective_to=effective_to,
        supersedes_id=supersedes_id,
    )

    try:
        # 2. 保存文件
        path, size = _save_file(file, doc.id)
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

        # 6. 插入 Milvus（块带租户 + 政策版本 + 生效期，检索时按两个维度过滤）
        vector_store.insert_chunks(
            doc.id, chunks, vectors, tenant_id,
            policy_key=doc.policy_key,
            doc_version=doc.version,
            effective_from=doc.effective_from,
            effective_to=doc.effective_to,
        )

        # 7. 更新元数据为完成态，并让检索缓存失效
        doc.chunk_count = len(chunks)
        doc.status = "done"
        repo.save(doc)
        # 入库成功后才把旧版本标记为 superseded，避免上传失败把旧政策提前作废
        if policy_key:
            repo.supersede_policy(
                policy_key, tenant_id, effective_from, exclude_id=doc.id
            )
        bump_kb_version()
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


def create_text_document(db: Session, name: str, content: str,
                         tenant_id: int | None = None,
                         category_id: int | None = None) -> Document:
    """把一段 Markdown 文本直接入库（FAQ 草稿一键发布）

    与上传文件的区别：不经过 UploadFile，直接把文本写成 .md 源文件，
    后续仍可按普通文档编辑、重建索引或删除。
    """
    name = (name or "").strip() or "FAQ 文档"
    content = (content or "").strip()
    if not content:
        raise BadRequestError("文档内容不能为空")

    safe_name = "".join(
        "-" if ch in '\\/:*?"<>|' else ch for ch in name
    ).strip() or "faq"
    file_name = f"{safe_name}.md"
    repo = DocumentRepository(db)
    doc = repo.create(file_name, "md", tenant_id, category_id=category_id, version=1)

    try:
        chunks = splitter.split_text(content)
        if not chunks:
            raise BadRequestError("文档切分后没有内容")
        vectors = embedding.embed(chunks)

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        path = os.path.join(UPLOAD_DIR, f"{doc.id}_{file_name}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        vector_store.insert_chunks(
            doc.id, chunks, vectors, tenant_id,
            policy_key=None, doc_version=1,
            effective_from=None, effective_to=None,
        )
        doc.size = os.path.getsize(path)
        doc.chunk_count = len(chunks)
        doc.status = "done"
        repo.save(doc)
        bump_kb_version()
    except AppError:
        doc.status = "failed"
        repo.save(doc)
        raise
    except Exception as exc:
        doc.status = "failed"
        repo.save(doc)
        raise AppServiceError(f"文档入库失败：{exc}") from exc
    return doc


def list_documents(db: Session, keyword: str | None = None,
                   tenant_id: int | None = None) -> list[Document]:
    """文档列表（按上传时间倒序，支持按名称关键词搜索）"""
    return DocumentRepository(db).list(keyword, tenant_id)


def list_versions(db: Session, doc_id: int,
                  tenant_id: int | None = None) -> list[Document]:
    """查看某文档所属政策的全部版本；普通文档返回自身"""
    repo = DocumentRepository(db)
    doc = repo.get(doc_id, tenant_id)
    if not doc:
        raise NotFoundError("文档不存在")
    if not doc.policy_key:
        return [doc]
    scope = tenant_id if tenant_id is not None else doc.tenant_id
    return repo.list_by_policy(doc.policy_key, scope)


def _reindex_document(db: Session, doc: Document,
                      tenant_id: int | None, path: str) -> None:
    """用原始文件重建单个文档的向量（元数据/版本状态变更后同步检索层）"""
    try:
        text = loader.load_document(path, doc.type)
        if not text.strip():
            raise BadRequestError("文档内容为空，无法重建索引")
        chunks = splitter.split_text(text)
        if not chunks:
            raise BadRequestError("文档切分后没有内容")
        vectors = embedding.embed(chunks)

        vector_store.delete_by_doc_id(doc.id, tenant_id)
        vector_store.insert_chunks(
            doc.id, chunks, vectors, tenant_id,
            policy_key=doc.policy_key,
            doc_version=doc.version,
            effective_from=doc.effective_from,
            effective_to=doc.effective_to,
        )
        doc.size = os.path.getsize(path)
        doc.chunk_count = len(chunks)
        doc.status = "done"
    except AppError:
        doc.status = "failed"
        raise
    except Exception as exc:
        doc.status = "failed"
        raise AppServiceError(f"文档重建索引失败：{exc}") from exc


def update_document(db: Session, doc_id: int, tenant_id: int | None,
                    name: str, category_id: int | None,
                    effective_from: datetime | None,
                    effective_to: datetime | None) -> Document:
    """编辑文档元数据；生效时间变化时同步重建向量元数据

    政策标识 / 版本号不允许修改：它们是历史版本追溯的主键。
    """
    repo = DocumentRepository(db)
    doc = repo.get(doc_id, tenant_id)
    if not doc:
        raise NotFoundError("文档不存在")

    # 平台管理员跨租户操作时，用文档实际所属租户维护向量索引
    scope = tenant_id if tenant_id is not None else doc.tenant_id

    name = (name or "").strip()
    if not name:
        raise BadRequestError("文档名称不能为空")
    if effective_from and effective_to and effective_to <= effective_from:
        raise BadRequestError("生效结束时间必须晚于开始时间")

    dates_changed = (
        doc.effective_from != effective_from or doc.effective_to != effective_to
    )
    source_path = _resolve_source_path(doc) if dates_changed else None
    if dates_changed and not source_path:
        raise BadRequestError("原始文件不存在，无法同步生效时间，请上传新版本")

    # 重命名种子文档时，把原始文件复制为「文档ID_新名称」，保证后续仍可重建索引
    if name != doc.name:
        existing = glob.glob(os.path.join(UPLOAD_DIR, f"{doc.id}_*"))
        if not existing:
            origin = source_path or _resolve_source_path(doc)
            if origin:
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                shutil.copy2(origin, os.path.join(UPLOAD_DIR, f"{doc.id}_{name}"))

    doc.name = name
    doc.category_id = category_id
    doc.effective_from = effective_from
    doc.effective_to = effective_to
    repo.save(doc)

    if dates_changed and source_path:
        _reindex_document(db, doc, scope, source_path)
        repo.save(doc)
        bump_kb_version()
    return doc


def activate_version(db: Session, doc_id: int,
                     tenant_id: int | None = None) -> Document:
    """把指定版本设为当前生效版本，其余版本自动置为已被替代"""
    repo = DocumentRepository(db)
    doc = repo.get(doc_id, tenant_id)
    if not doc:
        raise NotFoundError("文档不存在")
    if not doc.policy_key:
        raise BadRequestError("普通文档没有版本概念，无需切换版本")

    scope = tenant_id if tenant_id is not None else doc.tenant_id
    family = repo.list_by_policy(doc.policy_key, scope)
    now = datetime.now()
    changed: list[tuple[Document, str]] = []
    for item in family:
        before_from, before_to = item.effective_from, item.effective_to
        before_status = item.lifecycle_status
        if item.id == doc.id:
            item.lifecycle_status = "active"
            if item.effective_from is None or item.effective_from > now:
                item.effective_from = now
            item.effective_to = None
        else:
            item.lifecycle_status = "superseded"
            if item.effective_to is None:
                item.effective_to = now
        if (before_from, before_to, before_status) != (
            item.effective_from, item.effective_to, item.lifecycle_status
        ):
            path = _resolve_source_path(item)
            if not path:
                raise BadRequestError(
                    f"版本 v{item.version} 原始文件不存在，无法同步检索索引"
                )
            changed.append((item, path))

    repo.save_all(family)
    for item, path in changed:
        _reindex_document(db, item, scope, path)
    repo.save_all([item for item, _ in changed] or family)
    bump_kb_version()
    return doc


def delete_document(db: Session, doc_id: int, tenant_id: int | None = None) -> None:
    """删除文档（元数据 + Milvus 向量）；生效中的政策版本需先切换"""
    repo = DocumentRepository(db)
    doc = repo.get(doc_id, tenant_id)
    if not doc:
        raise NotFoundError("文档不存在")

    scope = tenant_id if tenant_id is not None else doc.tenant_id
    if doc.policy_key and doc.lifecycle_status == "active":
        family = repo.list_by_policy(doc.policy_key, scope)
        if len(family) > 1:
            raise BadRequestError("当前版本正在生效，请先激活其他版本后再删除")

    # 先删 Milvus 向量（Milvus 不可用时仍要能删元数据），限定文档所属租户
    try:
        vector_store.delete_by_doc_id(doc_id, scope)
    except Exception:
        pass

    repo.delete(doc)
    bump_kb_version()
