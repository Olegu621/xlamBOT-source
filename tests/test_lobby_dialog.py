import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np
import state_finder
from stage_manager import StageManager
from thinking_levels import ThinkingQuality

ROOT=Path(__file__).resolve().parents[1]

class LobbyDialogTests(unittest.TestCase):
    def test_connection_requires_caption_window_and_action(self):
        template=np.full((60,400,3),63,np.uint8)
        cv2.putText(template,'Connection lost',(8,43),cv2.FONT_HERSHEY_SIMPLEX,1.3,(245,245,245),3)
        for width,height in [(1920,1080),(1280,720)]:
            scaled=cv2.resize(template,(round(400*width/1920),round(60*height/1080)))
            frame=np.full((height,width,3),(0,80,200),np.uint8)
            frame[round(height*.35):round(height*.71),round(width*.25):round(width*.76)]=63
            x,y=round(width*.27),round(height*.38)
            frame[y:y+scaled.shape[0],x:x+scaled.shape[1]]=scaled
            with patch.object(state_finder,'load_template',return_value=scaled):
                self.assertIsNone(state_finder.connection_lost_retry_position(frame))
                frame[round(height*.60):round(height*.61),round(width*.29):round(width*.36)]=(110,220,220)
                point=state_finder.connection_lost_retry_position(frame)
                self.assertEqual(point,(round(width*618.5/1920),round(height*654.5/1080)))
                # A caption on a colourful results screen does not prove a modal.
                frame[round(height*.46):round(height*.58),round(width*.27):round(width*.7)]=(0,80,200)
                self.assertIsNone(state_finder.connection_lost_retry_position(frame))

    def test_counter_sync_has_no_mandatory_lobby_wait(self):
        manager=StageManager.__new__(StageManager);manager._lobby_synced=False
        events=[]
        manager._sleep_interruptible=lambda seconds:events.append(('sleep',seconds)) or False
        manager.sync_trophies_from_screen=lambda:events.append(('read',None))
        self.assertTrue(manager._sync_lobby_counters())
        self.assertEqual(events,[('read',None),('sleep',.12),('read',None)])
        manager._sync_lobby_counters();self.assertEqual(len(events),3)

    def test_30fps_without_compute_reserve_does_not_upgrade(self):
        q=ThinkingQuality('medium')
        for i in range(1800):q.observe(1/33,i/30,60)
        self.assertEqual(q.recommended,'medium')
        self.assertEqual(q.mode,'medium')
        self.assertEqual(q.snapshot()['target_fps'],20)

if __name__=='__main__':unittest.main()
