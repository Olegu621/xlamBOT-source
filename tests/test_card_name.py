import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import trophy_reader as reader


class CardNameTests(unittest.TestCase):
    def test_white_letter_pass_removes_coloured_artwork(self):
        crop = np.full((28, 125, 3), (60, 200, 15), np.uint8)
        crop[:, :55] = (215, 70, 100)
        crop[6:22, 75:85] = (255, 255, 255)
        received = []
        ocr = SimpleNamespace(image_to_string=lambda image, **kw: received.append(image) or 'NITA')
        with patch.object(reader, '_crop', return_value=crop), patch.object(reader, 'pytesseract', ocr):
            self.assertEqual(reader._read_white_region_text(None, None), 'NITA')
        image = received[0]
        self.assertTrue(np.all(image[30:90, 30:200] == 255))
        self.assertLess(image[60, 340], 10)

    def test_empty_or_coloured_region_does_not_invoke_ocr(self):
        ocr = SimpleNamespace(image_to_string=lambda *a, **kw: self.fail('No white letters'))
        for crop in (None, np.full((28, 125, 3), (220, 60, 100), np.uint8)):
            with patch.object(reader, '_crop', return_value=crop), patch.object(reader, 'pytesseract', ocr):
                self.assertEqual(reader._read_white_region_text(None, None), '')

    def test_calibrated_name_fallback_requires_an_exact_known_name(self):
        for text, expected in [('NITA', 'nita'), ('N1TA', None), ('ANTTAY', None), ('NITA COLT', None)]:
            with self.subTest(text=text), patch.object(reader, '_known_brawler_names', return_value=['nita', 'colt']), \
                    patch.object(reader, '_calibrated_card_region', return_value=(1, 2, 3, 4)), \
                    patch.object(reader, '_read_region_text', return_value='ANTTAY'), \
                    patch.object(reader, '_read_white_region_text', return_value=text) as white:
                self.assertEqual(reader._read_card_name(None), expected)
                white.assert_called_once_with(None, (1, 2, 3, 4))


if __name__ == '__main__':
    unittest.main()
