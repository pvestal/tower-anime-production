"""
Unit tests for Character Consistency Engine
Tests the core algorithms that ensure characters remain visually consistent
"""

import sys
import time
from unittest.mock import patch

import numpy as np
import pytest

# Import the module we're testing
sys.path.insert(0, '/opt/tower-anime-production')
from api.character_consistency_mock import CharacterConsistencyEngine


class TestCharacterConsistencyEngine:


    """Test suite for character consistency functionality"""
    """Test suite for character consistency functionality"""

    @pytest.fixture
    def engine(self):

        """Provide a fresh engine instance for each test"""
        return CharacterConsistencyEngine()

    @pytest.fixture
    def mock_image(self):

        """Create a mock image array"""
        return np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)

    @pytest.fixture
    def sample_embedding(self):

        """Generate a sample embedding vector"""
        np.random.seed(42)  # For reproducibility
        return np.random.randn(512).tolist()

    @pytest.fixture
    def sample_character(self):

        """Sample character data for testing"""
        return {
            "id": 1,
            "name": "Kai Nakamura",
            "reference_image": "path/to/kai_reference.png",
            "embedding_data": {
                "face_embedding": [0.1] * 512,
                "version": "1.0"
            },
            "style_template": {
                "art_style": "anime",
                "sub_style": "shounen",
                "line_weight": 2.0,
                "shading_type": "cel"
            },
            "color_palette": {
                "hair_color": [30, 30, 35],
                "eye_color": [100, 150, 200],
                "skin_tone": [250, 220, 190]
            },
            "consistency_threshold": 0.85
        }

    def test_engine_initialization(self, engine):

        """Test that engine initializes with correct defaults"""
        assert engine is not None
        assert hasattr(engine, 'reference_embeddings')
        assert hasattr(engine, 'style_templates')
        assert hasattr(engine, 'pose_library')
        assert isinstance(engine.reference_embeddings, dict)
        assert isinstance(engine.style_templates, dict)
        assert isinstance(engine.pose_library, dict)

    def test_embedding_generation_shape(self, engine, mock_image):

        """Test that embeddings have correct shape and range"""
        with patch.object(engine, '_extract_face_features') as mock_extract:
            mock_extract.return_value = np.random.randn(512)

            embedding = engine.generate_embedding(mock_image)

            assert embedding is not None
            assert len(embedding) == 512
            assert all(-10 <= val <= 10 for val in embedding)  # Reasonable range

    def test_consistency_score_identical_embeddings(self, engine, sample_embedding):

        """Test that identical embeddings return perfect score"""
        score = engine.calculate_consistency_score(
            sample_embedding,
            sample_embedding
        )

        assert score == 1.0

    def test_consistency_score_different_embeddings(self, engine):

        """Test that different embeddings return lower score"""
        embedding1 = np.random.randn(512).tolist()
        embedding2 = np.random.randn(512).tolist()

        score = engine.calculate_consistency_score(embedding1, embedding2)

        assert 0 <= score <= 1.0
        assert score < 1.0  # Should not be perfect match

    def test_consistency_score_threshold_logic(self, engine):

        """Test consistency threshold evaluation"""
        # Create embeddings with known similarity
        np.random.seed(42)  # Fixed seed for reproducibility
        base = np.random.randn(512)
        similar = base + np.random.randn(512) * 0.1  # Small variation
        different = np.random.randn(512)  # Completely different

        high_score = engine.calculate_consistency_score(
            base.tolist(),
            similar.tolist()
        )
        low_score = engine.calculate_consistency_score(
            base.tolist(),
            different.tolist()
        )

        assert high_score > low_score
        assert high_score > 0.7  # Should be relatively high
        # More forgiving threshold for random embeddings
        assert low_score < 0.6   # Should be relatively low

    def test_style_template_extraction(self, engine, mock_image):

        """Test style template extraction from image"""
        with patch.object(engine, '_analyze_art_style') as mock_analyze:
            mock_analyze.return_value = {
                "line_weight": 2.0,
                "color_saturation": 0.8,
                "shading_type": "cel",
                "detail_level": "medium"
            }

            style = engine.extract_style_template(mock_image)

            assert "line_weight" in style
            assert "color_saturation" in style
            assert "shading_type" in style
            assert isinstance(style["line_weight"], (int, float))
            assert 0 <= style["color_saturation"] <= 1

    def test_color_palette_extraction(self, engine, mock_image):

        """Test color palette extraction"""
        with patch.object(engine, '_extract_dominant_colors') as mock_colors:
            mock_colors.return_value = {
                "hair_color": [30, 30, 35],
                "eye_color": [100, 150, 200],
                "skin_tone": [250, 220, 190],
                "clothing_primary": [50, 50, 150]
            }

            palette = engine.extract_color_palette(mock_image)

            assert "hair_color" in palette
            assert "eye_color" in palette
            assert "skin_tone" in palette

            # Check color value ranges
            for color_name, rgb in palette.items():
                assert len(rgb) == 3
                assert all(0 <= val <= 255 for val in rgb)

    def test_ensure_consistency_modifies_params(self, engine, sample_character):

        """Test that ensure_consistency modifies generation parameters"""
        generation_params = {
            "prompt": "anime character standing",
            "model": "AOM3A1B",
            "steps": 25,
            "cfg_scale": 8.0
        }

        # Store character reference
        engine.reference_embeddings[sample_character["id"]] = sample_character["embedding_data"]
        engine.style_templates[sample_character["id"]] = sample_character["style_template"]

        modified_params = engine.ensure_consistency(
            sample_character["id"],
            generation_params
        )

        assert modified_params != generation_params
        assert "consistency_weight" in modified_params
        assert "reference_embedding" in modified_params
        assert "style_preservation" in modified_params

    def test_pose_library_management(self, engine):

        """Test adding and retrieving poses from library"""
        character_id = 1
        pose_name = "standing_neutral"
        pose_data = {
            "keypoints": [[100, 100], [150, 120], [200, 140]],
            "confidence": 0.95
        }

        # Add pose to library
        engine.add_pose_to_library(character_id, pose_name, pose_data)

        # Retrieve pose
        retrieved = engine.get_pose_from_library(character_id, pose_name)

        assert retrieved == pose_data
        assert character_id in engine.pose_library
        assert pose_name in engine.pose_library[character_id]

    @pytest.mark.parametrize("threshold,score,expected", [
        (0.9, 0.95, True),   # Score exceeds high threshold
        (0.9, 0.85, False),  # Score below high threshold
        (0.7, 0.75, True),   # Score exceeds low threshold
        (0.7, 0.65, False),  # Score below low threshold
    ])

    def test_consistency_threshold_evaluation(self, engine, threshold, score, expected):

        """Test threshold-based consistency validation"""
        result = engine.evaluate_consistency(score, threshold)
        assert result == expected

    def test_batch_consistency_check(self, engine, sample_character):

        """Test checking consistency across multiple images"""
        # Create mock embeddings for multiple generated images
        base_embedding = np.random.randn(512)
        variations = [
            base_embedding + np.random.randn(512) * 0.05,  # Very similar
            base_embedding + np.random.randn(512) * 0.1,   # Similar
            base_embedding + np.random.randn(512) * 0.2,   # Somewhat similar
        ]

        scores = engine.batch_consistency_check(
            base_embedding.tolist(),
            [v.tolist() for v in variations]
        )

        assert len(scores) == 3
        assert all(0 <= s <= 1 for s in scores)
        # Scores should decrease with increasing variation
        assert scores[0] > scores[1] > scores[2]

    def test_character_evolution_tracking(self, engine):

        """Test tracking character changes over time"""
        character_id = 1

        # Add initial version
        engine.add_character_version(character_id, "young", {
            "embedding": [0.1] * 512,
            "age": 15
        })

        # Add evolved version
        engine.add_character_version(character_id, "adult", {
            "embedding": [0.2] * 512,
            "age": 25
        })

        # Retrieve versions
        versions = engine.get_character_versions(character_id)

        assert len(versions) == 2
        assert "young" in versions
        assert "adult" in versions
        assert versions["young"]["age"] == 15
        assert versions["adult"]["age"] == 25

    def test_consistency_degradation_over_generations(self, engine):

        """Test that consistency degrades with repeated generations"""
        initial_embedding = np.random.randn(512)
        current = initial_embedding.copy()
        scores = []

        # Simulate multiple generations with slight drift
        for generation in range(5):
            drift = np.random.randn(512) * 0.05
            current = current + drift
            score = engine.calculate_consistency_score(
                initial_embedding.tolist(),
                current.tolist()
            )
            scores.append(score)

        # Consistency should generally decrease
        assert scores[0] > scores[-1]
        # But should still be relatively high for small drift
        assert all(s > 0.7 for s in scores)

    def test_apply_consistency_to_workflow(self, engine, sample_character):

        """Test applying consistency parameters to ComfyUI workflow"""
        workflow = {
            "nodes": {
                "1": {"type": "checkpoint_loader"},
                "2": {"type": "clip_text_encoder"},
                "3": {"type": "sampler"}
            }
        }

        engine.reference_embeddings[sample_character["id"]] = sample_character["embedding_data"]

        modified_workflow = engine.apply_consistency_to_workflow(
            workflow,
            sample_character["id"]
        )

        assert modified_workflow != workflow
        assert "consistency_node" in str(modified_workflow)

    def test_error_handling_invalid_embedding(self, engine):

        """Test handling of invalid embeddings"""
        with pytest.raises(ValueError):
            engine.calculate_consistency_score(
                [0.1] * 512,  # Valid
                [0.1] * 256   # Invalid size
            )

        with pytest.raises(ValueError):
            engine.calculate_consistency_score(
                None,
                [0.1] * 512
            )

    def test_persistence_save_and_load(self, engine, tmp_path, sample_character):

        """Test saving and loading engine state"""
        # Add test data
        engine.reference_embeddings[1] = sample_character["embedding_data"]
        engine.style_templates[1] = sample_character["style_template"]

        # Save state
        save_path = tmp_path / "engine_state.json"
        engine.save_state(save_path)

        # Create new engine and load state
        new_engine = CharacterConsistencyEngine()
        new_engine.load_state(save_path)

        assert new_engine.reference_embeddings == engine.reference_embeddings
        assert new_engine.style_templates == engine.style_templates

    @pytest.mark.performance
    def test_embedding_generation_performance(self, engine, mock_image):

        """Test that embedding generation is fast enough"""

        with patch.object(engine, '_extract_face_features') as mock_extract:
            mock_extract.return_value = np.random.randn(512)

            start = time.time()
            for _ in range(100):
                engine.generate_embedding(mock_image)
            duration = time.time() - start

            # Should process 100 images in less than 1 second
            assert duration < 1.0
            print(f"Processed 100 embeddings in {duration:.3f}s")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
