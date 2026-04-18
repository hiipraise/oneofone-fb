// src/pages/PredictPage.jsx
import React, { useState, useEffect, useRef } from 'react'
import { generatePrediction, validateMatch, getLiveLeagues } from '../services/api'
import PredictionCard from '../components/PredictionCard'
import ExtendedMarketsPanel from '../components/ExtendedMarketsPanel'
import { useApiContract } from '../hooks/useApiContract'
import { useMetricsSummary } from '../hooks/useData'
import { SPORT_LABELS } from '../config/apiContract'

const PIPELINE_STEPS = {
  soccer: [
    'Validating fixture in live database',
    'Fetching team form + ESPN stats',
    'Fetching injury reports',
    'Fetching head-to-head history',
    'Fetching betting odds signals',
    'Running HistGradientBoosting + calibration',
    'Computing goals O/U (Poisson model)',
    'Computing BTTS, correct score, corners, cards',
    'Computing Asian handicap',
  ],
}

export default function PredictPage() {
  const { contract } = useApiContract()
  const { data: summary } = useMetricsSummary()
  const sports = contract.supported_sports
  const teamNameMin = contract.field_limits.team_name.min
  const validationRequestIdRef = useRef(0)
  const leaguesRequestIdRef = useRef(0)

  const [form, setForm] = useState({
    home_team: '', away_team: '',
    sport: sports[0] || 'soccer', league: '', match_date: '',
    skip_validation: false,
  })
  const [leagues, setLeagues]         = useState([])
  const [leaguesLoading, setLeaguesLoading] = useState(false)
  const [validation, setValidation]   = useState(null)
  const [validating, setValidating]   = useState(false)
  const [loading, setLoading]         = useState(false)
  const [result, setResult]           = useState(null)
  const [error, setError]             = useState(null)

  useEffect(() => {
    if (!sports.includes(form.sport)) {
      setForm((prev) => ({ ...prev, sport: sports[0] || 'soccer' }))
    }
  }, [sports, form.sport])

  useEffect(() => {
    setLeagues([])
    setForm(p => ({ ...p, league: '' }))
    if (!form.sport) return
    const requestId = leaguesRequestIdRef.current + 1
    leaguesRequestIdRef.current = requestId
    setLeaguesLoading(true)
    getLiveLeagues(form.sport)
      .then((res) => {
        if (leaguesRequestIdRef.current !== requestId) return
        setLeagues(res.data.leagues || [])
      })
      .catch(() => {
        if (leaguesRequestIdRef.current !== requestId) return
        setLeagues([])
      })
      .finally(() => {
        if (leaguesRequestIdRef.current !== requestId) return
        setLeaguesLoading(false)
      })
  }, [form.sport])

  useEffect(() => {
    const t = setTimeout(() => {
      if (form.home_team.trim().length >= teamNameMin && form.away_team.trim().length >= teamNameMin) {
        const requestId = validationRequestIdRef.current + 1
        validationRequestIdRef.current = requestId
        setValidating(true)
        validateMatch(form.home_team, form.away_team, form.sport, form.match_date || undefined)
          .then((res) => {
            if (validationRequestIdRef.current !== requestId) return
            setValidation(res.data)
          })
          .catch(() => {
            if (validationRequestIdRef.current !== requestId) return
            setValidation(null)
          })
          .finally(() => {
            if (validationRequestIdRef.current !== requestId) return
            setValidating(false)
          })
      } else {
        validationRequestIdRef.current += 1
        setValidation(null)
        setValidating(false)
      }
    }, 800)
    return () => clearTimeout(t)
  }, [form.home_team, form.away_team, form.sport, form.match_date, teamNameMin])

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setForm(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }))
    setResult(null)
    setError(null)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.home_team.trim() || !form.away_team.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await generatePrediction({
        home_team: form.home_team.trim(), away_team: form.away_team.trim(),
        sport: form.sport, league: form.league || undefined,
        match_date: form.match_date || undefined,
        skip_validation: form.skip_validation,
      })
      setResult(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Prediction failed. Check team names and try again.')
    } finally {
      setLoading(false)
    }
  }

  const label1 = 'HOME TEAM'
  const label2 = 'AWAY TEAM'
  const ph1    = 'e.g. Manchester City'
  const ph2    = 'e.g. Arsenal'

  return (
    <div className="max-w-3xl animate-fade-in">
      <div className="mb-6">
        <h1 className="font-display text-xl text-white tracking-wide">GENERATE PREDICTION</h1>
        <p className="font-body text-xs text-gray-600 mt-1">
          Supports Football/Soccer — live data, extended markets
        </p>
      </div>

      <div className="card p-6 mb-4">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { label: label1, name: 'home_team', placeholder: ph1 },
              { label: label2, name: 'away_team', placeholder: ph2 },
            ].map(({ label, name, placeholder }) => (
              <div key={name}>
                <label className="label block mb-1.5">{label} *</label>
                <input
                  type="text" name={name} value={form[name]}
                  onChange={handleChange} placeholder={placeholder}
                  required disabled={loading}
                  className="w-full bg-brand-gray border border-brand-midgray focus:border-brand-red outline-none text-white font-body text-sm px-4 py-2.5 rounded-sm placeholder-gray-700 transition-colors disabled:opacity-50"
                />
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="label block mb-1.5">SPORT *</label>
              <select
                name="sport" value={form.sport} onChange={handleChange} disabled={loading}
                className="w-full bg-brand-gray border border-brand-midgray focus:border-brand-red outline-none text-white font-body text-sm px-4 py-2.5 rounded-sm transition-colors disabled:opacity-50"
              >
                {sports.map(s => (
                  <option key={s} value={s}>
                    {SPORT_LABELS[s] || (s.charAt(0).toUpperCase() + s.slice(1))}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label block mb-1.5">
                LEAGUE{leaguesLoading && <span className="text-gray-700 ml-1">(loading…)</span>}
              </label>
              <select
                name="league" value={form.league} onChange={handleChange}
                disabled={loading || leaguesLoading}
                className="w-full bg-brand-gray border border-brand-midgray focus:border-brand-red outline-none text-white font-body text-sm px-4 py-2.5 rounded-sm transition-colors disabled:opacity-50"
              >
                <option value="">
                  {leaguesLoading ? 'Loading…' : leagues.length ? 'Select league…' : 'Any / Unknown'}
                </option>
                {leagues.map(l => (
                  <option key={l.id} value={l.name}>
                    {l.name}{l.country ? ` (${l.country})` : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label block mb-1.5">MATCH DATE</label>
              <input
                type="date" name="match_date" value={form.match_date}
                onChange={handleChange} disabled={loading}
                className="w-full bg-brand-gray border border-brand-midgray focus:border-brand-red outline-none text-white font-body text-sm px-4 py-2.5 rounded-sm transition-colors disabled:opacity-50"
              />
            </div>
          </div>

          {/* Validation indicator */}
          {form.home_team.length >= teamNameMin && form.away_team.length >= teamNameMin && (
            <div>
              {validating ? (
                <div className="flex items-center gap-2 text-gray-500">
                  <div className="w-3 h-3 border border-gray-500 border-t-transparent rounded-full animate-spin" />
                  <span className="font-display text-xs">CHECKING FIXTURE DATABASE...</span>
                </div>
              ) : validation?.found ? (
                <div className="bg-brand-greendark border border-brand-green rounded-sm p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="w-2 h-2 rounded-full bg-brand-green" />
                    <span className="font-display text-xs text-brand-greenlight">MATCH VERIFIED</span>
                  </div>
                  <div className="font-display text-xs text-gray-400">
                    {validation.fixture?.league_name && <span className="mr-3">{validation.fixture.league_name}</span>}
                    {validation.fixture?.match_date && <span>{validation.fixture.match_date}</span>}
                  </div>
                </div>
              ) : validation && !validation.found ? (
                <div className="bg-brand-reddark border border-brand-red rounded-sm p-3">
                  <span className="font-display text-xs text-brand-redlight block">MATCH NOT FOUND IN LIVE FIXTURES</span>
                  <span className="font-display text-xs text-gray-500 block mt-1">
                    Must be scheduled within 14 days. Check spelling.
                  </span>
                  <label className="flex items-center gap-2 mt-2 cursor-pointer">
                    <input type="checkbox" name="skip_validation" checked={form.skip_validation} onChange={handleChange} className="w-3 h-3 accent-brand-red" />
                    <span className="font-display text-xs text-gray-500">Override — predict anyway</span>
                  </label>
                </div>
              ) : null}
            </div>
          )}

          {error && (
            <div className="bg-brand-reddark border border-brand-red text-brand-redlight font-display text-xs px-4 py-3 rounded-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !form.home_team || !form.away_team || (validation && !validation.found && !form.skip_validation)}
            className="btn-primary self-start"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" />
                FETCHING LIVE DATA...
              </span>
            ) : 'GENERATE PREDICTION'}
          </button>
        </form>
      </div>

      {/* Loading pipeline */}
      {loading && (
        <div className="card p-5 mb-4">
          <p className="font-display text-xs text-gray-500 mb-3">RUNNING PREDICTION PIPELINE</p>
          <div className="flex flex-col gap-1.5">
            {(PIPELINE_STEPS[form.sport] || PIPELINE_STEPS.soccer).map((step, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-brand-red animate-pulse"
                  style={{ animationDelay: `${i * 0.18}s` }} />
                <span className="font-display text-xs text-gray-600">{step}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div className="flex flex-col gap-4 animate-slide-up">
          <PredictionCard prediction={result} engineStatusBySport={summary?.is_trained || null} />
          {result.extended_markets && (
            <ExtendedMarketsPanel markets={result.extended_markets} sport={result.sport} />
          )}
        </div>
      )}
    </div>
  )
}
