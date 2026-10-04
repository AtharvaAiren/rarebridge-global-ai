import { useCallback, useEffect, useMemo, useState } from 'react'
import { useApiClient } from '../../api/ApiContext.tsx'
import type { OverviewResponse, SourceMap } from '../../api/types.ts'
import { Icon } from '../../components/Icon.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { useApiResource } from '../../hooks/useApiResource.ts'
import { routeHash } from '../../routing.ts'
import { navigate } from '../../hooks/useRoute.ts'
import { useAssessment, type EvidenceControls } from '../evidence/useAssessment.ts'
import { BriefSheet } from '../brief/BriefSheet.tsx'
import { AtlasGraph } from '../graph/AtlasGraph.tsx'
import type { AtlasRequest } from '../graph/types.ts'
import { JourneyBar } from './JourneyBar.tsx'
import { CoverageNotes, DiseaseHeader, Opportunities, Organizations, PossiblyRelated, RouteCallout } from './RouteSections.tsx'
import { recordedRoutes, splitRelated } from './routes.ts'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import { ResearchLeads } from '../research/ResearchLeads.tsx'

type RouteViewProps = {
  diseaseId: string
  goalId: string
  evidenceId?: string
  isBriefOpen: boolean
}

export function RouteView({ diseaseId, goalId, evidenceId, isBriefOpen }: RouteViewProps) {
  const client = useApiClient()
  const { state, retry } = useApiResource(`overview:${diseaseId}:${goalId}`, (signal) =>
    client.overview(diseaseId, goalId, signal),
  )

  return (
    <main id="main" className="rb-container view view--route" tabIndex={-1}>
      <a className="back-link" href={routeHash({ name: 'home' })}>
        <Icon name="arrowLeft" />
        Back to search
      </a>
      {state.status === 'loading' && <LoadingState label="Loading the research overview…" />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'success' && (
        <RouteContent key={diseaseId} overview={state.data} evidenceId={evidenceId} isBriefOpen={isBriefOpen} />
      )}
    </main>
  )
}

type RequestCommand = { kind: 'trace'; routeKey: string } | { kind: 'select'; nodeId: string }

type RouteContentProps = {
  overview: OverviewResponse
  evidenceId?: string
  isBriefOpen: boolean
}

function RouteContent({ overview, evidenceId, isBriefOpen }: RouteContentProps) {
  const { setResearchContacts } = usePreferences()
  useEffect(() => () => setResearchContacts([]), [setResearchContacts])
  const [request, setRequest] = useState<AtlasRequest | null>(null)
  const evidenceState = useAssessment(evidenceId)
  useEffect(() => {
    const contacts = [...overview.organizations, ...(evidenceState?.current?.contacts ?? [])]
    setResearchContacts([...new Map(contacts.map((contact) => [contact.id, contact])).values()])
  }, [overview.organizations, evidenceState?.current, setResearchContacts])
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<string | undefined>(evidenceId)
  const routeTo = (nextEvidenceId: string | undefined, isBrief = false) =>
    navigate({
      name: 'disease',
      diseaseId: overview.disease.id,
      goal: overview.goal_id,
      evidenceId: nextEvidenceId,
      isBriefOpen: isBrief,
    })
  const evidence: EvidenceControls = {
    state: evidenceState,
    open: (assessmentId) => { setSelectedAssessmentId(assessmentId); routeTo(assessmentId) },
    close: () => routeTo(undefined),
    openBrief: () => evidenceId && routeTo(evidenceId, true),
  }
  const closeBrief = useCallback(() => {
    navigate({ name: 'disease', diseaseId: overview.disease.id, goal: overview.goal_id, evidenceId })
  }, [overview.disease.id, overview.goal_id, evidenceId])
  const [sources, setSources] = useState<SourceMap>({})
  const routes = useMemo(() => recordedRoutes(overview), [overview])
  const { withRoutes, candidates } = useMemo(() => splitRelated(overview), [overview])
  const calloutRelated = withRoutes[0]
  const calloutEntries = routes.filter((entry) => entry.related.id === calloutRelated?.id)
  const resourceId = overview.opportunities[0]?.asset.id
  const firstAssessmentId = overview.opportunities[0]?.assessment_id

  const send = (command: RequestCommand) =>
    setRequest((current) => ({ ...command, nonce: (current?.nonce ?? 0) + 1 }))
  const trace = (routeKey: string) => send({ kind: 'trace', routeKey })
  const showOnMap = (nodeId: string) => send({ kind: 'select', nodeId })

  return (
    <>
      <DiseaseHeader overview={overview} />
      {calloutRelated && (
        <RouteCallout related={calloutRelated} entries={calloutEntries} sources={sources} onTrace={trace} />
      )}
      <AtlasGraph
        overview={overview}
        selectedAssessmentId={evidenceId ?? selectedAssessmentId}
        request={request}
        evidence={evidence}
        onGraphLoaded={(graph) => setSources(graph.sources)}
      />
      <ResearchLeads overview={overview} onExplore={showOnMap} hiddenSourceIds={evidenceState?.hidden} />
      <Opportunities overview={overview} onShowOnMap={showOnMap} onOpenEvidence={evidence.open} />
      <Organizations overview={overview} />
      <PossiblyRelated candidates={candidates} goalId={overview.goal_id} />
      <CoverageNotes overview={overview} />
      <JourneyBar
        canTrace={routes.length > 0}
        canShowResource={resourceId !== undefined}
        canOpenEvidence={firstAssessmentId !== undefined}
        onConnection={() => routes[0] && trace(routes[0].key)}
        onResource={() => resourceId && showOnMap(resourceId)}
        onEvidence={() => firstAssessmentId && evidence.open(evidenceId ?? firstAssessmentId)}
        canOpenBrief={evidenceState?.current != null}
        onBrief={evidence.openBrief}
      />
      {isBriefOpen && evidenceState && <BriefSheet evidence={evidenceState} onClose={closeBrief} />}
    </>
  )
}
