import tempfile,json,zipfile
from pathlib import Path
from training_capture import TrainingSession
from training_models import model_catalog,normalize_names
root=Path(tempfile.mkdtemp(prefix='annotation-',dir='../'))
catalog=model_catalog();assert len(catalog['classes'])==7
assert normalize_names(str({0:str({0:'gas'}),1:str({1:'bush'})}))==['gas','bush']
s=TrainingSession('qa','qa',root);(root/'images').mkdir()
for i in range(2):
 (root/'images'/f'f{i}.jpg').write_bytes(b'fixture'+bytes([i]));s.add_frame(f'f{i}.jpg',1280,720)
boxes=[{'cls':name,'x1':10+i*100,'y1':20,'x2':80+i*100,'y2':100} for i,name in enumerate(catalog['classes'])]
r=s.set_boxes('f0.jpg',boxes,True,0);assert len(r['boxes'])==7 and r['revision']==1
stored=json.loads((root/'session.json').read_text());assert len(stored['frames'][0]['boxes'])==7
for invalid in [dict(boxes[0],cls='invented'),dict(boxes[0],x1=float('nan')),dict(boxes[0],x2=11)]:
 try:s.set_boxes('f0.jpg',[invalid],True,1);raise AssertionError('invalid accepted')
 except ValueError:pass
 assert len(s._frame('f0.jpg')['boxes'])==7
try:s.set_boxes('f0.jpg',[],True,0);raise AssertionError('conflict accepted')
except ValueError:pass
try:s.export_zip();raise AssertionError('unchecked export')
except ValueError:pass
s.set_boxes('f1.jpg',boxes,True,0)
with zipfile.ZipFile(s.export_zip()) as z:
 manifest=json.loads(z.read('model_manifest.json'));assert manifest['classes']==catalog['classes']
 for m in catalog['models']:
  prefix='datasets/'+Path(m['file']).stem+'/'
  yaml=z.read(prefix+'data.yaml').decode();assert json.dumps(dict(enumerate(m['classes']))) in yaml
  labels=[n for n in z.namelist() if n.startswith(prefix+'labels/')]
  for name in labels:
   lines=z.read(name).decode().splitlines()
   expected=list(range(len(m['classes'])))
   if m['file']=='gasDetector.onnx':expected.append(m['classes'].index('bush'))
   assert sorted(int(line.split()[0]) for line in lines)==sorted(expected)
   assert all(0<=float(v)<=1 for line in lines for v in line.split()[1:])

s.add_frame('skip.jpg',1280,720);(root/'images'/'skip.jpg').write_bytes(b'ignore-this-fixture');s.set_boxes('skip.jpg',[],True,0,True)
with zipfile.ZipFile(s.export_zip()) as z:
 assert not any(n.endswith('/skip.jpg') for n in z.namelist())
 assert 'skip.jpg' in json.loads(z.read('model_manifest.json'))['excluded_frames']

s.meta['frames']=[{'file':str(i)} for i in range(37)];s.meta['frame_count']=10;s.select_frames();kept=s.kept_frames();assert len(kept)==10 and kept[0]['file']=='0' and kept[-1]['file']=='36'

legacy=root/'legacy';legacy.mkdir();legacy_frames=[{'file':'legacy.jpg','w':1280,'h':720,'boxes':[boxes[0]],'checked':True}]
(legacy/'session.json').write_text(json.dumps({'classes':['gas','bush','wall','close_bush'],'frames':legacy_frames}))
loaded=TrainingSession('qa','legacy',legacy);assert len(loaded.meta['classes'])==7 and loaded.meta['frames'][0]['checked'] is False and len(loaded.meta['frames'][0]['boxes'])==1

out={'classes':catalog['classes'],'models':catalog['models'],'checks':['legacy review flags reset while boxes remain intact','7-class persistence','malformed ONNX gas names recovered','invalid boxes reject without losing saved labels','revision conflicts reject','unchecked export rejects','all four per-model class IDs preserved','normalized YOLO coordinates','uniform full-battle sampling','excluded frames absent from every exported dataset']}
Path('../../outputs/xlamBOT-training-tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=True,indent=2))
