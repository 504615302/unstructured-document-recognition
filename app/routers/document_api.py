from fastapi import APIRouter, HTTPException

from app.models.data_models import (
    DocumentProcessData,
    UnstructuredDocumentRequest,
    UnstructuredDocumentResponse,
)
from app.settings import logger
from app.utils.document_processor import (
    DocumentProcessingError,
    DocumentProcessor,
    UnconfiguredBusinessCodeError,
    UnsupportedBusinessCodeError,
)


router = APIRouter(prefix="/documents", tags=["非结构化文档处理"])


@router.post("/process", response_model=UnstructuredDocumentResponse)
async def process_unstructured_document(request: UnstructuredDocumentRequest):
    """使用业务专属提示词识别具体类型，再执行该类型专属的固定结构取数。"""
    try:
        document_type, type_config, extracted = await DocumentProcessor().process(
            request.business_code, request.data
        )
        return UnstructuredDocumentResponse(
            success=True,
            data=DocumentProcessData(
                business_code=request.business_code.strip().lower(),
                document_type=document_type,
                type_name=type_config.name,
                extracted_data=extracted,
            ),
        )
    except (UnsupportedBusinessCodeError, UnconfiguredBusinessCodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocumentProcessingError as exc:
        logger.error(f"文档处理失败: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("文档处理发生未预期异常")
        raise HTTPException(status_code=500, detail="文档处理失败") from exc
