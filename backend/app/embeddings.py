from typing import List
import vertexai
from vertexai.language_models import TextEmbeddingModel
from .config import PROJECT_ID, VERTEX_LOCATION

_MODEL_NAME = "text-embedding-004"

def embed_query(text: str) -> List[float]:
    vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
    model = TextEmbeddingModel.from_pretrained(_MODEL_NAME)
    emb = model.get_embeddings([text])[0].values
    return list(emb)
