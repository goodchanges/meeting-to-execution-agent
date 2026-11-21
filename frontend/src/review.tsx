import { useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight, GitPullRequest, Plus } from 'lucide-react'
import { type Decision, type Relation, type Task, useData } from './api'
import { Badge, Controls, dateLabel, Empty, Evidence, Load, ModeLabel, onSubmit, PageHead, Problem, TextLink } from './ui'

function DecisionCard({ item }: { item: Decision }) {
  const [edit, setEdit] = useState(false)
  return <article className="panel record"><div className="record-top"><div><small>{item.topic}</small><h3>{item.description}</h3></div><Badge status={item.status} /></div>
    <ModeLabel mode={item.processing_mode} />
    {item.responsible_speaker && <p>{item.responsible_speaker}</p>}
    <Evidence text={item.evidence_excerpt} time={item.evidence_ts} verified={item.evidence_verified} />
    <TextLink to={`/meetings/${item.meeting_id}`}>Source meeting</TextLink>
    <Controls>{(run, pending) => <div className="review-controls">
      {edit && <form onSubmit={onSubmit(data => void run(`/decisions/${item.id}`, {
        description: data.get('description'), responsible_speaker: data.get('speaker') || null,
      }, 'PATCH').then(ok => { if (ok) setEdit(false) }))}>
        <label>Decision<textarea name="description" required defaultValue={item.description} /></label>
        <label>Responsible speaker<input name="speaker" defaultValue={item.responsible_speaker ?? ''} /></label>
        <button disabled={pending}>Save edits</button>
      </form>}
      <div className="buttons">
        <button className="primary" disabled={pending || edit} onClick={() => void run(`/decisions/${item.id}/review`, { action: 'approve' })}>Approve decision</button>
        <button disabled={pending || edit} onClick={() => void run(`/decisions/${item.id}/review`, { action: 'reject' })}>Reject</button>
        <button disabled={pending} onClick={() => setEdit(!edit)}>{edit ? 'Cancel edit' : 'Edit'}</button>
        {item.status === 'NEEDS_REVIEW' && <TextLink to="/conflicts">Check comparisons</TextLink>}
      </div>
    </div>}</Controls>
  </article>
}

export function TaskCard({ item }: { item: Task }) {
  const [edit, setEdit] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const settings = useData<import('./api').Settings>('/settings', confirm)
  const editable = item.github_state === 'NOT_CREATED' && !item.completed_at
  const needs = ['PENDING', 'NEEDS_REVIEW'].includes(item.approval_status)
  const repo = item.github_repo ?? settings.data?.github_repo
  const canPublish = !item.completed_at && item.approval_status === 'APPROVED'
  const path = `/action-items/${item.id}`
  return <article className="panel record">
    <div className="record-top"><div><h3>{item.title}</h3><p>{item.owner ?? 'Unassigned'} · {item.deadline ? dateLabel(item.deadline) : 'Deadline needs review'}</p></div>
      <Badge status={item.completed_at ? 'COMPLETED' : item.approval_status} /></div>
    <ModeLabel mode={item.processing_mode} />
    {item.description !== item.title && <p>{item.description}</p>}
    <Evidence text={item.evidence_excerpt} time={item.evidence_ts} verified={item.evidence_verified} />
    <TextLink to={`/meetings/${item.meeting_id}`}>Source meeting</TextLink>
    {item.github_error && <Problem message={item.github_error} />}
    {item.github_issue_url && <p><a className="text-link" href={item.github_issue_url} target="_blank" rel="noreferrer"><GitPullRequest size={17} /> Open GitHub issue <ArrowRight size={15} /></a></p>}
    <Controls>{(run, pending) => <div className="review-controls">
      {edit && <form onSubmit={onSubmit(data => void run(path, {
        title: data.get('title'), description: data.get('description'), owner: data.get('owner') || null, deadline: data.get('deadline') || null,
      }, 'PATCH').then(ok => { if (ok) setEdit(false) }))}>
        <label>Title<input name="title" required maxLength={180} defaultValue={item.title} /></label>
        <label>Description<textarea name="description" required maxLength={2000} defaultValue={item.description} /></label>
        <label>Owner<input name="owner" defaultValue={item.owner ?? ''} /></label>
        <label>Deadline<input type="date" name="deadline" defaultValue={item.deadline ?? ''} /></label>
        <button disabled={pending}>Save edits</button>
      </form>}
      {confirm && <div className="confirm"><h3>Post this task to GitHub?</h3>
        <Load query={settings}>{prefs => <p>{repo ? `GitHub repository: ${repo}. The issue includes the task, deadline and quoted transcript evidence.${prefs.github_ready ? '' : ' A server token is required.'}` : 'Set a repository in Settings before posting.'}</p>}</Load>
        <div className="buttons"><button className="primary" disabled={pending || !repo || !settings.data?.github_ready} onClick={() => void run(path + '/github').then(ok => { if (ok) setConfirm(false) })}>Confirm post</button>
          <button disabled={pending} onClick={() => setConfirm(false)}>Cancel</button><TextLink to="/settings">Settings</TextLink></div>
      </div>}
      <div className="buttons">
        {needs && <><button className="primary" disabled={pending || edit || item.approval_status === 'NEEDS_REVIEW'} onClick={() => void run(path + '/review', { action: 'approve' })}>Approve task</button>
          <button disabled={pending || edit} onClick={() => void run(path + '/review', { action: 'reject' })}>Reject</button></>}
        {editable && <button disabled={pending} onClick={() => setEdit(!edit)}>{edit ? 'Cancel edit' : 'Edit'}</button>}
        {canPublish && !confirm && !edit && !item.github_issue_url && <button className="primary" disabled={pending} onClick={() => setConfirm(true)}>
          <Plus size={16} />{item.github_state === 'NOT_CREATED' ? 'Create GitHub issue' : 'Retry GitHub issue'}</button>}
        {canPublish && !edit && !confirm && <button disabled={pending || item.github_state === 'CREATING'} onClick={() => void run(path + '/complete')}>Mark complete</button>}
      </div>
    </div>}</Controls>
  </article>
}

export function ReviewCenter() {
  const decisions = useData<Decision[]>('/decisions')
  const tasks = useData<Task[]>('/action-items')
  return <><PageHead title="Review center" subtitle="Confirm the extracted records before they enter decision memory or move to execution." />
    <section><h2>Decisions</h2><Load query={decisions}>{all => {
      const pending = all.filter(row => ['PROPOSED', 'NEEDS_REVIEW'].includes(row.status))
      return pending.length ? <div className="stack">{pending.map(item => <DecisionCard key={item.id} item={item} />)}</div> : <Empty title="No decisions awaiting review"><TextLink to="/meetings">Browse meetings</TextLink></Empty>
    }}</Load></section>
    <section><h2>Action items</h2><Load query={tasks}>{all => {
      const pending = all.filter(row => ['PENDING', 'NEEDS_REVIEW'].includes(row.approval_status))
      return pending.length ? <div className="stack">{pending.map(item => <TaskCard key={item.id} item={item} />)}</div> : <Empty title="No tasks awaiting review"><TextLink to="/actions">View action items</TextLink></Empty>
    }}</Load></section>
  </>
}

export function ActionItems() {
  const query = useData<Task[]>('/action-items')
  return <><PageHead title="Action items" subtitle="Track owners, due dates and GitHub delivery." />
    <Load query={query}>{items => items.length ? <div className="stack">{items.map(item => <TaskCard key={item.id} item={item} />)}</div>
      : <Empty title="No action items yet"><TextLink to="/upload">Upload a transcript</TextLink></Empty>}</Load>
  </>
}

export function Memory() {
  const query = useData<Decision[]>('/decisions')
  return <><PageHead title="Decision memory" subtitle="Follow approved decisions and their history by subject." />
    <Load query={query}>{items => {
      const groups = new Map<string, Decision[]>()
      for (const row of items.filter(item => ['APPROVED', 'SUPERSEDED'].includes(item.status))) {
        groups.set(row.subject_key, [...(groups.get(row.subject_key) ?? []), row])
      }
      return groups.size ? <div className="stack">{[...groups].map(([key, history]) => <section key={key} className="panel inset">
        <h2>{history[0].topic}</h2><ol className="timeline">
          {history.map(row => <li key={row.id}><div className="record-top"><h3>{row.description}</h3><Badge status={row.status} /></div>
            <ModeLabel mode={row.processing_mode} /><Evidence text={row.evidence_excerpt} time={row.evidence_ts} />
            {row.superseded_by_decision_id && <p>Replaced by {history.find(next => next.id === row.superseded_by_decision_id)?.description ?? items.find(next => next.id === row.superseded_by_decision_id)?.description}</p>}
            <TextLink to={`/meetings/${row.meeting_id}`}>Source meeting</TextLink></li>)}</ol>
      </section>)}</div> : <Empty title="Decision memory is empty"><TextLink to="/review">Review extracted decisions</TextLink></Empty>
    }}</Load>
  </>
}

const choices = { KEEP_PREVIOUS: 'Keep previous', ACCEPT_NEW_SUPERSEDES: 'Accept replacement', KEEP_BOTH: 'Keep both', DISMISSED_CONSISTENT: 'Acknowledge' }
function ComparisonCard({ item }: { item: Relation }) {
  const [choice, setChoice] = useState<keyof typeof choices | ''>('')
  return <article className="panel record">
    <div className="record-top"><h3>{item.new.decision.topic}</h3><Badge status={item.relation} /></div>
    <ModeLabel mode={item.processing_mode} />
    <div className="comparison">{(['prior', 'new'] as const).map(side => <div key={side}>
      <small>{side === 'prior' ? 'Previous decision' : 'New decision'}</small>
      <h3>{item[side].decision.description}</h3>
      <Link to={`/meetings/${item[side].meeting.id}`}>{item[side].meeting.title}</Link> · {dateLabel(item[side].meeting.meeting_date)}
      <Evidence text={side === 'prior' ? item.prior_evidence : item.new_evidence} time={item[side].decision.evidence_ts} />
    </div>)}</div>
    <p>{item.reason}</p>
    {item.resolution !== 'PENDING' ? <Badge status={item.resolution} /> : <Controls>{(run, pending) => <form
      onSubmit={onSubmit(data => { if (choice) void run(`/relations/${item.id}/resolve`, { resolution: choice, note: data.get('note') || null }) })}>
      <label>Resolution<select value={choice} onChange={event => setChoice(event.target.value as keyof typeof choices | '')} required>
        <option value="">Choose a resolution</option>
        {Object.entries(choices).filter(([key]) => (item.relation === 'CONSISTENT') === (key === 'DISMISSED_CONSISTENT'))
          .map(([key, value]) => <option key={key} value={key}>{value}</option>)}
      </select></label>
      <label>Resolution note (optional)<input name="note" maxLength={2000} /></label>
      <button className="primary" disabled={pending || !choice}>Confirm resolution</button>
    </form>}</Controls>}
  </article>
}

export function Conflicts() {
  const query = useData<Relation[]>('/relations')
  return <><PageHead title="Conflict center" subtitle="Compare the original evidence and decide what should carry forward." />
    <Load query={query}>{items => items.length ? <div className="stack">{items.map(item => <ComparisonCard key={item.id} item={item} />)}</div>
      : <Empty title="No decision comparisons yet"><TextLink to="/meetings">Browse meetings</TextLink></Empty>}</Load>
  </>
}

