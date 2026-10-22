import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from sketch import LABELS
from sketch_ai import read_sketch, validate_reading, ENDPOINT, NoRedirect


def proposal():
    fields = {key: dict(value=None, status='absent', evidence='Brak wymiaru na szkicu.') for key in LABELS}
    for key, value in dict(width=440, height=160, top=30, left=30, right=60).items():
        fields[key] = dict(value=value, status='certain', evidence=f'Zapis {value} przy strzałkach odpowiedniego wymiaru.')
    return dict(kind='U', units='mm', dimensions=fields, notes=['Sprawdź wszystkie wartości przed zatwierdzeniem.'])


class Response(io.BytesIO):
    pass


class SketchAITests(unittest.TestCase):
    def test_only_explicit_certain_dimensions_transferred(self):
        data = proposal()
        data['dimensions']['height'] = dict(value=190, status='unclear', evidence='Nie wiadomo, czy 160 to wymiar wewnętrzny.')
        reading = validate_reading(data)
        self.assertNotIn('height', reading.dimensions)
        self.assertNotIn('inner_height', reading.dimensions)
        self.assertEqual(reading.dimensions['width'], 440)
        self.assertIn('Nie wiadomo', reading.report)

    def test_unknown_units_or_shape_does_not_fill_values(self):
        for changes in (dict(units='unknown'), dict(kind='Nieznany')):
            self.assertEqual(validate_reading(dict(proposal(), **changes)).dimensions, {})

    def test_invalid_values_not_accepted(self):
        for value in (float('nan'), float('inf'), -1, True, '440'):
            data = proposal()
            data['dimensions']['width']['value'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_reading(data)
        data = proposal()
        data['dimensions']['width']['evidence'] = ''
        with self.assertRaises(ValueError):
            validate_reading(data)

    @patch('sketch_ai.urllib.request.build_opener')
    def test_request_and_structured_response(self, opener):
        api = dict(status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(proposal()))])])
        opener.return_value.open.return_value = Response(json.dumps(api).encode())
        reading = read_sketch(b'\x89PNG\r\n\x1a\nexample', 'sk-test-key-never-real')
        self.assertEqual(reading.dimensions['height'], 160)
        request = opener.return_value.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.method, 'POST')
        self.assertFalse(body['store'])
        self.assertNotIn('sk-test-key-never-real', request.data.decode())
        self.assertTrue(body['text']['format']['strict'])
        self.assertEqual(body['input'][0]['content'][1]['detail'], 'high')
        self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 90)

    @patch('sketch_ai.urllib.request.build_opener')
    def test_auth_and_network_errors_do_not_echo_response_or_key(self, opener):
        for exc in (HTTPError(ENDPOINT, 401, 'private-key-do-not-show', {}, io.BytesIO(b'private-key-do-not-show')), URLError('private-key-do-not-show')):
            opener.return_value.open.side_effect = exc
            with self.assertRaises(ValueError) as error:
                read_sketch(b'\x89PNG\r\n\x1a\nexample', 'sk-test-key-never-real')
            self.assertNotIn('private-key', str(error.exception))
            self.assertNotIn('sk-test-key', str(error.exception))

    @patch('sketch_ai.urllib.request.build_opener')
    def test_incomplete_or_invalid_response_does_not_make_contour(self, opener):
        for api in (dict(status='incomplete', output=[]), dict(status='completed', output=[]), dict(status='completed', output=[dict(content=[dict(type='refusal')])]), dict(status='completed', output=[dict(content=[dict(type='output_text', text='not json')])])):
            opener.return_value.open.return_value = Response(json.dumps(api).encode())
            with self.subTest(api=api), self.assertRaises(ValueError):
                read_sketch(b'\x89PNG\r\n\x1a\nexample', 'sk-test-key-never-real')

    @patch('sketch_ai.urllib.request.build_opener')
    def test_bad_key_or_image_does_not_make_network_request(self, opener):
        for png, key in ((b'not png', 'sk-test-key-never-real'), (b'\x89PNG\r\n\x1a\n', ''), (b'\x89PNG\r\n\x1a\n', 'bad\nheader')):
            with self.assertRaises(ValueError):
                read_sketch(png, key)
        opener.assert_not_called()

    def test_redirect_is_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 307, 'redirect', {}, 'https://elsewhere.example'))


if __name__ == '__main__':
    unittest.main()
