import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import {
  ShieldCheck,
  ShieldAlert,
  Users,
  KeyRound,
  Eye,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  History,
  UserCheck
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || (typeof window !== 'undefined' && window.location.hostname.includes('leamss.com') ? 'https://api.leamss.com' : 'http://localhost:8001');
const API = `${BACKEND_URL}/api`;

export default function AdminCaseGovernanceWidget({ onSelectCase, onFilterUnassigned }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [decisionModalOpen, setDecisionModalOpen] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [decisionType, setDecisionType] = useState('approved');
  const [decisionNotes, setDecisionNotes] = useState('');

  const getHeaders = () => {
    const token = localStorage.getItem('token');
    return { headers: { Authorization: `Bearer ${token}` } };
  };

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/case-workspace/admin/governance-summary`, getHeaders());
      setSummary(res.data);
    } catch (err) {
      console.error('Failed to load governance summary:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const handleDecisionSubmit = async () => {
    if (!selectedRequest) return;
    try {
      await axios.post(
        `${API}/case-workspace/${selectedRequest.case_id}/access-requests/${selectedRequest.id}/decision`,
        { decision: decisionType, notes: decisionNotes },
        getHeaders()
      );
      toast.success(`Access request marked as ${decisionType}`);
      setDecisionModalOpen(false);
      setSelectedRequest(null);
      setDecisionNotes('');
      loadSummary();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit decision');
    }
  };

  const pendingRequests = summary?.pending_requests || [];
  const activeGrants = summary?.active_grants || [];
  const recentAudits = summary?.recent_sensitive_actions || [];
  const unassignedCount = summary?.unassigned_cases_count || 0;
  const expiringCount = summary?.expiring_grants_24h_count || 0;

  return (
    <Card className="border border-emerald-900/20 bg-gradient-to-r from-slate-900 to-slate-800 text-white p-5 shadow-sm mb-6" data-testid="admin-case-governance-widget">
      {/* HEADER */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-lg bg-emerald-500/20 border border-emerald-400/30 flex items-center justify-center text-emerald-400">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-base text-white tracking-tight">Case Security & Access Governance Overview</h3>
              <Badge className="bg-emerald-500 text-slate-950 font-bold text-[10px] px-2">Admin Control</Badge>
            </div>
            <p className="text-xs text-slate-300">
              System-wide visibility across permanent case assignments, temporary grants, and sensitive actions
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <Button
            size="sm"
            variant="ghost"
            onClick={loadSummary}
            disabled={loading}
            className="h-8 text-xs text-slate-300 hover:text-white hover:bg-slate-700/50"
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setExpanded(!expanded)}
            className="h-8 text-xs text-slate-300 hover:text-white hover:bg-slate-700/50"
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* METRIC PILLS */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
        {/* PENDING ELEVATION REQUESTS */}
        <div className={`p-3 rounded-lg border transition-all ${pendingRequests.length > 0 ? 'bg-amber-950/40 border-amber-500/40' : 'bg-slate-800/60 border-slate-700'}`}>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-300 font-medium">Pending Approvals</span>
            <ShieldAlert className={`h-4 w-4 ${pendingRequests.length > 0 ? 'text-amber-400' : 'text-slate-400'}`} />
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-bold text-white">{pendingRequests.length}</span>
            <span className="text-[11px] text-slate-400">elevation requests</span>
          </div>
        </div>

        {/* ACTIVE TEMPORARY GRANTS */}
        <div className="p-3 rounded-lg bg-slate-800/60 border border-slate-700">
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-300 font-medium">Active Grants</span>
            <UserCheck className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-bold text-white">{activeGrants.length}</span>
            <span className="text-[11px] text-slate-400">
              {expiringCount > 0 ? <span className="text-amber-400 font-semibold">{expiringCount} expiring &lt;24h</span> : 'temporary reviewers'}
            </span>
          </div>
        </div>

        {/* UNASSIGNED CASES */}
        <div className={`p-3 rounded-lg border transition-all ${unassignedCount > 0 ? 'bg-red-950/30 border-red-500/30' : 'bg-slate-800/60 border-slate-700'}`}>
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-300 font-medium">Unassigned Cases</span>
            <Users className={`h-4 w-4 ${unassignedCount > 0 ? 'text-red-400' : 'text-slate-400'}`} />
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-xl font-bold text-white">{unassignedCount}</span>
            {unassignedCount > 0 && onFilterUnassigned && (
              <button
                onClick={onFilterUnassigned}
                className="text-[11px] text-red-300 underline hover:text-white"
              >
                Filter Cases
              </button>
            )}
          </div>
        </div>

        {/* AUDIT LOG EVENTS */}
        <div className="p-3 rounded-lg bg-slate-800/60 border border-slate-700">
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-300 font-medium">Audited Actions</span>
            <History className="h-4 w-4 text-blue-400" />
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-bold text-white">{recentAudits.length}</span>
            <span className="text-[11px] text-slate-400">recent sensitive events</span>
          </div>
        </div>
      </div>

      {/* EXPANDED CONTENT: PENDING REQUESTS & RECENT AUDIT */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-slate-700/80 space-y-4">
          {/* PENDING REQUESTS SECTION */}
          {pendingRequests.length > 0 && (
            <div className="bg-amber-950/30 border border-amber-500/40 rounded-lg p-3.5">
              <div className="flex items-center gap-2 mb-2.5">
                <ShieldAlert className="h-4 w-4 text-amber-400" />
                <h4 className="font-semibold text-xs text-amber-200 uppercase tracking-wider">
                  Pending Sensitive Access Approvals ({pendingRequests.length})
                </h4>
              </div>

              <div className="space-y-2">
                {pendingRequests.map((req) => (
                  <div key={req.id} className="bg-slate-900/90 border border-slate-700 p-3 rounded flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-xs text-white">{req.requester_name || req.requester_email}</span>
                        <Badge variant="outline" className="text-[10px] bg-slate-800 text-amber-300 border-amber-400/40">
                          {req.action}
                        </Badge>
                        <span className="text-xs text-slate-400">Duration: {req.requested_duration_hours || 24}h</span>
                      </div>
                      <p className="text-xs text-slate-300 italic">
                        &quot;{req.reason}&quot;
                      </p>
                      <p className="text-[11px] text-slate-400">
                        Case ID: <span className="font-mono text-slate-200">{req.case_id}</span>
                      </p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        className="h-7 text-xs bg-emerald-600 hover:bg-emerald-500 text-white"
                        onClick={() => {
                          setSelectedRequest(req);
                          setDecisionType('approved');
                          setDecisionNotes('');
                          setDecisionModalOpen(true);
                        }}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        className="h-7 text-xs"
                        onClick={() => {
                          setSelectedRequest(req);
                          setDecisionType('rejected');
                          setDecisionNotes('');
                          setDecisionModalOpen(true);
                        }}
                      >
                        <XCircle className="h-3.5 w-3.5 mr-1" /> Reject
                      </Button>
                      {onSelectCase && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs bg-slate-800 text-slate-200 border-slate-600 hover:bg-slate-700"
                          onClick={() => onSelectCase(req.case_id)}
                        >
                          <ExternalLink className="h-3.5 w-3.5 mr-1" /> Open Case
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SENSITIVE AUDIT LOG PREVIEW */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <History className="h-3.5 w-3.5 text-slate-400" /> Recent Security & Access Audit Trail
              </span>
              <span className="text-[11px] text-slate-400">Last 5 events</span>
            </div>

            {recentAudits.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No recent sensitive actions recorded in audit logs.</p>
            ) : (
              <div className="space-y-1.5">
                {recentAudits.slice(0, 5).map((log, idx) => (
                  <div key={idx} className="bg-slate-800/40 border border-slate-700/60 px-3 py-1.5 rounded text-xs flex justify-between items-center text-slate-300">
                    <div className="flex items-center gap-2 truncate">
                      <Badge variant="outline" className="text-[10px] bg-slate-900 border-slate-600 text-slate-300 font-mono">
                        {log.action}
                      </Badge>
                      <span className="truncate">{log.user_name || log.user_id || 'System'}</span>
                      {log.summary?.reason && (
                        <span className="text-slate-400 text-[11px] truncate hidden md:inline">
                          — &quot;{log.summary.reason}&quot;
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-slate-400 shrink-0 ml-2">
                      {log.timestamp ? new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* DECISION MODAL */}
      <Dialog open={decisionModalOpen} onOpenChange={setDecisionModalOpen}>
        <DialogContent className="max-w-md bg-white text-slate-900">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-600" />
              <span>{decisionType === 'approved' ? 'Approve' : 'Reject'} Sensitive Access Request</span>
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div className="bg-slate-50 p-3 rounded border border-slate-200 space-y-1">
              <div><strong>Requester:</strong> {selectedRequest?.requester_name || selectedRequest?.requester_email}</div>
              <div><strong>Requested Action:</strong> <code className="bg-slate-200 px-1 py-0.5 rounded">{selectedRequest?.action}</code></div>
              <div><strong>Case ID:</strong> {selectedRequest?.case_id}</div>
              <div><strong>Justification:</strong> {selectedRequest?.reason}</div>
            </div>

            <div>
              <label className="block font-medium mb-1">Administrative Notes (Optional):</label>
              <Textarea
                placeholder="Enter approval rationale or rejection notes..."
                value={decisionNotes}
                onChange={(e) => setDecisionNotes(e.target.value)}
                className="text-xs"
                rows={3}
              />
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" size="sm" onClick={() => setDecisionModalOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant={decisionType === 'approved' ? 'default' : 'destructive'}
              className={decisionType === 'approved' ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : ''}
              onClick={handleDecisionSubmit}
            >
              Confirm {decisionType === 'approved' ? 'Approval' : 'Rejection'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
