import unittest
import numpy as np
from coin_receipt import coin_receipt,TITLE
from pathlib import Path
import cv2
from onboarding import template
from state_finder import get_state

class CoinReceiptTests(unittest.TestCase):
    def frame(self):
        frame=np.full((720,1280,3),(10,75,180),np.uint8)
        for encoded,x,y in [(TITLE,482,96)]:
            glyph=template(encoded,720)
            frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
        frame[175:535,420:845]=cv2.cvtColor(cv2.imread(str(Path(__file__).parent/'fixtures/coin_pile.png')),cv2.COLOR_BGR2RGB)
        return frame

    def test_coin_reveal_routes_to_existing_bounded_handler(self):
        self.assertTrue(coin_receipt(self.frame()))
        self.assertEqual(get_state(self.frame()),'reward_received')

    def test_title_icon_background_and_visibility_are_all_required(self):
        for region in [(slice(90,160),slice(None)),(slice(175,535),slice(420,845)),(slice(None),slice(0,260))]:
            frame=self.frame();frame[region]=0
            self.assertFalse(coin_receipt(frame))
        self.assertFalse(coin_receipt((self.frame()*.4).astype(np.uint8)))
        self.assertFalse(coin_receipt(None))
