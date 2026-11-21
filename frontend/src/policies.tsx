import { PageHead } from './ui'

export function Privacy() {
  return <><PageHead title="Privacy policy" subtitle="Draft for legal review before commercial use." />
    <section className="panel inset legal"><h2>Workspace data</h2>
    <p>MeetFlow stores account details, source transcripts, extracted records, task activity and settings in the workspace database. Only upload transcripts you have permission to share.</p>
    <h2>Service providers</h2><p>In live mode, OpenAI receives transcript segments and decision evidence for analysis. When you confirm posting, GitHub receives the task details and its source evidence. If configured, an email provider delivers password reset links.</p>
    <h2>Deletion and retention</h2><p>Account deletion removes owned application records. Pseudonymous audit events are retained. Issues already created in GitHub remain in that repository. Copies in backups age out according to the operator’s retention policy.</p></section>
  </>
}
export function Terms() {
  return <><PageHead title="Terms of service" subtitle="Draft for legal review before commercial use." />
    <section className="panel inset legal"><h2>Use and review</h2><p>Use only meeting material you have permission to process. Review extracted records and evidence before approving or sharing them. Posted issues are governed by the destination repository and GitHub’s terms.</p>
    <h2>Availability</h2><p>MeetFlow provides an experimental workflow for reviewing meeting decisions. Use a separate system of record for critical obligations.</p></section>
  </>
}

