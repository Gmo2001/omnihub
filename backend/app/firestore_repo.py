from typing import Any, Dict, List, Optional
from google.cloud import firestore
from .config import PROJECT_ID, FIRESTORE_DATABASE, COL_DOCS, COL_CHUNKS, COL_CONCEPTS, COL_HEALTH, HEALTH_DOC

def get_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)

def health_check(fs: firestore.Client) -> Dict[str, Any]:
    ref = fs.collection(COL_HEALTH).document(HEALTH_DOC)
    ref.set({"status": "WRITE_OK", "ts": firestore.SERVER_TIMESTAMP}, merge=True)
    snap = ref.get()
    return snap.to_dict() if snap.exists else {}

def list_docs(fs: firestore.Client, limit: int = 3000) -> List[Dict[str, Any]]:
    docs = []
    for s in fs.collection(COL_DOCS).limit(limit).stream():
        d = s.to_dict() or {}
        d.setdefault("id", s.id)
        docs.append(d)
    return docs

def list_concepts(fs: firestore.Client, limit: int = 5000) -> List[Dict[str, Any]]:
    items = []
    for s in fs.collection(COL_CONCEPTS).limit(limit).stream():
        d = s.to_dict() or {}
        d.setdefault("id", s.id)
        items.append(d)
    return items

def get_chunks_by_ids(fs: firestore.Client, chunk_ids: List[str]) -> List[Dict[str, Any]]:
    out = []
    if not chunk_ids:
        return []
    
    col = fs.collection(COL_CHUNKS)
    # Deduplicate
    chunk_ids = list(set(chunk_ids))
    
    # Batch limit usually around 10 here for safe, but FireStore allows more.
    # We will just pass the list. If it's too big, we might need chunking, but for topK=8 it is fine.
    refs = [col.document(cid) for cid in chunk_ids]
    
    for snap in fs.get_all(refs):
        if snap.exists:
            d = snap.to_dict() or {}
            d.setdefault("chunk_id", snap.id)
            out.append(d)
    return out

def get_docs_by_ids(fs: firestore.Client, doc_ids: List[str]) -> List[Dict[str, Any]]:
    out = []
    if not doc_ids:
        return out
        
    doc_ids = list(set(doc_ids))
    col = fs.collection(COL_DOCS)
    refs = [col.document(did) for did in doc_ids]
    for snap in fs.get_all(refs):
        if snap.exists:
            d = snap.to_dict() or {}
            d.setdefault("id", snap.id)
            out.append(d)
    return out

def get_concepts_by_ids(fs: firestore.Client, concept_ids: List[str]) -> List[Dict[str, Any]]:
    out = []
    if not concept_ids:
        return out
        
    concept_ids = list(set(concept_ids))
    col = fs.collection(COL_CONCEPTS)
    refs = [col.document(cid) for cid in concept_ids]
    for snap in fs.get_all(refs):
        if snap.exists:
            d = snap.to_dict() or {}
            d.setdefault("id", snap.id)
            out.append(d)
    return out

def get_chunks_by_doc_id(fs: firestore.Client, doc_id: str) -> List[Dict[str, Any]]:
    docs = []
    # Queries require an index if multiple fields, but here we query by one field usually.
    # chunks where parent_doc_id == doc_id
    query = fs.collection(COL_CHUNKS).where("parent_doc_id", "==", doc_id).limit(200)
    for s in query.stream():
        d = s.to_dict() or {}
        d.setdefault("chunk_id", s.id)
        docs.append(d)
    return docs
