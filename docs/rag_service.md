# RAG Service

## Scope

This phase implements an independent `rag_service` with:

- document ingestion
- text chunking
- embedding-provider boundary
- FAISS vector index
- lightweight rerank placeholder
- minimal FastAPI API
- local orchestrator adapter

It does not implement web crawling, production hybrid retrieval, or large-model reasoning.

## Directory Overview

- `services/rag_service/main.py`: FastAPI app entrypoint
- `services/rag_service/service.py`: service-layer orchestration
- `services/rag_service/ingest.py`: document ingest flow
- `services/rag_service/retriever.py`: retrieval flow
- `services/rag_service/reranker.py`: lightweight rerank placeholder
- `services/rag_service/vectorstore.py`: FAISS wrapper
- `services/rag_service/storage/document_store.py`: JSON metadata store
- `services/rag_service/chunking/text_chunker.py`: overlapping chunk splitter
- `services/rag_service/embeddings/`: embedding provider boundary and implementations
- `services/rag_service/client.py`: orchestrator-facing local adapter

## Runtime Flow

### Ingest

1. `POST /documents/ingest`
2. Service chunks the text
3. Embedding provider creates chunk vectors
4. FAISS index stores vectors
5. Document metadata store persists chunk/source mapping

### Query

1. `POST /query`
2. Service builds a query embedding
3. FAISS returns candidate chunks
4. Reranker applies lightweight lexical/context boosts
5. Response returns traceable chunk text, source, score, and metadata

## Orchestrator Integration

The orchestrator now uses `LocalRAGServiceClient` in `run_rag`.
That means:

- `run_rag` no longer depends on the mock service
- workflow state can carry real retrieved `sources`, `summary`, and `results`
- report/confidence still remain placeholder-backed, but now consume real retrieval output

## Environment Variables

- `RAG_SERVICE_NAME`
- `VECTORSTORE_DIR`
- `DEFAULT_TOP_K`
- `USE_MOCK_EMBEDDING`
- `EMBEDDING_MODEL_NAME`
- `RAG_EMBEDDING_DIMENSION`
- `RAG_CHUNK_SIZE`
- `RAG_CHUNK_OVERLAP`
- `RAG_SEARCH_CANDIDATE_MULTIPLIER`

## Validation

```bash
python -m pytest tests/test_chunker.py tests/test_vectorstore.py tests/test_rag_api.py
python -m pytest tests/test_orchestrator_flow.py
```
