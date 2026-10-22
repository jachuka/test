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

    def test_full_sheet_is_preserved_when_time_expires(self):
        poly = Polygon([(0, 0), (246, 0), (246, 115), (166, 115), (166, 40), (0, 40)])
        result = nest(poly, 3050, 2050, 5, 10, seconds=0)
        self.assertEqual(len(result.shapes), 200)
        self.assertTrue(result.limited)
        self.assertGreater(max(p.bounds[3] for p in result.shapes), 1900)

    def test_repeating_groups_improve_count_and_preserve_clearance(self):
        poly = Polygon([(0, 0), (246, 0), (246, 115), (166, 115), (166, 40), (0, 40)])
        result = nest(poly, 3050, 2050, 5, 10, seconds=3)
        self.assertGreater(len(result.shapes), 200)
        usable = box(10, 10, 3040, 2040)
        from shapely.strtree import STRtree
        tree = STRtree(result.shapes)
        for i, shape in enumerate(result.shapes):
            self.assertTrue(usable.covers(shape))
            for j in tree.query(shape.buffer(5.2)):
                if j > i:
                    self.assertGreaterEqual(shape.distance(result.shapes[j]), 5 - 1e-6)
                    self.assertLess(shape.intersection(result.shapes[j]).area, 1e-6)

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        result = nest(box(0, 0, 10, 10), 100, 100, 0, 0, cancel=cancel)
        self.assertTrue(result.limited)
        self.assertEqual(result.shapes, [])

    def test_scan_and_vector_rejection(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            image = np.full((200, 300), 255, dtype=np.uint8)
            for y in range(20, 120):
                image[y, 20:220 - 2 * (y - 20)] = 0
            path = Path(folder) / 'scan.png'
            fitz.Pixmap(fitz.csGRAY, 300, 200, image.tobytes(), False).save(path)
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

    def test_scan_holes_and_diagonal_pixels(self):
        import numpy as np
        from irregular import trace_silhouettes
        image = np.full((50, 50), 255, dtype=np.uint8)
        image[5:25, 5:25] = 0
        image[10:20, 10:20] = 255
        image[25:35, 25:35] = 0
        shapes = trace_silhouettes(image)
        self.assertEqual(len(shapes), 2)
        self.assertEqual([p.area for p in shapes], [400, 100])
        self.assertTrue(all(p.is_valid for p in shapes))

    def test_transparent_scan(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            rgba = np.zeros((50, 50, 4), dtype=np.uint8)
            rgba[10:30, 10:40, 3] = 255
            path = Path(folder) / 'transparent.png'
            fitz.Pixmap(fitz.csRGB, 50, 50, rgba.tobytes(), True).save(path)
            shapes = read_scan(path)
            self.assertEqual(len(shapes), 1)
            self.assertEqual(shapes[0].bounds[2:], (30, 20))

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
