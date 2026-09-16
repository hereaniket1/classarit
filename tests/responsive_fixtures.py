"""Render synthetic pages for browser layout checks; never imports the app or its DB."""
import json
import sys
from pathlib import Path
from datetime import datetime,timedelta,timezone,date
from types import SimpleNamespace
from jinja2 import Environment,FileSystemLoader,select_autoescape

ROOT=Path(__file__).resolve().parents[1]
output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
env=Environment(loader=FileSystemLoader(ROOT/'app/templates'),autoescape=select_autoescape())
user={'id':'owner','full_name':'Aniket Pathak','user_type':'OWNER'}
w={'id':'workspace','name':'Atrasnu Musical','workspace_type':'INDIVIDUAL','timezone':'Asia/Kolkata','owner_user_id':'owner'}
p={'id':'program','workspace_id':'workspace','name':'Piano Beginners','activity_id':'activity','program_kind':'COURSE','status':'ACTIVE','capacity':10,'level':None,'default_delivery_mode':'ONLINE','default_meeting_url':'https://example.com','default_duration_minutes':60,'students':12,'completed_sessions':8}
ss={'id':'session','program_id':'program','title':'Piano Beginners','starts_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'ends_at':(datetime.now(timezone.utc)+timedelta(days=1,hours=1)).isoformat(),'status':'SCHEDULED','delivery_mode':'ONLINE','meeting_url':'https://example.com','venue_id':None,'capacity':10}
snapshot={'workspace':w,'roles':['OWNER','TEACHER'],'membership_id':'member','members':[{'id':'member','full_name':'Aniket Pathak','status':'ACTIVE','roles':['OWNER','TEACHER']}],'activities':[{'id':'activity','name':'Piano'}],'venues':[{'id':'venue','name':'Music hall','address':'A long street address in Bengaluru, India'}],'spaces':[],'programs':[p],'program_teachers':[{'program_id':'program','membership_id':'member'}],'students':[{'id':'student','full_name':'Student With A Long Name','email':'a.long.student.email@example.com','phone':'+91 9999999999'}],'guardians':[],'student_guardians':[],'enrollments':[{'id':'enrollment','student_id':'student','program_id':'program','status':'ACTIVE'}],'sessions':[ss],'recurring_series':[],'session_teachers':[],'participants':[{'id':'participant','program_id':'program','session_id':'session','student_id':'student','participation_kind':'ENROLLMENT','status':'BOOKED'}],'attendance':[],'invitations':[],'entitlements':[],'bookings':[],'policy':{'teacher_cancellation_eligible':True,'student_absence_eligible':False,'validity_days':30,'minimum_notice_hours':0,'included_in_original_fee':True}}
card={**w,'programs':[p],'student_count':18,'teacher_count':3,'upcoming_sessions':8,'popular':[p],'most_used':[p]}
cards=[card,{**card,'id':'second','name':'Shanatrika','workspace_type':'INSTITUTE','popular':[],'most_used':[]},{**card,'id':'third','name':'Community Music and Sports Academy for Young Learners'}]
base={'request':None,'user':user,'csrf_token':'fixture-csrf','workspaces':[],'workspace':None,'invitation':None,'teacher_only':False,'google_ready':True}
def render(path,template,**extra):
    (output/(path+'.html')).write_text(env.get_template(template).render(**(base|extra)))
render('owner','account_dashboard.html',appowner=False,owned_workspaces=cards,assigned_workspaces=[],totals={'workspaces':3,'students':54,'classes':3,'active_teachers':3},is_owner=True,can_create=True)
render('teacher','account_dashboard.html',user={**user,'user_type':'MEMBER'},appowner=False,owned_workspaces=[],assigned_workspaces=[{**w,'roles':['TEACHER'],'can_manage':False,'classes':[{**p,'upcoming_sessions':1}]}],totals={},is_owner=False,can_create=False)
render('workspace','workspace.html',workspace=w,workspaces=[{**c,'roles':['OWNER','TEACHER']} for c in cards],owner_view=True)
render('onboarding','workspace.html')
render('invitation','workspace.html',invitation='fixture-token')
render('home','home.html')
render('login','login.html')
render('callback','auth/callback.html',success=False,message='Please try signing in again.')
(output/'snapshot.json').write_text(json.dumps(snapshot))
print('Rendered 8 synthetic pages; no database access')
