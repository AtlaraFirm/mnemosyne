from mnemosyne.services.embed import _embed, _qdrant
from mnemosyne.services.vault import read_note
from mnemosyne.config import get_settings
from pathlib import Path

def find_related(path: str, limit: int = 5, threshold: float = 0.75) -> list[dict]:
    settings = get_settings()
    abs_path = Path(settings.vault_path) / path
    note = read_note(abs_path)
    query_vector = _embed(note.title + " " + note.body[:500])
    client = _qdrant()
    hits = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=limit + 10,
        with_payload=True,
    )
    existing_links = {l.lower() for l in note.wikilinks}
    results = []
    for hit in hits:
        if hit.score < threshold:
            continue
        title = hit.payload.get("note_title", "")
        hit_path = hit.payload.get("note_path", "")
        if hit_path == path:
            continue
        if title.lower() in existing_links:
            continue
        results.append({
            "path": hit_path,
            "title": title,
            "heading": hit.payload.get("heading", ""),
            "score": round(hit.score, 3),
        })
        if len(results) >= limit:
            break
    return results
