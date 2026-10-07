import requests
import json
import sys

# Set stdout to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

login_res = requests.post('http://127.0.0.1:8001/api/auth/login', json={'email': 'admin@leamss.com', 'password': 'Admin@123'})
token = login_res.json().get('token')
headers = {'Authorization': f'Bearer {token}'}

with open('test_data/sample_resume_chef.txt', 'rb') as f:
    r = requests.post('http://127.0.0.1:8001/api/eligibility/profiles/resume-extract', files={'file': f}, headers=headers)
data = r.json()

print("TOP KEYS:", list(data.keys()))
print("CLIENT NAME:", data.get('client_name') or data.get('name'))
pa = data.get('primary_applicant', {})
print("PA KEYS:", list(pa.keys()))
print("PA PERSONAL:", pa.get('personal'))
print("PA PROFESSIONAL:", pa.get('professional'))
print("PA WORK HISTORY COUNT:", len(pa.get('work_history', [])))
if pa.get('work_history'):
    for i, w in enumerate(pa['work_history']):
        print(f"\nWork #{i+1}:")
        print("  Employer:", w.get('employer_name') or w.get('employer'))
        print("  Designation:", w.get('job_title') or w.get('designation'))
        print("  Nature:", w.get('company_nature') or w.get('nature_of_company'))
        print("  Duties count:", len(w.get('duty_bullets', [])))
        for b in w.get('duty_bullets', []):
            print("    * ", b)
