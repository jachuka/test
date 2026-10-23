import unittest
import pymupdf as fitz
from zoom_preview import bounded_scale, render_png, MAX_PIXELS


class ZoomRenderingTests(unittest.TestCase):
    def test_render_scales_display_without_modifying_source(self):
        pix=fitz.Pixmap(fitz.csRGB,(0,0,240,120),False)
        pix.clear_with(255)
        source=pix.tobytes('png')
        for scale,size in ((.5,(120,60)),(1,(240,120)),(2.5,(600,300))):
            result=fitz.Pixmap(render_png(source,scale))
            self.assertEqual((result.width,result.height),size)
        original=fitz.Pixmap(source)
        self.assertEqual((original.width,original.height),(240,120))

    def test_scale_limit_bounds_memory_for_large_images(self):
        scale=bounded_scale(10000,8000,4)
        self.assertLessEqual(10000*8000*scale*scale,MAX_PIXELS+1)
        self.assertEqual(bounded_scale(200,100,100),4)

    def test_invalid_zoom_is_rejected(self):
        for scale in (0,-1,float('nan'),float('inf')):
            with self.subTest(scale=scale),self.assertRaises(ValueError):
                bounded_scale(100,100,scale)


if __name__=='__main__':
    unittest.main()
