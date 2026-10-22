import unittest
from packing import calculate


class PackingTests(unittest.TestCase):
    def test_exact_grid(self):
        self.assertEqual(len(calculate(100, 100, 25, 20, 0, 0).rectangles), 20)

    def test_gap_and_margin(self):
        self.assertEqual(len(calculate(110, 110, 40, 40, 10, 10).rectangles), 4)

    def test_rotation(self):
        self.assertEqual(len(calculate(60, 100, 100, 60, 0, 0, False).rectangles), 0)
        self.assertEqual(len(calculate(60, 100, 100, 60, 0, 0).rectangles), 1)

    def test_mixed_rows(self):
        self.assertEqual(len(calculate(100, 100, 60, 40, 0, 0).rectangles), 3)

    def test_geometry(self):
        for w, h, pw, ph, gap, margin in [(2000, 1000, 300, 200, 5, 10), (150, 210, 35, 60, 3, 7)]:
            rects = calculate(w, h, pw, ph, gap, margin).rectangles
            for i, (x, y, a, b) in enumerate(rects):
                self.assertGreaterEqual(x, margin)
                self.assertGreaterEqual(y, margin)
                self.assertLessEqual(x + a, w - margin + 1e-8)
                self.assertLessEqual(y + b, h - margin + 1e-8)
                for xx, yy, aa, bb in rects[i + 1:]:
                    self.assertTrue(x + a + gap <= xx + 1e-8 or xx + aa + gap <= x + 1e-8 or y + b + gap <= yy + 1e-8 or yy + bb + gap <= y + 1e-8)

    def test_invalid(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                calculate(value, 100, 20, 20, 0, 0)


if __name__ == '__main__':
    unittest.main()
