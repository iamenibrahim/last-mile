"""Search the cached FEMA / eCFR / SBA / SAMHSA documents for exact sentences.

Azure AI Search ranks when it is configured; a local BM25 ranker runs
otherwise. Either way the engine only ranks. Every hit is re-located in its
hash-verified source document before it is returned, and a hit that cannot be
found verbatim is dropped, so a search result is always a real quote with its
character offsets and source URL - never a summary and never generated text.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass

import httpx

from . import sources

INDEX_NAME = "lastmile-source-quotes"
API_VERSION = "2024-07-01"
TIMEOUT = 10.0
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"(])")
_WORD = re.compile(r"[a-z0-9']{3,}")
_STOP = {"the", "and", "for", "you", "your", "are", "with", "that", "this", "can", "may",
         "not", "from", "have", "has", "will", "who", "what", "how", "any", "all", "our"}


@dataclass(frozen=True)
class Passage:
    id: str
    doc_id: str
    start: int
    end: int
    text: str


def passages() -> list[Passage]:
    """Every sentence of every verified source document, with its offsets."""
    out: list[Passage] = []
    for doc in sources.corpus().values():
        cursor = 0
        for sentence in _SENTENCE_END.split(doc.text):
            start = doc.text.find(sentence, cursor)
            cursor = start + len(sentence)
            if len(sentence) >= 25:
                out.append(Passage(f"{doc.id}-{start}", doc.id, start, cursor, sentence))
    return out


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def _local_rank(query: str, top: int) -> list[Passage]:
    """Offline fallback: BM25 over sentences. Azure AI Search does this better."""
    wanted = _words(query)
    if not wanted:
        return []
    corpus = [(passage, _WORD.findall(passage.text.lower())) for passage in passages()]
    frequency: dict[str, int] = {}
    for _, words in corpus:
        for word in set(words) & wanted:
            frequency[word] = frequency.get(word, 0) + 1
    total = len(corpus)
    average = sum(len(words) for _, words in corpus) / max(1, total)
    scored = []
    for passage, words in corpus:
        score = 0.0
        for word in wanted:
            tf = words.count(word)
            if tf:
                idf = math.log(1 + (total - frequency[word] + 0.5) / (frequency[word] + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(words) / average))
        if score:
            scored.append((score, passage))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [passage for _, passage in scored[:top]]


class AzureQuoteIndex:
    """Azure AI Search index over the source sentences, created and filled on first use."""

    def __init__(self, endpoint: str, key: str) -> None:
        self._base = endpoint.rstrip("/")
        self._headers = {"api-key": key, "Content-Type": "application/json"}
        self._synced = False

    def _url(self, path: str) -> str:
        return f"{self._base}{path}?api-version={API_VERSION}"

    def _sync(self) -> None:
        if self._synced:
            return
        docs = passages()
        index = {
            "name": INDEX_NAME,
            "fields": [
                {"name": "id", "type": "Edm.String", "key": True},
                {"name": "doc_id", "type": "Edm.String", "filterable": True},
                {"name": "text", "type": "Edm.String", "searchable": True, "analyzer": "en.microsoft"},
                {"name": "start", "type": "Edm.Int32"},
                {"name": "end", "type": "Edm.Int32"},
            ],
        }
        httpx.put(self._url(f"/indexes/{INDEX_NAME}"), headers=self._headers, json=index,
                  timeout=TIMEOUT).raise_for_status()
        count = httpx.get(self._url(f"/indexes/{INDEX_NAME}/docs/$count"), headers=self._headers,
                          timeout=TIMEOUT)
        if count.status_code != 200 or int(count.text.strip().lstrip("﻿")) != len(docs):
            for i in range(0, len(docs), 500):
                batch = [
                    {"@search.action": "mergeOrUpload", "id": p.id, "doc_id": p.doc_id,
                     "text": p.text, "start": p.start, "end": p.end}
                    for p in docs[i : i + 500]
                ]
                httpx.post(self._url(f"/indexes/{INDEX_NAME}/docs/index"), headers=self._headers,
                           json={"value": batch}, timeout=TIMEOUT).raise_for_status()
        self._synced = True

    def search(self, query: str, top: int) -> list[Passage]:
        self._sync()
        r = httpx.post(self._url(f"/indexes/{INDEX_NAME}/docs/search"), headers=self._headers,
                       json={"search": query, "top": top, "select": "id,doc_id,text,start,end"},
                       timeout=TIMEOUT)
        r.raise_for_status()
        return [Passage(v["id"], v["doc_id"], v["start"], v["end"], v["text"]) for v in r.json()["value"]]


_INDEX: AzureQuoteIndex | None = None


def _azure_index() -> AzureQuoteIndex | None:
    global _INDEX
    endpoint, key = os.environ.get("AZURE_SEARCH_ENDPOINT"), os.environ.get("AZURE_SEARCH_KEY")
    if not (endpoint and key) or os.environ.get("LAST_MILE_OFFLINE") == "1":
        return None
    if _INDEX is None:
        _INDEX = AzureQuoteIndex(endpoint, key)
    return _INDEX


def search(query: str, top: int = 5) -> dict:
    top = max(1, min(top, 10))
    engine = "local-bm25"
    hits: list[Passage] = []
    index = _azure_index()
    if index is not None:
        try:
            hits = index.search(query, top)
            engine = "azure-ai-search"
        except Exception:
            hits = []
    if engine != "azure-ai-search":
        hits = _local_rank(query, top)

    results, dropped = [], 0
    for hit in hits:
        citation = sources.locate(hit.doc_id, hit.text)
        if citation is None:
            dropped += 1  # not verbatim in the verified source: never shown
            continue
        results.append(citation.to_dict())
    return {
        "query": query,
        "engine": engine,
        "results": results,
        "dropped_unverifiable": dropped,
        "boundary": "Exact sentences from the cited pages. They do not decide eligibility.",
    }
