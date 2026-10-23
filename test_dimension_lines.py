import unittest
import numpy as np
from dimension_lines import dimension_spans


class DimensionLineTests(unittest.TestCase):
    def test_vertical_chain_splits_at_internal_witnesses_but_total_stays(self):
        mask=np.zeros((380,450),dtype=bool)
        mask[60:321,330]=True
        mask[60:321,390]=True
        mask[140,280:331]=True;mask[230,280:331]=True
        points=[(120,60),(280,60),(280,140),(220,140),(220,230),(280,230),(280,320),(120,320)]
        lines=[('y',330,60,320),('y',390,60,320),('x',140,280,330),('x',230,280,330)]
        result=dimension_spans(mask,points,lines)
        self.assertEqual([line for line in result if line[:2]==('y',330)],
                         [('y',330,60,140),('y',330,140,230),('y',330,230,320)])
        self.assertIn(('y',390,60,320),result)

    def test_horizontal_chain_short_tick_is_not_required_to_be_long_line(self):
        mask=np.zeros((220,420),dtype=bool);mask[90,50:371]=True
        mask[90:111,210]=True
        points=[(50,40),(370,40),(370,160),(210,160),(210,180),(50,180)]
        result=dimension_spans(mask,points,[('x',90,50,370)])
        cuts=[line[3] for line in result[:-1]]
        self.assertEqual(len(cuts),1)
        self.assertLess(abs(cuts[0]-210),2)
        self.assertEqual(result[0][2],50);self.assertEqual(result[-1][3],370)

    def test_contour_coordinate_level_alone_does_not_split_line(self):
        mask=np.zeros((350,450),dtype=bool);mask[40:301,350]=True
        points=[(50,40),(250,40),(250,140),(200,140),(200,230),(250,230),(250,300),(50,300)]
        lines=[('y',350,40,300)]
        self.assertEqual(dimension_spans(mask,points,lines),lines)

    def test_disconnected_text_strokes_are_not_junction_ticks(self):
        mask=np.zeros((350,450),dtype=bool);mask[40:301,350]=True
        # Długi pionowy napis obok linii, odłączony od jej tuszu.
        mask[138:143,360:381]=True
        points=[(50,40),(250,40),(250,140),(200,140),(200,300),(50,300)]
        lines=[('y',350,40,300)]
        self.assertEqual(dimension_spans(mask,points,lines),lines)

    def test_plain_rectangle_and_source_mask_stay_unchanged(self):
        mask=np.zeros((240,320),dtype=bool)
        mask[30,30:281]=True;mask[210,30:281]=True
        mask[30:211,30]=True;mask[30:211,280]=True
        points=[(30,30),(280,30),(280,210),(30,210)]
        lines=[('x',30,30,280),('x',210,30,280),('y',30,30,210),('y',280,30,210)]
        original=mask.copy();source=list(points)
        self.assertEqual(dimension_spans(mask,points,lines),lines)
        self.assertTrue(np.array_equal(original,mask));self.assertEqual(source,points)

    def test_thick_dimension_line_does_not_bridge_gap_to_text(self):
        mask=np.zeros((350,450),dtype=bool)
        mask[40:301,349:353]=True
        mask[138:143,356:381]=True
        points=[(50,40),(250,40),(250,140),(200,140),(200,300),(50,300)]
        lines=[('y',349,40,300)]
        self.assertEqual(dimension_spans(mask,points,lines),lines)


if __name__=='__main__':unittest.main()
