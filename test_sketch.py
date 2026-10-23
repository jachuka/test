import tempfile
import unittest
from pathlib import Path
from shapely.geometry import Polygon, box
from sketch import build_contour, arc_geometry
from irregular import export_pdf, read_vector_pdf, NestResult, nest


def edges_from_points(points):
    return [dict(dx=points[(i+1)%len(points)][0]-p[0], dy=points[(i+1)%len(points)][1]-p[1]) for i,p in enumerate(points)]


class SketchTests(unittest.TestCase):
    def test_quarter_round_from_explicit_radius_keeps_physical_dimensions(self):
        from math import pi
        edges=edges_from_points([(0,0),(90,0),(100,10),(100,60),(0,60)])
        edges[1]['arc']=dict(radius='10',sweep=90)
        model=build_contour(edges)
        self.assertAlmostEqual(model.dimensions['width'],100)
        self.assertAlmostEqual(model.dimensions['height'],60)
        self.assertEqual(len(model.vertices),5)
        self.assertGreater(len(model.polygon.exterior.coords),6)
        self.assertAlmostEqual(model.segments[1]['length'],pi*5)
        self.assertAlmostEqual(model.polygon.area,5900+pi*100/4,delta=1.0)

    def test_semicircle_extends_bounds_without_measuring_image(self):
        from math import pi
        edges=edges_from_points([(0,0),(10,0),(10,10),(0,10)])
        edges[0]['arc']=dict(radius=5,sweep=180)
        model=build_contour(edges)
        self.assertAlmostEqual(model.dimensions['width'],10)
        self.assertAlmostEqual(model.dimensions['height'],15)
        self.assertAlmostEqual(model.vertices[0][1],5)
        self.assertAlmostEqual(model.segments[0]['center'][1],5)
        self.assertAlmostEqual(model.segments[0]['midpoint'][1],0)
        self.assertAlmostEqual(model.segments[0]['length'],pi*5)
        self.assertAlmostEqual(model.polygon.area,100+pi*25/2,delta=.6)

    def test_arc_direction_and_flattening_tolerance(self):
        from math import hypot
        for sweep in (-180,180):
            arc=arc_geometry((0,0),(5,0),dict(radius=2.5,sweep=sweep))
            self.assertEqual(arc['points'][0],(0,0))
            self.assertEqual(arc['points'][-1],(5,0))
            self.assertAlmostEqual(arc['midpoint'][1],-2.5 if sweep>0 else 2.5)
            self.assertAlmostEqual(arc['sweep'],sweep)
            for a,b in zip(arc['points'],arc['points'][1:]):
                midpoint=((a[0]+b[0])/2,(a[1]+b[1])/2)
                sagitta=2.5-hypot(midpoint[0]-2.5,midpoint[1])
                self.assertLessEqual(sagitta,.05000001)

    def test_arc_rejects_missing_impossible_or_conflicting_radius(self):
        for arc in (dict(radius='',sweep=180),dict(radius=-1,sweep=180),
                    dict(radius='nan',sweep=180),dict(radius=2,sweep=180),
                    dict(radius=3),dict(radius=3,clockwise='yes'),
                    dict(radius=3,sweep=180),dict(radius=2.5,sweep=45),
                    dict(radius=2.5,sweep=-180,clockwise=True)):
            with self.subTest(arc=arc),self.assertRaises(ValueError):
                arc_geometry((0,0),(5,0),arc)
        with self.assertRaises(ValueError):
            arc_geometry((0,0),(0,0),dict(radius=2.5,sweep=180))

    def test_arc_cannot_supply_unknown_dimensions_from_pixels(self):
        edges=[dict(dx='',dy=0,arc=dict(radius=5,sweep=180)),
               dict(dx=0,dy=''),dict(dx='',dy=0),dict(dx=0,dy='')]
        with self.assertRaisesRegex(ValueError,'Brakuje wymiarów'):
            build_contour(edges)

    def test_concave_hooks_round_corners_and_chamfers_from_dimensions(self):
        from math import pi
        # A dimensioned generic profile: two semicircular hooks, two outer
        # rounds and two 4x4 chamfers. This is not an imported private file.
        points=[(3,0),(117,0),(120,3),(120,35),(90,35),(90,44),
                (90,50),(84,50),(80,46),(80,14),(40,14),(40,46),
                (36,50),(30,50),(30,44),(30,35),(0,35),(0,3)]
        edges=edges_from_points(points)
        for index,sweep in ((1,90),(5,180),(13,180),(17,90)):
            edges[index]['arc']=dict(radius=3,sweep=sweep)
        model=build_contour(edges)
        self.assertEqual(model.dimensions,dict(width=120,height=50))
        self.assertEqual(sum(s['kind']=='arc' for s in model.segments),4)
        exact_area=Polygon(points).area+9*(1.5*pi-1)
        self.assertAlmostEqual(model.polygon.area,exact_area,delta=1.0)
        self.assertTrue(model.polygon.is_valid)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'curved-profile.pdf'
            export_pdf(path,NestResult([model.polygon],120,50,0,0))
            restored=read_vector_pdf(path)[0]
            self.assertLess(restored.hausdorff_distance(model.polygon),.001)

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
