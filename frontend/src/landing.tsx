import { Activity, ArrowDown, ArrowRight, Check, ClipboardList, FileText, GitCompareArrows } from 'lucide-react'
import { Link } from 'react-router'

export function Brand() {
  return <Link to="/" className="brand"><span><Activity size={19} aria-hidden="true" /></span>MeetFlow</Link>
}

export function Footer() {
  return <footer><span>MeetFlow</span><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link></footer>
}

const workflow = [
  { icon: FileText, title: 'Bring the transcript.', description: 'Upload a meeting transcript or paste the text. Speaker names and timestamps stay with the source.' },
  { icon: GitCompareArrows, title: 'Review what changed.', description: 'Check decisions against their source and compare them with earlier meetings before approving a replacement.' },
  { icon: ClipboardList, title: 'Follow the work.', description: 'Review owners and deadlines, generate reminders, and confirm which approved tasks to send to GitHub.' },
]

function MeetingPreview() {
  return <figure className="landing-preview" aria-label="Sample MeetFlow workspace">
    <div className="preview-window">
      <div className="preview-header">
        <span><Activity size={18} aria-hidden="true" /> MeetFlow</span>
        <span className="preview-label">Sample workspace</span>
      </div>
      <div className="preview-body">
        <article className="preview-decision">
          <div className="preview-card-label"><GitCompareArrows size={17} aria-hidden="true" /> Decision memory</div>
          <h2>Launch date</h2>
          <div className="preview-change">
            <div><small>Kickoff · Nov 18</small><strong>Dec 15</strong><span>Superseded</span></div>
            <ArrowRight size={19} aria-hidden="true" />
            <div><small>Follow-up · Nov 20</small><strong>Dec 10</strong><span><Check size={12} aria-hidden="true" /> Approved</span></div>
          </div>
        </article>
        <article className="preview-task">
          <div className="preview-card-label"><ClipboardList size={17} aria-hidden="true" /> Action items</div>
          <h2>Prepare the launch checklist</h2>
          <div className="preview-assignee"><span aria-hidden="true">A</span><div><strong>Alex</strong><small>Due Dec 5</small></div></div>
        </article>
      </div>
    </div>
  </figure>
}

export function Landing() {
  return <div className="landing">
    <header className="landing-header">
      <nav className="landing-nav" aria-label="Site navigation">
        <Brand />
        <a className="landing-nav-workflow" href="#workflow">How it works</a>
        <Link to="/login" className="landing-sign-in">Sign in</Link>
      </nav>
    </header>
    <main>
      <section className="landing-hero">
        <h1>Turn meetings<br />into <span>clear next steps.</span></h1>
        <p>See what your team decided, who owns the work, and what changed since the last meeting.</p>
        <div className="landing-actions">
          <Link className="button primary" to="/register">Create a workspace <ArrowRight size={17} aria-hidden="true" /></Link>
          <a className="landing-workflow-link" href="#workflow">How it works <ArrowDown size={16} aria-hidden="true" /></a>
        </div>
        <MeetingPreview />
      </section>
      <section className="landing-workflow" id="workflow">
        <h2>From transcript to follow-through.</h2>
        <div className="landing-workflow-grid">
          {workflow.map(({ icon: Icon, title, description }) => <article key={title}>
            <Icon size={24} aria-hidden="true" /><h3>{title}</h3><p>{description}</p>
          </article>)}
        </div>
      </section>
    </main>
    <Footer />
  </div>
}
