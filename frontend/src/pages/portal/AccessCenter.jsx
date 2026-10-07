/**
 * Backlog Phase 0-1 — Access & Security Center
 *
 * Everyone:   My sessions (log out other devices) · Request access · My requests
 * Approvers:  Approval inbox (maker-checker, SoD warnings)
 * Admins:     Feature registry + kill switch · SoD violations · Audit-chain check
 *             · Statutory settings (PF / ESI / PT / TDS, effective-dated)
 *
 * All data comes from /api/governance/* (backend/routers/governance.py).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft, ShieldCheck, RefreshCw, Power, CheckCircle, XCircle, LogOut } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL
  || (typeof window !== 'undefined' && window.location.hostname.includes('leamss.com') ? 'https://api.leamss.com' : 'http://localhost:8001');
const API = `${BACKEND_URL}/api/governance`;
const hdrs = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
const errText = (e) => {
  const d = e?.response?.data?.detail;
  if (!d) return e?.message || 'Request failed';
  if (typeof d === 'string') return d;
  return d.message || JSON.stringify(d);
};
const when = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—');
const RISK_TONE = { low: 'bg-slate-100 text-slate-700', medium: 'bg-sky-100 text-sky-800', high: 'bg-amber-100 text-amber-800', critical: 'bg-rose-100 text-rose-800' };
const STATUS_TONE = { pending: 'bg-amber-100 text-amber-800', approved: 'bg-emerald-100 text-emerald-800', rejected: 'bg-rose-100 text-rose-800', cancelled: 'bg-slate-100 text-slate-600', active: 'bg-emerald-100 text-emerald-800', ended: 'bg-slate-100 text-slate-600', revoked: 'bg-rose-100 text-rose-800' };

function Pill({ tone, children }) {
  return <span className={`inline-block rounded px-2 py-0.5 text-[11px] font-semibold ${tone || 'bg-slate-100 text-slate-700'}`}>{children}</span>;
}

function Empty({ children }) {
  return <p className="py-8 text-center text-sm text-slate-500">{children}</p>;
}

// ───────────────────────── My sessions ─────────────────────────
function SessionsTab() {
  const [rows, setRows] = useState([]);
  const load = useCallback(async () => {
    try { setRows((await axios.get(`${API}/sessions/me`, hdrs())).data); } catch (e) { toast.error(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const revokeOthers = async () => {
    try { const r = await axios.post(`${API}/sessions/me/revoke-others`, {}, hdrs()); toast.success(`Logged out ${r.data.revoked} other session(s)`); load(); } catch (e) { toast.error(errText(e)); }
  };
  const revoke = async (sid) => {
    try { await axios.post(`${API}/sessions/${sid}/revoke`, {}, hdrs()); toast.success('Session ended'); load(); } catch (e) { toast.error(errText(e)); }
  };
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-slate-900">Where you are logged in</h3>
          <p className="text-xs text-slate-500">If you see a device you do not recognise, log it out and change your password.</p>
        </div>
        <Button size="sm" variant="outline" onClick={revokeOthers} data-testid="revoke-others"><LogOut className="mr-1 h-4 w-4" />Log out other devices</Button>
      </div>
      {rows.length === 0 ? <Empty>No sessions recorded yet. Sessions appear after your next login.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left text-xs uppercase text-slate-500"><th className="py-2">Started</th><th>Last active</th><th>Device</th><th>IP</th><th>Type</th><th>Status</th><th /></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className="border-b last:border-0">
                  <td className="py-2">{when(s.created_at)}{s.current && <Badge className="ml-2" variant="secondary">this device</Badge>}</td>
                  <td>{when(s.last_seen_at)}</td>
                  <td className="max-w-[260px] truncate" title={s.user_agent}>{s.user_agent || '—'}</td>
                  <td>{s.ip || '—'}</td>
                  <td>{s.kind}{s.impersonated_by ? ' (by admin)' : ''}</td>
                  <td><Pill tone={STATUS_TONE[s.status]}>{s.status}</Pill></td>
                  <td className="text-right">{s.status === 'active' && !s.current && <Button size="sm" variant="ghost" onClick={() => revoke(s.id)}>End</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ───────────────────────── Request access + my requests ─────────────────────────
function RequestTab({ catalog }) {
  const [form, setForm] = useState({ feature_key: '', days: '', reason: '' });
  const [filter, setFilter] = useState('');
  const [mine, setMine] = useState([]);
  const load = useCallback(async () => {
    try { setMine((await axios.get(`${API}/access-requests/mine`, hdrs())).data); } catch (e) { toast.error(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const options = useMemo(() => catalog.filter((f) => f.stage !== 'retired'
    && (!filter || `${f.key} ${f.name}`.toLowerCase().includes(filter.toLowerCase()))).slice(0, 60), [catalog, filter]);
  const submit = async () => {
    try {
      await axios.post(`${API}/access-requests`, { feature_key: form.feature_key, reason: form.reason, days: form.days ? Number(form.days) : null }, hdrs());
      toast.success('Request sent for approval');
      setForm({ feature_key: '', days: '', reason: '' });
      load();
    } catch (e) { toast.error(errText(e)); }
  };
  const cancel = async (id) => {
    try { await axios.post(`${API}/access-requests/${id}/cancel`, {}, hdrs()); load(); } catch (e) { toast.error(errText(e)); }
  };
  const chosen = catalog.find((f) => f.key === form.feature_key);
  return (
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      <Card className="space-y-3 p-4">
        <h3 className="font-semibold text-slate-900">Request access</h3>
        <div>
          <Label>Find a feature</Label>
          <Input placeholder="e.g. refunds, payroll, payouts" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <select className="mt-2 w-full rounded border p-2 text-sm" size={6} value={form.feature_key}
            onChange={(e) => setForm({ ...form, feature_key: e.target.value })} data-testid="feature-select">
            {options.map((f) => <option key={f.key} value={f.key}>{f.name} · {f.key}</option>)}
          </select>
          <Input className="mt-2" placeholder="feature key" value={form.feature_key} onChange={(e) => setForm({ ...form, feature_key: e.target.value })} />
        </div>
        {chosen && <p className="text-xs text-slate-600">Risk <Pill tone={RISK_TONE[chosen.risk]}>{chosen.risk}</Pill> — high and critical access needs more than one approver and is time-limited (critical: 7 days max).</p>}
        <div>
          <Label>For how many days?</Label>
          <Input type="number" min="1" max="365" placeholder="leave blank for the maximum allowed" value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} />
        </div>
        <div>
          <Label>Business reason</Label>
          <Textarea rows={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Why do you need this access?" />
        </div>
        <Button className="w-full bg-[#2a777a] hover:bg-[#1f5e60]" disabled={!form.feature_key || form.reason.trim().length < 10} onClick={submit} data-testid="submit-request">Send request</Button>
      </Card>
      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between"><h3 className="font-semibold text-slate-900">My requests</h3><Button size="sm" variant="ghost" onClick={load}><RefreshCw className="h-4 w-4" /></Button></div>
        {mine.length === 0 ? <Empty>No requests yet.</Empty> : (
          <div className="space-y-2">
            {mine.map((r) => (
              <div key={r.id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{r.feature_name || r.feature_key}</span>
                  <Pill tone={RISK_TONE[r.risk]}>{r.risk}</Pill>
                  <Pill tone={STATUS_TONE[r.status]}>{r.status}</Pill>
                  {r.status === 'pending' && <span className="text-xs text-slate-500">waiting for: {r.steps[r.current_step]}</span>}
                  {r.status === 'pending' && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => cancel(r.id)}>Cancel</Button>}
                </div>
                <p className="mt-1 text-xs text-slate-600">{r.reason}</p>
                {r.sod_conflicts?.length > 0 && <p className="mt-1 text-xs text-rose-700">Separation-of-duties conflict: {r.sod_conflicts.map((c) => c.name).join(', ')}</p>}
                <p className="mt-1 text-[11px] text-slate-400">Raised {when(r.created_at)} for {r.target_name}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ───────────────────────── Approvals ─────────────────────────
function ApprovalsTab({ isOwner }) {
  const [rows, setRows] = useState([]);
  const [comment, setComment] = useState({});
  const load = useCallback(async () => {
    try { setRows((await axios.get(`${API}/access-requests/inbox`, hdrs())).data); } catch (e) { toast.error(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const decide = async (r, approve) => {
    const body = { comment: comment[r.id] || '' };
    if (approve && r.sod_conflicts?.length && isOwner) {
      const why = window.prompt('This grant breaks a separation-of-duties rule. Enter the override reason (it is recorded in the audit trail):');
      if (!why) return;
      body.sod_override_reason = why;
    }
    try {
      await axios.post(`${API}/access-requests/${r.id}/${approve ? 'approve' : 'reject'}`, body, hdrs());
      toast.success(approve ? 'Approved' : 'Rejected');
      load();
    } catch (e) { toast.error(errText(e)); }
  };
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center justify-between"><h3 className="font-semibold text-slate-900">Waiting for your decision</h3><Button size="sm" variant="ghost" onClick={load}><RefreshCw className="h-4 w-4" /></Button></div>
      {rows.length === 0 ? <Empty>Nothing to approve.</Empty> : rows.map((r) => (
        <div key={r.id} className="mb-2 rounded border p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{r.target_name}</span><span className="text-slate-500">wants</span>
            <span className="font-medium">{r.feature_name || r.feature_key}</span>
            <Pill tone={RISK_TONE[r.risk]}>{r.risk}</Pill>
            <span className="text-xs text-slate-500">step {r.current_step + 1} of {r.steps.length}: {r.awaiting_step} · {r.requested_days} days</span>
          </div>
          <p className="mt-1 text-xs text-slate-600">{r.reason}</p>
          {r.sod_conflicts?.length > 0 && <p className="mt-1 text-xs font-medium text-rose-700">Separation-of-duties conflict: {r.sod_conflicts.map((c) => c.name).join(', ')}{isOwner ? ' — you can override with a reason.' : ' — only the owner can override.'}</p>}
          <div className="mt-2 flex gap-2">
            <Input className="h-8" placeholder="comment (optional)" value={comment[r.id] || ''} onChange={(e) => setComment({ ...comment, [r.id]: e.target.value })} />
            <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => decide(r, true)}><CheckCircle className="mr-1 h-4 w-4" />Approve</Button>
            <Button size="sm" variant="outline" className="text-rose-700" onClick={() => decide(r, false)}><XCircle className="mr-1 h-4 w-4" />Reject</Button>
          </div>
        </div>
      ))}
    </Card>
  );
}

// ───────────────────────── Feature registry (admin) ─────────────────────────
function FeaturesTab({ catalog, reload }) {
  const [q, setQ] = useState('');
  const shown = catalog.filter((f) => !q || `${f.key} ${f.name} ${f.owner_dept}`.toLowerCase().includes(q.toLowerCase()));
  const kill = async (f) => {
    const reason = window.prompt(`Switch OFF "${f.name}" for everyone? Enter the reason:`);
    if (!reason) return;
    try { await axios.post(`${API}/features/${f.key}/kill`, { reason }, hdrs()); toast.success('Switched off (all servers within 30 s)'); reload(); } catch (e) { toast.error(errText(e)); }
  };
  const unkill = async (f) => {
    try { await axios.post(`${API}/features/${f.key}/unkill`, {}, hdrs()); toast.success('Restored'); reload(); } catch (e) { toast.error(errText(e)); }
  };
  const patch = async (f, changes) => {
    try { await axios.patch(`${API}/features/${f.key}`, changes, hdrs()); reload(); } catch (e) { toast.error(errText(e)); }
  };
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center gap-2">
        <Input placeholder="Search features" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" />
        <span className="text-xs text-slate-500">{shown.length} of {catalog.length}</span>
      </div>
      <div className="max-h-[560px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white"><tr className="border-b text-left text-xs uppercase text-slate-500"><th className="py-2">Feature</th><th>Owner</th><th>Risk</th><th>Stage</th><th>Status</th><th /></tr></thead>
          <tbody>
            {shown.map((f) => (
              <tr key={f.key} className="border-b last:border-0">
                <td className="py-2"><div className="font-medium">{f.name}</div><div className="text-[11px] text-slate-400">{f.key}</div></td>
                <td>{f.owner_dept}</td>
                <td>
                  <select className="rounded border px-1 py-0.5 text-xs" value={f.risk} onChange={(e) => patch(f, { risk: e.target.value })}>
                    {['low', 'medium', 'high', 'critical'].map((r) => <option key={r}>{r}</option>)}
                  </select>
                </td>
                <td>
                  <select className="rounded border px-1 py-0.5 text-xs" value={f.stage} onChange={(e) => patch(f, { stage: e.target.value })}>
                    {['development', 'pilot', 'department', 'company', 'retired'].map((s) => <option key={s}>{s}</option>)}
                  </select>
                </td>
                <td>{f.killed ? <Pill tone="bg-rose-100 text-rose-800">OFF</Pill> : <Pill tone="bg-emerald-100 text-emerald-800">on</Pill>}</td>
                <td className="text-right">
                  {f.killed
                    ? <Button size="sm" variant="outline" onClick={() => unkill(f)}>Restore</Button>
                    : <Button size="sm" variant="ghost" className="text-rose-700" onClick={() => kill(f)}><Power className="mr-1 h-3.5 w-3.5" />Kill</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ───────────────────────── Controls (admin): SoD + audit ─────────────────────────
function ControlsTab() {
  const [viol, setViol] = useState(null);
  const [chain, setChain] = useState(null);
  const [events, setEvents] = useState([]);
  const run = async () => {
    try {
      const [v, c, e] = await Promise.all([
        axios.get(`${API}/sod/violations`, hdrs()), axios.get(`${API}/audit/verify`, hdrs()),
        axios.get(`${API}/audit/events?limit=50`, hdrs()),
      ]);
      setViol(v.data); setChain(c.data); setEvents(e.data);
    } catch (e) { toast.error(errText(e)); }
  };
  useEffect(() => { run(); }, []);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <h3 className="font-semibold text-slate-900">Audit trail integrity</h3>
        {chain && (chain.ok
          ? <p className="mt-2 text-sm text-emerald-700">Verified — {chain.checked} events, no tampering detected.</p>
          : <p className="mt-2 text-sm font-medium text-rose-700">BROKEN at event #{chain.broken_at_seq}: {chain.reason}. Report to the MD immediately.</p>)}
        <h4 className="mt-4 text-sm font-semibold text-slate-800">People holding conflicting powers</h4>
        {viol && (viol.length === 0 ? <p className="text-sm text-slate-500">None found.</p> : viol.map((v) => (
          <div key={v.user_id} className="mt-1 text-sm"><span className="font-medium">{v.name}</span> <span className="text-slate-500">({v.department || '—'})</span>: {v.violations.map((x) => x.name).join(', ')}</div>
        )))}
        <Button size="sm" variant="outline" className="mt-3" onClick={run}><RefreshCw className="mr-1 h-4 w-4" />Re-check</Button>
      </Card>
      <Card className="p-4">
        <h3 className="font-semibold text-slate-900">Latest audit events</h3>
        <div className="mt-2 max-h-[420px] overflow-auto text-xs">
          {events.map((e) => (
            <div key={e.id} className="border-b py-1.5 last:border-0">
              <span className="text-slate-400">#{e.seq} {when(e.at)}</span> <span className="font-medium">{e.action}</span> <span className="text-slate-500">by {e.actor_name || e.actor_id}</span>
              {e.severity !== 'info' && <Pill tone={e.severity === 'critical' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'}>{e.severity}</Pill>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ───────────────────────── Statutory settings (admin/HR) ─────────────────────────
function StatutoryTab() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ key: '', value: '', effective_from: '', note: '', source_url: '' });
  const load = useCallback(async () => {
    try { setRows((await axios.get(`${API}/statutory`, hdrs())).data); } catch (e) { toast.error(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const add = async () => {
    let value = form.value;
    try { value = JSON.parse(form.value); } catch (e) { /* keep as text */ }
    try { await axios.post(`${API}/statutory`, { ...form, value }, hdrs()); toast.success('New rate saved — past payrolls are unaffected'); setForm({ key: '', value: '', effective_from: '', note: '', source_url: '' }); load(); } catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <Card className="p-4">
        <h3 className="font-semibold text-slate-900">Statutory settings (history kept forever)</h3>
        <p className="mb-2 text-xs text-slate-500">Payroll uses the value in force on the last day of the wage month. Confirm every value with your CA.</p>
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white"><tr className="border-b text-left text-xs uppercase text-slate-500"><th className="py-2">Key</th><th>Value</th><th>From</th><th>Note</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id || `${r.key}-${r.effective_from}`} className="border-b last:border-0 align-top">
                  <td className="py-1.5 font-mono text-xs">{r.key}</td>
                  <td className="max-w-[220px] break-words font-mono text-xs">{typeof r.value === 'object' ? JSON.stringify(r.value) : String(r.value)}</td>
                  <td className="whitespace-nowrap text-xs">{r.effective_from}</td>
                  <td className="text-xs text-slate-600">{r.note}{r.source_url && <> · <a className="text-[#2a777a] underline" href={r.source_url} target="_blank" rel="noreferrer">source</a></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card className="space-y-2 p-4">
        <h3 className="font-semibold text-slate-900">Add a new rate</h3>
        <Label>Key</Label><Input placeholder="pf.wage_ceiling_inr" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} />
        <Label>Value</Label><Input placeholder="25000" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />
        <Label>Effective from</Label><Input type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
        <Label>Note</Label><Input placeholder="Gazette / circular reference" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        <Label>Source URL</Label><Input value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} />
        <Button className="w-full bg-[#2a777a] hover:bg-[#1f5e60]" disabled={!form.key || !form.effective_from || form.note.length < 5} onClick={add}>Save new version</Button>
      </Card>
    </div>
  );
}

// ───────────────────────── Page ─────────────────────────
export default function AccessCenter() {
  const navigate = useNavigate();
  const [me, setMe] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [requestable, setRequestable] = useState([]);
  const [allowed, setAllowed] = useState(new Set());

  const loadCatalog = useCallback(async (canSeeRegistry) => {
    if (!canSeeRegistry) return;
    try { setCatalog((await axios.get(`${API}/features`, hdrs())).data); } catch (e) { /* not an admin */ }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [u, f] = await Promise.all([
          axios.get(`${BACKEND_URL}/api/auth/me`, hdrs()), axios.get(`${API}/features/me`, hdrs()),
        ]);
        setMe(u.data);
        const set = new Set(f.data.features);
        setAllowed(set);
        loadCatalog(set.has('governance.feature_registry'));
        axios.get(`${API}/features/requestable`, hdrs()).then((r) => setRequestable(r.data)).catch(() => {});
      } catch (e) {
        if (e?.response?.status === 401) navigate('/');
        else toast.error(errText(e));
      }
    })();
  }, [navigate, loadCatalog]);

  const role = me?.rbac_role || me?.role;
  const isOwner = role === 'admin_owner';
  const can = (k) => allowed.has(k);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="access-center-page">
      <div className="mx-auto max-w-6xl p-4 md:p-6">
        <div className="mb-4 flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)}><ArrowLeft className="h-4 w-4" /></Button>
          <ShieldCheck className="h-6 w-6 text-[#2a777a]" />
          <div>
            <h1 className="text-lg font-bold text-slate-900">Access &amp; Security Center</h1>
            <p className="text-xs text-slate-500">Your sessions, access requests and approvals{can('governance.feature_registry') ? ', plus company-wide controls' : ''}.</p>
          </div>
        </div>
        <Tabs defaultValue="sessions">
          <TabsList className="mb-3 flex-wrap">
            <TabsTrigger value="sessions">My sessions</TabsTrigger>
            <TabsTrigger value="request">Request access</TabsTrigger>
            <TabsTrigger value="approvals">Approvals</TabsTrigger>
            {can('governance.feature_registry') && <TabsTrigger value="features">Feature registry</TabsTrigger>}
            {(can('governance.sod_rules') || can('governance.audit_chain')) && <TabsTrigger value="controls">Controls &amp; audit</TabsTrigger>}
            {can('governance.statutory_settings') && <TabsTrigger value="statutory">Statutory settings</TabsTrigger>}
          </TabsList>
          <TabsContent value="sessions"><SessionsTab /></TabsContent>
          <TabsContent value="request"><RequestTab catalog={requestable} /></TabsContent>
          <TabsContent value="approvals"><ApprovalsTab isOwner={isOwner} /></TabsContent>
          {can('governance.feature_registry') && <TabsContent value="features"><FeaturesTab catalog={catalog} reload={() => loadCatalog(true)} /></TabsContent>}
          {(can('governance.sod_rules') || can('governance.audit_chain')) && <TabsContent value="controls"><ControlsTab /></TabsContent>}
          {can('governance.statutory_settings') && <TabsContent value="statutory"><StatutoryTab /></TabsContent>}
        </Tabs>
      </div>
    </div>
  );
}
