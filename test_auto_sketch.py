import subprocess
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import patch
import numpy as np
import pymupdf as fitz
from auto_sketch import detect_contours,topology,match_dimensions,OCRWord,missing_dimension,known_dimension,ocr_numbers
from sketch import build_contour


def drawing(points,split=False):
    with fitz.open() as doc:
        page=doc.new_page(width=500,height=420)
        page.draw_polyline(points+[points[0]],color=(0,0,0),width=2)
        if split:
            page.draw_line((50,200),(100,200),color=(0,0,0),width=1)
        return page.get_pixmap(alpha=False).tobytes('png')


class AutoSketchTests(unittest.TestCase):
    def test_detects_eight_corners_without_template(self):
        points=[(50,50),(450,50),(450,350),(380,350),(380,110),(100,110),(100,350),(50,350)]
        for split in (False,True):
            result=detect_contours(drawing(points,split))
            self.assertEqual(len(result.contours),1)
            self.assertEqual(len(result.contours[0]),8)
            edges,extra=topology(result.contours[0])
            self.assertTrue(all(e['dx'] in ('',0) and e['dy'] in ('',0) for e in edges))
            self.assertTrue(all(item['value']==0 for item in extra))
            with self.assertRaisesRegex(ValueError,'Brakuje wymiarów'):
                build_contour(edges,extra)

    def test_faint_outline_with_diagonal_annotation_leaders(self):
        points=[(100,50),(350,50),(350,150),(300,150),(300,100),(150,100),
                (150,600),(300,600),(300,550),(350,550),(350,650),(100,650)]
        with fitz.open() as doc:
            page=doc.new_page(width=500,height=700)
            page.draw_polyline(points+[points[0]],color=(.82,)*3,width=2)
            for a,b in [((100,50),(220,310)),((350,50),(220,310)),
                        ((100,650),(220,410)),((350,650),(220,410)),((220,310),(220,410))]:
                page.draw_line(a,b,color=(.82,)*3,width=2)
            png=page.get_pixmap(alpha=False).tobytes('png')
        with self.assertRaises(ValueError):
            detect_contours(png,205)
        result=detect_contours(png,225)
        self.assertEqual(len(result.contours[0]),12)
        from shapely.geometry import Polygon
        self.assertLess(Polygon(points).hausdorff_distance(Polygon(result.contours[0])),5)

    def test_region_and_gap_repair_keep_ocr_and_source_coordinates(self):
        from shapely.geometry import Polygon
        points=[(100,100),(350,100),(350,600),(100,600),(100,500),(250,500),(250,200),(100,200)]
        with fitz.open() as doc:
            page=doc.new_page(width=500,height=700)
            page.draw_polyline(points+[points[0]],width=2)
            # Zewnętrzna linia wymiarowa tworzy zamknięte pole obok formatki.
            page.draw_polyline([(350,100),(400,100),(400,600),(350,600)],width=1)
            # Przerwa większa niż domyślne domykanie tuszu.
            page.draw_rect((190,98,194,102),color=(1,1,1),fill=(1,1,1))
            png=page.get_pixmap(alpha=False).tobytes('png')
        region=(80,80,370,620)
        with self.assertRaises(ValueError):
            detect_contours(png,region=region,gap=1)
        result=detect_contours(png,region=region,gap=2)
        self.assertEqual(len(result.contours[0]),8)
        self.assertLess(Polygon(points).hausdorff_distance(Polygon(result.contours[0])),3)
        self.assertEqual(result.mask.shape,(700,500))
        self.assertTrue(result.mask[200,399:402].any())
        self.assertEqual(result.png,png)
        self.assertEqual(result.region,region)
        self.assertEqual(len(result.raw_contours),len(result.contours))
        self.assertLess(Polygon(result.raw_contours[0]).hausdorff_distance(Polygon(result.contours[0])),5)
        self.assertIn('domykanie przerw',' '.join(result.warnings))
        # Kontur nadal wymaga wymiarów, nie jest przeskalowany z pikseli.
        with self.assertRaisesRegex(ValueError,'Brakuje wymiarów'):
            build_contour(*topology(result.contours[0]))

    def test_invalid_detection_region_and_gap_are_rejected(self):
        png=drawing([(50,50),(400,50),(400,300),(50,300)])
        for region in ((10,10,5,20),(-1,0,400,300),(0,0,999,999),(0,0,10,10),(0,0,float('nan'),100)):
            with self.subTest(region=region),self.assertRaises(ValueError):
                detect_contours(png,region=region)
        for gap in (-1,4,1.5):
            with self.subTest(gap=gap),self.assertRaises(ValueError):
                detect_contours(png,gap=gap)

    def test_disjoint_dimension_like_regions_raise_review_warning(self):
        with fitz.open() as doc:
            page=doc.new_page(width=500,height=420)
            page.draw_rect((40,40,200,300),width=2)
            page.draw_rect((240,40,400,300),width=1)
            result=detect_contours(page.get_pixmap(alpha=False).tobytes('png'))
        self.assertEqual(len(result.contours),2)
        self.assertIn('liniami wymiarowymi',' '.join(result.warnings))

    def test_arbitrary_slanted_outline(self):
        result=detect_contours(drawing([(50,50),(400,50),(450,200),(250,350),(50,220)]))
        self.assertEqual(len(result.contours[0]),5)

    def test_no_closed_shape_is_not_invented(self):
        with fitz.open() as doc:
            page=doc.new_page(width=500,height=420)
            page.draw_polyline([(50,50),(400,50),(400,300)],width=2)
            with self.assertRaises(ValueError):
                detect_contours(page.get_pixmap().tobytes('png'))

    def test_confident_ocr_requires_matching_dimension_line(self):
        points=[(100,100),(400,100),(400,300),(100,300)]
        mask=np.zeros((420,500),dtype=bool)
        mask[330,100:401]=True
        words=[OCRWord(300,96,(235,340,265,355)),OCRWord(1234,99,(10,10,60,25))]
        accepted,questions=match_dimensions(points,mask,words)
        self.assertEqual(len(accepted),1)
        self.assertEqual(accepted[0],dict(start=3,end=2,axis='x',value=300))
        self.assertEqual(questions,[])

    def test_horizontal_ocr_blob_cannot_label_vertical_line(self):
        points=[(100,50),(400,50),(400,350),(100,350)]
        mask=np.zeros((420,520),dtype=bool);mask[50:351,430]=True
        blob=OCRWord(4,99,(410,180,490,210),axis='x')
        accepted,questions=match_dimensions(points,mask,[blob])
        self.assertEqual(accepted,[])
        self.assertEqual(questions,[])
        # Ta sama linia może mieć prawidłowy odczyt z obrotu OCR.
        word=OCRWord(300,55,(440,180,452,220),axis='y')
        _,questions=match_dimensions(points,mask,[word])
        self.assertEqual(len(questions),1)
        self.assertEqual(questions[0]['image_line'],(430.,50.,430.,350.))

    def test_chained_dimension_label_matches_only_middle_section(self):
        points=[(100,50),(400,50),(400,150),(300,150),(300,250),(400,250),(400,350),(100,350)]
        mask=np.zeros((420,520),dtype=bool);mask[50:351,430]=True
        for y in (50,150,250,350):
            mask[y,300:451]=True
        accepted,_=match_dimensions(points,mask,[OCRWord(30,96,(440,188,452,212),axis='y')])
        self.assertEqual(accepted,[dict(start=2,end=5,axis='y',value=30)])

    def test_uncertain_or_conflicting_digits_become_questions(self):
        points=[(100,100),(400,100),(400,300),(100,300)]
        mask=np.zeros((420,500),dtype=bool);mask[330,100:401]=True
        for words in ([OCRWord(300,55,(235,340,265,355))],[OCRWord(300,99,(235,340,265,355)),OCRWord(800,99,(235,340,265,355))]):
            accepted,questions=match_dimensions(points,mask,words)
            self.assertEqual(accepted,[])
            self.assertEqual(len(questions),1)

    def test_questions_stop_when_coordinates_are_determined(self):
        points=[(0,0),(100,0),(100,50),(0,50)]
        edges,extra=topology(points)
        asked=0
        while (question:=missing_dimension(points,edges,extra)) is not None:
            axis=0 if question['axis']=='x' else 1
            value=points[question['end']][axis]-points[question['start']][axis]
            self.assertIsNone(known_dimension(edges,extra,question))
            extra.append(dict(**question,value=value));asked+=1
            self.assertEqual(known_dimension(edges,extra,question),value)
        self.assertEqual(asked,2)
        self.assertEqual(build_contour(edges,extra).polygon.area,5000)

    @patch('auto_sketch.subprocess.run')
    def test_ocr_is_local_subprocess_and_ignores_untrusted_text(self,run):
        tsv='level\tleft\ttop\twidth\theight\tconf\ttext\n5\t10\t10\t20\t10\t99\t160\n5\t10\t10\t20\t10\t99\tBPV300\n'
        run.return_value=subprocess.CompletedProcess([],0,tsv.encode(),b'')
        for executable in (PureWindowsPath('C:/Tesseract OCR/tesseract.exe'), PurePosixPath('/opt/tesseract-test')):
            with self.subTest(executable=str(executable)):
                run.reset_mock()
                words=ocr_numbers(np.zeros((100,120),dtype=bool),executable)
                self.assertEqual(len(words),4)
                self.assertTrue(all(word.value==160 for word in words))
                self.assertEqual([word.axis for word in words],['x','y','x','y'])
                self.assertEqual(run.call_count,4)
                for call in run.call_args_list:
                    self.assertIsInstance(call.args[0],list)
                    self.assertEqual(call.args[0][0],str(executable))
                    self.assertNotIn('shell',call.kwargs)
                    self.assertEqual(call.kwargs['timeout'],20)

    @patch('auto_sketch.subprocess.run')
    def test_ocr_failure_leaves_dimensions_unknown(self,run):
        run.side_effect=subprocess.TimeoutExpired('tesseract',20)
        self.assertEqual(ocr_numbers(np.zeros((100,120),dtype=bool),Path('/tmp/tesseract-test')),[])

    @patch('auto_sketch.subprocess.run')
    def test_missing_engine_is_distinct_from_zero_digits(self,run):
        from auto_sketch import format_ocr_report
        report={}
        self.assertEqual(ocr_numbers(np.zeros((10,10),dtype=bool),None,diagnostics=report),[])
        self.assertEqual(report['status'],'not_installed')
        self.assertIn('nie został uruchomiony',format_ocr_report(report))
        run.assert_not_called()

    @patch('auto_sketch.subprocess.run')
    def test_missing_english_language_is_reported(self,run):
        run.side_effect=[subprocess.CompletedProcess([],0,b'tesseract 5.5.0',b''),subprocess.CompletedProcess([],0,b'List of available languages (1):\npol\n',b'')]
        report={}
        self.assertEqual(ocr_numbers(np.zeros((10,10),dtype=bool),Path('/tmp/tesseract-test'),diagnostics=report),[])
        self.assertEqual(report['status'],'missing_eng')
        self.assertEqual(run.call_count,2)
        self.assertIn('eng.traineddata',report['errors'][0])

    @patch('auto_sketch.subprocess.run')
    def test_windows_launch_error_is_not_silently_ignored(self,run):
        run.side_effect=OSError('Zasady kontroli aplikacji zablokowały ten plik')
        report={}
        self.assertEqual(ocr_numbers(np.zeros((10,10),dtype=bool),Path('/tmp/tesseract-test'),diagnostics=report),[])
        self.assertEqual(report['status'],'launch_failure')
        self.assertIn('zablokowały',report['errors'][0])

    @patch('auto_sketch.subprocess.run')
    def test_successful_ocr_with_no_digits_is_reported(self,run):
        run.side_effect=[subprocess.CompletedProcess([],0,b'tesseract 5.5.0',b''),subprocess.CompletedProcess([],0,b'List of available languages (1):\neng\n',b'')]+[subprocess.CompletedProcess([],0,b'level\ttext\n',b'') for _ in range(4)]
        report={}
        self.assertEqual(ocr_numbers(np.zeros((10,10),dtype=bool),Path('/tmp/tesseract-test'),diagnostics=report),[])
        self.assertEqual(report['status'],'no_digits')
        self.assertEqual(report['successful'],4)

    @patch('auto_sketch.subprocess.run')
    def test_nonzero_ocr_exit_is_reported(self,run):
        run.side_effect=[subprocess.CompletedProcess([],0,b'tesseract 5.5.0',b''),subprocess.CompletedProcess([],0,b'List of available languages (1):\neng\n',b'')]+[subprocess.CompletedProcess([],1,b'',b'Failed loading language eng') for _ in range(4)]
        report={}
        self.assertEqual(ocr_numbers(np.zeros((10,10),dtype=bool),Path('/tmp/tesseract-test'),diagnostics=report),[])
        self.assertEqual(report['status'],'run_failure')
        self.assertEqual(report['successful'],0)
        self.assertEqual(len(report['errors']),4)

    def test_unread_number_targets_actual_arrow_line(self):
        from auto_sketch import unread_dimension_lines
        points=[(100,100),(400,100),(400,300),(100,300)]
        mask=np.zeros((420,500),dtype=bool)
        mask[330,100:401]=True
        # Dwa groty wzdłuż rzeczywistej linii wymiarowej.
        for offset in range(2,10):
            half=max(2,offset//2)
            mask[330-half:331+half,100+offset]=True
            mask[330-half:331+half,400-offset]=True
        # Krawędź konturu nie powinna być traktowana jako napis wymiarowy.
        mask[100,100:401]=True
        accepted,questions=match_dimensions(points,mask,[])
        self.assertEqual(accepted,[])
        self.assertEqual(len(questions),1)
        question=questions[0]
        self.assertEqual(question['source'],'unread_label')
        self.assertIsNone(question['value'])
        self.assertAlmostEqual(question['image_line'][1],330,delta=2)
        self.assertEqual(question['start'],3)
        self.assertEqual(question['end'],2)

    def test_uncertain_ocr_keeps_label_and_line_location(self):
        points=[(100,100),(400,100),(400,300),(100,300)]
        mask=np.zeros((420,500),dtype=bool);mask[330,100:401]=True
        _,questions=match_dimensions(points,mask,[OCRWord(300,55,(235,340,265,355))])
        self.assertEqual(questions[0]['label_bounds'],(235,340,265,355))
        self.assertEqual(questions[0]['image_line'],(100.,330.,400.,330.))
        self.assertEqual(questions[0]['source'],'uncertain_ocr')

    def test_question_crop_is_real_source_pixels(self):
        from auto_sketch import question_crop
        png=drawing([(50,50),(450,50),(450,350),(50,350)])
        crop=question_crop(png,dict(label_bounds=(50,50,80,70)))
        pix=fitz.Pixmap(crop)
        self.assertGreater(pix.width,0);self.assertLess(pix.width,500)
        self.assertTrue(any(value<100 for value in pix.samples))
        self.assertIsNone(question_crop(png,{}))

    def test_zoomable_question_crop_keeps_both_line_ends_and_original_context(self):
        from copy import deepcopy
        from auto_sketch import question_crop
        with fitz.open() as doc:
            page=doc.new_page(width=500,height=420)
            # Dwa oryginalne oznaczenia poza linią muszą pozostać czytelne.
            page.draw_rect(fitz.Rect(40,180,60,185),color=(0,0,0),fill=(0,0,0))
            page.draw_rect(fitz.Rect(440,180,460,185),color=(0,0,0),fill=(0,0,0))
            png=page.get_pixmap(alpha=False).tobytes('png')
        question=dict(image_line=(50,200,450,200),label_bounds=(235,235,265,250),value=None)
        original=deepcopy(question)
        pix=fitz.Pixmap(question_crop(png,question,include_line=True))
        pixels=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        self.assertEqual((pix.width,pix.height),(461,111))
        # X źródła 40/440 odpowiada X 20/420 w wycinku o początku (20,170).
        self.assertTrue((pixels[10:15,20:40,:3]<30).all())
        self.assertTrue((pixels[10:15,420:440,:3]<30).all())
        blue=(pixels[:,:,0]<50)&(pixels[:,:,1]<150)&(pixels[:,:,2]>220)
        self.assertTrue(blue[29:32,29:32].any())
        self.assertTrue(blue[29:32,429:432].any())
        self.assertEqual(question,original)
        # Bez opcji pozostaje dotychczasowy, mały wycinek samego napisu.
        self.assertLess(fitz.Pixmap(question_crop(png,question)).width,200)

    def test_zoomable_fallback_line_crop_clips_to_source_and_keeps_full_span(self):
        from auto_sketch import question_crop
        png=drawing([(50,50),(450,50),(450,350),(50,350)])
        question=dict(image_line=(260,10,260,410),source='missing_relation')
        pix=fitz.Pixmap(question_crop(png,question,include_line=True))
        self.assertEqual((pix.width,pix.height),(61,420))
        pixels=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        self.assertGreater(pixels[10,30,2],220)
        self.assertLess(pixels[10,30,0],50)
        self.assertGreater(pixels[409,30,2],220)
        self.assertLess(pixels[409,30,0],50)
        self.assertEqual(question['image_line'],(260,10,260,410))
        self.assertIsNone(question_crop(png,dict(image_line=(900,900,1000,1000)),include_line=True))
        self.assertIsNone(question_crop(png,dict(image_line=(0,0,float('nan'),100)),include_line=True))
        self.assertIsNone(question_crop(png,dict(label_bounds=(0,0)),include_line=True))

    def test_fallback_crop_keeps_source_vertices_beside_projected_line(self):
        from copy import deepcopy
        from auto_sketch import question_crop
        with fitz.open() as doc:
            page=doc.new_page(width=800,height=900)
            # Końce relacji X/Y są na obrysie, obok rzutowanej linii.
            page.draw_rect(fitz.Rect(478,336,482,340),color=(0,0,0),fill=(0,0,0))
            page.draw_rect(fitz.Rect(654,812,658,816),color=(0,0,0),fill=(0,0,0))
            png=page.get_pixmap(alpha=False).tobytes('png')
        question=dict(image_line=(568,338,568,814),context_bounds=(480,338,656,814))
        original=deepcopy(question)
        pix=fitz.Pixmap(question_crop(png,question,include_line=True))
        self.assertEqual((pix.width,pix.height),(237,537))
        pixels=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        self.assertTrue((pixels[28:32,28:32,:3]<30).all())
        self.assertTrue((pixels[504:508,204:208,:3]<30).all())
        # context_bounds nie jest napisem OCR i nie tworzy pomarańczowej ramki.
        orange=(pixels[:,:,0]>220)&(pixels[:,:,1]>70)&(pixels[:,:,1]<190)&(pixels[:,:,2]<60)
        self.assertFalse(orange.any())
        self.assertEqual(question,original)

    def test_dimension_crop_connects_external_line_to_named_vertices(self):
        from auto_sketch import question_crop
        from copy import deepcopy
        png=drawing([(50,50),(300,50),(300,350),(50,350)])
        question=dict(image_line=(430,50,430,350),witness_points=[(300,50,'P2'),(300,350,'P3')])
        original=deepcopy(question)
        pix=fitz.Pixmap(question_crop(png,question,include_line=True))
        self.assertEqual((pix.width,pix.height),(191,361))
        pixels=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        # Źródło(300,50) w wycinku(270,20): niebieski okrąg przy wierzchołku
        # i przerywane połączenie aż do pionowej linii wymiarowej.
        blue=(pixels[:,:,0]<80)&(pixels[:,:,1]<170)&(pixels[:,:,2]>200)
        self.assertTrue(blue[25:36,25:36].any())
        self.assertTrue(blue[29:32,50:140].any())
        self.assertGreater(blue[40:300,159:162].sum(),100)
        self.assertEqual(question,original)


if __name__=='__main__':
    unittest.main()
