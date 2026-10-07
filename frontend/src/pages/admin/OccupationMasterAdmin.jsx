/**
 * Phase 6.9 — Occupation Master Admin Console.
 *
 * Single page with 4 tabs covering 6.9.2 → 6.9.5:
 *   • Browse & Verify (6.9.3) — list all draft codes, open 3-panel editor
 *   • Bulk Import   (6.9.2) — CSV/Excel upload + preview + commit
 *   • Country Templates (6.9.5) — view/edit factor lists, add new country
 *   • Status & Settings (6.9.4) — verification threshold + auto-flag outdated
 *
 * Route: /admin/kb/occupation-master
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  ArrowLeft, Search, Upload, Sparkles, Globe2, Settings2, FileText,
  CheckCircle2, AlertCircle, Loader2, Wand2, Save, RefreshCw, Trash2,
  ExternalLink, Plus, ShieldCheck,
} from 'lucide-react';

import { formatApiError } from '@/lib/apiErrors';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function OccupationMasterAdmin() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const token = localStorage.getItem('token');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const tab = params.get('tab') || 'browse';

  return (
    <div className="min-h-screen bg-slate-50 p-5" data-testid="kb-admin-page">
      <div className="max-w-7xl mx-auto space-y-4">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => navigate('/admin/eligibility/knowledge-base')} data-testid="back-btn">
            <ArrowLeft className="h-4 w-4 mr-1" />KB Home
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Globe2 className="h-7 w-7 text-indigo-600" />
              Occupation Master Admin Console
              <Badge className="bg-indigo-600 text-white text-[9px]">Phase 6.9</Badge>
            </h1>
            <p className="text-sm text-slate-500">AI drafts · Admin verifies · Sales uses verified data</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto border-teal-300 text-teal-700 hover:bg-teal-50"
            onClick={() => navigate('/admin/kb/eoi-backlog')}
            data-testid="open-eoi-backlog"
          >
            <FileText className="h-4 w-4 mr-1" />EOI Backlog Data
          </Button>
        </div>

        <Tabs value={tab} onValueChange={(v) => setParams({ tab: v })}>
          <TabsList className="bg-white border" data-testid="kb-tabs">
            <TabsTrigger value="browse" data-testid="tab-browse"><FileText className="h-4 w-4 mr-1" />Browse &amp; Verify</TabsTrigger>
            <TabsTrigger value="import" data-testid="tab-import"><Upload className="h-4 w-4 mr-1" />Bulk Import</TabsTrigger>
            <TabsTrigger value="templates" data-testid="tab-templates"><Globe2 className="h-4 w-4 mr-1" />Country Templates</TabsTrigger>
            <TabsTrigger value="settings" data-testid="tab-settings"><Settings2 className="h-4 w-4 mr-1" />Status &amp; Settings</TabsTrigger>
          </TabsList>

          <TabsContent value="browse"><BrowseAndVerify headers={headers} /></TabsContent>
          <TabsContent value="import"><BulkImport headers={headers} /></TabsContent>
          <TabsContent value="templates"><CountryTemplates headers={headers} /></TabsContent>
          <TabsContent value="settings"><StatusSettings headers={headers} /></TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// 6.9.3 — Browse & Verify (with 3-panel editor)
// ════════════════════════════════════════════════════════════════
function BrowseAndVerify({ headers }) {
  const [list, setList] = useState([]);
  const [filters, setFilters] = useState({ status: 'all', country: 'AU', search: '' });
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (filters.status && filters.status !== 'all') p.append('status', filters.status);
      else p.append('status', 'all');
      if (filters.country && filters.country !== 'all') p.append('country', filters.country);
      if (filters.search) p.append('search', filters.search);
      p.append('limit', '300');
      const r = await axios.get(`${API}/occupation-master?${p}`, { headers });
      setList(r.data.items || []);
    } catch (e) {
      toast.error(formatApiError(e, 'Failed to load occupations'));
    } finally { setLoading(false); }
  }, [filters, headers]);

  useEffect(() => { load(); }, [load]);

  if (editing) {
    return <ThreePanelEditor item={editing} headers={headers}
      onSaved={() => { setEditing(null); load(); }}
      onCancel={() => setEditing(null)} />;
  }

  return (
    <div className="space-y-3">
      <Card className="p-3">
        <div className="flex flex-wrap gap-2 items-center">
          <Input placeholder="Search code / title…" value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            className="max-w-xs h-9" data-testid="browse-search" />
          <Select value={filters.country || 'all'} onValueChange={(v) => setFilters({ ...filters, country: v === 'all' ? '' : v })}>
            <SelectTrigger className="w-32 h-9" data-testid="browse-country"><SelectValue placeholder="Country" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All countries</SelectItem>
              <SelectItem value="AU">🇦🇺 AU (Australia)</SelectItem>
              <SelectItem value="CA">🇨🇦 CA (Canada)</SelectItem>
              <SelectItem value="NZ">🇳🇿 NZ (New Zealand)</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filters.status || 'all'} onValueChange={(v) => setFilters({ ...filters, status: v === 'all' ? 'all' : v })}>
            <SelectTrigger className="w-32 h-9" data-testid="browse-status"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="verified">Verified (Active)</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="outdated">Outdated</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" className="h-9" onClick={load} data-testid="browse-refresh">
            <RefreshCw className="h-3.5 w-3.5 mr-1" />Refresh
          </Button>
          <span className="text-xs text-slate-500 ml-auto font-medium">{list.length} codes shown</span>
        </div>
      </Card>

      {loading ? (
        <Card className="p-10 text-center text-slate-400"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></Card>
      ) : list.length === 0 ? (
        <Card className="p-10 text-center text-slate-400 text-sm">No codes match these filters.</Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2" data-testid="codes-grid">
          {list.map((it) => <CodeCard key={it.occupation_id} item={it} onOpen={() => setEditing(it)} />)}
        </div>
      )}
    </div>
  );
}

function CodeCard({ item, onOpen }) {
  const statusColor = {
    verified: 'bg-emerald-100 text-emerald-700',
    draft: 'bg-amber-100 text-amber-700',
    outdated: 'bg-rose-100 text-rose-700',
    superseded: 'bg-slate-100 text-slate-500',
  }[item.status] || 'bg-slate-100';
  return (
    <Card className="p-3 hover:shadow-md transition cursor-pointer" onClick={onOpen} data-testid={`code-card-${item.occupation_id}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-mono text-slate-500">{item.country_code} · {item.code}</p>
          <p className="text-sm font-bold truncate">{item.title}</p>
          <p className="text-[10px] text-slate-500 truncate">
            {(item.assessing_authority || {}).name || '—'} · Skill Lv {item.skill_level || '?'}
          </p>
        </div>
        <Badge className={`${statusColor} text-[9px]`} data-testid={`status-${item.occupation_id}`}>
          {item.status}
        </Badge>
      </div>
      <div className="flex items-center justify-between mt-2 text-[10px] text-slate-500">
        <span>{item.classification_type}</span>
        {item.ai_draft?.generated_at && <span title="AI draft cached"><Sparkles className="h-2.5 w-2.5 inline" /> AI draft</span>}
      </div>
    </Card>
  );
}

function ThreePanelEditor({ item, headers, onSaved, onCancel }) {
  const [edit, setEdit] = useState(item);
  const [authorities, setAuthorities] = useState([]);
  const [genLoading, setGenLoading] = useState(false);
  const [polishLoading, setPolishLoading] = useState(null);
  const [saving, setSaving] = useState(false);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [sourceRef, setSourceRef] = useState(item.verification?.source_reference || '');
  const [reviewNotes, setReviewNotes] = useState(item.verification?.review_notes || '');

  // Fetch authorities list
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/assessing-authorities?country=${item.country_code || 'AU'}`, { headers });
        if (active) setAuthorities(r.data.items || []);
      } catch (e) {
        console.error('Failed to load authorities', e);
      }
    })();
    return () => { active = false; };
  }, [item.country_code, headers]);

  const aiDraft = edit.ai_draft || {};

  const handleAuthorityChange = (authCode) => {
    const selected = authorities.find((a) => a.code === authCode);
    if (!selected) return;
    setEdit((s) => ({
      ...s,
      assessing_authority_id: selected.id,
      assessing_authority: {
        code: selected.code,
        short_name: selected.code,
        name: selected.full_name || selected.name,
        full_name: selected.full_name,
        website: selected.website,
      },
      skill_assessment_details: {
        ...(s.skill_assessment_details || {}),
        authority: selected.code,
        msa_fee_aud: selected.fees?.msa_fee_aud,
        rpl_fee_aud: selected.fees?.rpl_fee_aud,
        processing_weeks: selected.processing?.standard_days_max ? `${Math.round(selected.processing.standard_days_min / 7)}–${Math.round(selected.processing.standard_days_max / 7)} weeks` : '8–12 weeks',
      },
    }));
  };

  const generate = async () => {
    setGenLoading(true);
    try {
      const r = await axios.post(`${API}/occupation-master/${item.occupation_id}/ai-draft`, {}, { headers });
      setEdit((s) => ({ ...s, ai_draft: r.data.ai_draft }));
      toast.success('AI draft generated', { description: 'Review the LEFT panel and copy useful bits to your edit.' });
    } catch (e) {
      toast.error(formatApiError(e, 'AI draft failed'));
    } finally { setGenLoading(false); }
  };

  const copyAiField = (fieldKey, aiValue) => {
    setEdit((s) => ({ ...s, [fieldKey]: aiValue }));
    toast.success(`Copied AI ${fieldKey.replace('_', ' ')} to editor`);
  };

  const polish = async (fieldKey, fieldLabel) => {
    const text = edit[fieldKey];
    if (!text || (Array.isArray(text) && !text.length)) {
      toast.error('Field is empty');
      return;
    }
    const payload = Array.isArray(text) ? text.join('\n') : text;
    setPolishLoading(fieldKey);
    try {
      const r = await axios.post(`${API}/kb/polish-text`, {
        text: payload, field_label: fieldLabel,
        context: `Occupation: ${item.code} ${item.title}, ${item.country_code}`,
      }, { headers });
      const polished = Array.isArray(text) ? r.data.polished.split('\n').filter(Boolean) : r.data.polished;
      setEdit((s) => ({ ...s, [fieldKey]: polished }));
      toast.success('Text polished', { description: 'Facts preserved · grammar + tone improved.' });
    } catch (e) {
      toast.error(formatApiError(e, 'Polish failed'));
    } finally { setPolishLoading(null); }
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        title: edit.title,
        description: edit.description,
        typical_tasks: edit.typical_tasks,
        alternative_titles: edit.alternative_titles,
        specialisations: edit.specialisations,
        skill_level: edit.skill_level ? parseInt(edit.skill_level) : undefined,
        skillselect_tier: edit.skillselect_tier,
        assessing_authority: edit.assessing_authority,
        assessing_authority_id: edit.assessing_authority_id,
        caveats: edit.caveats,
        min_invitation_points: edit.min_invitation_points,
        visa_pathways: edit.visa_pathways,
        state_territory_eligibility: edit.state_territory_eligibility,
        state_demand: edit.state_demand,
        skill_assessment_details: edit.skill_assessment_details,
        classification_version: edit.classification_version,
      };
      await axios.put(`${API}/occupation-master/${item.occupation_id}`, payload, { headers });
      toast.success('Draft saved successfully');
      onSaved();
    } catch (e) {
      toast.error(formatApiError(e, 'Save failed'));
    } finally { setSaving(false); }
  };

  const verify = async () => {
    if (!sourceRef.trim()) { toast.error('Add an official source URL/reference first'); return; }
    setSaving(true);
    try {
      const payload = {
        source_reference: sourceRef,
        review_notes: reviewNotes,
        title: edit.title,
        description: edit.description,
        typical_tasks: edit.typical_tasks,
        alternative_titles: edit.alternative_titles,
        specialisations: edit.specialisations,
        skill_level: edit.skill_level ? parseInt(edit.skill_level) : undefined,
        skillselect_tier: edit.skillselect_tier,
        assessing_authority: edit.assessing_authority,
        assessing_authority_id: edit.assessing_authority_id,
        caveats: edit.caveats,
        min_invitation_points: edit.min_invitation_points,
        visa_pathways: edit.visa_pathways,
        state_territory_eligibility: edit.state_territory_eligibility,
        skill_assessment_details: edit.skill_assessment_details,
      };
      await axios.post(`${API}/occupation-master/${item.occupation_id}/verify`, payload, { headers });
      toast.success('✓ Verified & published', { description: 'All changes propagated to Knowledge Base & Sales.' });
      onSaved();
    } catch (e) {
      toast.error(formatApiError(e, 'Verify failed'));
    } finally { setSaving(false); }
  };

  const [migrotoLoading, setMigrotoLoading] = useState(false);
  const syncMigroto = async () => {
    if (item.country_code !== 'AU') {
      toast.error('Migroto live sync is available for Australia (ANZSCO) occupations');
      return;
    }
    setMigrotoLoading(true);
    try {
      const r = await axios.post(`${API}/migroto/sync/${item.code}`, {}, { headers });
      if (r.data.status === 'success') {
        const details = await axios.get(`${API}/migroto/occupation/${item.code}`, { headers });
        const insight = details.data?.data;
        if (insight) {
          setEdit((s) => ({
            ...s,
            classification_version: insight.occupation?.version || r.data.migroto_info?.classification_version || s.classification_version,
            skillselect_tier: insight.occupation?.tier || s.skillselect_tier,
            typical_tasks: insight.occupation?.essential_tasks ? insight.occupation.essential_tasks.split('\n').filter(Boolean) : s.typical_tasks,
            migroto_synced: true,
            migroto_last_update: insight.eoi_backlog_last_update,
          }));
        }
        toast.success('✓ Synced with Migroto Skilled Migration Registry', {
          description: `Verified ANZSCO code ${item.code} (${r.data.migroto_info?.classification_version || 'v1.3, v2022'}). Tier & backlog updated.`
        });
      } else {
        toast.error(r.data.error || 'Migroto sync failed');
      }
    } catch (e) {
      toast.error(formatApiError(e, 'Failed to sync with Migroto'));
    } finally {
      setMigrotoLoading(false);
    }
  };

  const selectedAuthCode = edit.assessing_authority?.code || edit.assessing_authority?.short_name || edit.skill_assessment_details?.authority || '';
  const currentAuthDoc = authorities.find((a) => a.code === selectedAuthCode);

  return (
    <Card className="p-4 space-y-4" data-testid="three-panel-editor">
      {/* Header with status badges and actions */}
      <div className="flex items-start justify-between flex-wrap gap-3 pb-3 border-b">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-mono font-bold bg-slate-100 px-2 py-0.5 rounded text-slate-700">
              {item.country_code} · {item.code}
            </span>
            <Badge className="text-[10px] bg-emerald-100 text-emerald-800 border-emerald-300">
              {edit.status || item.status}
            </Badge>
            <Badge className="text-[10px] bg-indigo-100 text-indigo-800 border-indigo-300">
              {edit.classification_version || edit.classification_type || item.classification_type} (2013 / 2022)
            </Badge>
            {edit.skillselect_tier && (
              <Badge className="text-[10px] bg-teal-100 text-teal-800 border-teal-300">
                {String(edit.skillselect_tier).replace('_', ' ').toUpperCase()}
              </Badge>
            )}
            {(edit.migroto_synced || item.migroto_synced) && (
              <Badge className="text-[10px] bg-teal-600 text-white border-teal-700" title="Synchronized with Migroto Australian Skilled Migration Registry">
                Migroto Live ✓
              </Badge>
            )}
          </div>
          <h2 className="text-xl font-bold mt-1 text-slate-900">{edit.title || item.title}</h2>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          {item.country_code === 'AU' && (
            <Button
              variant="outline"
              size="sm"
              onClick={syncMigroto}
              disabled={migrotoLoading}
              className="border-teal-400 text-teal-700 hover:bg-teal-50"
              data-testid="editor-migroto-sync"
              title="Pull latest ANZSCO version, SkillSelect tier, and invitation data from Migroto"
            >
              {migrotoLoading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <RefreshCw className="h-3 w-3 mr-1 text-teal-600" />}
              Migroto Live Sync
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={onCancel} data-testid="editor-cancel">
            Back
          </Button>
          <Button size="sm" onClick={save} disabled={saving} className="bg-slate-700 hover:bg-slate-800" data-testid="editor-save-draft">
            {saving ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Save className="h-3 w-3 mr-1" />}
            Save Draft
          </Button>
          <Button size="sm" onClick={() => setVerifyOpen(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium" data-testid="editor-open-verify">
            <CheckCircle2 className="h-3 w-3 mr-1" />
            Verify &amp; Publish
          </Button>
        </div>
      </div>

      {/* 3-Panel Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* PANEL 1: LEFT — AI Draft & Baseline (Read + Apply) */}
        <Card className="p-3 bg-purple-50/40 border-purple-200 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-purple-100">
            <h3 className="text-xs font-bold uppercase text-purple-900 flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-purple-600" />
              AI Draft (Baseline Insights)
            </h3>
            <Button size="sm" variant="outline" onClick={generate} disabled={genLoading} className="h-7 text-[10px] border-purple-300 bg-white" data-testid="generate-ai-draft">
              {genLoading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Wand2 className="h-3 w-3 mr-1 text-purple-600" />}
              Generate Draft
            </Button>
          </div>

          {aiDraft.generated_at ? (
            <div className="space-y-3 text-xs">
              <div>
                <div className="flex justify-between items-center mb-1">
                  <span className="font-semibold text-purple-800">Draft Description</span>
                  <button onClick={() => copyAiField('description', aiDraft.description)} className="text-[10px] text-purple-600 hover:underline">Apply →</button>
                </div>
                <p className="bg-white p-2 rounded border border-purple-100 whitespace-pre-wrap text-[11px] leading-relaxed">{aiDraft.description || '—'}</p>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <span className="font-semibold text-purple-800">Draft Tasks</span>
                  <button onClick={() => copyAiField('typical_tasks', aiDraft.typical_tasks)} className="text-[10px] text-purple-600 hover:underline">Apply →</button>
                </div>
                <ul className="list-disc list-inside bg-white p-2 rounded border border-purple-100 space-y-1 text-[11px]">
                  {(aiDraft.typical_tasks || []).map((t, i) => <li key={i}>{t}</li>)}
                </ul>
              </div>

              {aiDraft.qualification_rules && (
                <div>
                  <span className="font-semibold text-purple-800 block mb-1">Qualification Guidance</span>
                  <p className="bg-white p-2 rounded border border-purple-100 text-[11px]">{aiDraft.qualification_rules}</p>
                </div>
              )}

              {aiDraft.ai_confidence_note && (
                <div className="bg-amber-50 border border-amber-200 p-2 rounded text-[10px] text-amber-900">
                  <strong>⚠️ AI Note:</strong> {aiDraft.ai_confidence_note}
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-slate-500 text-center py-10 space-y-2">
              <Sparkles className="h-8 w-8 mx-auto text-purple-400 opacity-60" />
              <p className="font-medium text-slate-700">No AI Draft Cached</p>
              <p className="text-[11px] text-slate-500">Click &quot;Generate Draft&quot; to fetch Claude Sonnet baseline recommendations.</p>
            </div>
          )}
        </Card>

        {/* PANEL 2: MIDDLE — Admin Edit & Classification Master */}
        <Card className="p-3 bg-emerald-50/40 border-emerald-200 space-y-3">
          <h3 className="text-xs font-bold uppercase text-emerald-900 pb-2 border-b border-emerald-100 flex items-center gap-1.5">
            ✏️ Admin Master Edit (Single Source of Truth)
          </h3>
          <div className="space-y-3">
            <Field label="Occupation Title">
              <Input value={edit.title || ''} onChange={(e) => setEdit({ ...edit, title: e.target.value })} className="h-8 text-xs bg-white" data-testid="edit-title" />
            </Field>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Skill Level (1–5)">
                <Input type="number" min="1" max="5" value={edit.skill_level || ''} onChange={(e) => setEdit({ ...edit, skill_level: e.target.value })} className="h-8 text-xs bg-white" />
              </Field>
              <Field label="SkillSelect Tier">
                <Select
                  value={typeof edit.skillselect_tier === 'object' && edit.skillselect_tier !== null
                    ? (edit.skillselect_tier.tier || 'tier_4')
                    : (edit.skillselect_tier || 'tier_4')}
                  onValueChange={(v) => setEdit({ ...edit, skillselect_tier: v })}
                >
                  <SelectTrigger className="h-8 text-xs bg-white"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tier_1">Tier 1 (Priority Health & Education)</SelectItem>
                    <SelectItem value="tier_2">Tier 2 (Core Skills / CSOL)</SelectItem>
                    <SelectItem value="tier_3">Tier 3 (MLTSSL Strategic Trades & Mgmt)</SelectItem>
                    <SelectItem value="tier_4">Tier 4 (Short-Term / Regional)</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </div>

            <Field label={<>Description <PolishBtn loading={polishLoading === 'description'} onClick={() => polish('description', 'Description')} /></>}>
              <Textarea value={edit.description || ''} onChange={(e) => setEdit({ ...edit, description: e.target.value })} className="text-xs min-h-[75px] bg-white leading-relaxed" data-testid="edit-description" />
            </Field>

            <Field label={<>Typical Tasks (one per line) <PolishBtn loading={polishLoading === 'typical_tasks'} onClick={() => polish('typical_tasks', 'Typical Tasks')} /></>}>
              <Textarea value={(edit.typical_tasks || []).join('\n')}
                onChange={(e) => setEdit({ ...edit, typical_tasks: e.target.value.split('\n').filter(Boolean) })}
                className="text-xs min-h-[95px] bg-white" data-testid="edit-tasks" />
            </Field>

            <Field label="Alternative Titles (comma-separated)">
              <Input value={(edit.alternative_titles || []).join(', ')}
                onChange={(e) => setEdit({ ...edit, alternative_titles: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                className="h-8 text-xs bg-white" data-testid="edit-alt-titles" />
            </Field>

            <Field label="Specialisations (comma-separated)">
              <Input value={(edit.specialisations || []).join(', ')}
                onChange={(e) => setEdit({ ...edit, specialisations: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                className="h-8 text-xs bg-white" />
            </Field>

            <Field label="Caveats / Regulatory Notes">
              <Textarea value={typeof edit.caveats === 'string' ? edit.caveats : Array.isArray(edit.caveats) ? edit.caveats.join('\n') : (edit.caveats?.notes || '')}
                onChange={(e) => setEdit({ ...edit, caveats: e.target.value })}
                placeholder="e.g. Caveat 1: Minimum annual remuneration AUD $73,150..."
                className="text-xs min-h-[50px] bg-white" />
            </Field>
          </div>
        </Card>

        {/* PANEL 3: RIGHT — Assessing Authority & Verification Hub Control */}
        <Card className="p-3 bg-blue-50/40 border-blue-200 space-y-3">
          <h3 className="text-xs font-bold uppercase text-blue-900 pb-2 border-b border-blue-100 flex items-center gap-1.5">
            🛡️ Verification Hub &amp; Assessing Body Control
          </h3>

          <div className="space-y-3">
            <Field label="Assessing Authority (Designated Body)">
              <Select value={selectedAuthCode} onValueChange={handleAuthorityChange}>
                <SelectTrigger className="h-8 text-xs bg-white font-medium text-slate-800">
                  <SelectValue placeholder="Select assessing body…" />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  {authorities.map((a) => (
                    <SelectItem key={a.code} value={a.code}>
                      <span className="font-bold">{a.code}</span> — {a.full_name || a.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            {/* Live Authority Details & Cascaded Fees */}
            {currentAuthDoc && (
              <div className="p-2.5 rounded border border-blue-200 bg-white space-y-1.5 text-xs">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-blue-950">{currentAuthDoc.full_name}</span>
                  <Badge className="text-[9px] bg-blue-100 text-blue-800">{currentAuthDoc.code}</Badge>
                </div>
                <div className="grid grid-cols-2 gap-1 text-[11px] pt-1 border-t border-slate-100">
                  <div>
                    <span className="text-slate-500">Standard Fee:</span>{' '}
                    <strong className="text-emerald-700">AUD ${currentAuthDoc.fees?.msa_fee_aud || '—'}</strong>
                  </div>
                  <div>
                    <span className="text-slate-500">RPL Fee:</span>{' '}
                    <strong className="text-emerald-700">AUD ${currentAuthDoc.fees?.rpl_fee_aud || '—'}</strong>
                  </div>
                  <div className="col-span-2">
                    <span className="text-slate-500">Turnaround:</span>{' '}
                    <strong>{Math.round((currentAuthDoc.processing?.standard_days_min || 60) / 7)}–{Math.round((currentAuthDoc.processing?.standard_days_max || 90) / 7)} weeks</strong>
                  </div>
                </div>
                {currentAuthDoc.website && (
                  <a href={currentAuthDoc.website} target="_blank" rel="noreferrer" className="text-[10px] text-blue-600 hover:underline flex items-center gap-1 pt-1">
                    <ExternalLink className="h-2.5 w-2.5" /> Official Website
                  </a>
                )}
              </div>
            )}

            <Field label="Official Source URL (ABS ANZSCO / Home Affairs)">
              <Input value={sourceRef} onChange={(e) => setSourceRef(e.target.value)}
                placeholder="https://www.abs.gov.au/anzsco/..." className="h-8 text-xs bg-white" data-testid="source-ref" />
            </Field>

            <Field label="Review Notes (Audit Record)">
              <Textarea value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)}
                className="text-xs min-h-[60px] bg-white" placeholder="What did you double-check in official gazettes…" data-testid="review-notes" />
            </Field>

            {item.verification?.source_reference && (
              <p className="text-[10px] text-slate-500 italic bg-white p-1.5 rounded border border-slate-200">
                Last verified: {item.verification.source_reference}
              </p>
            )}

            {verifyOpen && (
              <div className="mt-3 pt-3 border-t border-blue-200 space-y-2 bg-blue-100/50 p-2.5 rounded">
                <p className="text-xs font-bold text-blue-950">Confirm Verification &amp; Publishing</p>
                <p className="text-[11px] text-blue-800">All changes will immediately cascade to Smart Sales and Knowledge Hub.</p>
                <Button size="sm" className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold" onClick={verify} disabled={saving || !sourceRef.trim()} data-testid="confirm-verify">
                  {saving ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
                  Publish Changes Now
                </Button>
                <Button size="sm" variant="outline" className="w-full bg-white" onClick={() => setVerifyOpen(false)}>Cancel</Button>
              </div>
            )}
          </div>
        </Card>
      </div>
    </Card>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <Label className="text-[10px] uppercase font-bold text-slate-600 mb-1 flex items-center justify-between">{label}</Label>
      {children}
    </div>
  );
}

function PolishBtn({ onClick, loading }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className="text-[10px] px-2 py-0.5 rounded bg-purple-100 text-purple-700 hover:bg-purple-200 disabled:opacity-50 inline-flex items-center gap-1"
      title="Polish text with AI (no fact changes)"
      data-testid="polish-btn"
    >
      {loading ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Wand2 className="h-2.5 w-2.5" />}
      Polish
    </button>
  );
}


// ════════════════════════════════════════════════════════════════
// 6.9.2 — Bulk Import
// ════════════════════════════════════════════════════════════════
function BulkImport({ headers }) {
  const [file, setFile] = useState(null);
  const [country, setCountry] = useState('AU');
  const [classification, setClassification] = useState('ANZSCO');
  const [version, setVersion] = useState('ANZSCO 2013 v1.3');
  const [onDuplicate, setOnDuplicate] = useState('skip');
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [committed, setCommitted] = useState(null);

  const onPreview = async () => {
    if (!file) { toast.error('Pick a CSV/Excel file first'); return; }
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('country_code', country);
      fd.append('classification_type', classification);
      const r = await axios.post(`${API}/occupation-master/import/preview`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      setPreview(r.data);
      setCommitted(null);
      if (!r.data.ok) toast.error(r.data.error);
      else toast.success(`Parsed ${r.data.total_rows} rows`);
    } catch (e) {
      toast.error(formatApiError(e, 'Preview failed'));
    } finally { setLoading(false); }
  };

  const onCommit = async () => {
    if (!file || !preview?.ok) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('country_code', country);
      fd.append('classification_type', classification);
      fd.append('classification_version', version);
      fd.append('on_duplicate', onDuplicate);
      const r = await axios.post(`${API}/occupation-master/import/commit`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      setCommitted(r.data);
      toast.success(`Imported ${r.data.imported}, updated ${r.data.updated}, skipped ${r.data.skipped}`,
        { description: r.data.errors.length > 0 ? `${r.data.errors.length} warnings — see below` : 'All clean' });
    } catch (e) {
      toast.error(formatApiError(e, 'Commit failed'));
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-3">
      <Card className="p-4 space-y-3" data-testid="import-form">
        <h3 className="text-sm font-bold flex items-center gap-2"><Upload className="h-4 w-4" />Upload ANZSCO / NOC dataset</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <Field label="File (CSV / XLSX)">
            <Input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="import-file" />
          </Field>
          <Field label="Country">
            <Select value={country} onValueChange={setCountry}>
              <SelectTrigger className="h-9" data-testid="import-country"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="AU">🇦🇺 Australia</SelectItem>
                <SelectItem value="CA">🇨🇦 Canada</SelectItem>
                <SelectItem value="NZ">🇳🇿 New Zealand</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Classification">
            <Select value={classification} onValueChange={setClassification}>
              <SelectTrigger className="h-9" data-testid="import-classification"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ANZSCO">ANZSCO</SelectItem>
                <SelectItem value="OSCA">OSCA</SelectItem>
                <SelectItem value="NOC">NOC</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Version label">
            <Input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="e.g. ANZSCO 2013 v1.3" className="h-9" data-testid="import-version" />
          </Field>
        </div>
        <div className="flex gap-2">
          <Button onClick={onPreview} disabled={!file || loading} className="bg-slate-700" data-testid="import-preview-btn">
            {loading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Search className="h-3 w-3 mr-1" />}
            Preview
          </Button>
          {preview?.ok && (
            <>
              <Select value={onDuplicate} onValueChange={setOnDuplicate}>
                <SelectTrigger className="w-40 h-9" data-testid="import-on-dup"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="skip">On duplicate: Skip</SelectItem>
                  <SelectItem value="update">On duplicate: Update</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={onCommit} disabled={loading} className="bg-emerald-600 hover:bg-emerald-700" data-testid="import-commit-btn">
                {loading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
                Commit Import
              </Button>
            </>
          )}
        </div>
      </Card>

      {preview && preview.ok && (
        <Card className="p-3 space-y-3" data-testid="import-preview">
          <h3 className="text-sm font-bold">Preview · {preview.total_rows} rows detected</h3>
          {preview.duplicates_in_db_count > 0 && (
            <div className="bg-amber-50 border border-amber-200 p-2 rounded text-xs">
              ⚠️ <strong>{preview.duplicates_in_db_count}</strong> codes already exist in {country}.
              {' '}On Commit they will be {onDuplicate === 'skip' ? 'SKIPPED' : 'UPDATED (verification block preserved)'}.
            </div>
          )}
          {preview.duplicates_in_file.length > 0 && (
            <div className="bg-rose-50 border border-rose-200 p-2 rounded text-xs">
              ⚠️ {preview.duplicates_in_file.length} duplicate codes WITHIN the file — first occurrence wins.
            </div>
          )}
          <div className="bg-slate-50 p-2 rounded text-[10px] font-mono">
            <p className="font-semibold mb-1">Detected column mapping:</p>
            <pre>{JSON.stringify(preview.detected_mapping, null, 2)}</pre>
          </div>
          <div className="overflow-x-auto">
            <table className="text-[10px] w-full border-collapse">
              <thead className="bg-slate-100">
                <tr>
                  <th className="text-left p-1.5 border">Code</th>
                  <th className="text-left p-1.5 border">Title</th>
                  <th className="text-left p-1.5 border">Skill Lv</th>
                  <th className="text-left p-1.5 border">Unit group</th>
                  <th className="text-left p-1.5 border">Tasks (count)</th>
                </tr>
              </thead>
              <tbody>
                {preview.sample_rows.map((r, i) => (
                  <tr key={i} className="border-b">
                    <td className="p-1.5 border font-mono">{r.code}</td>
                    <td className="p-1.5 border">{r.title}</td>
                    <td className="p-1.5 border">{r.skill_level ?? '—'}</td>
                    <td className="p-1.5 border">{r.hierarchy?.unit_group_name || r.hierarchy?.unit_group || '—'}</td>
                    <td className="p-1.5 border">{(r.typical_tasks || []).length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {committed && (
        <Card className="p-3 bg-emerald-50/40 border-emerald-200" data-testid="import-result">
          <h3 className="text-sm font-bold text-emerald-800">Import committed</h3>
          <div className="grid grid-cols-4 gap-2 mt-2">
            <Stat label="Imported" value={committed.imported} color="emerald" />
            <Stat label="Updated" value={committed.updated} color="blue" />
            <Stat label="Skipped" value={committed.skipped} color="slate" />
            <Stat label="Warnings" value={committed.errors.length} color="amber" />
          </div>
          {committed.errors.length > 0 && (
            <details className="mt-2 text-[10px]">
              <summary className="cursor-pointer font-semibold">Show warnings</summary>
              <ul className="list-disc list-inside mt-1 space-y-0.5">
                {committed.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </details>
          )}
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value, color }) {
  const map = { emerald: 'bg-emerald-100 text-emerald-700', blue: 'bg-blue-100 text-blue-700',
    slate: 'bg-slate-100 text-slate-700', amber: 'bg-amber-100 text-amber-700' };
  return (
    <div className={`p-2 rounded ${map[color]}`}>
      <p className="text-[9px] uppercase font-bold">{label}</p>
      <p className="text-xl font-bold">{value}</p>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// 6.9.5 — Country Templates
// ════════════════════════════════════════════════════════════════
function CountryTemplates({ headers }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/country-templates`, { headers });
      setTemplates(r.data.items || []);
    } catch (e) {
      toast.error(formatApiError(e, 'Failed to load templates'));
    } finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-3">
      <Card className="p-3 bg-amber-50/40 border-amber-300">
        <p className="text-xs">
          <strong>📋 Status:</strong> {templates.length} templates loaded. CA + NZ flagged for full
          admin rebuild against current IRCC CRS / NZ SMC 6-points rules.
          AU is template-mirrored from the legacy Schedule 6 points and needs verification.
          Once a template is verified, the calculator can be wired to read from it.
        </p>
      </Card>

      {loading ? (
        <Card className="p-10 text-center"><Loader2 className="h-6 w-6 animate-spin mx-auto text-slate-400" /></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="templates-grid">
          {templates.map((t) => <TemplateCard key={t.country_code} t={t} headers={headers} onReload={load} />)}
        </div>
      )}
    </div>
  );
}

function TemplateCard({ t, headers, onReload }) {
  const [expanded, setExpanded] = useState(false);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [sourceRef, setSourceRef] = useState('');
  const [reviewNotes, setReviewNotes] = useState('');
  const [verifying, setVerifying] = useState(false);
  const statusColor = {
    verified: 'bg-emerald-100 text-emerald-700',
    draft: 'bg-amber-100 text-amber-700',
    outdated: 'bg-rose-100 text-rose-700',
  }[t.status] || 'bg-slate-100';

  const submitVerify = async () => {
    if (!sourceRef.trim() || sourceRef.trim().length < 5) {
      toast.error('Source URL required (min 5 chars) — paste the official link you verified against');
      return;
    }
    setVerifying(true);
    try {
      await axios.post(`${API}/country-templates/${t.country_code}/verify`, {
        source_reference: sourceRef.trim(),
        review_notes: reviewNotes.trim() || null,
      }, { headers });
      toast.success(`${t.country_code} template verified · Calculator + Reports will use these factors now`);
      setVerifyOpen(false);
      setSourceRef('');
      setReviewNotes('');
      onReload();
    } catch (e) {
      toast.error(formatApiError(e, 'Verify failed'));
    } finally { setVerifying(false); }
  };

  return (
    <Card className="p-3" data-testid={`template-card-${t.country_code}`}>
      <div className="flex items-start justify-between">
        <div>
          <h4 className="text-base font-bold">{t.flag} {t.country_name}</h4>
          <p className="text-[10px] text-slate-500">{t.classification_system} · pass mark {t.pass_mark}</p>
        </div>
        <Badge className={`${statusColor} text-[9px]`}>{t.status}</Badge>
      </div>
      <div className="mt-2 space-y-1">
        <p className="text-[10px]"><strong>{t.factors.length}</strong> factors · <strong>{t.visa_subclasses.length}</strong> visa subclasses</p>
        {t.notes && <p className="text-[10px] italic text-amber-700 bg-amber-50 p-1.5 rounded">{t.notes}</p>}
      </div>
      {t.status === 'verified' && t.verification?.verified_at && (
        <div className="mt-2 p-1.5 rounded bg-emerald-50 border border-emerald-200">
          <p className="text-[10px] text-emerald-800 flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3" />
            Verified {new Date(t.verification.verified_at).toLocaleDateString()}
          </p>
          {t.verification.source_reference && (
            <a href={t.verification.source_reference} target="_blank" rel="noopener noreferrer"
               className="text-[9px] text-emerald-700 hover:underline break-all"
               data-testid={`template-source-${t.country_code}`}>
              ↗ {t.verification.source_reference.slice(0, 60)}…
            </a>
          )}
        </div>
      )}
      <div className="flex gap-2 mt-2">
        <Button size="sm" variant="outline" className="flex-1 h-7 text-[10px]"
                onClick={() => setExpanded(!expanded)}
                data-testid={`template-expand-${t.country_code}`}>
          {expanded ? 'Collapse' : 'View factors'}
        </Button>
        {t.status !== 'verified' && (
          <Button size="sm" className="flex-1 h-7 text-[10px] bg-emerald-600 hover:bg-emerald-700"
                  onClick={() => setVerifyOpen(true)}
                  data-testid={`template-verify-${t.country_code}`}>
            <ShieldCheck className="h-3 w-3 mr-1" />Verify
          </Button>
        )}
      </div>
      {verifyOpen && (
        <div className="mt-2 p-2 bg-blue-50 border border-blue-300 rounded space-y-2"
             data-testid={`template-verify-form-${t.country_code}`}>
          <p className="text-[10px] font-semibold text-blue-900">Verify Template — paste official URL</p>
          <Input
            placeholder="https://immi.gov.au/visas/..."
            value={sourceRef}
            onChange={(e) => setSourceRef(e.target.value)}
            className="h-7 text-[10px]"
            data-testid={`template-source-input-${t.country_code}`}
          />
          <Textarea
            placeholder="Review notes (optional) — what did you cross-check?"
            value={reviewNotes}
            onChange={(e) => setReviewNotes(e.target.value)}
            className="text-[10px] min-h-[40px]"
            rows={2}
            data-testid={`template-notes-input-${t.country_code}`}
          />
          <div className="flex gap-2">
            <Button size="sm" className="flex-1 h-7 text-[10px] bg-emerald-600"
                    onClick={submitVerify} disabled={verifying || !sourceRef.trim()}
                    data-testid={`template-confirm-verify-${t.country_code}`}>
              {verifying ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
              Confirm Verify
            </Button>
            <Button size="sm" variant="outline" className="flex-1 h-7 text-[10px]"
                    onClick={() => { setVerifyOpen(false); setSourceRef(''); setReviewNotes(''); }}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {expanded && (
        <div className="mt-2 space-y-1 text-[10px] max-h-64 overflow-y-auto">
          {t.factors.map((f) => (
            <div key={f.factor_id} className="bg-slate-50 p-1.5 rounded border">
              <p className="font-semibold">{f.factor_name}</p>
              <p className="text-slate-500">{f.options?.length || 0} options · {f.is_additional_factor ? 'Additional' : 'Core'}</p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════
// 6.9.4 — Status & Settings
// ════════════════════════════════════════════════════════════════
function StatusSettings({ headers }) {
  const [settings, setSettings] = useState(null);
  const [stats, setStats] = useState(null);
  const [saving, setSaving] = useState(false);
  const [flagging, setFlagging] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, st] = await Promise.all([
        axios.get(`${API}/kb/settings`, { headers }),
        axios.get(`${API}/occupation-master/stats`, { headers }),
      ]);
      setSettings(s.data);
      setStats(st.data);
    } catch (e) {
      toast.error(formatApiError(e, 'Failed to load settings'));
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const updateField = (k, v) => setSettings((s) => ({ ...s, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/kb/settings`, {
        outdated_threshold_months: parseInt(settings.outdated_threshold_months, 10),
        verification_gate_percent: parseInt(settings.verification_gate_percent, 10),
        enforce_verified_only: !!settings.enforce_verified_only,
      }, { headers });
      toast.success('Settings saved');
      load();
    } catch (e) {
      toast.error(formatApiError(e, 'Save failed'));
    } finally { setSaving(false); }
  };

  const autoFlag = async () => {
    setFlagging(true);
    try {
      const r = await axios.post(`${API}/kb/auto-flag-outdated`, {}, { headers });
      toast.success(`Flagged ${r.data.occupations_flagged_outdated} occupations + ${r.data.bodies_flagged_outdated} bodies as outdated`,
        { description: `Threshold: ${r.data.threshold_months} months` });
      load();
    } catch (e) {
      toast.error(formatApiError(e, 'Auto-flag failed'));
    } finally { setFlagging(false); }
  };

  if (!settings) return <Card className="p-10 text-center"><Loader2 className="h-6 w-6 animate-spin mx-auto text-slate-400" /></Card>;

  return (
    <div className="space-y-3">
      {stats && (
        <Card className="p-3" data-testid="stats-summary">
          <h3 className="text-sm font-bold mb-2">Current State</h3>
          <div className="grid grid-cols-4 gap-2">
            <Stat label="Total" value={stats.total} color="slate" />
            <Stat label="Verified" value={stats.by_status.verified} color="emerald" />
            <Stat label="Draft" value={stats.by_status.draft} color="amber" />
            <Stat label="Outdated" value={stats.by_status.outdated} color="blue" />
          </div>
          <p className="text-[10px] text-slate-500 mt-2">{stats.pending_percent}% pending verification</p>
        </Card>
      )}

      <Card className="p-4 space-y-3" data-testid="settings-form">
        <h3 className="text-sm font-bold">Verification Settings</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="Outdated threshold (months)">
            <Input type="number" min="1" max="60" value={settings.outdated_threshold_months}
              onChange={(e) => updateField('outdated_threshold_months', e.target.value)} className="h-9" data-testid="setting-threshold" />
            <p className="text-[10px] text-slate-500 mt-1">Verified records older than this auto-flag as outdated when admin runs the sweep.</p>
          </Field>
          <Field label="Verification gate (%)">
            <Input type="number" min="50" max="100" value={settings.verification_gate_percent}
              onChange={(e) => updateField('verification_gate_percent', e.target.value)} className="h-9" data-testid="setting-gate" />
            <p className="text-[10px] text-slate-500 mt-1">Hide drafts from sales once ≥ this % of records are verified.</p>
          </Field>
          <Field label="Enforce verified-only (sales)">
            <Select value={String(!!settings.enforce_verified_only)}
              onValueChange={(v) => updateField('enforce_verified_only', v === 'true')}>
              <SelectTrigger className="h-9" data-testid="setting-enforce"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="false">Off — sales sees drafts (transition)</SelectItem>
                <SelectItem value="true">On — drafts hidden from sales</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-[10px] text-slate-500 mt-1">Once verification reaches the threshold, switch this ON.</p>
          </Field>
        </div>
        <div className="flex gap-2 pt-2 border-t">
          <Button onClick={save} disabled={saving} className="bg-slate-700" data-testid="settings-save">
            {saving ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Save className="h-3 w-3 mr-1" />}Save settings
          </Button>
          <Button onClick={autoFlag} disabled={flagging} variant="outline" className="border-amber-400 text-amber-800" data-testid="settings-auto-flag">
            {flagging ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <AlertCircle className="h-3 w-3 mr-1" />}
            Sweep & Flag Outdated
          </Button>
        </div>
      </Card>
    </div>
  );
}
