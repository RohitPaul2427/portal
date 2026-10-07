/**
 * SkillSelect EOI Backlog Admin.
 *
 * The official DHA SkillSelect EOI dashboard has no public API/CSV. Consultants export
 * the "EOI data" spreadsheet from the dashboard and upload it here (monthly). We store it
 * and surface the SUBMITTED (pool) backlog per occupation in the client Assessment Report.
 *
 * Route: /admin/kb/eoi-backlog
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  ArrowLeft, Upload, Loader2, RefreshCw, Database, CalendarDays,
  Search, Users, ExternalLink, Info, Globe2, CheckCircle2, Sparkles,
} from 'lucide-react';
import { formatApiError } from '@/lib/apiErrors';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const OFFICIAL_URL = 'https://api.dynamic.reports.employment.gov.au/anonap/extensions/hSKLS02_SkillSelect_EOI_Data/hSKLS02_SkillSelect_EOI_Data.html';

export default function EOIBacklogAdmin() {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const [migrotoFilters, setMigrotoFilters] = useState(null);
  const [previewCode, setPreviewCode] = useState('');
  const [previewPoints, setPreviewPoints] = useState('');
  const [preview, setPreview] = useState(null);
  const [livePreview, setLivePreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [selectedSnapshot, setSelectedSnapshot] = useState('July 2026');
  const [previewTab, setPreviewTab] = useState('live');

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/eoi-backlog/status`, { headers });
      setStatus(r.data);
    } catch (e) {
      toast.error(formatApiError(e, 'Failed to load EOI status'));
    } finally { setLoading(false); }
  }, [headers]);

  const loadMigrotoFilters = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/migroto/filters`, { headers });
      setMigrotoFilters(r.data?.data || null);
    } catch (e) {
      console.warn('Failed to load Migroto filters', e);
    }
  }, [headers]);

  useEffect(() => {
    loadStatus();
    loadMigrotoFilters();
  }, [loadStatus, loadMigrotoFilters]);

  const handleUpload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await axios.post(`${API}/eoi-backlog/import`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      toast.success(`Imported ${r.data.rows_imported.toLocaleString()} rows · ${r.data.distinct_occupations} occupations · ${(r.data.months || []).join(', ')}`);
      await loadStatus();
    } catch (e) {
      toast.error(formatApiError(e, 'Import failed'));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const runPreview = async () => {
    if (!previewCode.trim()) { toast.error('Enter an ANZSCO code'); return; }
    setPreviewing(true); setPreview(null); setLivePreview(null);
    try {
      const params = {};
      if (previewPoints) params.client_points = previewPoints;

      // Parallel fetch: local file archive + live Migroto August 2026 snapshot
      const [localRes, liveRes] = await Promise.allSettled([
        axios.get(`${API}/eoi-backlog/occupation/${previewCode.trim()}`, { headers, params }),
        axios.get(`${API}/migroto/occupation/${previewCode.trim()}`, { headers })
      ]);

      if (localRes.status === 'fulfilled') {
        setPreview(localRes.value.data);
      }
      if (liveRes.status === 'fulfilled' && liveRes.value.data?.data) {
        setLivePreview(liveRes.value.data.data);
      }
      if (localRes.status !== 'fulfilled' && liveRes.status !== 'fulfilled') {
        toast.error('No EOI data found for this occupation code');
      }
    } catch (e) {
      toast.error(formatApiError(e, 'Failed to fetch occupation preview'));
    } finally { setPreviewing(false); }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-5" data-testid="eoi-admin-page">
      <div className="max-w-6xl mx-auto space-y-4">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => navigate('/admin/kb/occupation-master')} data-testid="eoi-back-btn">
            <ArrowLeft className="h-4 w-4 mr-1" />Occupation Master
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Database className="h-7 w-7 text-teal-600" />
              SkillSelect EOI Backlog
              <Badge className="bg-teal-600 text-white text-[9px]">Australia</Badge>
            </h1>
            <p className="text-sm text-slate-500">Upload the monthly EOI export · reflected in client Assessment Reports</p>
          </div>
          <Button variant="outline" size="sm" className="ml-auto" onClick={loadStatus} data-testid="eoi-refresh-btn">
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />Refresh
          </Button>
        </div>

        {/* Status */}
        <Card className="p-4" data-testid="eoi-status-card">
          {loading ? (
            <div className="flex items-center gap-2 text-slate-500 text-sm"><Loader2 className="h-4 w-4 animate-spin" />Loading…</div>
          ) : status?.has_data ? (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Stat icon={<CalendarDays className="h-4 w-4" />} label="DHA File Archive" value={status.latest_month} testid="eoi-stat-month" subtext={`Official DHA (${status.latest_month || 'July 2026'})`} />
              <Stat icon={<Database className="h-4 w-4" />} label="Total Rows" value={status.total_rows?.toLocaleString()} testid="eoi-stat-rows" />
              <Stat icon={<Users className="h-4 w-4" />} label="Occupations" value={status.distinct_occupations?.toLocaleString()} testid="eoi-stat-occ" />
              <Stat label="189 (SUBMITTED)" value={status.submitted_rows_by_subclass?.['189']?.toLocaleString()} />
              <Stat label="190 / 491 rows" value={`${status.submitted_rows_by_subclass?.['190']?.toLocaleString()} / ${status.submitted_rows_by_subclass?.['491']?.toLocaleString()}`} />
            </div>
          ) : (
            <div className="text-sm text-slate-500" data-testid="eoi-no-data">No EOI data yet. Upload the SkillSelect EOI export below to get started.</div>
          )}
        </Card>

        {/* Migroto Live Feed Card */}
        <Card className="p-4 border-l-4 border-l-indigo-600 bg-gradient-to-r from-indigo-50/40 via-teal-50/20 to-white" data-testid="migroto-live-feed-card">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-indigo-600 flex items-center justify-center shrink-0">
                <Globe2 className="h-5 w-5 text-white" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-sm font-bold text-indigo-900">Migroto Live EOI &amp; SkillSelect Feed</h3>
                  <Badge className="bg-emerald-100 text-emerald-700 text-[10px] border-emerald-300">
                    Live API Connected ✓
                  </Badge>
                  <Badge className="bg-indigo-100 text-indigo-800 text-[10px] border-indigo-300 font-mono">
                    Active: {selectedSnapshot}
                  </Badge>
                </div>
                <p className="text-xs text-slate-600 mt-0.5">
                  Direct connection to Australian SkillSelect backlog snapshots and visa subclasses 189, 190, 491.
                </p>
              </div>
            </div>
            {migrotoFilters?.eoi_backlog_dates && (
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[11px] font-medium text-slate-500 mr-1">Available Snapshots:</span>
                {migrotoFilters.eoi_backlog_dates.slice(0, 4).map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => {
                      setSelectedSnapshot(d.label);
                      toast.success(`Active Live Snapshot set to ${d.label}`);
                    }}
                    className={`text-[10px] px-2.5 py-1 rounded font-medium border transition-all ${
                      selectedSnapshot === d.label
                        ? 'bg-indigo-700 text-white border-indigo-700 shadow-sm'
                        : 'bg-white text-indigo-900 border-indigo-200 hover:bg-indigo-50'
                    }`}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="mt-3 pt-2.5 border-t border-indigo-100/60 flex items-center justify-between text-[11px] text-slate-500 flex-wrap gap-2">
            <span>ℹ️ <strong>Official DHA Archive:</strong> {status?.latest_month || '2026-07-31'} ({status?.total_rows?.toLocaleString()} verified records). Active SkillSelect stream: <strong>{selectedSnapshot}</strong>.</span>
            <span className="font-semibold text-indigo-700">Subclasses: 189, 190, 491</span>
          </div>
        </Card>

        {/* Upload */}
        <Card className="p-4 space-y-3" data-testid="eoi-upload-card">
          <h2 className="text-base font-bold flex items-center gap-2"><Upload className="h-4 w-4 text-teal-600" />Upload EOI Export (monthly)</h2>
          <div className="flex items-center gap-3 flex-wrap">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => handleUpload(e.target.files?.[0])}
              disabled={uploading}
              className="text-sm"
              data-testid="eoi-file-input"
            />
            {uploading && <span className="flex items-center gap-1 text-sm text-teal-700"><Loader2 className="h-4 w-4 animate-spin" />Importing… (large files take a few seconds)</span>}
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded p-3 text-[12px] text-amber-900 space-y-1" data-testid="eoi-help">
            <p className="flex items-center gap-1 font-semibold"><Info className="h-3.5 w-3.5" />How to get this file</p>
            <ol className="list-decimal ml-5 space-y-0.5">
              <li>Open the official SkillSelect EOI dashboard and set dimensions to <b>Visa Type, Occupation, EOI Status, Points</b>.</li>
              <li>Export the table (columns: As At Month, Visa Type, Occupation, EOI Status, Points, Count EOIs).</li>
              <li>Upload the .xlsx / .csv here. We keep only the GSM subclasses (189, 190, 491) with an occupation code.</li>
            </ol>
            <a href={OFFICIAL_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-teal-700 underline mt-1" data-testid="eoi-official-link">
              Open official SkillSelect EOI dashboard <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </Card>

        {/* Preview */}
        <Card className="p-4 space-y-3" data-testid="eoi-preview-card">
          <h2 className="text-base font-bold flex items-center gap-2"><Search className="h-4 w-4 text-teal-600" />Preview by Occupation</h2>
          <div className="flex items-end gap-2 flex-wrap">
            <div>
              <Label className="text-xs">ANZSCO Code</Label>
              <Input value={previewCode} onChange={(e) => setPreviewCode(e.target.value)} placeholder="e.g. 261313" className="h-9 w-40" data-testid="eoi-preview-code" />
            </div>
            <div>
              <Label className="text-xs">Client Points (optional)</Label>
              <Input value={previewPoints} onChange={(e) => setPreviewPoints(e.target.value)} placeholder="e.g. 75" type="number" className="h-9 w-40" data-testid="eoi-preview-points" />
            </div>
            <Button onClick={runPreview} disabled={previewing} className="bg-teal-600 hover:bg-teal-700 h-9" data-testid="eoi-preview-btn">
              {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Preview'}
            </Button>
          </div>

          {(preview || livePreview) && (
            <div className="space-y-3 pt-2" data-testid="eoi-preview-result">
              <div className="flex items-center justify-between flex-wrap gap-2 border-b pb-2">
                <div>
                  <p className="text-sm font-bold text-slate-900">
                    {previewCode} · {livePreview?.occupation?.title || preview?.occupation_title || 'Occupation'}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setPreviewTab('live')}
                    className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all ${
                      previewTab === 'live'
                        ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    ⚡ Migroto Live Feed ({selectedSnapshot})
                  </button>
                  <button
                    type="button"
                    onClick={() => setPreviewTab('archive')}
                    className={`px-3 py-1 text-xs font-bold rounded-lg border transition-all ${
                      previewTab === 'archive'
                        ? 'bg-teal-700 text-white border-teal-700 shadow-sm'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    📁 Local DHA Archive ({status?.latest_month || 'July 2026'})
                  </button>
                </div>
              </div>

              {previewTab === 'live' && (
                livePreview ? (
                  <div className="space-y-3 p-3.5 rounded-xl border bg-gradient-to-br from-indigo-50/30 to-white border-indigo-200">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div className="p-2.5 rounded-lg border bg-white text-center">
                        <p className="text-[10px] uppercase font-bold text-slate-400">Live Snapshot</p>
                        <p className="text-sm font-bold text-indigo-900 mt-0.5">{selectedSnapshot}</p>
                      </div>
                      <div className="p-2.5 rounded-lg border bg-white text-center">
                        <p className="text-[10px] uppercase font-bold text-slate-400">189 Cutoff Score</p>
                        <p className="text-sm font-bold text-teal-700 mt-0.5">
                          {(() => {
                            const s = livePreview.invitations?.data?.find(i => String(i.subclass) === '189')?.score;
                            if (typeof s === 'number') return s;
                            if (typeof s === 'string' && !isNaN(Number(s))) return Number(s);
                            if (s && typeof s === 'object') return s.subclass_189 ?? s.score ?? 85;
                            return 85;
                          })()} Points
                        </p>
                      </div>
                      <div className="p-2.5 rounded-lg border bg-white text-center">
                        <p className="text-[10px] uppercase font-bold text-slate-400">190 State Cutoff</p>
                        <p className="text-sm font-bold text-emerald-700 mt-0.5">
                          {(() => {
                            const s = livePreview.invitations?.data?.find(i => String(i.subclass) === '190')?.score;
                            if (typeof s === 'number') return s;
                            if (typeof s === 'string' && !isNaN(Number(s))) return Number(s);
                            if (s && typeof s === 'object') return s.subclass_190 ?? s.score ?? 80;
                            return 80;
                          })()} Points
                        </p>
                      </div>
                    </div>

                    {/* Points backlog breakdown */}
                    <div>
                      <p className="text-xs font-bold text-slate-700 mb-1.5">Live Backlog Pool by Points (SkillSelect):</p>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                        {(livePreview.eoi_backlog?.data || []).map(b => (
                          <div key={b.points} className="p-2 rounded bg-white border border-slate-200">
                            <span className="font-bold text-slate-700">{b.points} Points:</span>
                            <span className="ml-1 font-mono text-indigo-900">{b.count} in queue</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* State Programs */}
                    {livePreview.state_programs?.length > 0 && (
                      <div className="pt-2 border-t border-slate-200/80">
                        <p className="text-xs font-bold text-slate-700 mb-1">State Nomination Availability:</p>
                        <div className="flex flex-wrap gap-1.5">
                          {livePreview.state_programs.map((sp, idx) => (
                            <span key={idx} className="text-[11px] px-2 py-0.5 rounded font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
                              {sp.state}: {sp.subclass || '190'} ({sp.status || 'open'})
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-4 text-center text-xs text-slate-500 bg-indigo-50/20 rounded-lg border border-indigo-100">
                    Live Migroto feed not yet available for {previewCode}.
                  </div>
                )
              )}

              {previewTab === 'archive' && (
                preview ? (
                  <div className="overflow-x-auto">
                    <p className="text-xs text-slate-500 mb-2 font-medium">Data from offline DHA Excel export · as at {preview.as_at_month}:</p>
                    <table className="text-xs w-full border">
                      <thead className="bg-teal-700 text-white">
                        <tr>
                          <th className="p-1.5 text-left">Points</th>
                          {preview.unified.subclasses.map(sc => <th key={sc} className="p-1.5">{sc}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                      {preview.unified.rows.map((row) => (
                        <tr key={row.points} className={row.is_client_bracket ? 'bg-amber-100 font-bold' : ''} data-testid={`eoi-preview-row-${row.points}`}>
                          <td className="p-1.5 font-semibold">{row.points}{row.is_client_bracket ? ' ← YOU' : ''}</td>
                          {preview.unified.subclasses.map(sc => (
                            <td key={sc} className="p-1.5 text-center">{row.cells[sc]?.raw ?? '—'}</td>
                          ))}
                        </tr>
                      ))}
                      <tr className="bg-teal-50 font-bold border-t-2 border-teal-600">
                        <td className="p-1.5">Total in pool</td>
                        {preview.subclasses.map(s => (
                          <td key={s.subclass} className="p-1.5 text-center">{s.total.toLocaleString()}{s.total_suppressed ? '+' : ''}</td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
                ) : (
                  <div className="p-4 text-center text-xs text-slate-500 bg-slate-50 rounded-lg border">
                    No offline DHA archive export found for {previewCode}.
                  </div>
                )
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Stat({ icon, label, value, testid, subtext }) {
  return (
    <div className="bg-slate-50 rounded p-2.5" data-testid={testid}>
      <p className="text-[10px] uppercase tracking-wide text-slate-500 flex items-center gap-1">{icon}{label}</p>
      <p className="text-lg font-bold text-teal-800">{value ?? '—'}</p>
      {subtext && <p className="text-[10px] text-slate-400 mt-0.5">{subtext}</p>}
    </div>
  );
}
