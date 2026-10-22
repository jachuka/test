import tempfile
import unittest
from pathlib import Path
from shapely.geometry import box
from sketch import build_shape
from irregular import export_pdf, read_vector_pdf, NestResult, nest


class SketchTests(unittest.TestCase):
    def setUp(self):
        self.dims = dict(width='440', height='160', top='30', left='30', right='60')

    def test_correct_bv300_dimensions(self):
        model = build_shape('U', self.dims)
        self.assertEqual(model.polygon.bounds, (0, 0, 440, 160))
        self.assertEqual(model.dimensions['inner_width'], 350)
        self.assertEqual(model.dimensions['inner_height'], 130)
        self.assertEqual(model.polygon.area, 24900)
        self.assertFalse(model.polygon.contains(box(40, 40, 370, 150)))

    def test_missing_is_not_guessed(self):
        with self.assertRaisesRegex(ValueError, 'Brak wystarczających wymiarów'):
            build_shape('U', dict(width=440, height=160))

    def test_contradictory_height_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Sprzeczne wymiary'):
            build_shape('U', dict(self.dims, inner_height=160))

    def test_derived_external_dimensions(self):
        model = build_shape('U', dict(top=30, left=30, right=60, inner_width=350, inner_height=130))
        self.assertEqual(model.polygon.bounds, (0, 0, 440, 160))

    def test_invalid_geometry(self):
        for changes in (dict(left=400), dict(top=160), dict(width=-1), dict(height='nan'), dict(right='abc')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_shape('U', dict(self.dims, **changes))

    def test_rectangle_and_l_shape(self):
        self.assertEqual(build_shape('Prostokąt', dict(width='100,5', height=20)).polygon.area, 2010)
        model = build_shape('L', dict(width=115, height=246, top=83, left=34))
        self.assertEqual(model.polygon.area, 15087)
        self.assertEqual(model.dimensions['inner_width'], 81)
        self.assertEqual(model.dimensions['inner_height'], 163)

    def test_source_preview_rotation_pdf_and_image(self):
        import pymupdf as fitz
        from sketch import preview_png
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / 'sketch.pdf'
            with fitz.open() as doc:
                page = doc.new_page(width=200, height=100)
                page.insert_text((20, 30), '440 x 160')
                doc.save(pdf)
            normal = fitz.Pixmap(preview_png(pdf))
            rotated = fitz.Pixmap(preview_png(pdf, 90))
            self.assertEqual((normal.width, normal.height), (rotated.height, rotated.width))
            png = Path(folder) / 'scan.png'
            normal.save(png)
            self.assertGreater(fitz.Pixmap(preview_png(png)).width, 0)

    def test_export_and_nesting(self):
        model = build_shape('U', self.dims)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'contour.pdf'
            export_pdf(path, NestResult([model.polygon], 440, 160, 0, 0))
            restored = read_vector_pdf(path)
            self.assertEqual(len(restored), 1)
            self.assertAlmostEqual(restored[0].area, model.polygon.area, delta=.1)
        result = nest(model.polygon, 3050, 2050, 5, 10, seconds=.5)
        self.assertGreater(len(result.shapes), 0)
        self.assertTrue(all(box(10, 10, 3040, 2040).covers(p) for p in result.shapes))


if __name__ == '__main__':
    unittest.main()
