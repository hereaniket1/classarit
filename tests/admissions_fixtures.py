"""Synthetic UI fixtures; no DB imports or real account data."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

root = Path(__file__).resolve().parents[1]
out = root / '.cache' / 'admissions-review'
out.mkdir(parents=True, exist_ok=True)
env = Environment(loader=FileSystemLoader(root/'app/templates'), autoescape=select_autoescape())
base = dict(request=None, user=dict(id='fixture', full_name='Review Owner', user_type='OWNER', account_type='ORGANIZATION'),
    csrf_token='fixture-token', workspace=None, workspaces=[], invitation=None, teacher_only=False,
    display_role='OWNER', executive_access=True, google_ready=True, signup_enabled=True,
    email_verification_enabled=True, invite_request_enabled=True,
    terms={'title':'Review terms','body':'Plain text terms. <script>alert(1)</script>'})
for filename, template, extra in [
    ('login','login.html',{}),
    ('open-signup','login.html',{'invite_request_enabled':False}),
    ('home','home.html',{}),
    ('executive','executive_dashboard.html',{}),
    ('organization','workspace.html',{'account_type':'ORGANIZATION'}),
    ('reuse','workspace.html',{'account_type':'ORGANIZATION','business_profile':{'legal_name':'Review Academy'}}),
    ('individual','workspace.html',{'account_type':'INDIVIDUAL'}),
    ('google-profile','auth/google_profile.html',{'user':{**base['user'],'account_type':None}}),
]:
    (out/(filename+'.html')).write_text(env.get_template(template).render(**(base|extra)), encoding='utf-8')
print('Rendered eight synthetic pages:', out)
