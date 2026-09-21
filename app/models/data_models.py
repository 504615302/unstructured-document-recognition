from typing import Any, Dict, Optional

from pydantic import BaseModel


class UnstructuredDocumentRequest(BaseModel):
    business_code: str
    data: Any


class DocumentProcessData(BaseModel):
    business_code: str
    document_type: str
    type_name: str
    extracted_data: Dict[str, Any]


class UnstructuredDocumentResponse(BaseModel):
    success: bool
    data: Optional[DocumentProcessData] = None
    error: str = ""
