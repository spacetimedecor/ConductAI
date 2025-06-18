# conductdoc/retriever.py
"""🧠🔍 This module contains the Retriever, a dynamic, multi-source knowledge base."""
import logging
from typing import List, Sequence

from bs4 import BeautifulSoup
from bs4.element import Tag, PageElement
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from .models import CodeElement

class Retriever:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        logging.info("🧠 Initializing a DYNAMIC RAG Retriever...")
        logging.info(f"  -> Loading sentence-transformer model '{model_name}'...")
        self.model = SentenceTransformer(model_name)
        self.chunks: List[str] = []
        self.embeddings: np.ndarray = np.array([])
        self.index: faiss.Index | None = None
        logging.info("✅ Retriever initialized. Ready to build knowledge base.")

    def build_initial_indexes(self, docs_html: str, code_elements: List[CodeElement]):
        logging.info("  -> Building initial knowledge base from docs and code...")
        doc_chunks = self._chunk_html(docs_html)
        code_chunks = self._chunk_code(code_elements)
        initial_chunks = doc_chunks + code_chunks
        if not initial_chunks:
            logging.warning("⚠️ No initial chunks found to build index.")
            return
        self.add_chunks(initial_chunks)
        logging.info(f"  -> Initial knowledge base built with {len(initial_chunks)} chunks.")

    def add_chunks(self, new_chunks: List[str]):
        if not new_chunks: return
        logging.info(f"  -> Dynamically adding {len(new_chunks)} new chunks to the knowledge base...")
        new_embeddings = self.model.encode(new_chunks, show_progress_bar=False)
        if self.index is None:
            dimension = new_embeddings.shape[1]
            self.index = faiss.IndexFlatL2(dimension)
            self.embeddings = new_embeddings
            self.chunks = new_chunks
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings])
            self.chunks.extend(new_chunks)
        self.index.add(x=new_embeddings.astype('float32')) # type: ignore

    def _chunk_html(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, 'html.parser')
        chunks = []
        all_sections: Sequence[PageElement] = soup.find_all('section')
        for section in all_sections:
            if not isinstance(section, Tag): continue
            source = section.get('data-source', 'unknown_source')
            content_tags = section.find_all(['h1', 'h2', 'h3', 'p', 'li', 'pre'])
            for tag in content_tags:
                text = tag.get_text(separator=' ', strip=True)
                if len(text.split()) > 5:
                    chunks.append(f"From documentation file '{source}': {text}")
        return chunks

    def _chunk_code(self, elements: List[CodeElement]) -> List[str]:
        chunks = []
        for el in elements:
            chunk = f'Code from file: {el.filepath}\nType: {el.type}\nName: {el.name}\nDocstring: "{el.docstring}"\nSource Code:\n```python\n{el.source_code}\n```'
            chunks.append(chunk.strip())
        return chunks

    def retrieve(self, query: str, k: int = 5) -> List[str]:
        if self.index is None or not self.chunks: return []
        logging.info(f"  -> Searching for top {k} chunks for query: '{query}'")
        query_embedding = self.model.encode([query])
        if query_embedding.ndim == 1:
            query_embedding = np.expand_dims(query_embedding, axis=0)
        distances, indices = self.index.search(x=query_embedding.astype('float32'), k=k) # type: ignore
        valid_indices = [i for i in indices[0] if i != -1]
        return [self.chunks[i] for i in valid_indices]