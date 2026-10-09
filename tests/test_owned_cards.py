import unittest
from unittest.mock import patch
import numpy as np
import owned_cards as c
import trophy_reader as reader


class OwnedCardTests(unittest.TestCase):
    def grid(self, w=1280, h=720):
        frame=np.full((h,w,3),(15,110,245),np.uint8)
        # Large left unlock tile; owned cards begin to its right.
        frame[round(h*.15):round(h*.94),round(w*.08):round(w*.39)]=(30,230,20)
        glyph=c._badge(h)
        for x,y in [(w*.49,h*.36),(w*.76,h*.36),(w*.49,h*.66)]:
            x,y=round(x),round(y)
            frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph[:,:,None]
        return frame

    def test_unlock_tile_does_not_receive_first_card_tap(self):
        for w,h in [(1280,720),(1920,1080),(960,540)]:
            frame=self.grid(w,h)
            point,anchor=c.resolved_card(frame,(510,300))
            self.assertIsNotNone(anchor)
            self.assertGreater(point[0],900)
            self.assertLess(point[0],1100)
            self.assertLess(point[1],500)
            # A calibrated point on the first owned card remains untouched.
            self.assertEqual(c.resolved_card(frame,(1100,300)),((1100,300),None))

    def test_no_badge_retains_legacy_calibration(self):
        frame=np.full((720,1280,3),60,np.uint8)
        self.assertIsNone(c.first_owned_card(frame))
        self.assertEqual(c.resolved_card(frame,(510,300)),((510,300),None))

    def test_fallback_ocr_reads_selected_card_instead_of_left_tile(self):
        frame=self.grid()
        anchor=c.first_owned_card(frame)
        name,trophies=c.reading_regions(frame,anchor)
        with patch.object(reader,'OCR_AVAILABLE',True),patch.object(reader,'_known_brawler_names',return_value=['shelly']),patch.object(reader,'_read_region_text',return_value='SHELLY') as text,patch.object(reader,'_read_region_digits',return_value=35) as digits:
            self.assertEqual(reader.read_card(frame,anchor=anchor),{'brawler':'shelly','trophies':35})
        self.assertEqual(text.call_args.args[1],name)
        self.assertEqual(digits.call_args.args[1],trophies)
        self.assertGreater(name[0],900)
        self.assertGreater(trophies[0],900)
