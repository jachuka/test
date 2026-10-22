import tempfile
import unittest
from pathlib import Path
from shapely.geometry import Polygon, box
from sketch import build_contour
from irregular import export_pdf, read_vector_pdf, NestResult, nest


def edges_from_points(points):
    return [dict(dx=points[(i+1)%len(points)][0]-p[0], dy=points[(i+1)%len(points)][1]-p[1]) for i,p in enumerate(points)]


class SketchTests(unittest.TestCase):
    def test_bv300_from_dimensions_and_constraints(self):
        edges=[dict(dx=440,dy=0),dict(dx=0,dy=160),dict(dx=-60,dy=0),dict(dx=0,dy=''),dict(dx='',dy=0),dict(dx=0,dy=''),dict(dx=-30,dy=0),dict(dx=0,dy='')]
        dimensions=[dict(start=0,end=4,axis='y',value=30),dict(start=2,end=6,axis='y',value=0)]
        model=build_contour(edges,dimensions)
        expected=Polygon([(0,0),(440,0),(440,160),(380,160),(380,30),(30,30),(30,160),(0,160)])
        self.assertTrue(model.polygon.equals(expected))
        self.assertEqual(model.polygon.area,24900)
        self.assertEqual(model.dimensions,dict(width=440,height=160))

    def test_arbitrary_slanted_five_sided_contour(self):
        points=[(0,0),(120,0),(90,50),(40,80),(-10,40)]
        model=build_contour(edges_from_points(points))
        self.assertEqual(len(model.vertices),5)
        self.assertEqual(model.dimensions,dict(width=130,height=80))
        self.assertEqual(model.polygon.area,Polygon(points).area)

    def test_concave_many_sided_contour(self):
        points=[(0,0),(100,0),(100,30),(60,30),(60,60),(90,60),(90,90),(30,90),(30,50),(0,50)]
        self.assertTrue(build_contour(edges_from_points(points)).polygon.equals(Polygon(points)))

    def test_missing_is_not_guessed(self):
        with self.assertRaisesRegex(ValueError,'Brakuje wymiarów'):
            build_contour([dict(dx='',dy=0),dict(dx=0,dy=''),dict(dx='',dy=0),dict(dx=0,dy='')])

    def test_unknown_closing_side_can_be_derived(self):
        model=build_contour([dict(dx=100,dy=0),dict(dx=0,dy=50),dict(dx=-100,dy=0),dict(dx=0,dy='')])
        self.assertEqual(model.vertices[-1],(0,50))
        self.assertEqual(model.polygon.area,5000)

    def test_conflicting_dimension_rejected(self):
        edges=edges_from_points([(0,0),(100,0),(100,50),(0,50)])
        with self.assertRaisesRegex(ValueError,'Sprzeczne wymiary'):
            build_contour(edges,[dict(start=0,end=2,axis='x',value=110)])
        edges[-1]['dy']=-60
        with self.assertRaisesRegex(ValueError,'Sprzeczne wymiary'):
            build_contour(edges)

    def test_invalid_contours_rejected(self):
        for points in ([(0,0),(100,100),(0,100),(100,0)],[(0,0),(100,0),(100,0),(0,100)],[(0,0),(10,0),(20,0)]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                build_contour(edges_from_points(points))
        with self.assertRaises(ValueError):
            build_contour([dict(dx=1,dy=0)]*2)
        with self.assertRaises(ValueError):
            build_contour([dict(dx='nan',dy=0)]*3)

    def test_decimal_comma_and_signed_dimensions(self):
        model=build_contour([dict(dx='100,5',dy=0),dict(dx=0,dy='20,5'),dict(dx='-100,5',dy=0),dict(dx=0,dy='-20,5')])
        self.assertEqual(model.polygon.area,100.5*20.5)

    def test_source_preview_rotation_pdf_and_image(self):
        import pymupdf as fitz
        from sketch import preview_png
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'sketch.pdf'
            with fitz.open() as doc:
                page=doc.new_page(width=200,height=100)
                page.insert_text((20,30),'440 x 160')
                doc.save(pdf)
            normal=fitz.Pixmap(preview_png(pdf))
            rotated=fitz.Pixmap(preview_png(pdf,90))
            self.assertEqual((normal.width,normal.height),(rotated.height,rotated.width))
            png=Path(folder)/'scan.png'
            normal.save(png)
            self.assertGreater(fitz.Pixmap(preview_png(png)).width,0)

    def test_export_and_nesting_arbitrary_contour(self):
        model=build_contour(edges_from_points([(0,0),(120,0),(90,50),(40,80),(-10,40)]))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'contour.pdf'
            export_pdf(path,NestResult([model.polygon],130,80,0,0))
            restored=read_vector_pdf(path)
            self.assertEqual(len(restored),1)
            self.assertAlmostEqual(restored[0].area,model.polygon.area,delta=.1)
        result=nest(model.polygon,3050,2050,5,10,seconds=.5)
        self.assertGreater(len(result.shapes),0)
        self.assertTrue(all(box(10,10,3040,2040).covers(p) for p in result.shapes))


if __name__=='__main__':
    unittest.main()
