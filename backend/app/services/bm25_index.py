import math
from collections import Counter

from app.repositories.memories import MemoryRecord
from app.services.local_models import tokenize


class BM25Index:
    def __init__(self, memories: list[MemoryRecord]) -> None:
        self.memories = memories
        self.documents = [memory.tokens or tokenize(memory.content) for memory in memories]
        self.doc_freq: Counter[str] = Counter()
        for document in self.documents:
            for token in set(document):
                self.doc_freq[token] += 1
        self.avg_len = (
            sum(len(document) for document in self.documents) / len(self.documents)
            if self.documents
            else 0.0
        )

    def search(self, query: str, top_k: int) -> list[tuple[MemoryRecord, float]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scored: list[tuple[MemoryRecord, float]] = []
        for memory, document in zip(self.memories, self.documents, strict=False):
            score = self._score_document(query_tokens, document)
            if score > 0:
                scored.append((memory, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def _score_document(self, query_tokens: list[str], document: list[str]) -> float:
        if not document:
            return 0.0
        counts = Counter(document)
        score = 0.0
        k1 = 1.5
        b = 0.75
        total_docs = max(1, len(self.documents))
        for token in query_tokens:
            frequency = counts[token]
            if frequency <= 0:
                continue
            doc_frequency = self.doc_freq[token]
            idf = math.log(1 + (total_docs - doc_frequency + 0.5) / (doc_frequency + 0.5))
            denominator = frequency + k1 * (1 - b + b * len(document) / max(self.avg_len, 1.0))
            score += idf * (frequency * (k1 + 1)) / denominator
        return score
