"""Document management routes for the RAG service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from services.rag_service.service import RAGService

router = APIRouter(tags=["documents"])


async def get_rag_service(request: Request) -> RAGService:
    return request.app.state.rag_service


@router.get("/documents", summary="List all ingested documents")
async def list_documents(
    service: RAGService = Depends(get_rag_service),
) -> list[dict]:
    return service.list_documents()


@router.get("/documents/{document_id}", summary="Get a single document")
async def get_document(
    document_id: str,
    service: RAGService = Depends(get_rag_service),
) -> dict:
    doc = service.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document_not_found")
    return doc


@router.delete("/documents/{document_id}", summary="Delete a document")
async def delete_document(
    document_id: str,
    service: RAGService = Depends(get_rag_service),
) -> dict:
    deleted = service.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="document_not_found")
    return {"status": "deleted", "document_id": document_id}
