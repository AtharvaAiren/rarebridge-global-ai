/**
 * The collaboration brief, built only from the current assessment response
 * (the "after" state when sources are hidden). Copy, download and print all
 * render this one model, so they can never disagree. Pure module.
 */
import type { AssessmentCheck, AssessmentResponse, Contact } from '../api/types.ts'
import { diseaseDisplayName } from './diseases.ts'
import { findGoal } from './goals.ts'
import { reviewSpec, statusSpec } from './status.ts'

export const BRIEF_DISCLAIMER =
  'Prepared with RareBridge from a three-disease demonstration collection. Not medical advice. Statuses describe what cited sources say, not clinical validation.'

const DEFAULT_ROLE = 'study coordinator'

export interface BriefSource {
  number: number
  id: string
  title: string
  url: string
  publishedOn: string | null
  aliases: string[]
  isHidden: boolean
}

export interface BriefCheck {
  question: string
  statusLabel: string
  sourceNumbers: number[]
  rationale: string[]
  nextQuestion: string
  contactRole: string
  isRequired: boolean
}

export interface BriefContact {
  label: string
  kind: string
  role: string
  url: string
  reviewLabel: string
  isAllSourcesHidden: boolean
}

export interface BriefModel {
  title: string
  diseaseName: string
  diseaseFullName: string
  goalLabel: string
  goalDefinition: string
  goalDetail: string
  resourceLabel: string
  resourceUrl: string
  accessStatus: string
  outcomeLabel: string
  outcomeNote: string | null
  supported: BriefCheck[]
  open: BriefCheck[]
  differences: string[]
  questions: { question: string; contactRole: string }[]
  contacts: BriefContact[]
  sources: BriefSource[]
  hiddenSources: { id: string; title: string }[]
  nextStep: string
  generation: string
  coverage: string
  limitations: string
  dataNote: string
  preparedOn: string
  preparedOnIso: string
  disclaimer: string
}

export interface BriefInput {
  assessment: AssessmentResponse
  hidden: readonly string[]
  preparedOn: Date
  dataMode: 'live' | 'demo'
}

export function buildBrief({ assessment, hidden, preparedOn, dataMode }: BriefInput): BriefModel {
  const after = assessment.after
  const target = after.target_disease
  const goal = findGoal(assessment.goal_id ?? 'natural_history')
  const numbering = numberSources(assessment)
  const toCheck = (check: AssessmentCheck): BriefCheck => ({
    question: check.question,
    statusLabel: statusSpec(check.status).label,
    sourceNumbers: check.active_evidence.map((e) => numbering.get(e.source_id)).filter((n): n is number => n !== undefined),
    rationale: check.active_evidence.map((e) => e.rationale),
    nextQuestion: check.next_question,
    contactRole: check.contact_role,
    isRequired: check.required,
  })

  return {
    title: `Collaboration brief: ${after.asset?.label ?? 'research resource'}`,
    diseaseName: target ? diseaseDisplayName(target.id, target.label) : 'the disease',
    diseaseFullName: target?.label ?? '',
    goalLabel: goal?.label ?? after.goal ?? 'Research goal',
    goalDefinition: goal?.definition ?? '',
    goalDetail: after.goal ?? '',
    resourceLabel: after.asset?.label ?? '',
    resourceUrl: after.asset?.url ?? '',
    accessStatus: after.asset?.access_status ?? '',
    outcomeLabel: statusSpec(after.outcome).label,
    outcomeNote: hidden.length === 0 ? null : outcomeNote(assessment, hidden.length),
    supported: after.checks.filter((c) => c.status === 'supported').map(toCheck),
    open: after.checks.filter((c) => c.status !== 'supported').map(toCheck),
    differences: differencesFrom(assessment),
    questions: after.followup_questions.map((q) => ({ question: q.question, contactRole: q.contact_role })),
    contacts: assessment.contacts.map(toContact),
    sources: [...numbering.entries()].map(([id, number]) => {
      const source = assessment.sources[id]
      return {
        number,
        id,
        title: source?.title ?? id,
        url: source?.url ?? '',
        publishedOn: source?.published_on ?? null,
        aliases: source?.aliases ?? [],
        isHidden: hidden.includes(id),
      }
    }),
    hiddenSources: hidden.map((id) => ({ id, title: assessment.sources[id]?.title ?? id })),
    nextStep: nextStepFor(after.followup_questions[0]?.contact_role),
    generation:
      assessment.explanation.generation_mode === 'none'
        ? 'Built from the recorded assessment and its sources. No AI-generated text.'
        : `Includes an AI-generated explanation (${assessment.explanation.generation_mode}${assessment.explanation.model ? `, ${assessment.explanation.model}` : ''}).`,
    coverage: assessment.coverage,
    limitations: after.limitations,
    dataNote:
      dataMode === 'demo'
        ? 'Demo data: saved example responses, not the live service.'
        : `Live data from the local RareBridge service (${assessment.data_origin}).`,
    preparedOn: preparedOn.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }),
    preparedOnIso: isoDate(preparedOn),
    disclaimer: BRIEF_DISCLAIMER,
  }
}

function outcomeNote(assessment: AssessmentResponse, hiddenCount: number): string {
  const changed = assessment.changed_checks.length
  const isSame = assessment.before.outcome === assessment.after.outcome
  const checks = changed === 1 ? '1 check' : `${changed} checks`
  const sources = hiddenCount === 1 ? 'one source' : `${hiddenCount} sources`
  const overall = isSame ? 'did not change' : `changed from "${statusSpec(assessment.before.outcome).label}"`
  const interpretation = assessment.interpretation ? ` ${assessment.interpretation}` : ''
  return `${checks} changed with ${sources} hidden; the overall result ${overall}.${interpretation}`
}

/** Sources cited by checks first (in check order), then every other source in the response. */
function numberSources(assessment: AssessmentResponse): Map<string, number> {
  const cited = assessment.after.checks.flatMap((c) => [...c.active_evidence, ...c.withdrawn_evidence].map((e) => e.source_id))
  const ordered = [...new Set([...cited, ...Object.keys(assessment.sources)])]
  return new Map(ordered.map((id, index) => [id, index + 1]))
}

function differencesFrom(assessment: AssessmentResponse): string[] {
  const context = assessment.asset_context
  if (!context) return []
  const unverified = context.unverified ?? []
  return [
    context.documented_context,
    context.owner_status,
    unverified.length > 0 ? `Not yet checked: ${unverified.join('; ')}.` : undefined,
  ].filter((line): line is string => Boolean(line))
}

function toContact(contact: Contact): BriefContact {
  return {
    label: contact.label,
    kind: contact.kind.replace(/_/g, ' '),
    role: contact.role,
    url: contact.url,
    reviewLabel: reviewSpec(contact.review_status).label,
    isAllSourcesHidden: contact.all_sources_withdrawn === true,
  }
}

function nextStepFor(role: string | undefined): string {
  return `Send the open questions below to a ${role ?? DEFAULT_ROLE} through one of the public routes listed, and decide together which parts of the resource could inform your study. Nothing here confirms access, permission or suitability.`
}

export function isoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** A first draft for the person to edit. Addressed to a role, never an invented person. */
export function defaultDraft(model: BriefModel): string {
  const role = model.questions[0]?.contactRole ?? DEFAULT_ROLE
  const firstSource = model.sources[0]
  const described = firstSource ? `, described in "${firstSource.title}" (${firstSource.url})` : ''
  const questions = model.questions.map((q, i) => `${i + 1}. ${q.question}`).join('\n')
  return [
    `Dear ${role},`,
    '',
    `I lead a patient organization for ${model.diseaseName}. We are planning a natural-history study and found the ${model.resourceLabel}${described}.`,
    '',
    'We would like to understand whether parts of it could inform our own study. Our open questions are:',
    questions || '(no open questions recorded)',
    '',
    'Could you tell us who the right person is to discuss this, or point us to the relevant materials?',
    '',
    'Thank you,',
    '[Your name]',
    '[Your organization]',
  ].join('\n')
}

/** Plain-text rendering of the whole brief, including the edited draft. */
export function briefToText(model: BriefModel, draft: string): string {
  const lines: string[] = []
  const section = (title: string) => lines.push('', title.toUpperCase(), '-'.repeat(title.length))
  const refs = (numbers: number[]) => (numbers.length > 0 ? ` [${numbers.join(', ')}]` : '')

  lines.push(model.title, '='.repeat(model.title.length), `Prepared ${model.preparedOn}`)
  section('Goal')
  lines.push(`${model.goalLabel} for ${model.diseaseName}${model.diseaseFullName ? ` (${model.diseaseFullName})` : ''}.`)
  if (model.goalDefinition) lines.push(model.goalDefinition)
  section('Resource')
  lines.push(model.resourceLabel, model.resourceUrl, `Access: ${model.accessStatus}`, `Overall: ${model.outcomeLabel}`)
  if (model.outcomeNote) lines.push(model.outcomeNote)
  section('What the sources support')
  if (model.supported.length === 0) lines.push('No check is supported by the sources in this view.')
  model.supported.forEach((c) => lines.push(`- ${c.question}${refs(c.sourceNumbers)}`, ...c.rationale.map((r) => `  ${r}`)))
  section('Open checks')
  model.open.forEach((c) =>
    lines.push(
      `- ${c.question} (${c.statusLabel}${c.isRequired ? '' : ', not required'})${refs(c.sourceNumbers)}`,
      `  Next question: ${c.nextQuestion}`,
      `  Who could answer: ${c.contactRole}`,
    ),
  )
  if (model.differences.length > 0) {
    section('Relevant differences and limits')
    model.differences.forEach((d) => lines.push(`- ${d}`))
  }
  section('Proposed next step')
  lines.push(model.nextStep)
  section('Public contact routes')
  if (model.contacts.length === 0) lines.push('No contact route is recorded for this assessment.')
  model.contacts.forEach((c) =>
    lines.push(
      `- ${c.label} (${c.kind}; ${c.reviewLabel})`,
      `  ${c.role}`,
      `  ${c.url}`,
      ...(c.isAllSourcesHidden ? ['  Every source for this contact is hidden in this view.'] : []),
    ),
  )
  section('Draft message (review before sending)')
  lines.push(draft)
  section('Sources')
  model.sources.forEach((s) =>
    lines.push(
      `[${s.number}] ${s.title}${s.publishedOn ? ` (${s.publishedOn})` : ''}${s.isHidden ? ' (hidden in this view)' : ''}`,
      `    ${s.url}${s.aliases.length > 0 ? ` (also ${s.aliases.join(', ')})` : ''}`,
    ),
  )
  if (model.hiddenSources.length > 0) {
    section('Sources hidden in this view')
    lines.push('This brief reflects the assessment with these sources hidden:')
    model.hiddenSources.forEach((s) => lines.push(`- ${s.title} (${s.id})`))
  }
  section('About this brief')
  lines.push(model.generation, model.dataNote, model.coverage, model.limitations, '', `${model.disclaimer} Prepared ${model.preparedOn}.`)
  return `${lines.join('\n')}\n`
}

export function briefFileName(model: BriefModel): string {
  const slug = model.resourceLabel
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 48)
  return `rarebridge-brief-${slug || 'resource'}-${model.preparedOnIso}.txt`
}
