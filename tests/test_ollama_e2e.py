import pytest
from mnemosyne.services import embed
import ollama

@pytest.mark.skipif(not hasattr(ollama, "embed"), reason="Ollama not available")
def test_ollama_embed_e2e():
    # This is a real E2E test hitting the Ollama server
    text = "The quick brown fox jumps over the lazy dog."
    vec = embed._embed(text)
    assert isinstance(vec, list)
    assert all(isinstance(x, float) for x in vec)
    assert len(vec) > 10  # Should be a real embedding, not a stub
