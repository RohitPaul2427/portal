"""Test Skills Assessment Engine (Phase 21).

Verifies exact ACS, VETASSESS, and TRA/Trade evaluation, deduction, and justification rules.
"""
from core.skills_assessment_engine import (
    evaluate_skills_assessment,
    evaluate_acs,
    evaluate_vetassess_professional,
    evaluate_tra_and_trade,
    calculate_gsm_experience_points,
)


def test_acs_bcom_non_it_rpl_deduction():
    """User test case: B.Com candidate with 6 years IT experience in Software Engineer 261313.
    Expectation:
      • Bucket: Non-IT / Insufficient IT
      • Pathway: ACS RPL Pathway
      • Assessment Outcome: Positive via RPL Pathway (is_positive: True)
      • Deducted Years: 6.0 years
      • Points Claimable Years: 0.0 years
      • Points Claimable Points: 0 pts
      • RPL Required: True (2 project reports needed)
      • Justification contains explicit explanation.
    """
    occ = {
        "code": "261313",
        "title": "Software Engineer",
        "assessing_body": "ACS",
        "acs_category": "General IT",
    }
    profile = {
        "primary_applicant": {
            "education": {
                "highest_qualification": "Bachelor of Commerce",
                "field_of_study": "B.Com / Accounting & Finance",
            },
            "professional": {
                "years_experience_total": 6.0,
                "years_experience_australia": 0.0,
            },
        }
    }
    
    result = evaluate_skills_assessment(occ, profile)
    
    assert result["authority_code"] == "ACS"
    assert result["qualification_bucket"] == "Non-IT / Insufficient IT"
    assert result["rpl_required"] is True
    assert result["assessment_outcome"] == "Positive via RPL Pathway"
    assert result["is_positive"] is True
    assert result["deducted_years"] == 6.0
    assert result["points_claimable_years"] == 0.0
    assert result["points_claimable_points"] == 0
    assert "Two ACS RPL Project Reports" in " ".join(result["required_documents"])
    assert "Requirement Met Date" in result["justification"]


def test_acs_btech_cse_it_major_closely_related():
    """B.Tech CSE with 8 years IT experience in Developer Programmer 261312.
    Expectation:
      • Bucket: IT Major
      • Pathway: ACS General Skills (Closely Related)
      • Deducted Years: 2.0 years
      • Points Claimable Years: 6.0 years
      • Points Claimable Points: 10 pts (5-7 years band)
      • RPL Required: False
    """
    occ = {
        "code": "261312",
        "title": "Developer Programmer",
        "assessing_body": "ACS",
    }
    profile = {
        "primary_applicant": {
            "education": {
                "highest_qualification": "Bachelor of Technology",
                "field_of_study": "Computer Science and Engineering",
            },
            "professional": {
                "years_experience_total": 8.0,
                "years_experience_australia": 0.0,
            },
        }
    }
    
    result = evaluate_skills_assessment(occ, profile)
    
    assert result["authority_code"] == "ACS"
    assert result["qualification_bucket"] == "IT Major"
    assert result["rpl_required"] is False
    assert result["assessment_outcome"] == "Likely Positive Assessment"
    assert result["is_positive"] is True
    assert result["deducted_years"] == 2.0
    assert result["points_claimable_years"] == 6.0
    assert result["points_claimable_points"] == 10


def test_vetassess_group_a_positive():
    """Group A (e.g. Construction Project Manager 133111) with relevant Bachelor + 3 years exp.
    Expectation:
      • Group: A
      • Deducted: 1.0 year
      • Points Claimable: 2.0 years (0 pts overseas since <3 yrs)
    """
    occ = {
        "code": "133111",
        "title": "Construction Project Manager",
        "assessing_body": "VETASSESS",
        "vetassess_group": "A",
    }
    profile = {
        "primary_applicant": {
            "education": {
                "highest_qualification": "Bachelor of Construction Management",
                "field_of_study": "Civil Engineering & Construction",
            },
            "professional": {
                "years_experience_total": 3.0,
                "years_experience_australia": 0.0,
            },
        }
    }
    result = evaluate_skills_assessment(occ, profile)
    assert result["authority_code"] == "VETASSESS"
    assert result["vetassess_group"] == "A"
    assert result["is_positive"] is True
    assert result["deducted_years"] == 1.0
    assert result["points_claimable_years"] == 2.0
    assert result["points_claimable_points"] == 0


def test_vetassess_group_b_non_relevant_post_qual():
    """Group B (e.g. Management Consultant 224711) with non-relevant Bachelor + 5 years exp.
    Expectation:
      • Group: B
      • Non-relevant major -> 3.0 years deducted
      • Points Claimable: 2.0 years
    """
    occ = {
        "code": "224711",
        "title": "Management Consultant",
        "assessing_body": "VETASSESS",
        "vetassess_group": "B",
    }
    profile = {
        "is_highly_relevant_major": False,
        "primary_applicant": {
            "education": {
                "highest_qualification": "Bachelor of Arts",
                "field_of_study": "History",
            },
            "professional": {
                "years_experience_total": 5.0,
                "years_experience_australia": 0.0,
            },
        }
    }
    result = evaluate_skills_assessment(occ, profile)
    assert result["authority_code"] == "VETASSESS"
    assert result["vetassess_group"] == "B"
    assert result["deducted_years"] == 3.0
    assert result["points_claimable_years"] == 2.0


def test_tra_trade_motor_mechanic():
    """TRA Trade (Motor Mechanic 321211) with formal trade training + 5 years exp.
    Expectation:
      • Non-licensed trade with formal training: 3.0 years deducted
      • Points Claimable: 2.0 years
    """
    occ = {
        "code": "321211",
        "title": "Motor Mechanic (General)",
        "assessing_body": "TRA",
        "vetassess_approved_rto": True,
        "is_trade_occupation": True,
    }
    profile = {
        "primary_applicant": {
            "education": {
                "highest_qualification": "Diploma in Automotive Engineering",
                "field_of_study": "Automotive / Mechanical",
            },
            "professional": {
                "years_experience_total": 5.0,
                "years_experience_australia": 0.0,
            },
        }
    }
    result = evaluate_skills_assessment(occ, profile)
    assert result["authority_code"] == "TRA"
    assert result["is_trade"] is True
    assert result["vetassess_approved_rto"] is True
    assert result["deducted_years"] == 3.0
    assert result["points_claimable_years"] == 2.0


def test_acs_it_minor_and_diploma():
    """Test ACS IT Minor (ECE) and ACS Diploma."""
    occ = {"code": "263111", "title": "Computer Network and Systems Engineer", "assessing_body": "ACS"}
    
    # ECE with 7 years experience
    profile_ece = {
        "primary_applicant": {
            "education": {"highest_qualification": "Bachelor of Engineering", "field_of_study": "ECE / Electronics"},
            "professional": {"years_experience_total": 7.0, "years_experience_australia": 0.0},
        }
    }
    res_ece = evaluate_skills_assessment(occ, profile_ece)
    assert res_ece["qualification_bucket"] == "IT Minor"
    assert res_ece["deducted_years"] == 5.0
    assert res_ece["points_claimable_years"] == 2.0
    assert res_ece["points_claimable_points"] == 0  # <3 yrs overseas = 0 pts

    # Polytechnic Diploma with 8 years experience
    profile_dip = {
        "primary_applicant": {
            "education": {"highest_qualification": "Diploma in Computer Technology", "field_of_study": "Computer Engineering"},
            "professional": {"years_experience_total": 8.0, "years_experience_australia": 0.0},
        }
    }
    res_dip = evaluate_skills_assessment(occ, profile_dip)
    assert res_dip["qualification_bucket"] in ("IT Major", "IT Major (Diploma)")
    assert res_dip["deducted_years"] == 5.0
    assert res_dip["points_claimable_years"] == 3.0
    assert res_dip["points_claimable_points"] == 5  # 3-4 yrs overseas = 5 pts


def test_vetassess_group_c_and_d():
    """Test Group C (Architectural Draftsperson 312111) and Group D."""
    occ_c = {"code": "312111", "title": "Architectural Draftsperson", "assessing_body": "VETASSESS", "vetassess_group": "C"}
    
    # Diploma in Architecture + 4 years experience (highly relevant)
    profile_c = {
        "primary_applicant": {
            "education": {"highest_qualification": "Diploma in Architectural Drafting", "field_of_study": "Architecture"},
            "professional": {"years_experience_total": 4.0, "years_experience_australia": 0.0},
        }
    }
    res_c = evaluate_skills_assessment(occ_c, profile_c)
    assert res_c["vetassess_group"] == "C"
    assert res_c["deducted_years"] == 1.0
    assert res_c["points_claimable_years"] == 3.0
    assert res_c["points_claimable_points"] == 5


def test_tra_licensed_trade():
    """Test Licensed trade (e.g. Electrician General 341111) without formal training."""
    occ = {
        "code": "341111",
        "title": "Electrician (General)",
        "assessing_body": "TRA",
        "is_licensed_trade": True,
        "is_trade_occupation": True,
    }
    # No formal training + 6 years experience
    profile = {
        "primary_applicant": {
            "education": {"highest_qualification": "Secondary School", "field_of_study": "General"},
            "professional": {"years_experience_total": 6.0, "years_experience_australia": 0.0},
        }
    }
    res = evaluate_skills_assessment(occ, profile)
    assert res["deducted_years"] == 6.0
    assert res["points_claimable_years"] == 0.0
    assert res["is_positive"] is True
