import { useState, type FormEvent, type ReactNode } from 'react'
import { AlertCircle, Check, ChevronRight, LoaderCircle, PackageOpen } from 'lucide-react'
import { Link } from 'react-router'
import type { UseQueryResult } from '@tanstack/react-query'
import { useAction, type Mode } from './api'

export const human = (value: string) => value.toLowerCase().replaceAll('_', ' ').replace(/^./, c => c.toUpperCase())
export const dateLabel = (value: string) => new Intl.DateTimeFormat('en', {
  month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC',
}).format(new Date(value.slice(0, 10) + 'T00:00:00Z'))
export function Badge({ status }: { status: string }) { return <span className={'badge ' + status.toLowerCase()}>{human(status)}</span> }
export function ModeLabel({ mode }: { mode: Mode }) {
  return mode === 'demo' ? <span className="badge demo">DEMO MODE — not live AI</span> : null
}
export function PageHead({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return <header className="page-head"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{actions}</header>
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><PackageOpen size={24} /><h3>{title}</h3>{children}</div>
}
export function Problem({ message, retry }: { message: string; retry?: () => void }) {
  return <div role="alert" className="problem"><AlertCircle size={18} /><span>{message}</span>{retry && <button onClick={retry}>Retry</button>}</div>
}
export function Load<T>({ query, children }: { query: UseQueryResult<T>; children: (value: T) => ReactNode }) {
  if (query.isPending) return <div className="skeletons" role="status" aria-label="Loading"><i /><i /><i /></div>
  if (query.isError) return <Problem message={query.error.message} retry={() => void query.refetch()} />
  return children(query.data)
}
export function Evidence({ text, time, verified }: { text: string; time?: string | null; verified?: boolean }) {
  return <blockquote>{text}{time && <small>{time}</small>}{verified === false && <small className="warn">Evidence could not be verified. Check the transcript.</small>}</blockquote>
}

export type ActionRunner = (path: string, data?: unknown, method?: string) => Promise<boolean>
export function Controls({ children }: { children: (run: ActionRunner, pending: boolean) => ReactNode }) {
  const action = useAction()
  const [message, setMessage] = useState('')
  const run: ActionRunner = async (path, data, method) => {
    setMessage('')
    try {
      const response = await action.mutateAsync({ path, method, data })
      if (response.github_state === 'FAILED' || response.status === 'FAILED') return false
      setMessage(typeof response.created === 'number'
        ? `${response.created} new notifications.` : typeof response.generated === 'number'
        ? `${response.generated} digests generated.` : 'Saved.')
      return true
    } catch { return false }
  }
  return <>
    {children(run, action.isPending)}
    {action.isPending && <p className="feedback" role="status"><LoaderCircle className="spin" size={14} /> Working…</p>}
    {action.isError && <Problem message={action.error.message} retry={() => { if (action.variables) {
      const { path, data, method } = action.variables
      void run(path, data, method)
    } }} />}
    {message && <p className="feedback good" role="status"><Check size={16} /> {message}</p>}
  </>
}
export function onSubmit(send: (data: FormData) => void) {
  return (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    send(new FormData(event.currentTarget))
  }
}
export function TextLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link className="text-link" to={to}>{children}<ChevronRight size={15} /></Link>
}

