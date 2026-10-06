import unittest
from unittest.mock import MagicMock,patch
from types import SimpleNamespace
from datetime import date,datetime,time,timezone,timedelta
from uuid import uuid4
from fastapi import HTTPException
from app.workspaces.schemas import RecurringSessionInput
from app.workspaces.services import scheduling

class RecurringBatchTests(unittest.TestCase):
 def setUp(self):
  self.teacher,self.student=uuid4(),uuid4()
  self.a=SimpleNamespace(id=uuid4(),allow=MagicMock(),member={'id':self.teacher},workspace={'timezone':'UTC'},db=MagicMock())
  self.program={'id':uuid4(),'name':'Test','program_kind':'COURSE'}
  self.p=RecurringSessionInput(program_id=self.program['id'],start_date=date.today()+timedelta(days=30),start_time=time(9),repeat_weekdays=['WED'],repeat_months=3,duration_minutes=60,student_ids=[self.student])
  start=datetime.combine(self.p.start_date,time(9),timezone.utc)
  self.defaults=(self.program,[self.teacher],start,start+timedelta(hours=1),'ONLINE','https://example.com',None,None,2)
  self.a.db.insert.return_value={'id':uuid4()}
 def run_case(self,existing=(),capacity=2):
  self.a.db.all.side_effect=[[],[{'id':self.student}],list(existing)]
  defaults=(*self.defaults[:-1],capacity)
  with patch.object(scheduling,'session_defaults',return_value=defaults):
   return scheduling.create_recurring(self.a,self.p)
 def test_batch_inserts_sessions_teachers_and_students(self):
  result=self.run_case()
  self.assertGreaterEqual(result['count'],12)
  self.assertEqual(self.a.db.insert_many.call_count,3)
  participants=self.a.db.insert_many.call_args_list[2].args[1]
  self.assertEqual(len(participants),result['count'])
  self.assertTrue(all(r['student_id']==self.student and r['participation_kind']=='DIRECT' for r in participants))
  self.assertEqual(self.a.db.all.call_count,3)
 def test_teacher_and_student_conflicts_fail_before_insert(self):
  for teacher_ids,student_ids in [([self.teacher],[]),([],[self.student])]:
   self.a.db.insert.reset_mock()
   other={'starts_at':datetime.now(timezone.utc),'ends_at':datetime.now(timezone.utc)+timedelta(days=365),'teacher_ids':teacher_ids,'student_ids':student_ids,'venue_id':None,'space_id':None}
   with self.assertRaises(HTTPException) as error:self.run_case([other])
   self.assertEqual(error.exception.status_code,409)
   self.a.db.insert.assert_not_called()
 def test_capacity_failure_leaves_no_series(self):
  self.p=self.p.model_copy(update={'student_ids':[self.student,uuid4(),uuid4()]})
  with self.assertRaises(HTTPException):self.run_case()
  self.a.db.insert.assert_not_called()
 def test_replay_does_not_create_or_revalidate_occurrences(self):
  self.p=self.p.model_copy(update={'client_request_id':uuid4()})
  import hashlib,json
  fingerprint=hashlib.sha256(json.dumps(self.p.model_dump(mode='json',exclude={'client_request_id'}),sort_keys=True).encode()).hexdigest()
  self.a.db.first.return_value={'id':uuid4(),'request_hash':fingerprint}
  self.a.db.all.return_value=[{'id':uuid4()}]
  result=scheduling.create_recurring(self.a,self.p)
  self.assertTrue(result['replayed'])
  self.a.db.insert.assert_not_called()
if __name__=='__main__':unittest.main()
