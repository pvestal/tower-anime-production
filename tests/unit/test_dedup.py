"""Unit tests for packages.lora_training.dedup — hash-based perceptual dedup."""

import pytest

from packages.lora_training.dedup import (
    build_hash_index,
    invalidate_cache,
    is_duplicate,
    register_hash,
    _hash_caches,
)


@pytest.mark.unit
class TestDedup:

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        """Redirect BASE_PATH, mock perceptual_hash, and clear caches between tests."""
        monkeypatch.setattr("packages.lora_training.dedup.BASE_PATH", tmp_path)
        self.base = tmp_path

        # Deterministic mock: hash is derived from the filename stem
        self._hash_counter = 0
        self._hash_map: dict[str, str] = {}

        def _mock_hash(image_path, hash_size=8):
            name = str(image_path)
            if name not in self._hash_map:
                self._hash_map[name] = f"abcd{self._hash_counter:04x}"
                self._hash_counter += 1
            return self._hash_map[name]

        monkeypatch.setattr("packages.lora_training.dedup.perceptual_hash", _mock_hash)

        # Clear the module-level cache before each test
        _hash_caches.clear()

    def _create_image(self, slug: str, filename: str) -> None:
        """Create a tiny placeholder file in the character's images dir."""
        images_dir = self.base / slug / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        (images_dir / filename).write_bytes(b"\x89PNG_fake")

    # --- Tests ---

    def test_build_hash_index_returns_set_of_hashes(self):
        self._create_image("luigi", "gen_001.png")
        self._create_image("luigi", "gen_002.png")

        index = build_hash_index("luigi")
        assert isinstance(index, set)
        assert len(index) == 2

    def test_is_duplicate_returns_true_for_matching_hash(self):
        self._create_image("luigi", "gen_001.png")
        # Build index so the hash for gen_001 is recorded
        build_hash_index("luigi")

        # is_duplicate should return True for the same file (same hash)
        dup_path = self.base / "luigi" / "images" / "gen_001.png"
        assert is_duplicate(dup_path, "luigi") is True

    def test_is_duplicate_returns_false_for_new_hash(self):
        self._create_image("luigi", "gen_001.png")
        build_hash_index("luigi")

        # A different file path produces a different hash via our mock
        new_file = self.base / "incoming" / "new_image.png"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_bytes(b"\x89PNG_fake2")

        assert is_duplicate(new_file, "luigi") is False

    def test_invalidate_cache_clears_cache(self):
        self._create_image("luigi", "gen_001.png")
        build_hash_index("luigi")
        assert "luigi" in _hash_caches

        invalidate_cache("luigi")
        assert "luigi" not in _hash_caches

        # Clearing all
        self._create_image("bowser", "gen_001.png")
        build_hash_index("bowser")
        assert "bowser" in _hash_caches

        invalidate_cache()  # None clears everything
        assert len(_hash_caches) == 0
