import math
import unittest
from curve_detection import suggest_arcs


class CurveDetectionTests(unittest.TestCase):
    def test_semicircle_requires_explicit_physical_radius(self):
        arc=[(100+20*math.cos(a),60+20*math.sin(a)) for a in [i*math.pi/12 for i in range(13)]]
        points=arc+[(80,160),(120,160)]
        endpoints,specs=suggest_arcs(points)
        self.assertEqual(len(specs),1)
        spec=next(iter(specs.values()))
        self.assertEqual(spec['sweep'],180)
        self.assertIsNone(spec['radius'])
        self.assertGreaterEqual(len(spec['source_path']),6)
        self.assertLess(len(endpoints),len(points))

    def test_quarter_arc_and_orientation(self):
        arc=[(80+20*math.cos(a),60+20*math.sin(a)) for a in [i*math.pi/16 for i in range(9)]]
        points=arc+[(20,80),(20,20),(100,20)]
        for path,expected in ((points,90),(list(reversed(points)),-90)):
            _,specs=suggest_arcs(path)
            self.assertEqual(len(specs),1)
            self.assertEqual(next(iter(specs.values()))['sweep'],expected)

    def test_chamfers_corners_and_skewed_edges_remain_straight(self):
        points=[(0,0),(100,0),(110,10),(110,90),(100,100),(0,100),(-10,80),(-10,10)]
        endpoints,specs=suggest_arcs(points)
        self.assertEqual(specs,{})
        self.assertEqual(endpoints,points)

    def test_polygon_sampled_along_sharp_rectangle_does_not_become_arc(self):
        points=[(x,0) for x in range(0,101,5)]+[(100,y) for y in range(5,101,5)]+[(x,100) for x in range(95,-1,-5)]+[(0,y) for y in range(95,0,-5)]
        _,specs=suggest_arcs(points)
        self.assertEqual(specs,{})

    def test_source_scale_does_not_produce_mm_radius(self):
        arc=[(100+20*math.cos(a),60+20*math.sin(a)) for a in [i*math.pi/12 for i in range(13)]]
        for factor in (1,2):
            _,specs=suggest_arcs([(x*factor,y*factor) for x,y in arc+[(80,160),(120,160)]])
            self.assertEqual(len(specs),1)
            self.assertIsNone(next(iter(specs.values()))['radius'])


if __name__=='__main__':
    unittest.main()
