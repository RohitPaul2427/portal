import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import {
  ShieldCheck,
  Briefcase,
  KeyRound,
  UserCheck,
  Eye,
  EyeOff,
  Copy,
  Plus,
  RefreshCw,
  ExternalLink,
  Lock,
  Unlock,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  FileText,
  Users,
  UserCog,
  Check,
  X,
  HelpCircle,
  Shield,
  ShieldAlert,
  Layers,
  ArrowRightLeft,
  Info
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';
const API = `${BACKEND_URL}/api`;

const LIFECYCLE_STATES = [
  { value: 'intake', label: '1. Initial Intake' },
  { value: 'assessment', label: '2. Skills Assessment' },
  { value: 'document_gathering', label: '3. Document Gathering' },
  { value: 'lodgement_preparation', label: '4. Lodgement Preparation' },
  { value: 'lodged_awaiting_decision', label: '5. Lodged (Awaiting Decision)' },
  { value: 'decision_received', label: '6. Decision Received' },
  { value: 'post_decision', label: '7. Post-Decision & Settlement' }
];

const APPLICATION_TYPES = [
  { value: 'skills_assessment', label: 'Skills Assessment' },
  { value: 'eoi', label: 'EOI (Expression of Interest)' },
  { value: 'roi_nomination', label: 'State Nomination (ROI)' },
  { value: 'visa_lodgement', label: 'Visa Lodgement' },
  { value: 'other', label: 'Other Application' }
];

const MASTER_AUTHORITIES = [
  { value: 'SkillSelect', label: 'SkillSelect (Department of Home Affairs)' },
  { value: 'ACS', label: 'Australian Computer Society (ACS)' },
  { value: 'VETASSESS', label: 'VETASSESS' },
  { value: 'Engineers Australia', label: 'Engineers Australia (EA)' },
  { value: 'TRA', label: 'Trades Recognition Australia (TRA)' },
  { value: 'ANMAC', label: 'Nursing & Midwifery (ANMAC)' },
  { value: 'MedBA / AMC', label: 'Medical Board of Australia / AMC' },
  { value: 'CPA / CA ANZ / IPA', label: 'Accounting Assessing Authorities (CPA/CA/IPA)' },
  { value: 'NSW', label: 'New South Wales (NSW Investment)' },
  { value: 'VIC', label: 'Victoria (Live in Melbourne)' },
  { value: 'QLD', label: 'Queensland (Migration Queensland)' },
  { value: 'WA', label: 'Western Australia (Migration WA)' },
  { value: 'SA', label: 'South Australia (Skilled Migration SA)' },
  { value: 'TAS', label: 'Tasmania (Migration Tasmania)' },
  { value: 'ACT', label: 'Australian Capital Territory (Canberra Matrix)' },
  { value: 'NT', label: 'Northern Territory' },
  { value: 'other', label: 'Other Assessing Body / State' }
];

const GRANULAR_ACTION_OPTIONS = [
  { id: 'case.view', label: 'View Case Metadata & Applications', default: true },
  { id: 'document.preview', label: 'Preview Watermarked Documents', default: true },
  { id: 'document.upload', label: 'Upload Case Documents', default: false },
  { id: 'case.update', label: 'Update Case & Application Records', default: false },
  { id: 'document.download', label: 'Download Documents', default: false },
  { id: 'identifier.reveal', label: 'Reveal Protected Identifiers (Sensitive)', default: false },
  { id: 'credential.access', label: 'Access Credential Vault (Sensitive)', default: false }
];

export default function CaseWorkspacePanel({ caseData, onUpdate }) {
  const caseId = caseData?.id || caseData?.case_id;
  const [activeSubTab, setActiveSubTab] = useState('applications');
  const [loading, setLoading] = useState(false);
  const [overview, setOverview] = useState(null);
  const [applications, setApplications] = useState([]);
  const [vaultEntries, setVaultEntries] = useState([]);
  const [grants, setGrants] = useState([]);
  const [peopleData, setPeopleData] = useState(null);
  const [accessRequests, setAccessRequests] = useState([]);
  const [staffList, setStaffList] = useState([]);

  // Modals state
  const [newAppOpen, setNewAppOpen] = useState(false);
  const [appDetailsOpen, setAppDetailsOpen] = useState(false);
  const [selectedAppDetails, setSelectedAppDetails] = useState(null);

  // Identifier reveal state: mapping of app_id -> unmasked value
  const [revealModalOpen, setRevealModalOpen] = useState(false);
  const [selectedAppToReveal, setSelectedAppToReveal] = useState(null);
  const [revealReason, setRevealReason] = useState('');
  const [revealedIdentifiers, setRevealedIdentifiers] = useState({});

  // Vault state
  const [newVaultOpen, setNewVaultOpen] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [selectedVaultToCheckout, setSelectedVaultToCheckout] = useState(null);
  const [checkoutReason, setCheckoutReason] = useState('');
  const [checkedOutSecret, setCheckedOutSecret] = useState(null);

  // Grants state
  const [newGrantOpen, setNewGrantOpen] = useState(false);
  const [reassignOpen, setReassignOpen] = useState(false);
  const [reassignManagerId, setReassignManagerId] = useState('');
  const [reassignReason, setReassignReason] = useState('');

  // Access Requests state
  const [newRequestOpen, setNewRequestOpen] = useState(false);
  const [decisionModalOpen, setDecisionModalOpen] = useState(false);
  const [selectedRequestToDecide, setSelectedRequestToDecide] = useState(null);
  const [decisionType, setDecisionType] = useState('approved');
  const [decisionNotes, setDecisionNotes] = useState('');

  // Forms
  const [appForm, setAppForm] = useState({
    application_type: 'eoi',
    country: 'AU',
    authority_or_state: 'SkillSelect',
    subclass_or_stream: '189',
    reference_identifier: '',
    status: 'submitted',
    points_claimed: 80,
    submission_date: '',
    deadline: '',
    notes: ''
  });

  const [vaultForm, setVaultForm] = useState({
    portal_name: 'Department of Home Affairs - ImmiAccount',
    portal_url: 'https://online.immi.gov.au',
    username_or_id: '',
    secret_value: '',
    notes: ''
  });

  const [grantForm, setGrantForm] = useState({
    user_id: '',
    role_granted: 'reviewer',
    resource_scope: 'case',
    reason: '',
    expires_in_hours: 24,
    permissions: ['case.view', 'document.preview']
  });

  const [requestForm, setRequestForm] = useState({
    action: 'identifier.reveal',
    resource_id: '',
    resource_name: '',
    reason: '',
    requested_duration_hours: 24
  });

  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return { headers: { Authorization: `Bearer ${token}` } };
  };

  // Clear revealed unmasked identifiers when case switching
  useEffect(() => {
    setRevealedIdentifiers({});
    setCheckedOutSecret(null);
  }, [caseId]);

  const loadWorkspaceData = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    try {
      const [ovRes, appsRes, vaultRes, grantsRes, peopleRes, requestsRes, usersRes] = await Promise.all([
        axios.get(`${API}/case-workspace/${caseId}/overview`, getHeaders()).catch(() => ({ data: null })),
        axios.get(`${API}/case-workspace/${caseId}/applications`, getHeaders()).catch(() => ({ data: { applications: [] } })),
        axios.get(`${API}/case-workspace/${caseId}/vault`, getHeaders()).catch(() => ({ data: { credentials: [] } })),
        axios.get(`${API}/case-workspace/${caseId}/grants`, getHeaders()).catch(() => ({ data: { grants: [] } })),
        axios.get(`${API}/case-workspace/${caseId}/people-and-permissions`, getHeaders()).catch(() => ({ data: null })),
        axios.get(`${API}/case-workspace/${caseId}/access-requests`, getHeaders()).catch(() => ({ data: { requests: [] } })),
        axios.get(`${API}/users`, getHeaders()).catch(() => ({ data: [] }))
      ]);

      setOverview(ovRes?.data);
      setApplications(appsRes?.data?.applications || []);
      setVaultEntries(vaultRes?.data?.credentials || []);
      setGrants(grantsRes?.data?.grants || []);
      setPeopleData(peopleRes?.data);
      setAccessRequests(requestsRes?.data?.requests || []);
      if (usersRes?.data && Array.isArray(usersRes.data)) {
        setStaffList(usersRes.data.filter(u => u.role !== 'client'));
      }
    } catch (err) {
      console.error('Error loading workspace data:', err);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    loadWorkspaceData();
  }, [loadWorkspaceData]);

  // Overall Case Stage Change
  const handleLifecycleChange = async (newState) => {
    try {
      await axios.put(`${API}/case-workspace/${caseId}/lifecycle`, { lifecycle_state: newState }, getHeaders());
      toast.success('Overall case stage updated');
      loadWorkspaceData();
      if (onUpdate) onUpdate();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update case stage');
    }
  };

  // Duplicate Check for Applications
  const checkDuplicateApplication = (form) => {
    return applications.some(a =>
      a.application_type === form.application_type &&
      (a.authority_or_state || '').trim().toLowerCase() === (form.authority_or_state || '').trim().toLowerCase() &&
      (a.subclass_or_stream || '').trim().toLowerCase() === (form.subclass_or_stream || '').trim().toLowerCase()
    );
  };

  // Submit Application Form
  const handleCreateApplication = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/case-workspace/${caseId}/applications`, {
        ...appForm,
        case_id: caseId,
        client_id: caseData?.client_id || caseData?.client_user_id || 'client_ref'
      }, getHeaders());
      toast.success('Application registered in multi-register');
      setNewAppOpen(false);
      setAppForm({
        application_type: 'eoi',
        country: 'AU',
        authority_or_state: 'SkillSelect',
        subclass_or_stream: '189',
        reference_identifier: '',
        status: 'submitted',
        points_claimed: 80,
        submission_date: '',
        deadline: '',
        notes: ''
      });
      loadWorkspaceData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to register application');
    }
  };

  // Reveal Identifier (Audited with Toggle Hide)
  const handleRevealIdentifier = async () => {
    if (!revealReason.trim()) {
      toast.error('Operational justification is required to unmask sensitive identifier');
      return;
    }
    try {
      const res = await axios.post(`${API}/case-workspace/${caseId}/reveal-identifier`, {
        case_id: caseId,
        application_id: selectedAppToReveal.id,
        reason: revealReason
      }, getHeaders());

      setRevealedIdentifiers(prev => ({
        ...prev,
        [selectedAppToReveal.id]: res.data.reference_identifier
      }));
      setRevealModalOpen(false);
      setRevealReason('');
      toast.success('Identifier unmasked (Logged to immutable audit repository)');
    } catch (err) {
      const detail = err.response?.data?.detail;
      const errorMsg = typeof detail === 'string' ? detail : detail?.message || 'Failed to unmask identifier';
      toast.error(errorMsg);
    }
  };

  const handleHideIdentifier = (appId) => {
    setRevealedIdentifiers(prev => {
      const next = { ...prev };
      delete next[appId];
      return next;
    });
    toast.info('Identifier hidden from screen view');
  };

  // Vault Registration
  const handleCreateVault = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/case-workspace/${caseId}/vault`, {
        ...vaultForm,
        case_id: caseId
      }, getHeaders());
      toast.success('Government credential encrypted (AES-256 GCM) & stored in vault');
      setNewVaultOpen(false);
      setVaultForm({
        portal_name: 'Department of Home Affairs - ImmiAccount',
        portal_url: 'https://online.immi.gov.au',
        username_or_id: '',
        secret_value: '',
        notes: ''
      });
      loadWorkspaceData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to store credential');
    }
  };

  // Checkout Vault Credential (Audited)
  const handleCheckoutSecret = async () => {
    if (!checkoutReason.trim()) {
      toast.error('Operational justification is required for password checkout');
      return;
    }
    const credId = selectedVaultToCheckout?.id;
    if (!credId) {
      toast.error('No credential selected for checkout');
      return;
    }
    try {
      const res = await axios.post(`${API}/case-workspace/${caseId}/vault/${credId}/checkout`, {
        case_id: caseId,
        credential_id: credId,
        vault_id: credId,
        reason: checkoutReason
      }, getHeaders());
      setCheckedOutSecret(res.data.secret_value);
      toast.success('Secret decrypted (Cleartext checkout recorded in audit repository)');
    } catch (err) {
      try {
        const fallbackRes = await axios.post(`${API}/case-workspace/${caseId}/vault/checkout`, {
          case_id: caseId,
          credential_id: credId,
          vault_id: credId,
          reason: checkoutReason
        }, getHeaders());
        setCheckedOutSecret(fallbackRes.data.secret_value);
        toast.success('Secret decrypted (Cleartext checkout recorded in audit repository)');
      } catch (err2) {
        const detail = err2.response?.data?.detail || err.response?.data?.detail;
        const msg = typeof detail === 'string' ? detail : detail?.message || 'Failed to checkout credential';
        toast.error(msg);
      }
    }
  };

  // Issue Granular Temporary Grant
  const handleCreateGrant = async (e) => {
    e.preventDefault();
    if (!grantForm.permissions || grantForm.permissions.length === 0) {
      toast.error('Select at least one permitted action');
      return;
    }
    try {
      await axios.post(`${API}/case-workspace/${caseId}/grants`, {
        ...grantForm,
        case_id: caseId,
        duration_hours: grantForm.expires_in_hours
      }, getHeaders());
      toast.success('Temporary access grant issued');
      setNewGrantOpen(false);
      setGrantForm({
        user_id: '',
        role_granted: 'reviewer',
        resource_scope: 'case',
        reason: '',
        expires_in_hours: 24,
        permissions: ['case.view', 'document.preview']
      });
      loadWorkspaceData();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : detail?.message || 'Failed to issue grant');
    }
  };

  // Revoke Temporary Grant
  const handleRevokeGrant = async (grantId) => {
    try {
      await axios.post(`${API}/case-workspace/${caseId}/grants/${grantId}/revoke`, {
        reason: 'Revoked by authorized case administrator'
      }, getHeaders());
      toast.success('Access grant revoked immediately on backend');
      loadWorkspaceData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to revoke grant');
    }
  };

  // Reassign Case Manager (Reusing Canonical Workflow)
  const handleReassignManager = async (e) => {
    e.preventDefault();
    if (!reassignManagerId) {
      toast.error('Select a case manager');
      return;
    }
    try {
      const res = await axios.post(`${API}/case-workspace/${caseId}/reassign-manager`, {
        new_case_manager_id: reassignManagerId,
        reason: reassignReason || 'Administrative reassignment'
      }, getHeaders());
      toast.success(res.data.message || 'Case manager reassigned');
      setReassignOpen(false);
      setReassignManagerId('');
      setReassignReason('');
      loadWorkspaceData();
      if (onUpdate) onUpdate();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reassign case manager');
    }
  };

  // Submit Sensitive Access Request
  const handleCreateAccessRequest = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/case-workspace/${caseId}/access-requests`, {
        ...requestForm,
        case_id: caseId
      }, getHeaders());
      toast.success('Access request submitted for Case Head / Admin review');
      setNewRequestOpen(false);
      setRequestForm({
        action: 'identifier.reveal',
        resource_id: '',
        resource_name: '',
        reason: '',
        requested_duration_hours: 24
      });
      loadWorkspaceData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit access request');
    }
  };

  // Decide Access Request (Approve / Reject)
  const handleDecideRequest = async () => {
    if (!selectedRequestToDecide) return;
    try {
      await axios.post(`${API}/case-workspace/${caseId}/access-requests/${selectedRequestToDecide.id}/decision`, {
        decision: decisionType,
        notes: decisionNotes
      }, getHeaders());
      toast.success(`Access request marked as ${decisionType}`);
      setDecisionModalOpen(false);
      setSelectedRequestToDecide(null);
      setDecisionNotes('');
      loadWorkspaceData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update access request');
    }
  };

  const isDuplicateApp = newAppOpen && checkDuplicateApplication(appForm);
  const callerAuth = peopleData?.caller_authorization;

  return (
    <div className="space-y-6" data-testid="case-workspace-panel">
      {/* HEADER: CASE LIFECYCLE & EVIDENCE-BASED SECURITY INDICATORS */}
      <Card className="p-5 border-l-4 border-l-[#1F4D44] bg-white shadow-xs">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-gray-900 tracking-tight">Case Security & Multi-App Workspace</h3>
              <Badge className="bg-[#1F4D44] text-white text-xs">Case-Centred Controls</Badge>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Active Case: <span className="font-semibold text-slate-800">{caseData?.case_number || caseId}</span> • Client: <span className="font-semibold text-slate-800">{caseData?.client_name || 'Client'}</span>
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
            <div>
              <Label className="text-xs text-slate-600 block mb-1 font-medium">Overall Case Stage:</Label>
              <Select
                value={overview?.case?.lifecycle_state || caseData?.lifecycle_state || 'intake'}
                onValueChange={handleLifecycleChange}
              >
                <SelectTrigger className="w-[230px] h-9 text-xs bg-slate-50 border-slate-300">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LIFECYCLE_STATES.map((s) => (
                    <SelectItem key={s.value} value={s.value} className="text-xs">
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={loadWorkspaceData}
              disabled={loading}
              className="h-9 text-xs mt-auto"
            >
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>

        {/* EVIDENCE-BASED ACCESS & CONFIGURATION STATUS (NO DECORATIVE BADGES) */}
        <div className="mt-4 pt-3 border-t border-slate-200 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div className="p-2 rounded bg-slate-50 border border-slate-200">
            <div className="flex items-center gap-1.5 font-semibold text-slate-800">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
              <span>Access Control</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Role & Assignment Enforced (Deny-by-default)</p>
          </div>

          <div className="p-2 rounded bg-slate-50 border border-slate-200">
            <div className="flex items-center gap-1.5 font-semibold text-slate-800">
              <Lock className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
              <span>Credential Vault</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Local AES-256 GCM authenticated encryption</p>
          </div>

          <div className="p-2 rounded bg-slate-50 border border-slate-200">
            <div className="flex items-center gap-1.5 font-semibold text-slate-800">
              <FileText className="h-3.5 w-3.5 text-blue-600 shrink-0" />
              <span>Audit Repository</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Immutable checkout & unmask event logging</p>
          </div>

          <div className="p-2 rounded bg-slate-50 border border-slate-200">
            <div className="flex items-center gap-1.5 font-semibold text-slate-800">
              <Eye className="h-3.5 w-3.5 text-amber-600 shrink-0" />
              <span>Identifier Masking</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Masked by default; audited unmasking</p>
          </div>
        </div>
      </Card>

      {/* WORKSPACE SUB-NAVIGATION TABS */}
      <div className="flex border-b border-slate-200 gap-1 overflow-x-auto pb-px">
        <button
          onClick={() => setActiveSubTab('applications')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeSubTab === 'applications'
              ? 'border-[#1F4D44] text-[#1F4D44] bg-emerald-50/40 rounded-t'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Briefcase className="h-4 w-4" />
          Multi-Application Register
          <Badge variant="secondary" className="ml-1 text-xs px-1.5 py-0">
            {applications.length}
          </Badge>
        </button>

        <button
          onClick={() => setActiveSubTab('people')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeSubTab === 'people'
              ? 'border-[#1F4D44] text-[#1F4D44] bg-emerald-50/40 rounded-t'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Users className="h-4 w-4" />
          People & Permissions
          <Badge variant="secondary" className="ml-1 text-xs px-1.5 py-0">
            {grants.filter(g => !g.revoked_at && (!g.expires_at || new Date(g.expires_at) > new Date())).length} Grants
          </Badge>
        </button>

        <button
          onClick={() => setActiveSubTab('requests')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeSubTab === 'requests'
              ? 'border-[#1F4D44] text-[#1F4D44] bg-emerald-50/40 rounded-t'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <ShieldAlert className="h-4 w-4" />
          Access Requests & Approvals
          {accessRequests.filter(r => r.status === 'pending').length > 0 && (
            <Badge className="ml-1 bg-amber-500 text-white text-xs px-1.5 py-0">
              {accessRequests.filter(r => r.status === 'pending').length}
            </Badge>
          )}
        </button>

        <button
          onClick={() => setActiveSubTab('vault')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeSubTab === 'vault'
              ? 'border-[#1F4D44] text-[#1F4D44] bg-emerald-50/40 rounded-t'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <KeyRound className="h-4 w-4" />
          Credential Vault
          <Badge variant="secondary" className="ml-1 text-xs px-1.5 py-0">
            {vaultEntries.length}
          </Badge>
        </button>
      </div>

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 1: MULTI-APPLICATION REGISTER
          ───────────────────────────────────────────────────────────────────────────── */}
      {activeSubTab === 'applications' && (
        <Card className="p-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
            <div>
              <h4 className="font-bold text-gray-900 text-base">Multi-Application Register</h4>
              <p className="text-xs text-slate-500">
                Track distinct application streams (EOIs, State Nominations, Skills Assessments, Visa Lodgements). Sensitive identifiers are masked in list responses.
              </p>
            </div>
            <Button size="sm" onClick={() => setNewAppOpen(true)} className="bg-[#1F4D44] hover:bg-[#163832]">
              <Plus className="h-4 w-4 mr-1" /> Register Application
            </Button>
          </div>

          {applications.length === 0 ? (
            <div className="text-center py-10 bg-slate-50 rounded-lg border border-dashed border-slate-300">
              <Briefcase className="h-8 w-8 mx-auto text-slate-400 mb-2" />
              <p className="text-sm font-medium text-slate-700">No applications registered for this case</p>
              <p className="text-xs text-slate-500 mb-3">Add skills assessments, EOIs, state nominations, or visa lodgements.</p>
              <Button size="sm" variant="outline" onClick={() => setNewAppOpen(true)}>Register First Application</Button>
            </div>
          ) : (
            <div className="overflow-x-auto rounded border border-slate-200">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-100 text-slate-700 font-semibold uppercase tracking-wider text-[11px] border-b border-slate-200">
                  <tr>
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3">Authority / State</th>
                    <th className="py-2.5 px-3">Subclass</th>
                    <th className="py-2.5 px-3">Reference Identifier</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Points</th>
                    <th className="py-2.5 px-3">Submission Date</th>
                    <th className="py-2.5 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {applications.map((app) => {
                    const isRevealed = !!revealedIdentifiers[app.id];
                    const displayedRef = isRevealed ? revealedIdentifiers[app.id] : (app.masked_identifier || '—');

                    return (
                      <tr key={app.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3 px-3 font-semibold text-slate-900">
                          <span className="capitalize">{app.application_type?.replace('_', ' ')}</span>
                        </td>
                        <td className="py-3 px-3 text-slate-700 font-medium">{app.authority_or_state}</td>
                        <td className="py-3 px-3 text-slate-600">{app.subclass_or_stream || '—'}</td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1.5">
                            <span className={`font-mono text-xs px-2 py-0.5 rounded ${isRevealed ? 'bg-amber-100 text-amber-900 font-bold border border-amber-300' : 'bg-slate-100 text-slate-700'}`}>
                              {displayedRef}
                            </span>
                            {isRevealed ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 px-1.5 text-[11px] text-slate-600 hover:text-slate-900 hover:bg-slate-200"
                                onClick={() => handleHideIdentifier(app.id)}
                                title="Hide identifier from screen view"
                              >
                                <EyeOff className="h-3 w-3 mr-1 text-slate-500" /> Hide
                              </Button>
                            ) : (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 px-1.5 text-[11px] text-[#1F4D44] hover:bg-emerald-50"
                                onClick={() => {
                                  setSelectedAppToReveal(app);
                                  setRevealReason('');
                                  setRevealModalOpen(true);
                                }}
                                title="Reveal protected identifier (Audited)"
                              >
                                <Eye className="h-3 w-3 mr-1" /> Reveal identifier
                              </Button>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          <Badge variant="outline" className="capitalize text-[11px] bg-slate-50 text-slate-700 border-slate-300">
                            {app.status?.replace('_', ' ')}
                          </Badge>
                        </td>
                        <td className="py-3 px-3 text-slate-600">{app.points_claimed !== null && app.points_claimed !== undefined ? `${app.points_claimed} pts` : '—'}</td>
                        <td className="py-3 px-3 text-slate-500">{app.submission_date || '—'}</td>
                        <td className="py-3 px-3 text-right whitespace-nowrap">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs px-2"
                            onClick={() => {
                              setSelectedAppDetails(app);
                              setAppDetailsOpen(true);
                            }}
                          >
                            Details
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 2: PEOPLE & PERMISSIONS CONTROLS
          ───────────────────────────────────────────────────────────────────────────── */}
      {activeSubTab === 'people' && (
        <div className="space-y-6">
          {/* ACCESS EXPLANATION BANNER */}
          <div className="bg-blue-50 border border-blue-200 p-4 rounded-lg text-xs text-blue-900 flex items-start gap-3">
            <Info className="h-5 w-5 text-blue-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-sm text-blue-950 mb-0.5">Case Access Model & Governance Overview</p>
              <p className="text-blue-800 leading-relaxed">
                Permanent access belongs exclusively to the <strong>Assigned Case Manager</strong>, supervising <strong>Case Heads</strong>, and <strong>System Administrators</strong>.
                A count of 0 temporary grants indicates that <em>no external reviewers</em> have temporary coverage, while authorized permanent staff retain full operational control.
              </p>
              {callerAuth && (
                <p className="mt-2 text-blue-900 font-medium">
                  Your Current Authority: <span className="underline font-bold">{callerAuth.access_basis}</span>
                </p>
              )}
            </div>
          </div>

          {/* PERMANENT CASE ASSIGNMENT & ROLES */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* PRIMARY CASE MANAGER */}
            <Card className="p-5 border border-slate-200">
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold text-xs">
                    CM
                  </div>
                  <div>
                    <h5 className="font-bold text-slate-900 text-sm">Primary Case Manager</h5>
                    <p className="text-xs text-slate-500">Permanent assignment with routine operational authority</p>
                  </div>
                </div>
                {callerAuth?.can_reassign && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs h-7 border-[#1F4D44] text-[#1F4D44] hover:bg-[#1F4D44] hover:text-white"
                    onClick={() => {
                      setReassignManagerId('');
                      setReassignReason('');
                      setReassignOpen(true);
                    }}
                  >
                    <ArrowRightLeft className="h-3 w-3 mr-1" /> Reassign
                  </Button>
                )}
              </div>

              {peopleData?.assigned_case_manager ? (
                <div className="bg-slate-50 p-3 rounded border border-slate-200 space-y-1.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Name:</span>
                    <span className="font-semibold text-slate-900">{peopleData.assigned_case_manager.name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Email:</span>
                    <span className="text-slate-800 font-mono">{peopleData.assigned_case_manager.email}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Access Basis:</span>
                    <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-300 text-[10px]">
                      {peopleData.assigned_case_manager.access_type}
                    </Badge>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Assigned Since:</span>
                    <span className="text-slate-600">{peopleData.assigned_case_manager.assigned_since ? new Date(peopleData.assigned_case_manager.assigned_since).toLocaleDateString() : 'Active'}</span>
                  </div>
                </div>
              ) : (
                <div className="bg-amber-50 p-3 rounded border border-amber-200 text-xs text-amber-800 flex items-center justify-between">
                  <span>No primary Case Manager currently assigned to this case.</span>
                  {callerAuth?.can_reassign && (
                    <Button size="sm" onClick={() => setReassignOpen(true)} className="h-6 text-xs bg-amber-700 text-white">
                      Assign Now
                    </Button>
                  )}
                </div>
              )}
            </Card>

            {/* SUPERVISING CASE HEADS & ADMINISTRATORS */}
            <Card className="p-5 border border-slate-200">
              <div className="flex items-center gap-2 mb-3">
                <div className="h-8 w-8 rounded-full bg-blue-100 text-blue-800 flex items-center justify-center font-bold text-xs">
                  <Shield className="h-4 w-4" />
                </div>
                <div>
                  <h5 className="font-bold text-slate-900 text-sm">Supervisory & Administrative Authority</h5>
                  <p className="text-xs text-slate-500">Departmental supervision and master system oversight</p>
                </div>
              </div>

              <div className="space-y-2 text-xs">
                <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-slate-800">System Administrators (Global)</span>
                    <Badge variant="outline" className="text-[10px] bg-purple-50 text-purple-700 border-purple-200">Master Control</Badge>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Full authority across all cases, vault entries, audit logs, and temporary permissions.
                  </p>
                </div>

                <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-slate-800">Case Heads & Leads (Departmental)</span>
                    <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700 border-blue-200">Supervisory</Badge>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Authorized to supervise case progress, approve elevation requests, and reassign managers.
                  </p>
                </div>
              </div>
            </Card>
          </div>

          {/* TEMPORARY ACCESS GRANTS SECTION */}
          <Card className="p-6">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h4 className="font-bold text-gray-900 text-base">Granular Temporary Access Grants</h4>
                <p className="text-xs text-slate-500">
                  Time-limited grants for covering staff and external reviewers with granular action limits. Expire automatically on backend.
                </p>
              </div>
              {callerAuth?.can_grant_temporary && (
                <Button size="sm" onClick={() => setNewGrantOpen(true)} className="bg-[#1F4D44] hover:bg-[#163832]">
                  <Plus className="h-4 w-4 mr-1" /> Issue Temporary Grant
                </Button>
              )}
            </div>

            {grants.length === 0 ? (
              <div className="text-center py-8 bg-slate-50 rounded-lg border border-dashed border-slate-300">
                <UserCheck className="h-8 w-8 mx-auto text-slate-400 mb-2" />
                <p className="text-sm font-medium text-slate-700">No temporary access grants active for this case</p>
                <p className="text-xs text-slate-500 mb-3">Normal case work is handled by the assigned manager. Issue a grant only for peer reviews or cover.</p>
                {callerAuth?.can_grant_temporary && (
                  <Button size="sm" variant="outline" onClick={() => setNewGrantOpen(true)}>Issue Temporary Grant</Button>
                )}
              </div>
            ) : (
              <div className="divide-y divide-slate-200">
                {grants.map((g) => {
                  const isRevoked = !!g.revoked_at;
                  const isExpired = g.expires_at && new Date(g.expires_at) < new Date();
                  const isActive = !isRevoked && !isExpired;

                  return (
                    <div key={g.id} className="py-3.5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-sm text-slate-900">{g.user_name || g.user_email || g.user_id}</span>
                          <span className="text-xs text-slate-500 font-mono">({g.user_email || g.user_id})</span>
                          {isRevoked ? (
                            <Badge className="bg-red-100 text-red-700 border-red-200 text-xs">Revoked</Badge>
                          ) : isExpired ? (
                            <Badge className="bg-amber-100 text-amber-700 border-amber-200 text-xs">Expired</Badge>
                          ) : (
                            <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 text-xs">Active Grant</Badge>
                          )}
                          <span className="text-xs text-slate-500">Scope: <strong>{g.resource_scope || 'Entire Case'}</strong></span>
                        </div>

                        {/* Granular Action Badges */}
                        <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                          <span className="text-[11px] text-slate-500">Permitted:</span>
                          {(g.permissions || ['case.view']).map((perm) => (
                            <span key={perm} className="px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded text-[10px] font-mono border border-slate-200">
                              {perm}
                            </span>
                          ))}
                        </div>

                        <p className="text-xs text-slate-500">
                          Justification: <em>{g.reason || 'None specified'}</em> • Granted by: {g.granted_by_email || g.granted_by || 'Admin'}
                        </p>
                        {g.expires_at && (
                          <p className="text-[11px] text-slate-400 flex items-center gap-1">
                            <Clock className="h-3 w-3" /> Expires: {new Date(g.expires_at).toLocaleString()}
                          </p>
                        )}
                      </div>

                      {isActive && callerAuth?.can_revoke_temporary && (
                        <Button
                          size="sm"
                          variant="destructive"
                          className="text-xs h-7 self-start sm:self-center"
                          onClick={() => handleRevokeGrant(g.id)}
                        >
                          Revoke Access
                        </Button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* RECENT ACCESS AUDIT HISTORY */}
          <Card className="p-6">
            <h4 className="font-bold text-gray-900 text-base mb-1">Recent Access & Audit History</h4>
            <p className="text-xs text-slate-500 mb-4">
              Immutable event log for this case: manager reassignments, identifier unmasking, credential checkouts, and temporary access grants.
            </p>

            {peopleData?.access_history && peopleData.access_history.length > 0 ? (
              <div className="space-y-2 text-xs">
                {peopleData.access_history.map((log, idx) => (
                  <div key={idx} className="p-2.5 rounded bg-slate-50 border border-slate-200 flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-slate-900">{log.action}</span>
                        <span className="text-slate-500">by</span>
                        <span className="font-medium text-slate-800">{log.user_name || log.user_id}</span>
                      </div>
                      {log.summary?.reason && (
                        <p className="text-[11px] text-slate-600 mt-0.5">Reason: {log.summary.reason}</p>
                      )}
                    </div>
                    <span className="text-[11px] text-slate-400 whitespace-nowrap ml-2">
                      {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'Recent'}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic">No historical audit events logged for this case yet.</p>
            )}
          </Card>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 3: ACCESS REQUESTS & APPROVALS WORKFLOW
          ───────────────────────────────────────────────────────────────────────────── */}
      {activeSubTab === 'requests' && (
        <Card className="p-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
            <div>
              <h4 className="font-bold text-gray-900 text-base">Sensitive-Action Access Requests</h4>
              <p className="text-xs text-slate-500">
                Staff members needing exceptional access to protected identifiers or credentials must submit a recorded request. Case Heads and Administrators review and decide.
              </p>
            </div>
            <Button size="sm" onClick={() => setNewRequestOpen(true)} className="bg-[#1F4D44] hover:bg-[#163832]">
              <Plus className="h-4 w-4 mr-1" /> Request Access Elevation
            </Button>
          </div>

          {accessRequests.length === 0 ? (
            <div className="text-center py-10 bg-slate-50 rounded-lg border border-dashed border-slate-300">
              <ShieldAlert className="h-8 w-8 mx-auto text-slate-400 mb-2" />
              <p className="text-sm font-medium text-slate-700">No sensitive-action access requests for this case</p>
              <p className="text-xs text-slate-500 mb-3">
                Routine work does not require approval. Requesters may submit exceptional requests here.
              </p>
              <Button size="sm" variant="outline" onClick={() => setNewRequestOpen(true)}>Submit Access Request</Button>
            </div>
          ) : (
            <div className="divide-y divide-slate-200">
              {accessRequests.map((req) => {
                const isPending = req.status === 'pending';
                const isApproved = req.status === 'approved';
                const isRejected = req.status === 'rejected';

                return (
                  <div key={req.id} className="py-3.5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-sm text-slate-900">{req.requester_name || req.requester_email}</span>
                        <span className="text-xs text-slate-500">requested</span>
                        <Badge variant="outline" className="font-mono text-xs bg-slate-100 text-slate-800">
                          {req.action}
                        </Badge>
                        {isPending && <Badge className="bg-amber-100 text-amber-800 border-amber-300 text-xs">Pending Decision</Badge>}
                        {isApproved && <Badge className="bg-emerald-100 text-emerald-800 border-emerald-300 text-xs">Approved</Badge>}
                        {isRejected && <Badge className="bg-red-100 text-red-800 border-red-300 text-xs">Rejected</Badge>}
                      </div>

                      <p className="text-xs text-slate-600">
                        Target Resource: <span className="font-medium text-slate-800">{req.resource_name || req.resource_id}</span> • Duration: {req.requested_duration_hours}h
                      </p>
                      <p className="text-xs text-slate-500">
                        Reason: <em>"{req.reason}"</em>
                      </p>

                      {req.decided_at && (
                        <p className="text-[11px] text-slate-400">
                          Decided by {req.decided_by_email || 'Approver'} on {new Date(req.decided_at).toLocaleString()}
                          {req.decision_notes && ` (Note: ${req.decision_notes})`}
                        </p>
                      )}
                    </div>

                    {isPending && callerAuth?.can_approve_requests && (
                      <div className="flex items-center gap-2 self-start sm:self-center">
                        <Button
                          size="sm"
                          className="h-7 text-xs bg-emerald-700 hover:bg-emerald-800 text-white"
                          onClick={() => {
                            setSelectedRequestToDecide(req);
                            setDecisionType('approved');
                            setDecisionNotes('');
                            setDecisionModalOpen(true);
                          }}
                        >
                          <Check className="h-3.5 w-3.5 mr-1" /> Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          className="h-7 text-xs"
                          onClick={() => {
                            setSelectedRequestToDecide(req);
                            setDecisionType('rejected');
                            setDecisionNotes('');
                            setDecisionModalOpen(true);
                          }}
                        >
                          <X className="h-3.5 w-3.5 mr-1" /> Reject
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 4: CREDENTIAL VAULT
          ───────────────────────────────────────────────────────────────────────────── */}
      {activeSubTab === 'vault' && (
        <Card className="p-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
            <div>
              <h4 className="font-bold text-gray-900 text-base">Government Portal Credential Vault</h4>
              <p className="text-xs text-slate-500">
                External account logins (ImmiAccount, SkillSelect, State Portals) stored using AES-256 GCM authenticated encryption. Zero cleartext on disk or in regular responses.
              </p>
            </div>
            <Button size="sm" onClick={() => setNewVaultOpen(true)} className="bg-[#1F4D44] hover:bg-[#163832]">
              <Plus className="h-4 w-4 mr-1" /> Store Portal Login
            </Button>
          </div>

          {vaultEntries.length === 0 ? (
            <div className="text-center py-10 bg-slate-50 rounded-lg border border-dashed border-slate-300">
              <KeyRound className="h-8 w-8 mx-auto text-slate-400 mb-2" />
              <p className="text-sm font-medium text-slate-700">No portal credentials stored for this client</p>
              <p className="text-xs text-slate-500 mb-3">Secure client ImmiAccount or State Portal accounts with zero cleartext on disk.</p>
              <Button size="sm" variant="outline" onClick={() => setNewVaultOpen(true)}>Store First Login</Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {vaultEntries.map((v) => (
                <Card key={v.id} className="p-4 border border-slate-200 bg-white shadow-xs hover:border-[#1F4D44]/40 transition-colors">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <h5 className="font-bold text-slate-900 flex items-center gap-1.5 text-sm">
                        <Lock className="h-4 w-4 text-emerald-600" />
                        {v.portal_name}
                      </h5>
                      {v.portal_url && (
                        <a
                          href={v.portal_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-[#D4633F] hover:underline flex items-center gap-1 mt-0.5"
                        >
                          {v.portal_url} <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                    <Badge variant="outline" className="bg-slate-100 text-slate-700 text-[10px]">
                      AES-256 GCM
                    </Badge>
                  </div>

                  {/* Non-Secret Governance Metadata */}
                  <div className="space-y-1.5 my-3 text-xs bg-slate-50 p-2.5 rounded border border-slate-200">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Account Username / ID:</span>
                      <span className="font-mono font-medium text-slate-800">{v.username_or_id}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-slate-500">Password:</span>
                      <span className="font-mono text-slate-400 tracking-widest">{v.masked_secret || '••••••••••••'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Access Method:</span>
                      <span className="text-slate-700 font-medium">Audited Justification</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Last Accessed:</span>
                      <span className="text-slate-600">{v.last_accessed_at ? new Date(v.last_accessed_at).toLocaleString() : 'Never'}</span>
                    </div>
                  </div>

                  {v.notes && <p className="text-xs text-slate-500 mb-3 italic">Note: {v.notes}</p>}

                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full text-xs border-[#1F4D44] text-[#1F4D44] hover:bg-[#1F4D44] hover:text-white transition-colors"
                    onClick={() => {
                      setSelectedVaultToCheckout(v);
                      setCheckoutReason('');
                      setCheckedOutSecret(null);
                      setCheckoutOpen(true);
                    }}
                  >
                    <Unlock className="h-3.5 w-3.5 mr-1.5" /> Check Out Password (Audited)
                  </Button>
                </Card>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          MODALS & DIALOGS
          ───────────────────────────────────────────────────────────────────────────── */}

      {/* MODAL 1: REGISTER APPLICATION */}
      <Dialog open={newAppOpen} onOpenChange={setNewAppOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Register New Application</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateApplication} className="space-y-3 mt-2">
            {isDuplicateApp && (
              <div className="p-2.5 rounded bg-amber-50 border border-amber-300 text-amber-800 text-xs flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                <div>
                  <strong>Duplicate Notice:</strong> An application with this Type, Authority, and Subclass already exists on this case. If this is a separate stream or resubmission, you may proceed.
                </div>
              </div>
            )}

            <div>
              <Label className="text-xs">Application Type</Label>
              <Select
                value={appForm.application_type}
                onValueChange={(v) => setAppForm({ ...appForm, application_type: v })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {APPLICATION_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Assessing Body / Authority</Label>
                <Select
                  value={appForm.authority_or_state}
                  onValueChange={(v) => setAppForm({ ...appForm, authority_or_state: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {MASTER_AUTHORITIES.map(a => (
                      <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Subclass / Stream</Label>
                <Input
                  placeholder="e.g. 189, 190, 491, 186"
                  value={appForm.subclass_or_stream}
                  onChange={(e) => setAppForm({ ...appForm, subclass_or_stream: e.target.value })}
                />
              </div>
            </div>

            <div>
              <Label className="text-xs">Sensitive Reference Identifier (TRN / EOI ID / SkillSelect)</Label>
              <Input
                placeholder="e.g. DHA-9876543210 or E01234567"
                value={appForm.reference_identifier}
                onChange={(e) => setAppForm({ ...appForm, reference_identifier: e.target.value })}
              />
              <p className="text-[11px] text-slate-500 mt-0.5">Stored masked; unmasked only with recorded operational reason.</p>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Points Claimed</Label>
                <Input
                  type="number"
                  placeholder="e.g. 85"
                  value={appForm.points_claimed || ''}
                  onChange={(e) => setAppForm({ ...appForm, points_claimed: parseInt(e.target.value) || 0 })}
                />
              </div>
              <div>
                <Label className="text-xs">Status</Label>
                <Select
                  value={appForm.status}
                  onValueChange={(v) => setAppForm({ ...appForm, status: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="draft">Draft</SelectItem>
                    <SelectItem value="submitted">Submitted</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="additional_info_requested">Info Requested</SelectItem>
                    <SelectItem value="invited">Invited</SelectItem>
                    <SelectItem value="nominated">Nominated</SelectItem>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="refused">Refused</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Submission Date</Label>
                <Input
                  type="date"
                  value={appForm.submission_date}
                  onChange={(e) => setAppForm({ ...appForm, submission_date: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-xs">Next Deadline</Label>
                <Input
                  type="date"
                  value={appForm.deadline}
                  onChange={(e) => setAppForm({ ...appForm, deadline: e.target.value })}
                />
              </div>
            </div>

            <div>
              <Label className="text-xs">Operational Notes</Label>
              <Textarea
                placeholder="e.g. Primary skilled migration lodgement under ANZSCO 261313"
                value={appForm.notes}
                onChange={(e) => setAppForm({ ...appForm, notes: e.target.value })}
                rows={2}
              />
            </div>

            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setNewAppOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-[#1F4D44]">Save Application</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* MODAL 2: APPLICATION DETAILS DRAWER */}
      <Dialog open={appDetailsOpen} onOpenChange={setAppDetailsOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Application Record Details</DialogTitle>
          </DialogHeader>
          {selectedAppDetails && (
            <div className="space-y-3 mt-2 text-xs">
              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded border border-slate-200">
                <div>
                  <span className="text-slate-500 block">Type:</span>
                  <span className="font-semibold text-slate-900 capitalize">{selectedAppDetails.application_type?.replace('_', ' ')}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Status:</span>
                  <Badge variant="outline" className="capitalize text-[11px]">{selectedAppDetails.status?.replace('_', ' ')}</Badge>
                </div>
                <div>
                  <span className="text-slate-500 block">Authority / State:</span>
                  <span className="font-semibold text-slate-800">{selectedAppDetails.authority_or_state}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Subclass / Stream:</span>
                  <span className="font-semibold text-slate-800">{selectedAppDetails.subclass_or_stream || '—'}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Points Claimed:</span>
                  <span className="font-semibold text-slate-800">{selectedAppDetails.points_claimed !== null ? `${selectedAppDetails.points_claimed} pts` : '—'}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Submission Date:</span>
                  <span className="text-slate-800">{selectedAppDetails.submission_date || '—'}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Next Deadline:</span>
                  <span className="text-slate-800">{selectedAppDetails.deadline || '—'}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Registered At:</span>
                  <span className="text-slate-800">{selectedAppDetails.created_at ? new Date(selectedAppDetails.created_at).toLocaleString() : '—'}</span>
                </div>
              </div>

              {selectedAppDetails.notes && (
                <div className="p-3 bg-white rounded border border-slate-200">
                  <span className="text-slate-500 block font-semibold mb-1">Operational Notes:</span>
                  <p className="text-slate-700">{selectedAppDetails.notes}</p>
                </div>
              )}

              <DialogFooter className="mt-4">
                <Button type="button" variant="outline" onClick={() => setAppDetailsOpen(false)}>Close</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* MODAL 3: REVEAL IDENTIFIER (AUDITED) */}
      <Dialog open={revealModalOpen} onOpenChange={setRevealModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-slate-900">
              <Eye className="h-5 w-5 text-amber-600" />
              Audited Identifier Unmasking
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="bg-amber-50 border border-amber-200 p-3 rounded text-xs text-amber-900 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-600" />
              <div>
                <strong>Zero-Trust Audit Log:</strong> Unmasking sensitive government reference numbers requires a recorded operational justification. Your identity and IP address are logged to the immutable audit repository.
              </div>
            </div>

            <div>
              <Label className="text-xs">Application</Label>
              <p className="text-sm font-semibold text-slate-800">
                {selectedAppToReveal?.authority_or_state} — {selectedAppToReveal?.application_type?.replace('_', ' ')}
              </p>
            </div>

            <div>
              <Label className="text-xs">Mandatory Operational Reason</Label>
              <Textarea
                placeholder="e.g. Cross-referencing SkillSelect invitation round results against DHA portal"
                value={revealReason}
                onChange={(e) => setRevealReason(e.target.value)}
                rows={3}
                className="mt-1"
                required
              />
            </div>

            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setRevealModalOpen(false)}>Cancel</Button>
              <Button onClick={handleRevealIdentifier} className="bg-[#1F4D44]">
                Confirm & Unmask
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* MODAL 4: STORE PORTAL LOGIN IN VAULT */}
      <Dialog open={newVaultOpen} onOpenChange={setNewVaultOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Store Government Portal Login in Vault</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateVault} className="space-y-3 mt-2">
            <div className="bg-emerald-50 border border-emerald-200 p-3 rounded text-xs text-emerald-800 flex items-start gap-2">
              <Lock className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
              <div>
                <strong>Zero Plaintext Storage:</strong> Passwords are encrypted with AES-256 GCM authenticated encryption before saving. Cleartext is never returned in ordinary case responses.
              </div>
            </div>

            <div>
              <Label className="text-xs">Portal / Authority Name</Label>
              <Input
                placeholder="e.g. DHA ImmiAccount, Live in Melbourne, SkillSelect"
                value={vaultForm.portal_name}
                onChange={(e) => setVaultForm({ ...vaultForm, portal_name: e.target.value })}
                required
              />
            </div>
            <div>
              <Label className="text-xs">Portal Login URL</Label>
              <Input
                placeholder="https://online.immi.gov.au"
                value={vaultForm.portal_url}
                onChange={(e) => setVaultForm({ ...vaultForm, portal_url: e.target.value })}
              />
            </div>
            <div>
              <Label className="text-xs">Account Username / ID</Label>
              <Input
                placeholder="client.immi.username"
                value={vaultForm.username_or_id}
                onChange={(e) => setVaultForm({ ...vaultForm, username_or_id: e.target.value })}
                required
              />
            </div>
            <div>
              <Label className="text-xs">Secret / Password</Label>
              <Input
                type="password"
                placeholder="••••••••••••"
                value={vaultForm.secret_value}
                onChange={(e) => setVaultForm({ ...vaultForm, secret_value: e.target.value })}
                required
              />
            </div>
            <div>
              <Label className="text-xs">Operational Notes</Label>
              <Textarea
                placeholder="e.g. Client primary visa lodgement account"
                value={vaultForm.notes}
                onChange={(e) => setVaultForm({ ...vaultForm, notes: e.target.value })}
                rows={2}
              />
            </div>
            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setNewVaultOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-[#1F4D44]">Encrypt & Save in Vault</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* MODAL 5: CHECKOUT VAULT SECRET */}
      <Dialog open={checkoutOpen} onOpenChange={setCheckoutOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-slate-900">
              <KeyRound className="h-5 w-5 text-amber-600" />
              Audited Credential Checkout
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="bg-amber-50 border border-amber-200 p-3 rounded text-xs text-amber-800 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-600" />
              <div>
                <strong>Zero-Trust Protocol:</strong> Retrieving cleartext passwords requires a recorded operational justification. This action is permanently attributed to your account in the audit repository.
              </div>
            </div>

            <div>
              <Label className="text-xs">Portal</Label>
              <p className="text-sm font-semibold text-slate-800">
                {selectedVaultToCheckout?.portal_name} ({selectedVaultToCheckout?.username_or_id})
              </p>
            </div>

            {!checkedOutSecret ? (
              <div>
                <Label className="text-xs">Mandatory Operational Reason</Label>
                <Textarea
                  placeholder="e.g. Logging in to attach medical examination clearance to visa application"
                  value={checkoutReason}
                  onChange={(e) => setCheckoutReason(e.target.value)}
                  rows={3}
                  className="mt-1"
                />
              </div>
            ) : (
              <div className="bg-slate-900 text-white p-4 rounded-lg space-y-2 mt-2">
                <div className="flex justify-between items-center text-xs text-slate-400 font-mono">
                  <span>Decrypted Cleartext Password:</span>
                  <span className="text-amber-400">Do not share outside LEAMSS</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-lg text-emerald-400 tracking-wider">
                    {checkedOutSecret}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      navigator.clipboard.writeText(checkedOutSecret);
                      toast.success('Password copied to clipboard');
                    }}
                    className="text-white hover:bg-slate-800 h-7"
                  >
                    <Copy className="h-3.5 w-3.5 mr-1" /> Copy
                  </Button>
                </div>
              </div>
            )}

            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setCheckoutOpen(false)}>Close</Button>
              {!checkedOutSecret && (
                <Button onClick={handleCheckoutSecret} className="bg-[#1F4D44]">
                  Confirm & Retrieve
                </Button>
              )}
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* MODAL 6: ISSUE GRANULAR TEMPORARY GRANT */}
      <Dialog open={newGrantOpen} onOpenChange={setNewGrantOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Issue Temporary Access Grant</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateGrant} className="space-y-3 mt-2">
            <div>
              <Label className="text-xs">Target Staff Member</Label>
              {staffList && staffList.length > 0 && (
                <div className="mb-2">
                  <Select
                    value={staffList.some(s => s.id === grantForm.user_id || s.email === grantForm.user_id) ? grantForm.user_id : ''}
                    onValueChange={(val) => setGrantForm(prev => ({ ...prev, user_id: val }))}
                  >
                    <SelectTrigger className="text-xs">
                      <SelectValue placeholder="Quick-select team member..." />
                    </SelectTrigger>
                    <SelectContent>
                      {staffList.map((s) => (
                        <SelectItem key={s.id} value={s.email || s.id} className="text-xs">
                          {s.name} ({s.email}) — {s.role?.replace('_', ' ')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <Input
                placeholder="Or enter staff ID or email manually..."
                value={grantForm.user_id}
                onChange={(e) => setGrantForm({ ...grantForm, user_id: e.target.value })}
                required
              />
            </div>

            <div>
              <Label className="text-xs">Resource Scope</Label>
              <Select
                value={grantForm.resource_scope}
                onValueChange={(v) => setGrantForm({ ...grantForm, resource_scope: v })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="case">Entire Case (Standard Coverage)</SelectItem>
                  <SelectItem value="applications">Applications Only</SelectItem>
                  <SelectItem value="documents">Documents Only</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-xs font-semibold block mb-1.5">Granular Permitted Actions</Label>
              <div className="space-y-1.5 p-2.5 rounded bg-slate-50 border border-slate-200 max-h-44 overflow-y-auto">
                {GRANULAR_ACTION_OPTIONS.map((action) => {
                  const isChecked = grantForm.permissions.includes(action.id);
                  return (
                    <label key={action.id} className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setGrantForm(prev => ({ ...prev, permissions: [...prev.permissions, action.id] }));
                          } else {
                            setGrantForm(prev => ({ ...prev, permissions: prev.permissions.filter(p => p !== action.id) }));
                          }
                        }}
                        className="rounded border-slate-300 text-[#1F4D44] focus:ring-[#1F4D44]"
                      />
                      <span>{action.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>

            <div>
              <Label className="text-xs">Duration (Hours, Max 720h / 30 Days)</Label>
              <Input
                type="number"
                min="1"
                max="720"
                value={grantForm.expires_in_hours}
                onChange={(e) => setGrantForm({ ...grantForm, expires_in_hours: parseInt(e.target.value) || 24 })}
              />
            </div>

            <div>
              <Label className="text-xs">Mandatory Operational Justification</Label>
              <Textarea
                placeholder="e.g. Covering for primary case manager on annual leave"
                value={grantForm.reason}
                onChange={(e) => setGrantForm({ ...grantForm, reason: e.target.value })}
                rows={2}
                required
              />
            </div>

            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setNewGrantOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-[#1F4D44]">Issue Grant</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* MODAL 7: REASSIGN CASE MANAGER */}
      <Dialog open={reassignOpen} onOpenChange={setReassignOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reassign Primary Case Manager</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleReassignManager} className="space-y-3 mt-2">
            <p className="text-xs text-slate-500">
              Reassigning updates the canonical case manager for this case. Permanent case-assignment access will transfer to the new manager immediately.
            </p>

            <div>
              <Label className="text-xs">New Case Manager</Label>
              <Select
                value={reassignManagerId}
                onValueChange={setReassignManagerId}
              >
                <SelectTrigger><SelectValue placeholder="Select case manager..." /></SelectTrigger>
                <SelectContent>
                  {staffList
                    .filter(s => s.role === 'case_manager' || s.role === 'admin')
                    .map(m => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.name} ({m.email})
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-xs">Reassignment Reason</Label>
              <Textarea
                placeholder="e.g. Workload rebalancing or specialized skills assessment requirement"
                value={reassignReason}
                onChange={(e) => setReassignReason(e.target.value)}
                rows={2}
              />
            </div>

            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setReassignOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-[#1F4D44]">Confirm Reassignment</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* MODAL 8: SUBMIT ACCESS REQUEST */}
      <Dialog open={newRequestOpen} onOpenChange={setNewRequestOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Request Sensitive Action Elevation</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateAccessRequest} className="space-y-3 mt-2">
            <div>
              <Label className="text-xs">Action Requested</Label>
              <Select
                value={requestForm.action}
                onValueChange={(v) => setRequestForm({ ...requestForm, action: v })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="identifier.reveal">Reveal Protected Identifier</SelectItem>
                  <SelectItem value="credential.access">Access Credential Vault</SelectItem>
                  <SelectItem value="document.preview">Preview Confidential Document</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-xs">Target Resource Identifier</Label>
              <Input
                placeholder="e.g. Application ID, Document ID, or Credential ID"
                value={requestForm.resource_id}
                onChange={(e) => setRequestForm({ ...requestForm, resource_id: e.target.value })}
                required
              />
            </div>

            <div>
              <Label className="text-xs">Resource Label / Description</Label>
              <Input
                placeholder="e.g. VETASSESS Reference Number or DHA ImmiAccount"
                value={requestForm.resource_name}
                onChange={(e) => setRequestForm({ ...requestForm, resource_name: e.target.value })}
              />
            </div>

            <div>
              <Label className="text-xs">Requested Access Duration (Hours)</Label>
              <Input
                type="number"
                min="1"
                max="168"
                value={requestForm.requested_duration_hours}
                onChange={(e) => setRequestForm({ ...requestForm, requested_duration_hours: parseInt(e.target.value) || 24 })}
              />
            </div>

            <div>
              <Label className="text-xs">Business Justification Reason</Label>
              <Textarea
                placeholder="e.g. Required to attach medical report while primary manager is in client consultation"
                value={requestForm.reason}
                onChange={(e) => setRequestForm({ ...requestForm, reason: e.target.value })}
                rows={3}
                required
              />
            </div>

            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setNewRequestOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-[#1F4D44]">Submit Request</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* MODAL 9: DECIDE ACCESS REQUEST (APPROVE/REJECT) */}
      <Dialog open={decisionModalOpen} onOpenChange={setDecisionModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {decisionType === 'approved' ? 'Approve Access Request' : 'Reject Access Request'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <p className="text-xs text-slate-600">
              Request by <strong>{selectedRequestToDecide?.requester_name}</strong> for action{' '}
              <strong className="font-mono">{selectedRequestToDecide?.action}</strong>.
            </p>

            <div>
              <Label className="text-xs">Approver Notes (Optional)</Label>
              <Textarea
                placeholder="e.g. Approved for duration of lodgement preparation"
                value={decisionNotes}
                onChange={(e) => setDecisionNotes(e.target.value)}
                rows={2}
              />
            </div>

            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setDecisionModalOpen(false)}>Cancel</Button>
              <Button
                onClick={handleDecideRequest}
                className={decisionType === 'approved' ? 'bg-emerald-700 hover:bg-emerald-800 text-white' : 'bg-red-700 hover:bg-red-800 text-white'}
              >
                Confirm {decisionType === 'approved' ? 'Approval' : 'Rejection'}
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
