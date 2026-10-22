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


if __name__=='__main__':
    unittest.main()
