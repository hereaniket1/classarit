"""Manual recurring save check; every new schedule is rolled back, no emails sent."""
from pathlib import Path
import sys,time
from datetime import date,time as local_time,timedelta
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.auth.database import auth_engine
from app.workspaces.db import Store
from app.workspaces.access import Access
from app.workspaces.schemas import RecurringSessionInput
from app.workspaces.services.scheduling import create_recurring
from app.services.notifications import _recipient_rows
from fastapi import HTTPException

def check():
 with auth_engine().connect() as conn:
  tx=conn.begin()
  try:
   db=Store(conn)
   program=db.first("SELECT * FROM {s}.teaching_programs WHERE status='ACTIVE' ORDER BY created_at DESC LIMIT 1")
   workspace=db.first('SELECT * FROM {s}.workspaces WHERE id=:w',w=program['workspace_id'])
   member=db.first("SELECT * FROM {s}.workspace_memberships WHERE workspace_id=:w AND user_id=:u AND status='ACTIVE'",w=workspace['id'],u=workspace['owner_user_id'])
   a=Access(db,workspace,member,{'OWNER','TEACHER'},{'id':workspace['owner_user_id']})
   payload=RecurringSessionInput(program_id=program['id'],client_request_id=uuid4(),start_date=date.today()+timedelta(days=1000),start_time=local_time(9),repeat_weekdays=['WED'],repeat_months=3,duration_minutes=60)
   started=time.monotonic()
   result=create_recurring(a,payload)
   _recipient_rows(a,[row['id'] for row in result['sessions']])
   elapsed=time.monotonic()-started
   assert 12<=result['count']<=14
   repeated=create_recurring(a,payload)
   assert repeated['replayed'] and repeated['series']['id']==result['series']['id']
   assert db.first('SELECT count(*) n FROM {s}.class_sessions WHERE recurring_series_id=:id',id=result['series']['id'])['n']==result['count']
   try:
    create_recurring(a,payload.model_copy(update={'client_request_id':uuid4()}))
    raise AssertionError('Overlap was accepted')
   except HTTPException as error:
    assert error.status_code==409
   print(f'Passed: {result["count"]} weekly sessions plus recipient lookup in {elapsed:.2f}s; duplicate retry returns original series; overlap rejected. Test changes rolled back, no emails sent.')
  finally: tx.rollback()
if __name__=='__main__':
 try: check()
 except Exception as error:
  print(type(error).__name__)
  diagnostic=getattr(getattr(error,'orig',None),'diag',None)
  if diagnostic: print(diagnostic.message_primary)
  raise SystemExit(1)
