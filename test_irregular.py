import tempfile
import threading
import unittest
from pathlib import Path
import pymupdf as fitz
from shapely.geometry import Polygon, box
from irregular import MM, read_vector_pdf, read_scan, nest, export_pdf, NestResult


class IrregularTests(unittest.TestCase):
    def test_vector_import_mm_and_export_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.pdf'
            with fitz.open() as doc:
                page = doc.new_page(width=200 / MM, height=100 / MM)
                pen = page.new_shape()
                pen.draw_polyline([(10 / MM, 10 / MM), (70 / MM, 10 / MM), (10 / MM, 50 / MM), (10 / MM, 10 / MM)])
                pen.finish(closePath=True, color=(0, 0, 0))
                pen.commit()
                doc.save(source)
            shapes = read_vector_pdf(source)
            self.assertEqual(len(shapes), 1)
            self.assertAlmostEqual(shapes[0].bounds[2], 60, places=3)
            self.assertAlmostEqual(shapes[0].bounds[3], 40, places=3)
            result = nest(shapes[0], 200, 100, 3, 5, seconds=2)
            self.assertGreater(len(result.shapes), 0)
            output = Path(folder) / 'output.pdf'
            export_pdf(output, result)
            with fitz.open(output) as doc:
                self.assertAlmostEqual(doc[0].rect.width * MM, 200, places=3)
                self.assertAlmostEqual(doc[0].rect.height * MM, 100, places=3)
                self.assertEqual(len(doc[0].get_drawings()), len(result.shapes))
            restored = read_vector_pdf(output)
            self.assertGreater(len(restored), 0)
            for contour in restored:
                self.assertAlmostEqual(contour.area, shapes[0].area, delta=0.02)

    def test_spacing_and_margin(self):
        poly = Polygon([(0, 0), (40, 0), (40, 15), (15, 15), (15, 40), (0, 40)])
        result = nest(poly, 130, 100, 3, 7, seconds=3)
        self.assertGreaterEqual(len(result.shapes), 4)
        usable = box(7, 7, 123, 93)
        for i, p in enumerate(result.shapes):
            self.assertTrue(usable.covers(p))
            for q in result.shapes[i + 1:]:
                self.assertGreaterEqual(p.distance(q), 3 - 1e-6)
                self.assertLess(p.intersection(q).area, 1e-6)

    def test_triangle_nesting_uses_real_outline(self):
        triangle = Polygon([(0, 0), (40, 0), (0, 40)])
        result = nest(triangle, 85, 45, 1, 1, seconds=3)
        self.assertGreater(len(result.shapes), 2)  # bounding boxes fit only two

    def test_rotation_and_no_fit(self):
        self.assertEqual(len(nest(box(0, 0, 60, 30), 35, 65, 0, 1, rotate=False).shapes), 0)
        self.assertEqual(len(nest(box(0, 0, 60, 30), 35, 65, 0, 1).shapes), 1)
        self.assertEqual(len(nest(box(0, 0, 10, 10), 10, 10, 0, 6).shapes), 0)

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        result = nest(box(0, 0, 10, 10), 100, 100, 0, 0, cancel=cancel)
        self.assertTrue(result.limited)
        self.assertEqual(result.shapes, [])

    def test_scan_and_vector_rejection(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            image = np.full((200, 300), 255, dtype=np.uint8)
            cv2.fillPoly(image, [np.array([[20, 20], [220, 20], [20, 120]])], 0)
            path = Path(folder) / 'scan.png'
            cv2.imwrite(str(path), image)
            shapes = read_scan(path)
            self.assertEqual(len(shapes), 1)
            self.assertAlmostEqual(shapes[0].bounds[2], 200)
            pdf = Path(folder) / 'scan.pdf'
            with fitz.open() as doc:
                page = doc.new_page(width=300, height=200)
                page.insert_image(page.rect, filename=str(path))
                doc.save(pdf)
            with self.assertRaises(ValueError):
                read_vector_pdf(pdf)
            self.assertEqual(len(read_scan(pdf)), 1)

    def test_curved_contour(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'circle.pdf'
            with fitz.open() as doc:
                page = doc.new_page()
                page.draw_circle((100, 100), 40)
                doc.save(path)
            shape = read_vector_pdf(path)[0]
            self.assertAlmostEqual(shape.bounds[2], 80 * MM, places=3)
            self.assertGreater(len(shape.exterior.coords), 16)

    def test_invalid_export(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                export_pdf(Path(folder) / 'empty.pdf', NestResult([], 100, 100, 0, 0))
            with self.assertRaises(ValueError):
                export_pdf(Path(folder) / 'large.pdf', NestResult([box(0, 0, 10, 10)], 6000, 100, 0, 0))


if __name__ == '__main__':
    unittest.main()
