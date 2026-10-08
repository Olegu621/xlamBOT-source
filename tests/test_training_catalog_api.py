import ast,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from flask import Flask,jsonify
import training_capture

class TrainingCatalogTests(unittest.TestCase):
 def test_real_sessions_route_uses_exported_class_catalog(self):
  source=Path('webui/app.py');tree=ast.parse(source.read_text('utf-8'))
  names=['_class_choices','training_sessions_list']
  nodes=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in names]
  for n in nodes:n.decorator_list=[]
  app=Flask('training-catalog-test');namespace={'training_capture':training_capture,'training_recorder':SimpleNamespace(all_sessions=lambda:[]),'jsonify':jsonify}
  exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),namespace)
  app.add_url_rule('/api/training/sessions',view_func=namespace['training_sessions_list'])
  catalog={'classes':['gas','custom'],'models':[{'file':'gas.onnx','classes':['gas','custom']}]}
  with patch('training_models.model_catalog',return_value=catalog):response=app.test_client().get('/api/training/sessions')
  self.assertEqual(response.status_code,200)
  self.assertEqual([c['value'] for c in response.json['classes']],['gas','custom'])
  self.assertEqual(response.json['classes'][1]['label'],'custom')
 def test_existing_session_class_ids_keep_their_order(self):
  catalog={'classes':['gas','wall'],'models':[{'file':'gas.onnx','classes':['gas']},{'file':'wall.onnx','classes':['wall']}]}
  with patch('training_models.model_catalog',return_value=catalog):choices=training_capture.class_choices(['wall','gas'])
  self.assertEqual([c['value'] for c in choices],['wall','gas'])
  self.assertEqual(choices[0]['models'],['wall.onnx'])
