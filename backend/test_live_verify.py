import requests
import json

# 1. Login
login_res = requests.post('http://127.0.0.1:8001/api/auth/login', json={'email': 'admin@leamss.com', 'password': 'Admin@123'})
print('Login status:', login_res.status_code)
token = login_res.json().get('token')
headers = {'Authorization': f'Bearer {token}'}

# 2. Test Resume Extract (Rajesh Kumar - Software)
with open('backend/test_data/sample_resume.txt', 'rb') as f:
    files = {'file': ('sample_resume.txt', f, 'text/plain')}
    ext_res = requests.post('http://127.0.0.1:8001/api/eligibility/profiles/resume-extract', files=files, headers=headers)
print('Extract status:', ext_res.status_code)
ext_data = ext_res.json()
print('Extracted Candidate:', ext_data.get('client_name'))
print('Age / DOB:', ext_data.get('primary_applicant', {}).get('age'), '/', ext_data.get('primary_applicant', {}).get('dob'))
print('Company Nature:', ext_data.get('company_nature'))
print('Employer:', ext_data.get('employer_name') or ext_data.get('work_history', [{}])[0].get('employer_name'))
print('Duty count:', len(ext_data.get('duty_bullets', [])))

# 3. Test Suggest Occupation
sug_payload = {
    'description': ext_data.get('roles_and_responsibilities') or 'Senior Software Engineer with 8 years of experience developing microservices and distributed cloud systems',
    'country_codes': ['AU'],
    'max_suggestions': 4,
    'qualification': ext_data.get('qualification'),
    'field_of_study': ext_data.get('field_of_study'),
    'years_experience_total': ext_data.get('primary_applicant', {}).get('years_experience_total', 8.0),
    'profile': ext_data,
}
sug_res = requests.post('http://127.0.0.1:8001/api/sales/ai/suggest-occupation', json=sug_payload, headers=headers)
print('Suggest status:', sug_res.status_code)
sug_data = sug_res.json()
for i, s in enumerate(sug_data.get('suggestions', [])):
    print(f"\n--- Suggestion #{i+1}: {s.get('code')} - {s.get('title')} [{s.get('confidence')}] ---")
    print("Assessing Body:", s.get('assessing_body'))
    print("Duty Alignment:", s.get('duty_alignment', {}).get('summary'))
    print("Matched Tasks:", s.get('duty_alignment', {}).get('matched_tasks'))
    print("Company Alignment:", s.get('company_alignment', {}).get('summary'))
    print("Age Evaluation:", s.get('age_evaluation', {}).get('summary'))
    print("Deduction Summary:", s.get('skills_assessment', {}).get('deduction_summary'))
    print("Assessment Outcome:", s.get('skills_assessment', {}).get('assessment_outcome'))
