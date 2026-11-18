"""Explicit opt-in DB smoke test. All synthetic data is rolled back, even on failure."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.auth.database import auth_engine
from app.workspaces.db import Store
from app.workspaces.schemas import WorkspaceInput
from app.workspaces.services.organizations import create_workspace
from app.routes.student import (search_classes, upcoming, self_enroll, PlannerTaskInput,
    create_planner_task, planner_groups, planner_details, update_planner_series, delete_planner_series)
from fastapi import HTTPException


def run():
    with auth_engine().connect() as conn:
        tx=conn.begin()
        try:
            db=Store(conn)
            owner=db.insert('app_users',full_name='Portal smoke owner',status='ACTIVE',user_type='OWNER',account_type='INDIVIDUAL')
            user=db.insert('app_users',full_name='Portal smoke student',status='ACTIVE',user_type='MEMBER',account_type='STUDENT')
            user.update(email=f'{uuid4()}@example.com',email_verified=True)
            workspace=create_workspace(db,owner,WorkspaceInput(name='Portal smoke workspace',workspace_type='INDIVIDUAL'))
            activity=db.insert('activities',workspace_id=workspace['id'],name='Maths',category='ACADEMIC')
            name=f'Student smoke {uuid4()}'
            program=db.insert('teaching_programs',workspace_id=workspace['id'],activity_id=activity['id'],name=name,
                              capacity=1,status='ACTIVE',default_meeting_url='https://example.com/private',student_discoverable=True)
            start=datetime.now(timezone.utc)+timedelta(days=1)
            session=db.insert('class_sessions',workspace_id=workspace['id'],program_id=program['id'],title='Maths',
                              starts_at=start,ends_at=start+timedelta(hours=1),delivery_mode='ONLINE',meeting_url='https://example.com/private',capacity=1)
            results=search_classes(name,'','ONLINE',0,user,db)['classes']
            assert len(results)==1 and 'meeting_url' not in results[0]
            assert not upcoming(user,db)['sessions']
            record=db.insert('students',workspace_id=workspace['id'],full_name=user['full_name'],email=user['email'],linked_user_id=user['id'])
            db.insert('session_participants',workspace_id=workspace['id'],program_id=program['id'],session_id=session['id'],student_id=record['id'],participation_kind='DIRECT')
            assert len(upcoming(user,db)['sessions'])==1  # Staff-added schedule is already visible.
            assert not self_enroll(program['id'],user,db)['already_enrolled']
            assert self_enroll(program['id'],user,db)['already_enrolled']
            agenda=upcoming(user,db)
            assert len(agenda['sessions'])==1 and agenda['sessions'][0]['id']==session['id']
            assert len(agenda['classes'])==1
            assert not db.first('SELECT 1 FROM {s}.workspace_memberships WHERE user_id=:u',u=user['id'])
            outsider=db.insert('app_users',full_name='Other smoke student',status='ACTIVE',user_type='MEMBER',account_type='STUDENT')
            outsider.update(email=f'{uuid4()}@example.com',email_verified=True)
            assert not upcoming(outsider,db)['sessions']
            try: self_enroll(program['id'],outsider,db)
            except HTTPException as error: assert error.status_code==409
            else: raise AssertionError('Full class accepted enrollment')
            db.execute('UPDATE {s}.teaching_programs SET student_discoverable=false WHERE id=:p',p=program['id'])
            assert not search_classes(name,'','',0,user,db)['classes']
            plan = PlannerTaskInput(title='Study series', starts_at=start, repeat='WEEKLY', repeat_count=3)
            saved = create_planner_task(plan,user,db)
            groups = planner_groups(user,db)['groups']
            assert len(groups)==1 and groups[0]['count']==3
            series_id = saved['series_id']
            details = planner_details(series_id,user,db)['tasks']
            assert len(details)==3 and details[0]['recurrence']['repeat']=='WEEKLY'
            try: planner_details(series_id,outsider,db)
            except HTTPException as error: assert error.status_code==404
            else: raise AssertionError('Planner details leaked across accounts')
            edited = PlannerTaskInput(title='Edited series',starts_at=details[0]['starts_at'],
                                      duration_minutes=45,preserve_dates=True)
            update_planner_series(series_id,edited,user,db)
            updated = planner_details(series_id,user,db)['tasks']
            assert len(updated)==3 and all(row['title']=='Edited series' for row in updated)
            assert [row['starts_at'] for row in updated]==[row['starts_at'] for row in details]
            delete_planner_series(series_id,user,db)
            assert not planner_groups(user,db)['groups']
            db.execute('SET CONSTRAINTS ALL IMMEDIATE')
            print('Passed: discovery, private-link protection, self-enrollment, duplicate retry, upcoming, isolation, capacity, no staff membership; all synthetic data rolled back.')
        finally:
            tx.rollback()


if __name__=='__main__': run()
