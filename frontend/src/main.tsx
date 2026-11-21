import { Component, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Navigate, NavLink, Route, Routes, useNavigate } from 'react-router'
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import {
  Activity, Bell, BookOpen, CalendarDays, ClipboardCheck, FileText, GitCompareArrows, LayoutGrid,
  ListChecks, LogOut, Menu, Settings, UploadCloud, X,
} from 'lucide-react'
import { api, ApiError, type Account, useAction, useData } from './api'
import { AccountSettings, Dashboard, Notifications, WeeklyDigests } from './workspace'
import { ActionItems, Conflicts, Memory, ReviewCenter } from './review'
import { MeetingDetail, MeetingList, Upload } from './meetings'
import { Privacy, Terms } from './policies'
import { Empty, Load, ModeLabel, onSubmit, Problem, TextLink } from './ui'
import './styles.css'

function Brand() {
  return <Link to="/" className="brand"><span><Activity size={20} /></span>MeetFlow</Link>
}
function Footer() { return <footer><span>MeetFlow</span><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link></footer> }
type AuthMode = 'login' | 'register' | 'register/confirm' | 'forgot' | 'reset'
const authTitles: Record<AuthMode, string> = {
  login: 'Sign in to MeetFlow', register: 'Create your workspace', 'register/confirm': 'Complete registration', forgot: 'Reset your password', reset: 'Choose a new password',
}
function Auth({ mode }: { mode: AuthMode }) {
  const action = useAction()
  const navigate = useNavigate()
  const isReset = mode === 'reset'
  const isSignupConfirmation = mode === 'register/confirm'
  const password = mode === 'login' || isReset || isSignupConfirmation
  const submit = (fields: FormData) => {
    const data = Object.fromEntries(fields.entries())
    if (isReset || isSignupConfirmation) {
      const token = new URLSearchParams(window.location.hash.slice(1)).get('token')
      data.token = token ?? ''
    }
    const paths = { login: 'login', register: 'register', 'register/confirm': 'register/confirm', forgot: 'reset/request', reset: 'reset/confirm' }
    action.mutate({ path: '/auth/' + paths[mode], data }, {
      onSuccess: () => { if (isSignupConfirmation || mode === 'login') navigate('/'); if (isReset) navigate('/login', { replace: true }) },
    })
  }
  return <div className="auth-shell"><div className="auth-frame">
    <div className="auth-side"><Brand /><div><h2>From decisions<br />to execution.</h2><p>Keep a record of what your team decided, who owns the work, and what changes next.</p></div></div>
    <main className="auth-form"><h1>{authTitles[mode]}</h1>
      <form onSubmit={onSubmit(submit)}>
        {isSignupConfirmation && <label>Display name<input name="display_name" autoComplete="name" required maxLength={80} /></label>}
        {!isReset && !isSignupConfirmation && <label>Email<input name="email" type="email" autoComplete="email" required /></label>}
        {password && <label>{isReset ? 'New password' : 'Password'}<input name="password" type="password" required
          minLength={mode === 'login' ? undefined : 12} maxLength={128} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></label>}
        {action.isError && <Problem message={action.error.message} />}
        {(mode === 'forgot' || mode === 'register') && action.isSuccess && <p role="status">{String(action.data.message)}</p>}
        <button className="primary" disabled={action.isPending}>{action.isPending ? 'Working…' : {
          login: 'Sign in', register: 'Send registration link', 'register/confirm': 'Create account', forgot: 'Send reset link', reset: 'Set password',
        }[mode]}</button>
      </form>
      <p className="auth-links">{mode === 'login' ? <><Link to="/register">Create an account</Link><Link to="/forgot">Forgot password?</Link></> : <Link to="/login">Back to sign in</Link>}</p>
    </main>
  </div><Footer /></div>
}

const sections = [
  ['Workspace', [['/', 'Dashboard', LayoutGrid], ['/meetings', 'Meetings', FileText], ['/upload', 'Upload transcript', UploadCloud], ['/review', 'Review center', ClipboardCheck]]],
  ['Execution', [['/memory', 'Decision memory', BookOpen], ['/conflicts', 'Conflict center', GitCompareArrows], ['/actions', 'Action items', ListChecks], ['/notifications', 'Notifications', Bell], ['/digests', 'Weekly digests', CalendarDays]]],
] as const

function Shell({ account }: { account: Account }) {
  const [menu, setMenu] = useState(false)
  const [exitError, setExitError] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const query = useQueryClient()
  const navigate = useNavigate()
  const exit = () => { query.clear(); navigate('/login', { replace: true }) }
  const logout = async () => {
    setSigningOut(true)
    setExitError('')
    try { await api('/auth/logout', 'POST'); exit() }
    catch (error) { setExitError(error instanceof Error ? error.message : 'Sign-out failed. Try again.') }
    finally { setSigningOut(false) }
  }
  return <div className="shell">
    <a className="skip" href="#main">Skip to content</a>
    <aside className={menu ? 'sidebar open' : 'sidebar'}>
      <div className="sidebar-brand"><Brand /><button className="icon-button close" aria-label="Close navigation" onClick={() => setMenu(false)}><X /></button></div>
      <nav aria-label="Main navigation">
        {sections.map(([title, links]) => <div className="nav-group" key={title}><span>{title}</span>
          {links.map(([to, label, Icon]) => <NavLink end={to === '/'} key={to} to={to} onClick={() => setMenu(false)}><Icon size={18} />{label}</NavLink>)}</div>)}
        <NavLink to="/settings" onClick={() => setMenu(false)}><Settings size={18} /> Account & settings</NavLink>
      </nav>
      <div className="sidebar-bottom"><div className="avatar">{account.display_name.slice(0, 1).toUpperCase()}</div><div className="identity"><strong>{account.display_name}</strong><small>{account.email}</small></div>
        <button className="icon-button" aria-label="Sign out" disabled={signingOut} onClick={() => void logout()}><LogOut size={16} /></button></div>
      {exitError && <Problem message={exitError} retry={() => void logout()} />}
    </aside>
    {menu && <button className="scrim" aria-label="Close navigation" onClick={() => setMenu(false)} />}
    <div className="workspace"><header className="topbar">
      <button className="icon-button mobile-menu" aria-label="Open navigation" aria-expanded={menu} onClick={() => setMenu(open => !open)}><Menu /></button>
      <span>MeetFlow Workspace</span><span className="grow" /><ModeLabel mode={account.ai_mode} /><Link aria-label="Notifications" to="/notifications" className="icon-button top-bell"><Bell size={18} /></Link>
    </header>
    <main id="main" className="content">
      {!account.ai_ready && <Problem message={`Live AI is enabled. Set ${account.ai_provider === "gemini" ? "GEMINI_API_KEY" : "DEEPSEEK_API_KEY"} on the server to process transcripts.` } />}
      <Routes>
        <Route path="/" element={<Dashboard account={account} />} />
        <Route path="/meetings" element={<MeetingList />} /><Route path="/meetings/:id" element={<MeetingDetail />} />
        <Route path="/upload" element={<Upload />} /><Route path="/review" element={<ReviewCenter />} />
        <Route path="/memory" element={<Memory />} /><Route path="/conflicts" element={<Conflicts />} />
        <Route path="/actions" element={<ActionItems />} /><Route path="/notifications" element={<Notifications />} />
        <Route path="/digests" element={<WeeklyDigests />} /><Route path="/settings" element={<AccountSettings account={account} onExit={exit} />} />
        <Route path="/privacy" element={<Privacy />} /><Route path="/terms" element={<Terms />} />
        <Route path="*" element={<Empty title="Page not found"><TextLink to="/">Go to dashboard</TextLink></Empty>} />
      </Routes>
    </main><Footer /></div>
  </div>
}

function PrivateWorkspace() {
  const account = useData<Account>('/account')
  if (account.error instanceof ApiError && account.error.status === 401) return <Navigate to="/login" replace />
  return <Load query={account}>{value => <Shell account={value} />}</Load>
}
class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    return this.state.failed ? <main className="content"><Problem message="MeetFlow encountered an unexpected error." retry={() => window.location.reload()} /></main> : this.props.children
  }
}
const cache = new QueryClient()
createRoot(document.getElementById('root')!).render(<ErrorBoundary><QueryClientProvider client={cache}>
  <BrowserRouter><Routes>
    {(['login', 'register', 'register/confirm', 'forgot', 'reset'] as const).map(mode => <Route path={'/' + mode} key={mode} element={<Auth key={mode} mode={mode} />} />)}
    <Route path="/privacy" element={<main className="content"><Brand /><Privacy /><Footer /></main>} />
    <Route path="/terms" element={<main className="content"><Brand /><Terms /><Footer /></main>} />
    <Route path="/*" element={<PrivateWorkspace />} />
  </Routes></BrowserRouter>
</QueryClientProvider></ErrorBoundary>)

