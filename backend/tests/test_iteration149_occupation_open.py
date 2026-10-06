"""Iteration 149 — Verify _occupation_open_map derives occupation-open from SOL list membership.

Rule (Home Affairs Skilled Occupation List):
  * MLTSSL         -> open for 189, 190, 491
  * STSOL / CSOL   -> open for 190, 491 (NOT 189)
  * ROL            -> open for 491 only

Also covers regression scenarios for the primary occupation used by bulk pre-assessment reports.
"""
import os
import sys

# Make backend importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routers.assessment_reports import _occupation_open_map  # noqa: E402


class TestOccupationOpenMapUnit:
    """Direct unit-level tests on the derivation function."""

    def test_mltssl_all_open(self):
        doc = {"visa_pathways": {"pathway_lists": ["MLTSSL"]}}
        out = _occupation_open_map(doc)
        assert out["189"] is True
        assert out["190"] is True
        assert out["491"] is True

    def test_stsol_190_and_491_open_189_closed(self):
        doc = {"visa_pathways": {"pathway_lists": ["STSOL"]}}
        out = _occupation_open_map(doc)
        assert out["189"] is False
        assert out["190"] is True
        assert out["491"] is True

    def test_csol_only_via_visa_eligibility_derives_190_491_open_189_unknown(self):
        """611211 Insurance Agent case: no top-level pathway_lists, only visa_eligibility for
        482/186/494 all list=CSOL. Expect 189=None (unknown), 190/491=True."""
        doc = {
            "visa_pathways": {
                "visa_eligibility": [
                    {"visa_subclass": "482", "list": "CSOL", "eligible": True},
                    {"visa_subclass": "186", "list": "CSOL", "eligible": True},
                    {"visa_subclass": "494", "list": "CSOL", "eligible": True},
                ]
            }
        }
        out = _occupation_open_map(doc)
        # 189 stays None (unknown) since CSOL is not on MLTSSL and no explicit 189 entry
        assert out["189"] is None
        assert out["190"] is True
        assert out["491"] is True

    def test_rol_only_491_open(self):
        doc = {"visa_pathways": {"pathway_lists": ["ROL"]}}
        out = _occupation_open_map(doc)
        assert out["189"] is False
        assert out["190"] is False
        assert out["491"] is True

    def test_explicit_visa_eligibility_overrides_derived(self):
        """Explicit 189 eligible=False on an MLTSSL occupation should override derivation."""
        doc = {
            "visa_pathways": {
                "pathway_lists": ["MLTSSL"],
                "visa_eligibility": [
                    {"visa_subclass": "189", "list": "MLTSSL", "eligible": False},
                ],
            }
        }
        out = _occupation_open_map(doc)
        assert out["189"] is False
        assert out["190"] is True
        assert out["491"] is True

    def test_empty_doc_all_none(self):
        out = _occupation_open_map({})
        assert out == {"189": None, "190": None, "491": None}

    def test_mixed_visa_eligibility_lists_fold_into_derivation(self):
        """A 190 entry marked STSOL with eligible=True should keep 190 True and derive 491 True."""
        doc = {
            "visa_pathways": {
                "visa_eligibility": [
                    {"visa_subclass": "190", "list": "STSOL", "eligible": True},
                ]
            }
        }
        out = _occupation_open_map(doc)
        assert out["190"] is True
        # 491 is derived True from STSOL list membership
        assert out["491"] is True
        # 189 is not on the list -> None (unknown since no explicit 189 entry)
        assert out["189"] is None
