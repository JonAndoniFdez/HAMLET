"""Regression checks for quality-based 3D duplicate selection."""
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import pandas as pd
from src.core.detect_map import detect_points_from_texture, reconcile_points_with_3d_priority


class DuplicateQualityTests(unittest.TestCase):
    def test_order_independent_and_isolated_preserved(self):
        rows = [dict(pixel_x=10, pixel_y=10, x3d=0, y3d=0, z3d=0,
                     area=100, circularity=1, color_score=0),
                dict(pixel_x=20, pixel_y=20, x3d=.01, y3d=0, z3d=0,
                     area=80, circularity=.9, color_score=1),
                dict(pixel_x=30, pixel_y=30, x3d=10, y3d=0, z3d=0,
                     area=1, circularity=0, color_score=0)]
        for permutation in itertools.permutations(rows):
            clean, pixels, removed, _ = reconcile_points_with_3d_priority(
                pd.DataFrame(permutation), distance_threshold=.1)
            self.assertEqual(set(clean.pixel_x), {20, 30})
            self.assertEqual(removed, 1)
            self.assertEqual(list(clean.pixel_x), list(pixels.pixel_x))
            winner = clean.loc[clean.pixel_x == 20].iloc[0]
            self.assertAlmostEqual(winner.quality_score, .25*.9 + .35*.8 + .4)

    def test_ties_and_legacy_rows(self):
        rows = [dict(pixel_x=x, pixel_y=0, X=0, Y=0, Z=0) for x in (2, 1)]
        for permutation in itertools.permutations(rows):
            clean, _, removed, _ = reconcile_points_with_3d_priority(
                pd.DataFrame(permutation), distance_threshold=.1)
            self.assertEqual(list(clean.pixel_x), [1])
            self.assertEqual(removed, 1)

    def test_real_contours_and_wrapped_hue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hsv = np.zeros((100, 100, 3), np.uint8)
            cv2.circle(hsv, (25, 25), 10, (0, 150, 150), -1)
            cv2.rectangle(hsv, (55, 65), (90, 70), (8, 150, 150), -1)
            texture, ranges = root/'texture.png', root/'ranges.json'
            cv2.imwrite(str(texture), cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR))
            ranges.write_text(json.dumps({'ranges_parts': [
                {'lo': [0, 100, 100], 'hi': [10, 200, 200]},
                {'lo': [170, 100, 100], 'hi': [179, 200, 200]}]}))
            detected, _, _ = detect_points_from_texture(texture, ranges, k_open=1, k_close=1)
            self.assertEqual(len(detected), 2)
            circle = detected.loc[detected.pixel_x < 50].iloc[0]
            rectangle = detected.loc[detected.pixel_x > 50].iloc[0]
            self.assertGreater(circle.circularity, rectangle.circularity)
            self.assertGreater(circle.color_score, .98)
            self.assertGreater(circle.color_score, rectangle.color_score)


if __name__ == '__main__':
    unittest.main()
