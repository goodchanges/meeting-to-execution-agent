import { Bell, CalendarDays, CircleCheck, FileText, GitCompareArrows, UploadCloud } from 'lucide-react'
import { Link } from 'react-router'
import {
  type Account, type Decision, type Digest, type Meeting, type Notice, type Relation, type Settings,
  type Task, useData,
} from './api'
import { Badge, Controls, dateLabel, Empty, Load, ModeLabel, onSubmit, PageHead, TextLink } from './ui'

export function Dashboard({ account }: { account: Account }) {
  const meetings = useData<Meeting[]>('/meetings')
  const decisions = useData<Decision[]>('/decisions')
  const tasks = useData<Task[]>('/action-items')
  const relations = useData<Relation[]>('/relations')
  return <>
    <div className="hero"><span className="hero-kicker">WORKSPACE OVERVIEW</span>
      <h1>Good to see you,<br />{account.display_name}.</h1>
      <p>From decisions to execution.</p>
      <Link className="button primary" to="/upload"><UploadCloud size={18} /> Upload transcript</Link>
    </div>
    <div className="metrics">
      <Stat title="Meetings" icon={<FileText />} to="/meetings"><Load query={meetings}>{items => items.length}</Load></Stat>
      <Stat title="Approved decisions" icon={<CircleCheck />} to="/memory"><Load query={decisions}>{items => items.filter(item => item.status === 'APPROVED').length}</Load></Stat>
      <Stat title="Open approved tasks" icon={<CalendarDays />} to="/actions"><Load query={tasks}>{items => items.filter(item => item.approval_status === 'APPROVED' && !item.completed_at).length}</Load></Stat>
      <Stat title="Conflicts to resolve" icon={<GitCompareArrows />} to="/conflicts"><Load query={relations}>{items => items.filter(item => item.resolution === 'PENDING' && item.relation !== 'CONSISTENT').length}</Load></Stat>
    </div>
    <section className="panel inset"><div className="record-top"><h2>Recent meetings</h2><TextLink to="/meetings">View all</TextLink></div>
      <Load query={meetings}>{items => items.length ? items.slice(0, 5).map(item => <Link key={item.id} className="list-row" to={`/meetings/${item.id}`}>
        <span className="row-icon"><FileText size={18} /></span><span className="flex-fill"><strong>{item.title}</strong><small>{dateLabel(item.meeting_date)}</small></span><ModeLabel mode={item.processing_mode} /><Badge status={item.status} />
      </Link>) : <Empty title="Your workspace is ready"><TextLink to="/upload">Upload your first transcript</TextLink></Empty>}</Load>
    </section>
  </>
}

function Stat({ title, icon, to, children }: { title: string; icon: React.ReactNode; to: string; children: React.ReactNode }) {
  return <div className="panel stat"><Link to={to}>{icon}{title}</Link><div className="stat-value">{children}</div></div>
}

export function Notifications() {
  const query = useData<Notice[]>('/notifications')
  return <>
    <Controls>{(run, pending) => <PageHead title="Notifications" subtitle="In-app reminders and pending decision comparisons."
      actions={<button className="primary" disabled={pending} onClick={() => void run('/notifications/generate')}><Bell size={16} /> Generate reminders now</button>} />}</Controls>
    <Load query={query}>{entries => entries.length ? <div className="stack">{entries.map(item => <article className="panel record" key={item.id}>
      <div className="record-top"><h3>{item.message}</h3><Badge status={item.kind} /></div>
      <ModeLabel mode={item.processing_mode} />
      {item.read_at ? <span className="muted">Read</span> : <Controls>{(run, pending) => <button disabled={pending} onClick={() => void run(`/notifications/${item.id}/read`)}>Mark as read</button>}</Controls>}
    </article>)}</div> : <Empty title="No notifications"><TextLink to="/actions">Browse action items</TextLink></Empty>}</Load>
  </>
}
export function WeeklyDigests() {
  const query = useData<Digest[]>('/digests')
  return <>
    <Controls>{(run, pending) => <PageHead title="Weekly digests" subtitle="Weekly follow-through for each participant."
      actions={<button className="primary" disabled={pending} onClick={() => void run('/digests/generate')}>Generate now</button>} />}</Controls>
    <Load query={query}>{entries => entries.length ? <div className="stack">{entries.map(item => <article className="panel record" key={item.id}>
      <div className="record-top"><div><h3>{item.person_name}</h3><small>Week of {dateLabel(item.week_start)}</small></div><ModeLabel mode={item.processing_mode} /></div>
      <div className="digest-columns">
        <div><h4>Assigned tasks</h4>{item.payload.tasks.length ? <ul>{item.payload.tasks.map(task => <li key={task.id}>{task.title} · {task.deadline ? dateLabel(task.deadline) : 'No deadline specified'} <Badge status={task.status} /></li>)}</ul> : <p>No assigned tasks.</p>}</div>
        <div><h4>Approved decisions</h4>{item.payload.decisions.length ? <ul>{item.payload.decisions.map((decision, index) => <li key={index}>{decision}</li>)}</ul> : <p>No relevant decisions.</p>}</div>
        <div><h4>Pending comparisons</h4>{item.payload.conflicts.length ? <ul>{item.payload.conflicts.map((topic, index) => <li key={index}>{topic}</li>)}</ul> : <p>No pending comparisons.</p>}</div>
      </div>
    </article>)}</div> : <Empty title="No weekly digests"><TextLink to="/meetings">Browse meeting participants</TextLink></Empty>}</Load>
  </>
}
export function AccountSettings({ account, onExit }: { account: Account; onExit: () => void }) {
  const settings = useData<Settings>('/settings')
  const audit = useData<{ id: string; action: string; object_type: string; outcome: string; created_at: string }[]>('/audit')
  return <><PageHead title="Account & settings" subtitle={account.email} />
    <section className="panel inset"><h2>Workspace</h2>
      <Load query={settings}>{prefs => <Controls>{(run, pending) => <form className="form-narrow" onSubmit={onSubmit(data => void run('/settings',
        { timezone: data.get('timezone') }, 'PATCH'))}>
        <p>{prefs.github_repo ? `GitHub repository: ${prefs.github_repo}` : 'No GitHub repository is configured on the server.'}</p>
        {!prefs.github_ready && <p className="muted">An operator must configure the server repository and token to post issues.</p>}
        <label>Timezone<input name="timezone" defaultValue={prefs.timezone} required /></label><button className="primary" disabled={pending}>Save settings</button>
      </form>}</Controls>}</Load>
    </section>
    <section className="panel inset"><h2>Change password</h2>
      <Controls>{(run, pending) => <form className="form-narrow" onSubmit={onSubmit(data => void run('/account/password', {
        password: data.get('password'), new_password: data.get('new_password'),
      }).then(ok => { if (ok) onExit() }))}>
        <label>Current password<input name="password" type="password" autoComplete="current-password" required /></label>
        <label>New password<input name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required /></label>
        <button disabled={pending}>Change password and sign out</button>
      </form>}</Controls>
    </section>
    <section className="panel inset"><h2>Audit activity</h2><Load query={audit}>{rows => rows.length ? <ul className="audit-list">{rows.map(row => <li key={row.id}>
      <strong>{row.action}</strong> {row.object_type} · {row.outcome} <time>{dateLabel(row.created_at)}</time>
    </li>)}</ul> : <p>No events yet.</p>}</Load></section>
    <section className="panel inset danger-panel"><h2>Delete account</h2><p>Permanently delete your account and workspace data. Existing GitHub issues will remain on GitHub.</p>
      <Controls>{(run, pending) => <form className="form-narrow" onSubmit={onSubmit(data => void run('/account', {
        password: data.get('password'), confirmation: data.get('confirmation'),
      }, 'DELETE').then(ok => { if (ok) onExit() }))}>
        <label>Current password<input name="password" type="password" autoComplete="current-password" required /></label>
        <label>Type DELETE to confirm<input name="confirmation" pattern="DELETE" required /></label>
        <button className="danger" disabled={pending}>Delete account</button>
      </form>}</Controls>
    </section>
  </>
}

