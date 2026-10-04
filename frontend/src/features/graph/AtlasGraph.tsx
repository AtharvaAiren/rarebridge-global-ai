import { useEffect, useRef, useState } from 'react'
import { useApiClient } from '../../api/ApiContext.tsx'
import { GRAPH_NODES_DEFAULT, GRAPH_NODES_MORE } from '../../api/requests.ts'
import type { GraphResponse, OverviewResponse } from '../../api/types.ts'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { useApiResource } from '../../hooks/useApiResource.ts'
import { EvidencePanel } from '../evidence/EvidencePanel.tsx'
import { AtlasView } from './AtlasView.tsx'
import type { EvidenceControls } from '../evidence/useAssessment.ts'
import type { AtlasRequest } from './types.ts'
import { selectedGraphAssessment } from './binding.ts'

type AtlasGraphProps = {
  overview: OverviewResponse
  request: AtlasRequest | null
  /** Retains the resource chosen elsewhere when its evidence panel closes. */
  selectedAssessmentId?: string
  /** Lets the page show source titles from the same response. */
  onGraphLoaded?: (graph: GraphResponse) => void
  evidence: EvidenceControls
}

/**
 * Loads the graph for the disease and the selected scoped assessment. A failed
 * "show more" keeps the earlier real response on screen and says so; it
 * never substitutes other data.
 */
export function AtlasGraph({ overview, request, selectedAssessmentId, onGraphLoaded, evidence }: AtlasGraphProps) {
  const client = useApiClient()
  const diseaseId = overview.disease.id
  const assessmentId = selectedGraphAssessment(overview, evidence.state?.assessmentId, selectedAssessmentId)
  const [maxNodes, setMaxNodes] = useState(GRAPH_NODES_DEFAULT)
  const { state, lastData: snapshot, retry } = useApiResource(
    `graph:${diseaseId}:${assessmentId ?? ''}:${maxNodes}`,
    async (signal) => ({ graph: await client.graph({ diseaseId, assessmentId, maxNodes }, signal), diseaseId, assessmentId }),
  )
  const shown = snapshot?.graph ?? null
  const isPreviousContext = snapshot !== null &&
    (snapshot.diseaseId !== diseaseId || snapshot.assessmentId !== assessmentId)
  const onLoadedRef = useRef(onGraphLoaded)
  useEffect(() => {
    onLoadedRef.current = onGraphLoaded
  })

  useEffect(() => {
    if (shown) onLoadedRef.current?.(shown)
  }, [shown])

  if (!shown) {
    const mapState =
      state.status === 'error' ? (
        <ErrorState error={state.error} onRetry={retry} />
      ) : (
        <LoadingState label="Loading the research map…" />
      )
    // The evidence view never depends on the map: it still opens without one.
    return (
      <section className="atlas page-section" aria-labelledby="atlas-title">
        <h2 id="atlas-title" className="section-title">
          Research map
        </h2>
        {evidence.state ? (
          <div className="atlas__stage">
            <div>{mapState}</div>
            <div className="atlas__side">
              <div className="side-tabs">
                <span className="side-tab" aria-current="true">
                  Evidence
                </span>
                <button type="button" className="rb-btn rb-btn--quiet side-tabs__close" onClick={evidence.close}>
                  Close evidence
                </button>
              </div>
              <section className="inspector inspector--evidence" aria-label="Evidence">
                <EvidencePanel evidence={evidence.state} onPrepareBrief={evidence.openBrief} />
              </section>
            </div>
          </div>
        ) : (
          mapState
        )}
      </section>
    )
  }

  const expansionNotice =
    state.status === 'error' ? (
      <div className="atlas__notice">
        <ErrorState error={state.error} onRetry={retry} />
        <button type="button" className="rb-btn rb-btn--quiet" onClick={() => setMaxNodes(GRAPH_NODES_DEFAULT)}>
          Keep the smaller map
        </button>
        <p className="rb-meta">
          The map below is the earlier {shown.nodes.length}-item response
          {isPreviousContext ? ' for the previous research resource' : ''}.
        </p>
      </div>
    ) : isPreviousContext ? (
      <p className="atlas__notice rb-meta" role="status">
        Updating the map for your selected resource. The previous map remains visible while it loads.
      </p>
    ) : null

  return (
    <AtlasView
      overview={overview}
      graph={shown}
      assessmentId={snapshot?.assessmentId}
      request={request}
      canShowMore={shown.coverage.truncated && maxNodes < GRAPH_NODES_MORE}
      isLoadingMore={state.status === 'loading'}
      expansionNotice={expansionNotice}
      onShowMore={() => setMaxNodes(GRAPH_NODES_MORE)}
      evidence={evidence}
    />
  )
}
