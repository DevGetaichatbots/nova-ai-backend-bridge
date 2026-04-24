import json
import logging
from src.database import create_vector_table, insert_embeddings, similarity_search, fetch_all_chunks
from src.embeddings import generate_embeddings, generate_single_embedding
from src.pdf_processor import process_pdf_binary
from src.config import settings

logger = logging.getLogger(__name__)


class VectorStoreManager:
    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSION
    
    def create_store_from_pdf(self, session_id: str, file_name: str, pdf_bytes: bytes, table_name: str | None = None, progress_callback=None) -> dict:
        def _progress(step, detail, pct):
            if progress_callback:
                progress_callback(step, detail, pct)
        
        if table_name:
            safe_name = table_name.replace('-', '_').replace(' ', '_')[:63]
        else:
            safe_name = f"vs_{session_id}_{file_name.replace('.', '_').replace(' ', '_')}"[:63]
        
        _progress("table", f"Creating database table...", 5)
        logger.info(f"  Creating vector table: {safe_name}")
        safe_table_name = create_vector_table(safe_name, self.dimension)
        
        _progress("ocr", f"Running OCR on {file_name}...", 10)
        logger.info(f"  Extracting text from PDF ({len(pdf_bytes)} bytes)...")
        chunks = process_pdf_binary(pdf_bytes, filename=file_name)
        
        if not chunks:
            logger.warning(f"  No content extracted from PDF")
            _progress("error", "No content found in PDF", 0)
            return {
                "status": "error",
                "message": "No text content found in PDF",
                "table_name": safe_table_name
            }
        
        _progress("chunking", f"Extracted {len(chunks)} chunks from {file_name}", 40)
        logger.info(f"  Extracted {len(chunks)} chunks, generating embeddings...")
        texts = [chunk["content"] for chunk in chunks]
        
        _progress("embedding", f"Generating embeddings for {len(chunks)} chunks...", 50)
        embeddings = generate_embeddings(texts, progress_callback=lambda done, total: _progress(
            "embedding", f"Embedding batch {done}/{total}...", 50 + int((done / max(total, 1)) * 35)
        ))
        
        documents = []
        for i, chunk in enumerate(chunks):
            documents.append({
                "content": chunk["content"],
                "embedding": embeddings[i],
                "metadata": json.dumps(chunk["metadata"])
            })
        
        _progress("storing", f"Storing {len(documents)} embeddings in database...", 90)
        logger.info(f"  Storing {len(documents)} embeddings in database...")
        insert_embeddings(safe_table_name, documents)
        
        _progress("complete", f"Done — {len(chunks)} chunks stored", 100)
        logger.info(f"  Vector store ready: {safe_table_name}")
        return {
            "status": "success",
            "table_name": safe_table_name,
            "chunks_processed": len(chunks),
            "message": f"Successfully stored {len(chunks)} chunks in vector store"
        }
    
    def create_store_from_chunks(self, session_id: str, file_name: str, chunks: list, table_name: str | None = None, progress_callback=None) -> dict:
        def _progress(step, detail, pct):
            if progress_callback:
                progress_callback(step, detail, pct)

        if table_name:
            safe_name = table_name.replace('-', '_').replace(' ', '_')[:63]
        else:
            safe_name = f"vs_{session_id}_{file_name.replace('.', '_').replace(' ', '_')}"[:63]

        _progress("table", f"Creating database table...", 5)
        logger.info(f"  Creating vector table: {safe_name}")
        safe_table_name = create_vector_table(safe_name, self.dimension)

        if not chunks:
            logger.warning(f"  No content in chunks")
            _progress("error", "No content found", 0)
            return {"status": "error", "message": "No content found", "table_name": safe_table_name}

        _progress("chunking", f"Parsed {len(chunks)} chunks from {file_name}", 40)
        logger.info(f"  CSV direct store: {len(chunks)} chunks (skipping embeddings — fetch-all retrieval)")

        zero_embedding = [0.0] * self.dimension

        documents = []
        for chunk in chunks:
            documents.append({
                "content": chunk["content"],
                "embedding": zero_embedding,
                "metadata": json.dumps(chunk["metadata"])
            })

        _progress("storing", f"Storing {len(documents)} chunks in database...", 70)
        logger.info(f"  Storing {len(documents)} chunks in database...")
        insert_embeddings(safe_table_name, documents)

        _progress("complete", f"Done — {len(chunks)} chunks stored", 100)
        logger.info(f"  Vector store ready: {safe_name}")
        return {
            "status": "success",
            "table_name": safe_table_name,
            "chunks_processed": len(chunks),
            "message": f"Successfully stored {len(chunks)} chunks in vector store"
        }

    def search(self, table_name: str, query: str, top_k: int = 10) -> list[dict]:
        query_embedding = generate_single_embedding(query)
        results = similarity_search(table_name, query_embedding, top_k)
        
        return [
            {
                "content": r["content"],
                "similarity": float(r["similarity"]),
                "metadata": r["metadata"] if r["metadata"] else {}
            }
            for r in results
        ]
    
    def search_multiple_stores(self, table_names: list[str], query: str, top_k: int = 10) -> dict:
        query_embedding = generate_single_embedding(query)
        
        all_results = {}
        for table_name in table_names:
            try:
                results = similarity_search(table_name, query_embedding, top_k)
                all_results[table_name] = [
                    {
                        "content": r["content"],
                        "similarity": float(r["similarity"]),
                        "metadata": r["metadata"] if r["metadata"] else {}
                    }
                    for r in results
                ]
            except Exception as e:
                all_results[table_name] = {"error": str(e)}
        
        return all_results
    
    def fetch_all_from_stores(self, table_names: list[str], chunk_type: str = None) -> dict:
        all_results = {}
        for table_name in table_names:
            try:
                results = fetch_all_chunks(table_name, chunk_type=chunk_type)
                type_label = f" (type={chunk_type})" if chunk_type else ""
                all_results[table_name] = results
                logger.info(f"  Fetch from {table_name}: {len(results)} chunks{type_label}")
            except Exception as e:
                logger.error(f"  Full fetch error for {table_name}: {e}")
                all_results[table_name] = {"error": str(e)}
        
        return all_results


vector_store_manager = VectorStoreManager()
