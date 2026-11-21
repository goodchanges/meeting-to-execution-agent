import { useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router'
import { ArrowLeft, FileText, UploadCloud } from 'lucide-react'
import { ApiError, type Detail, type Meeting, type Mode, useAction, useData } from './api'
import { Badge, Controls, dateLabel, Empty, Load, ModeLabel, onSubmit, PageHead, Problem, TextLink } from './ui'

export function MeetingList() {
  const query = useData<Meeting[]>('/meetings')
  return <><PageHead title="Meetings" subtitle="Browse source transcripts and extracted records."
    actions={<Link className="button primary" to="/upload"><UploadCloud size={17} /> Upload transcript</Link>} />
    <Load query={query}>{items => items.length ? <div className="panel meeting-list">
      {items.map(item => <Link className="list-row" key={item.id} to={`/meetings/${item.id}`}>
        <span className="row-icon"><FileText size={18} /></span><span className="flex-fill"><strong>{item.title}</strong><small>{dateLabel(item.meeting_date)} · {item.source_format.toUpperCase()}</small></span>
        <ModeLabel mode={item.processing_mode} /><Badge status={item.status} />
      </Link>)}
    </div> : <Empty title="No meetings yet"><TextLink to="/upload">Upload a transcript</TextLink></Empty>}</Load>
  </>
}
export function Upload({ mode }: { mode: Mode }) {
  const [method, setMethod] = useState<'file' | 'paste'>('file')
  const [duplicate, setDuplicate] = useState<FormData | null>(null)
  const action = useAction()
  const navigate = useNavigate()
  const submit = (data: FormData) => {
    setDuplicate(null)
    if (method === 'file') data.delete('transcript')
    else data.delete('file')
    if (!data.get('meeting_date')) data.delete('meeting_date')
    action.mutate({ path: '/meetings', data }, {
      onSuccess: result => navigate(`/meetings/${result.id}`),
      onError: error => { if (error instanceof ApiError && error.status === 409) setDuplicate(data) },
    })
  }
  return <>
    <Link className="text-link back" to="/meetings"><ArrowLeft size={16} /> Meetings</Link>
    <PageHead title="Upload a transcript" subtitle="Preserve speaker names and cue timestamps for review." />
    {mode === 'demo' && <section className="panel inset sample-downloads" aria-labelledby="samples-heading">
      <h2 id="samples-heading">Demo transcripts</h2>
      <p>Download both samples and process the kickoff first.</p>
      <div className="buttons">
        <a className="button" href="/api/meetings/demo-samples/meeting1_2026-11-18.txt">Launch kickoff (TXT)</a>
        <a className="button" href="/api/meetings/demo-samples/meeting2_2026-11-20.vtt">Launch follow-up (VTT)</a>
      </div>
    </section>}
    <section className="panel form-panel">
      <div className="switch" role="group" aria-label="Transcript source">
        <button type="button" aria-pressed={method === 'file'} onClick={() => { setMethod('file'); setDuplicate(null) }}>Upload file</button>
        <button type="button" aria-pressed={method === 'paste'} onClick={() => { setMethod('paste'); setDuplicate(null) }}>Paste text</button>
      </div>
      <form onSubmit={onSubmit(submit)} onChange={() => { if (duplicate) setDuplicate(null) }}>
        <label>Meeting title<input name="title" required maxLength={180} placeholder="Product launch planning" /></label>
        <label>Meeting date<input type="date" name="meeting_date" required={method === 'paste'} />
          {method === 'file' && <small>Optional when the filename contains YYYY-MM-DD.</small>}</label>
        {method === 'file' ? <label className="file-field"><UploadCloud size={23} /> Transcript file
          <input type="file" name="file" accept=".txt,.vtt,.srt" required /><small>TXT, VTT or SRT</small>
        </label> : <label>Transcript<textarea name="transcript" required rows={9} placeholder="Alex: We agreed to launch on…" /></label>}
        {action.isError && <Problem message={action.error.message} />}
        <div className="buttons"><button className="primary" disabled={action.isPending}>{action.isPending ? 'Uploading…' : 'Save transcript'}</button>
          {duplicate && <button type="button" onClick={() => { duplicate.set('process_anyway', 'true'); submit(duplicate) }}>Upload duplicate anyway</button>}
        </div>
      </form>
    </section>
  </>
}

export function MeetingDetail() {
  const [replace, setReplace] = useState(false)
  const { id } = useParams()
  const query = useData<Detail>(`/meetings/${id}`)
  return <Load query={query}>{meeting => <>
    <Link className="text-link back" to="/meetings"><ArrowLeft size={16} /> Meetings</Link>
    <PageHead title={meeting.title} subtitle={dateLabel(meeting.meeting_date)} actions={<div className="buttons">
      <ModeLabel mode={meeting.processing_mode} /><Badge status={meeting.status} /></div>} />
    {meeting.status === 'PROCESSING' && <div className="panel inset"><p>Processing in progress. Refresh to check the result. An interrupted run can be retried after 15 minutes.</p>
      <button onClick={() => void query.refetch()}>Refresh</button><Controls>{(run, pending) => <button disabled={pending} onClick={() => void run(`/meetings/${id}/process`)}>Retry processing</button>}</Controls></div>}
    {['UPLOADED', 'FAILED'].includes(meeting.status) && <section className="panel inset">
      <h2>{meeting.status === 'FAILED' ? 'AI processing failed. Your transcript is saved.' : 'Transcript saved'}</h2>
      {meeting.failure_reason && <Problem message={meeting.failure_reason} />}
      <Controls>{(run, pending) => <button className="primary" disabled={pending} onClick={() => void run(`/meetings/${id}/process`)}>
        {meeting.status === 'FAILED' ? 'Retry processing' : 'Extract decisions and tasks'}</button>}</Controls>
    </section>}
    {meeting.status === 'EXTRACTED' && <div className="panel inset"><h2>Extraction complete</h2>
      <p>{meeting.decisions.length} decisions · {meeting.action_items.length} action items</p><TextLink to="/review">Open review center</TextLink>
      <Controls>{(run, pending) => replace ? <div className="confirm"><p>Replace this meeting’s unreviewed extraction? The original transcript stays saved.</p>
        <div className="buttons"><button disabled={pending} onClick={() => void run(`/meetings/${id}/process?reprocess=true`).then(ok => { if (ok) setReplace(false) })}>Confirm replacement</button>
          <button disabled={pending} onClick={() => setReplace(false)}>Cancel</button></div></div>
        : <div><button onClick={() => setReplace(true)}>Replace unreviewed extraction</button></div>}</Controls></div>}
    <section className="panel inset transcript"><h2>Transcript</h2>
      {meeting.participants.length > 0 && <p>{meeting.participants.map(person => person.name).join(' · ')}</p>}
      {meeting.segments.map(segment => <div className="segment" key={segment.id}>
        <div><strong>{segment.speaker_label ?? 'Unresolved speaker'}</strong>{segment.start_ts && <small>{segment.start_ts}</small>}</div>
        <p>{segment.text}</p>
      </div>)}</section>
  </>}</Load>
}

