#!/usr/bin/env python3
"""
Context-Aware QC System for Anime Production
Intelligently validates images based on prompt intent
"""

import cv2
import json
import re
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class ContextAwareQC:
    """Smart QC that validates images based on original prompt intent"""

    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # Intent detection patterns
        self.solo_patterns = [
            r'\b(solo)\b', r'\b(1girl)\b', r'\b(1boy)\b', r'\b(single person)\b',
            r'\b(only one)\b', r'\b(individual)\b', r'\b(portrait)\b'
        ]

        self.multi_patterns = [
            r'\b(\d+girls?)\b', r'\b(\d+boys?)\b', r'\b(\d+people)\b',
            r'\b(group)\b', r'\b(multiple)\b', r'\b(crowd)\b',
            r'\b(together)\b', r'\b(team)\b', r'\b(family)\b'
        ]

    def analyze_prompt_intent(self, prompt_text: str) -> Dict:
        """Determine expected number of people from prompt"""
        prompt_lower = prompt_text.lower()

        # Check for explicit solo intent
        solo_matches = []
        for pattern in self.solo_patterns:
            matches = re.findall(pattern, prompt_lower)
            solo_matches.extend(matches)

        # Check for explicit multi-person intent
        multi_matches = []
        expected_count = 1  # default

        for pattern in self.multi_patterns:
            matches = re.findall(pattern, prompt_lower)
            if matches:
                multi_matches.extend(matches)
                # Extract number if specified (e.g., "3girls" -> 3)
                for match in matches:
                    numbers = re.findall(r'\d+', match)
                    if numbers:
                        expected_count = max(expected_count, int(numbers[0]))

        # Determine intent
        if solo_matches and not multi_matches:
            intent = "SOLO"
            expected_count = 1
        elif multi_matches and not solo_matches:
            intent = "MULTIPLE"
            # expected_count already set above
        elif multi_matches and solo_matches:
            intent = "CONFLICTED"  # Contradictory prompts
            expected_count = 1  # Default to solo for safety
        else:
            intent = "UNCLEAR"
            expected_count = 1  # Default to solo

        return {
            'intent': intent,
            'expected_count': expected_count,
            'solo_indicators': solo_matches,
            'multi_indicators': multi_matches,
            'confidence': self._calculate_intent_confidence(solo_matches, multi_matches)
        }

    def _calculate_intent_confidence(self, solo_matches, multi_matches) -> float:
        """Calculate confidence in intent detection"""
        if solo_matches and not multi_matches:
            return 0.95
        elif multi_matches and not solo_matches:
            return 0.90
        elif solo_matches and multi_matches:
            return 0.30  # Conflicted - low confidence
        else:
            return 0.60  # Unclear but defaulting

    def context_aware_validation(self, image_path: str, original_prompt: str) -> Dict:
        """Validate image against original prompt intent"""
        try:
            # Analyze what the prompt intended
            intent_analysis = self.analyze_prompt_intent(original_prompt)

            # Detect actual people count in image
            img = cv2.imread(image_path)
            if img is None:
                return {'error': f'Could not load image: {image_path}'}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30)
            )

            actual_count = len(faces)
            expected_count = intent_analysis['expected_count']
            intent = intent_analysis['intent']

            # Smart validation based on intent
            validation_result = self._validate_against_intent(
                actual_count, expected_count, intent, intent_analysis['confidence']
            )

            result = {
                'image_path': image_path,
                'original_prompt': original_prompt,
                'intent_analysis': intent_analysis,
                'detected_faces': actual_count,
                'expected_faces': expected_count,
                'validation': validation_result,
                'passes_qc': validation_result['passes'],
                'face_coordinates': [
                    {'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)}
                    for x, y, w, h in faces
                ]
            }

            logger.info(f"Context QC: {Path(image_path).name} - Intent: {intent}, "
                       f"Expected: {expected_count}, Found: {actual_count}, "
                       f"Result: {'PASS' if validation_result['passes'] else 'FAIL'}")

            return result

        except Exception as e:
            logger.error(f"Error in context-aware QC: {e}")
            return {'error': str(e)}

    def _validate_against_intent(self, actual: int, expected: int, intent: str, confidence: float) -> Dict:
        """Validate actual count against expected based on intent"""

        if intent == "SOLO":
            # Solo intent - should be exactly 1 person
            passes = actual == 1
            reason = None if passes else f"Expected 1 person (solo), found {actual}"

        elif intent == "MULTIPLE":
            # Multiple intent - allow some flexibility
            tolerance = max(1, expected // 2)  # Allow ±50% of expected
            min_acceptable = max(2, expected - tolerance)
            max_acceptable = expected + tolerance

            passes = min_acceptable <= actual <= max_acceptable
            reason = None if passes else f"Expected ~{expected} people, found {actual} (acceptable range: {min_acceptable}-{max_acceptable})"

        elif intent == "CONFLICTED":
            # Conflicted prompts - be lenient, flag for review
            passes = 1 <= actual <= 3  # Allow 1-3 people for conflicted prompts
            reason = None if passes else f"Conflicted prompt intent, found {actual} people (outside acceptable range 1-3)"

        else:  # UNCLEAR
            # Unclear intent - default to solo expectations but be slightly lenient
            passes = actual == 1
            reason = None if passes else f"Unclear intent (defaulted to solo), found {actual} people"

        return {
            'passes': passes,
            'reason': reason,
            'confidence': confidence,
            'validation_type': intent
        }

def test_context_qc():
    """Test the context-aware QC system"""
    qc = ContextAwareQC()

    # Test prompts with different intents
    test_cases = [
        "photo of Yuki Tanaka, solo, 1girl, beautiful Japanese woman",
        "group photo of Yuki, Mei, and Rina together, 3girls",
        "solo 1girl Mei cooking but also 2girls in background",  # Conflicted
        "beautiful anime scene with characters"  # Unclear
    ]

    print("=== Context-Aware QC Intent Analysis ===")
    for prompt in test_cases:
        analysis = qc.analyze_prompt_intent(prompt)
        print(f"\nPrompt: {prompt}")
        print(f"Intent: {analysis['intent']}, Expected: {analysis['expected_count']}")
        print(f"Confidence: {analysis['confidence']:.2f}")

if __name__ == "__main__":
    test_context_qc()