#!/usr/bin/env python3
"""
Multi-Person Detection for Anime Quality Control
Detects multiple people in generated images and triggers re-generation
"""

import cv2
import numpy as np
import logging
from typing import Tuple, List, Dict, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class MultiPersonDetector:
    """Detects multiple people in images for QC purposes"""

    def __init__(self):
        # Initialize face cascade classifier
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.body_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_fullbody.xml')

        # Detection thresholds
        self.face_detection_params = {
            'scaleFactor': 1.1,
            'minNeighbors': 3,
            'minSize': (30, 30),
            'maxSize': (300, 300)
        }

        self.body_detection_params = {
            'scaleFactor': 1.1,
            'minNeighbors': 3,
            'minSize': (50, 50)
        }

    def detect_multiple_people(self, image_path: str) -> Dict:
        """
        Detect if image contains multiple people
        Returns detection results with counts and confidence
        """
        try:
            # Load image
            img = cv2.imread(image_path)
            if img is None:
                return {'error': f'Could not load image: {image_path}'}

            # Convert to grayscale for detection
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Detect faces
            faces = self.face_cascade.detectMultiScale(gray, **self.face_detection_params)

            # Detect full bodies (as backup/additional check)
            bodies = self.body_cascade.detectMultiScale(gray, **self.body_detection_params)

            # Analysis results
            face_count = len(faces)
            body_count = len(bodies)

            # Determine if multiple people detected
            multiple_people_detected = face_count > 1 or body_count > 1

            # Generate detailed report
            detection_result = {
                'image_path': image_path,
                'face_count': face_count,
                'body_count': body_count,
                'multiple_people_detected': multiple_people_detected,
                'passes_qc': not multiple_people_detected,
                'faces': [{'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)} for x, y, w, h in faces],
                'bodies': [{'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)} for x, y, w, h in bodies],
                'confidence_score': self._calculate_confidence(faces, bodies),
                'recommendation': 'REJECT' if multiple_people_detected else 'ACCEPT'
            }

            logger.info(f"QC Analysis: {image_path} - Faces: {face_count}, Bodies: {body_count}, Result: {detection_result['recommendation']}")

            return detection_result

        except Exception as e:
            logger.error(f"Error in multi-person detection: {e}")
            return {'error': str(e)}

    def _calculate_confidence(self, faces, bodies) -> float:
        """Calculate confidence score for detection"""
        if len(faces) == 1 and len(bodies) <= 1:
            return 0.95  # High confidence single person
        elif len(faces) > 1:
            return 0.85  # High confidence multiple people
        elif len(bodies) > 1:
            return 0.75  # Medium confidence multiple people
        else:
            return 0.60  # Low confidence/unclear

    def batch_check_directory(self, directory_path: str, pattern: str = "*.png") -> List[Dict]:
        """Check all images in directory for multiple people"""
        results = []
        directory = Path(directory_path)

        for image_file in directory.glob(pattern):
            result = self.detect_multiple_people(str(image_file))
            results.append(result)

        return results

    def generate_qc_report(self, results: List[Dict]) -> Dict:
        """Generate summary QC report"""
        total_images = len(results)
        passed_qc = sum(1 for r in results if r.get('passes_qc', False))
        failed_qc = total_images - passed_qc

        report = {
            'total_images_analyzed': total_images,
            'passed_qc': passed_qc,
            'failed_qc': failed_qc,
            'success_rate': (passed_qc / total_images * 100) if total_images > 0 else 0,
            'failed_images': [r['image_path'] for r in results if not r.get('passes_qc', False)],
            'analysis_summary': {
                'avg_face_count': np.mean([r.get('face_count', 0) for r in results]),
                'avg_body_count': np.mean([r.get('body_count', 0) for r in results]),
                'max_face_count': max([r.get('face_count', 0) for r in results]),
                'max_body_count': max([r.get('body_count', 0) for r in results])
            }
        }

        return report

def main():
    """Test the multi-person detector"""
    detector = MultiPersonDetector()

    # Test on recent images
    output_dir = "/mnt/1TB-storage/ComfyUI/output"
    results = detector.batch_check_directory(output_dir, "*.png")

    # Generate report
    report = detector.generate_qc_report(results)

    print("=== Multi-Person Detection QC Report ===")
    print(json.dumps(report, indent=2))

    # Show failed images
    for result in results:
        if not result.get('passes_qc', False):
            print(f"FAILED QC: {result['image_path']} - {result['face_count']} faces, {result['body_count']} bodies")

if __name__ == "__main__":
    main()