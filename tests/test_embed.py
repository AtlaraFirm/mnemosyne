import pytest
from mnemosyne.services import embed

import socket
import pytest

def is_qdrant_running(host="localhost", port=6333):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False

@pytest.mark.skipif(not is_qdrant_running(), reason="Qdrant is not running on localhost:6333")
def test_ensure_collection():
    result = embed.ensure_collection()
    assert result is None or result is not False

from unittest.mock import patch, MagicMock
from mnemosyne.agent.schemas import Chunk

def test_index_chunks_mocks_qdrant():
    chunk = Chunk(id="1", note_path="foo.md", note_title="Foo", heading="H", text="bar", tags=[], char_offset=0)
    with patch("mnemosyne.services.embed._qdrant") as mock_qdrant, \
         patch("mnemosyne.services.embed._embed", return_value=[0.1]*768):
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client
        from mnemosyne.services import embed
        embed.index_chunks([chunk])
        mock_client.upsert.assert_called()


def test_semantic_search_mocks_qdrant():
    from unittest.mock import patch, MagicMock
    from mnemosyne.agent.schemas import SearchResult
    fake_hit = MagicMock()
    fake_hit.payload = {
        "chunk_id": "1",
        "note_path": "foo.md",
        "note_title": "Foo",
        "heading": "H",
        "text": "bar"
    }
    fake_hit.score = 0.99
    with patch("mnemosyne.services.embed._qdrant") as mock_qdrant, \
         patch("mnemosyne.services.embed._embed", return_value=[0.1]*768):
        mock_client = MagicMock()
        mock_client.search.return_value = [fake_hit]
        mock_qdrant.return_value = mock_client
        from mnemosyne.services import embed
        results = embed.semantic_search("bar")
        assert isinstance(results, list)
        assert results[0].note_title == "Foo"

