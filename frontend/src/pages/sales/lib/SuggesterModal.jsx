// AI Occupation Suggester — opens from Step 3, calls /sales/ai/suggest-occupation
import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Bot, ChevronRight, Loader2, Check, AlertTriangle, FileText, Award, Scale, HelpCircle, ListChecks, Building2 } from 'lucide-react';
import { formatApiError } from '@/lib/apiErrors';
import { API, COUNTRIES } from './constants';

export default function SuggesterModal({
  onClose,
  onSelect,
  onSelectMultiple,
  headers,
  initialDescription = '',
  initialCountry = 'AU',
  initialQualification = '',
  initialFieldOfStudy = '',
  initialExpYears = 0,
  initialProfile = null,
  autoRun = false,
}) {
  const [description, setDescription] = useState(initialDescription);
  const [country, setCountry] = useState(initialCountry || 'AU');
  const [qualification, setQualification] = useState(initialQualification || initialProfile?.qualification || '');
  const [fieldOfStudy, setFieldOfStudy] = useState(initialFieldOfStudy || initialProfile?.field_of_study || '');
  const [expYears, setExpYears] = useState(initialExpYears || initialProfile?.years_experience_total || '');
  const [suggestions, setSuggestions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchedCountry, setSearchedCountry] = useState(null);
  const [selected, setSelected] = useState([]);
  const autoRanRef = useRef(false);

  const keyOf = (s) => `${s.code}-${s.country_code || searchedCountry || 'X'}`;
  const isSelected = (s) => selected.some(x => keyOf(x) === keyOf(s));
  const toggleSelect = (s) => {
    setSelected(prev => (
      prev.some(x => keyOf(x) === keyOf(s))
        ? prev.filter(x => keyOf(x) !== keyOf(s))
        : [...prev, s]
    ));
  };
  const useSelected = () => {
    if (!selected.length) return;
    if (onSelectMultiple) onSelectMultiple(selected);
    else if (onSelect) onSelect(selected[0]);
  };

  const countryName = (code) => (code === 'ALL' ? 'All countries' : (COUNTRIES.find(c => c.code === code)?.name || code));

  const submit = async (overrideCountry) => {
    const override = typeof overrideCountry === 'string' ? overrideCountry : null;
    const cc = override || country;
    if (description.trim().length < 15) {
      toast.error('Please enter at least 15 characters describing the profession');
      return;
    }
    if (override) setCountry(override);
    setLoading(true);
    try {
      const r = await axios.post(`${API}/sales/ai/suggest-occupation`, {
        description,
        country_codes: cc === 'ALL' ? null : [cc],
        max_suggestions: 5,
        qualification: qualification || undefined,
        field_of_study: fieldOfStudy || undefined,
        years_experience_total: expYears ? Number(expYears) : undefined,
        profile: initialProfile || undefined,
      }, { headers, timeout: 120000 });
      setSuggestions(r.data);
      setSearchedCountry(cc);
    } catch (e) {
      toast.error(formatApiError(e, 'AI suggestion failed'));
    } finally { setLoading(false); }
  };

  // When opened pre-filled from the resume flow, auto-run the suggestion once.
  useEffect(() => {
    if (autoRun && !autoRanRef.current && (initialDescription || '').trim().length >= 15) {
      autoRanRef.current = true;
      submit();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose} data-testid="suggester-modal">
      <Card className="max-w-3xl w-full bg-white p-5 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b pb-3 mb-3">
          <h3 className="text-base font-bold flex items-center gap-2">
            <Bot className="h-5 w-5 text-indigo-600" />AI Occupation &amp; Skills Assessment Suggester
            <Badge className="bg-amber-100 text-amber-700 text-[9px]">AI suggests — you verify &amp; decide</Badge>
          </h3>
          <Button variant="ghost" size="sm" onClick={onClose} className="h-7 w-7 p-0 text-slate-400 hover:text-slate-600">✕</Button>
        </div>

        <p className="text-[11px] text-slate-500 mb-3">
          Evaluates the candidate's profile, job duties, qualification, and experience against official assessing body rules (ACS, VETASSESS, TRA, Engineers Australia) to suggest matching occupation codes with exact deductions and points.
        </p>

        {!suggestions ? (
          <>
            <p className="text-[10px] font-semibold text-slate-500 mb-1">1. Target country <span className="font-normal text-slate-400">— codes &amp; criteria differ per country</span></p>
            <div className="grid grid-cols-4 gap-2 mb-3">
              {COUNTRIES.map(c => (
                <button key={c.code} onClick={() => setCountry(c.code)}
                  className={`p-2 rounded border-2 text-xs font-medium transition ${country === c.code ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 text-slate-600'}`}
                  data-testid={`suggester-country-${c.code}`}>
                  {c.flag} {c.name}
                </button>
              ))}
              <button onClick={() => setCountry('ALL')}
                className={`p-2 rounded border-2 text-xs font-medium transition ${country === 'ALL' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 text-slate-600'}`}
                data-testid="suggester-country-ALL">
                🌐 All
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 mb-3">
              <div>
                <label className="text-[10px] font-semibold text-slate-500 block mb-0.5">Highest Qualification</label>
                <Input
                  value={qualification}
                  onChange={e => setQualification(e.target.value)}
                  placeholder="e.g. Bachelor / B.Com / B.Tech"
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <label className="text-[10px] font-semibold text-slate-500 block mb-0.5">Field of Study</label>
                <Input
                  value={fieldOfStudy}
                  onChange={e => setFieldOfStudy(e.target.value)}
                  placeholder="e.g. Computer Science / Commerce"
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <label className="text-[10px] font-semibold text-slate-500 block mb-0.5">Total Experience (Years)</label>
                <Input
                  type="number"
                  step="0.5"
                  value={expYears}
                  onChange={e => setExpYears(e.target.value)}
                  placeholder="e.g. 6.0"
                  className="h-8 text-xs"
                />
              </div>
            </div>

            <p className="text-[10px] font-semibold text-slate-500 mb-1">2. Describe the profession &amp; duties</p>
            <Textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={5}
              placeholder="e.g., 6 years in software development, creating backend web applications with Python/Django and React. Completed Bachelor of Commerce (B.Com). Current designation: Senior Software Developer."
              data-testid="suggester-description"
              className="text-xs"
            />
            <p className="text-[10px] text-slate-400 mt-1">Min 15 chars · Include duties, tech stack, responsibilities, and education for accurate deduction calculations</p>
            <div className="flex gap-2 justify-end mt-3">
              <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
              <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={() => submit()} disabled={loading} data-testid="suggester-submit">
                {loading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Bot className="h-3 w-3 mr-1" />}
                {loading ? 'Analysing Assessment Rules…' : 'Find Matching Codes & Deductions'}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[11px] text-slate-600">
                Suggested codes for: <b>{countryName(searchedCountry)}</b>
                {qualification && <span className="ml-1 text-slate-400">· {qualification} ({fieldOfStudy || 'General'}) · {expYears || 0} yrs exp</span>}
              </p>
              {searchedCountry !== 'ALL' && (
                <Button size="sm" variant="outline" className="h-7 text-[10px]" onClick={() => submit('ALL')} disabled={loading} data-testid="suggester-search-all">
                  🌐 Search all countries
                </Button>
              )}
            </div>

            <div className="space-y-3">
              {(suggestions.suggestions || []).map((s, i) => {
                const sel = isSelected(s);
                const sa = s.skills_assessment || {};
                const isPositive = sa.is_positive !== false;
                const rplReq = Boolean(sa.rpl_required);
                const cdrReq = Boolean(sa.cdr_required);
                const deducted = sa.deducted_years != null ? Number(sa.deducted_years) : 0;
                const claimableYrs = sa.points_claimable_years != null ? Number(sa.points_claimable_years) : 0;
                const claimablePts = sa.points_claimable_points != null ? Number(sa.points_claimable_points) : 0;

                return (
                  <Card
                    key={`${s.code}-${s.country_code || 'X'}`}
                    className={`p-3.5 transition rounded-lg border ${sel ? 'ring-2 ring-indigo-500 border-indigo-500 bg-indigo-50/20' : 'border-slate-200 hover:border-slate-300'}`}
                    data-testid={`suggestion-${i}`}
                  >
                    {/* Header: Rank + Code + Title + Country */}
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <div>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-sm font-bold text-slate-800">
                            {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : '•'} {s.code} · {s.title}
                          </span>
                          {s.country_code && (
                            <Badge className="bg-slate-800 text-white text-[9px]" data-testid={`suggestion-country-${i}`}>
                              {(COUNTRIES.find(c => c.code === s.country_code)?.flag || '')} {s.country_code}
                            </Badge>
                          )}
                          <Badge className={s.confidence === 'high' ? 'bg-emerald-100 text-emerald-800 text-[9px]' : s.confidence === 'medium' ? 'bg-amber-100 text-amber-800 text-[9px]' : 'bg-slate-100 text-slate-600 text-[9px]'}>
                            {s.confidence?.toUpperCase()} MATCH
                          </Badge>
                        </div>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          Assessing Authority: <strong className="text-slate-700">{s.assessing_body}</strong> · Pathway: <span className="text-indigo-600 font-medium">{sa.pathway_name || s.pathway || 'General Migration'}</span>
                        </p>
                      </div>

                      <Button
                        size="sm"
                        variant={sel ? 'default' : 'outline'}
                        className={`text-xs h-8 px-3 shrink-0 ${sel ? 'bg-indigo-600 hover:bg-indigo-700 text-white font-semibold' : 'hover:border-indigo-400'}`}
                        onClick={() => toggleSelect(s)}
                        data-testid={`select-suggestion-${i}`}
                      >
                        {sel ? <><Check className="h-3.5 w-3.5 mr-1" />Selected{selected.length > 1 && selected[0] && keyOf(selected[0]) === keyOf(s) ? ' · Primary' : ''}</> : <>Select Code <ChevronRight className="h-3.5 w-3.5 ml-1" /></>}
                      </Button>
                    </div>

                    {/* AI Job Alignment Reasoning */}
                    <p className="text-[11px] text-slate-600 bg-slate-50 p-2 rounded border border-slate-100 mb-2">
                      <strong className="text-slate-700">Role Alignment:</strong> {s.reasoning}
                    </p>

                    {/* Core Duty & Task Alignment against ABS ANZSCO */}
                    {s.duty_alignment && (
                      <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 mb-2 space-y-1.5" data-testid={`duty-alignment-${i}`}>
                        <div className="flex items-center justify-between text-[11px]">
                          <div className="flex items-center gap-1.5 font-bold text-slate-800">
                            <ListChecks className="h-3.5 w-3.5 text-emerald-600" />
                            <span>Core Duty &amp; Task Alignment</span>
                          </div>
                          <Badge className="bg-emerald-100 text-emerald-800 text-[9px] font-semibold border border-emerald-200">
                            {s.duty_alignment.match_percentage}% Match ({s.duty_alignment.matched_tasks_count}/{s.duty_alignment.total_tasks_count} tasks)
                          </Badge>
                        </div>
                        <p className="text-[10.5px] text-slate-600 leading-tight">
                          {s.duty_alignment.summary}
                        </p>
                        {s.duty_alignment.matched_tasks && s.duty_alignment.matched_tasks.length > 0 && (
                          <div className="space-y-1 pt-1 border-t border-slate-200/60">
                            <span className="text-[9px] font-semibold uppercase text-slate-400 block">Matched Official ABS ANZSCO Tasks:</span>
                            <div className="space-y-0.5">
                              {s.duty_alignment.matched_tasks.map((t, tidx) => (
                                <div key={tidx} className="flex items-start gap-1.5 text-[10.5px] text-slate-700 bg-white/90 p-1.5 rounded border border-slate-100 leading-tight">
                                  <span className="text-emerald-600 font-bold shrink-0">✓</span>
                                  <span>{t}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Company Sector & Age GSM Points Evaluation */}
                    {(s.company_alignment || s.age_evaluation) && (
                      <div className="grid grid-cols-2 gap-2 mb-2 text-[10.5px]">
                        {s.company_alignment && (
                          <div className="bg-slate-50 border border-slate-200 rounded p-2 flex items-start gap-1.5">
                            <Building2 className="h-3.5 w-3.5 text-indigo-600 shrink-0 mt-0.5" />
                            <div>
                              <span className="font-bold text-slate-700 block">Employer &amp; Sector Fit</span>
                              <span className="text-slate-600 leading-tight block">{s.company_alignment.summary}</span>
                            </div>
                          </div>
                        )}
                        {s.age_evaluation && (
                          <div className="bg-slate-50 border border-slate-200 rounded p-2 flex items-start gap-1.5">
                            <Award className="h-3.5 w-3.5 text-amber-600 shrink-0 mt-0.5" />
                            <div>
                              <span className="font-bold text-slate-700 block">Age GSM Migration Points</span>
                              <span className="text-slate-600 leading-tight block">{s.age_evaluation.summary}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Assessing Body Deductions & Rules Analysis Box */}
                    <div className="bg-gradient-to-r from-amber-50/80 to-indigo-50/80 border border-indigo-100 rounded-lg p-2.5 space-y-1.5">
                      <div className="flex items-center justify-between flex-wrap gap-1">
                        <div className="flex items-center gap-1.5">
                          <Scale className="h-3.5 w-3.5 text-indigo-700" />
                          <span className="text-[11px] font-bold text-slate-800">
                            Assessment Criteria &amp; Experience Deductions
                          </span>
                        </div>
                        <Badge className={
                          rplReq
                            ? 'bg-amber-600 text-white text-[9px]'
                            : isPositive
                            ? 'bg-emerald-600 text-white text-[9px]'
                            : 'bg-rose-600 text-white text-[9px]'
                        }>
                          {sa.assessment_outcome || (isPositive ? 'Likely Positive' : 'Review Required')}
                        </Badge>
                      </div>

                      {/* 3-Pill Metric Comparison */}
                      <div className="grid grid-cols-3 gap-1.5 text-center pt-0.5">
                        <div className="bg-white/90 border border-slate-200 rounded p-1.5 shadow-sm">
                          <span className="text-[9px] text-slate-400 block uppercase font-semibold">Qualifying Deduction</span>
                          <span className={`text-xs font-bold ${deducted > 0 ? 'text-rose-600' : 'text-slate-700'}`}>
                            {deducted > 0 ? `-${deducted.toFixed(1)} yrs` : '0.0 yrs'}
                          </span>
                        </div>
                        <div className="bg-white/90 border border-slate-200 rounded p-1.5 shadow-sm">
                          <span className="text-[9px] text-slate-400 block uppercase font-semibold">Claimable Experience</span>
                          <span className="text-xs font-bold text-emerald-700">
                            {claimableYrs.toFixed(1)} yrs
                          </span>
                        </div>
                        <div className="bg-white/90 border border-slate-200 rounded p-1.5 shadow-sm">
                          <span className="text-[9px] text-slate-400 block uppercase font-semibold">GSM Points Claim</span>
                          <span className="text-xs font-bold text-indigo-700">
                            +{claimablePts} Points
                          </span>
                        </div>
                      </div>

                      {/* Specific Deduction Rationale & Conditions */}
                      <div className="text-[10px] text-slate-700 space-y-0.5 pt-0.5 leading-snug">
                        {rplReq && (
                          <div className="flex items-center gap-1 text-amber-800 font-semibold bg-amber-100/70 px-2 py-0.5 rounded">
                            <FileText className="h-3 w-3 shrink-0" />
                            <span>RPL Pathway Required: 6 years deducted for Non-ICT degree + 2 Project Reports required.</span>
                          </div>
                        )}
                        {cdrReq && (
                          <div className="flex items-center gap-1 text-blue-800 font-semibold bg-blue-100/70 px-2 py-0.5 rounded">
                            <Award className="h-3 w-3 shrink-0" />
                            <span>Engineers Australia: CDR Pathway required (3 Career Episodes + CPD) for non-accredited degrees.</span>
                          </div>
                        )}
                        {sa.justification ? (
                          <p className="text-slate-600 line-clamp-2">
                            <strong className="text-slate-700">Adviser note:</strong> {sa.justification}
                          </p>
                        ) : sa.conditions_summary ? (
                          <p className="text-slate-600">
                            <strong className="text-slate-700">Criteria:</strong> {sa.conditions_summary}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>

            {suggestions.general_advice && (
              <p className="text-[11px] italic mt-3 text-slate-600 bg-slate-50 p-2 rounded border border-slate-200">
                💡 {suggestions.general_advice}
              </p>
            )}

            <div className="flex gap-2 justify-between items-center mt-3 pt-2 border-t">
              <p className="text-[10px] text-slate-500" data-testid="suggester-selected-count">
                {selected.length > 0
                  ? `${selected.length} selected · first will be primary occupation`
                  : 'Select one or more codes to apply them to the assessment'}
              </p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => { setSuggestions(null); setSelected([]); }}>
                  Modify Inputs
                </Button>
                <Button
                  size="sm"
                  className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
                  onClick={useSelected}
                  disabled={selected.length === 0}
                  data-testid="suggester-use-selected"
                >
                  {selected.length > 1 ? `Use ${selected.length} Selected Codes` : 'Use Selected Code'}
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

