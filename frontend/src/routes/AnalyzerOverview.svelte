<script lang="ts">
  /** Analyzer overview card summarising scan status and top-level metrics. */
  import { onDestroy, onMount } from 'svelte';
  import KpiCard from '../lib/components/KpiCard.svelte';

  type ArtistSummary = { artist: string; songs: number };
  type GenreSummary = { genre: string; songs: number };
  type AnalyzerSummary = {
    files: number;
    songs: number;
    livesets: number;
    artists: ArtistSummary[];
    genres: GenreSummary[];
  };

  type JobMeta = {
    status?: string;
    processed?: number;
    registered?: number;
    current_path?: string | null;
    error?: string;
  };

  type JobStatus = {
    job_id: string;
    status: string;
    state: string;
    queued_at: string | null;
    started_at: string | null;
    ended_at: string | null;
    meta: JobMeta;
  };

  let summary: AnalyzerSummary = {
    files: 0,
    songs: 0,
    livesets: 0,
    artists: [],
    genres: []
  };
  let loading = true;
  let scanMessage: string | null = null;
  let error: string | null = null;
  let scanError: string | null = null;
  let scanJob: JobStatus | null = null;
  let queuingScan = false;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let wasActive = false;

  async function loadSummary() {
    loading = true;
    error = null;
    try {
      const response = await fetch('/api/v1/analyzer/summary');
      if (!response.ok) {
        throw new Error('Failed to load analyzer summary');
      }
      summary = (await response.json()) as AnalyzerSummary;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unexpected error while loading data';
    } finally {
      loading = false;
    }
  }

  async function startScan() {
    if (queuingScan || isScanActive(scanJob)) {
      return;
    }
    queuingScan = true;
    scanMessage = null;
    error = null;
    scanError = null;
    try {
      const response = await fetch('/api/v1/analyzer/library/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (!response.ok) {
        const details = await response.json().catch(() => ({}));
        throw new Error(details.detail ?? 'Failed to queue analyzer scan');
      }
      const payload = await response.json();
      scanJob = {
        job_id: payload.job_id,
        status: payload.status ?? 'queued',
        state: payload.status ?? 'queued',
        queued_at: new Date().toISOString(),
        started_at: null,
        ended_at: null,
        meta: { status: payload.status ?? 'queued' }
      };
      scanMessage = `Library scan queued (job ${payload.job_id})`;
      updatePolling();
      await loadScanStatus(payload.job_id);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unexpected error while starting scan';
    } finally {
      queuingScan = false;
    }
  }

  async function stopScan() {
    if (!scanJob) {
      return;
    }
    try {
      const params = new URLSearchParams();
      params.set('job_id', scanJob.job_id);
      const response = await fetch(`/api/v1/analyzer/library/scan/stop?${params.toString()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (!response.ok) {
        const details = await response.json().catch(() => ({}));
        throw new Error(details.detail ?? 'Failed to stop analyzer scan');
      }
      const payload = await response.json();
      scanJob = (payload.job as JobStatus) ?? null;
      updatePolling();
    } catch (err) {
      scanError = err instanceof Error ? err.message : 'Unexpected error while stopping scan';
    }
  }

  async function loadScanStatus(explicitJobId?: string) {
    try {
      const params = new URLSearchParams();
      const jobId = explicitJobId ?? scanJob?.job_id;
      if (jobId) {
        params.set('job_id', jobId);
      }
      const response = await fetch(
        `/api/v1/analyzer/library/scan/status${params.toString() ? `?${params.toString()}` : ''}`
      );
      if (!response.ok) {
        throw new Error('Failed to fetch scan status');
      }
      const payload = await response.json();
      scanJob = (payload.job as JobStatus) ?? null;
      updatePolling();
      if (!isScanActive(scanJob) && wasActive) {
        await loadSummary();
      }
      scanError = null;
    } catch (err) {
      scanError = err instanceof Error ? err.message : 'Failed to fetch scan status';
    }
  }

  function isScanActive(job: JobStatus | null): boolean {
    if (!job) {
      return false;
    }
    const status = (job.meta?.status ?? job.status ?? job.state ?? '').toLowerCase();
    return ['queued', 'running', 'started', 'cancelling'].includes(status);
  }

  function updatePolling() {
    const active = isScanActive(scanJob);
    if (active) {
      if (!pollTimer) {
        pollTimer = setInterval(() => {
          loadScanStatus().catch((err) => console.error(err));
        }, 5000);
      }
    } else if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    wasActive = active;
  }

  function scanStatusLabel(job: JobStatus | null): string {
    if (!job) {
      return 'Idle';
    }
    const status = (job.meta?.status ?? job.status ?? job.state ?? '').toLowerCase();
    if (status === 'finished') {
      return 'Finished';
    }
    if (status === 'cancelled') {
      return 'Cancelled';
    }
    if (status === 'failed') {
      return 'Failed';
    }
    if (status === 'cancelling') {
      return 'Stopping…';
    }
    if (status === 'queued') {
      return 'Queued';
    }
    return 'Running';
  }

  function scanStatusClass(job: JobStatus | null): string {
    if (!job) {
      return 'idle';
    }
    const status = (job.meta?.status ?? job.status ?? job.state ?? '').toLowerCase();
    if (status === 'finished') {
      return 'finished';
    }
    if (status === 'cancelled') {
      return 'cancelled';
    }
    if (status === 'failed') {
      return 'failed';
    }
    if (status === 'queued') {
      return 'queued';
    }
    if (status === 'cancelling') {
      return 'stopping';
    }
    return 'running';
  }

  function formatPath(path: string | null | undefined): string {
    return path ? path : '—';
  }

  function formatCount(value: number | undefined): string {
    return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—';
  }

  function formatTimestamp(value: string | null | undefined): string {
    if (!value) {
      return '—';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'medium'
    }).format(date);
  }

  onMount(() => {
    loadSummary();
    loadScanStatus();
  });

  onDestroy(() => {
    if (pollTimer) {
      clearInterval(pollTimer);
    }
  });
</script>

<section class="overview">
  <div class="actions">
    <button on:click={startScan} disabled={queuingScan || isScanActive(scanJob)}>
      {queuingScan ? 'Queuing…' : isScanActive(scanJob) ? 'Scan running' : 'Start analyzer scan'}
    </button>
    {#if isScanActive(scanJob)}
      <button class="secondary" on:click={stopScan}>Stop scan</button>
    {/if}
    {#if queuingScan || isScanActive(scanJob)}
      <div class="progress" role="status" aria-live="polite">
        <span class="visually-hidden">Analyzer scan active…</span>
      </div>
    {/if}
    {#if scanMessage}
      <span class="status success">{scanMessage}</span>
    {/if}
    {#if error}
      <span class="status error">{error}</span>
    {/if}
    {#if scanError}
      <span class="status error">{scanError}</span>
    {/if}
  </div>

  <section class="job-status" aria-live="polite">
    <header class="job-status__header">
      <span class="job-status__title">Analyzer scan</span>
      <span class={`badge ${scanStatusClass(scanJob)}`}>{scanStatusLabel(scanJob)}</span>
    </header>
    {#if scanJob}
      <dl class="job-metrics">
        <div>
          <dt>Files processed</dt>
          <dd>{formatCount(scanJob.meta?.processed)}</dd>
        </div>
        <div>
          <dt>Registered</dt>
          <dd>{formatCount(scanJob.meta?.registered)}</dd>
        </div>
      </dl>
      <p class="job-detail"><strong>Current path:</strong> {formatPath(scanJob.meta?.current_path)}</p>
      <p class="job-detail">
        <strong>Updated:</strong> {formatTimestamp(scanJob.ended_at ?? scanJob.started_at ?? scanJob.queued_at)}
      </p>
      {#if scanJob.meta?.error}
        <p class="status error">Error: {scanJob.meta.error}</p>
      {/if}
    {:else}
      <p class="job-detail">No analyzer scan running.</p>
    {/if}
  </section>

  {#if loading}
    <p class="status">Loading analyzer data…</p>
  {:else}
    <div class="kpi-grid">
      <KpiCard label="Media files" value={summary.files.toLocaleString()} />
      <KpiCard label="Songs (&lt; 10 min)" value={summary.songs.toLocaleString()} />
      <KpiCard label="Livesets (≥ 10 min)" value={summary.livesets.toLocaleString()} />
    </div>

    <div class="table-wrapper">
      <h2>Artists with songs</h2>
      {#if summary.artists.length}
        <table>
          <thead>
            <tr>
              <th>Artist</th>
              <th>Songs</th>
            </tr>
          </thead>
          <tbody>
            {#each summary.artists as artist}
              <tr>
                <td>{artist.artist}</td>
                <td>{artist.songs.toLocaleString()}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="empty">No songs recorded yet.</p>
      {/if}
    </div>

    <div class="table-wrapper">
      <h2>Genres with songs</h2>
      {#if summary.genres.length}
        <table>
          <thead>
            <tr>
              <th>Genre</th>
              <th>Songs</th>
            </tr>
          </thead>
          <tbody>
            {#each summary.genres as genre}
              <tr>
                <td>{genre.genre}</td>
                <td>{genre.songs.toLocaleString()}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="empty">No genres recorded yet.</p>
      {/if}
    </div>
  {/if}
</section>

<style>
  .overview {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    align-items: center;
  }

  .actions {
    display: flex;
    gap: 1rem;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
  }

  .actions button {
    background: var(--accent-color);
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 999px;
    cursor: pointer;
    transition: opacity 0.2s ease;
  }

  .actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .actions .secondary {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.6);
    color: rgba(255, 255, 255, 0.85);
  }

  .job-status {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 1rem 1.5rem;
    width: min(640px, 100%);
  }

  .job-status__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .job-status__title {
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-size: 0.85rem;
    opacity: 0.8;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background: rgba(255, 255, 255, 0.25);
    color: #1a202c;
  }

  .badge.running {
    background: var(--accent-color);
    color: #fff;
  }

  .badge.finished {
    background: #38b2ac;
    color: #fff;
  }

  .badge.cancelled {
    background: #718096;
    color: #fff;
  }

  .badge.failed {
    background: #e53e3e;
    color: #fff;
  }

  .badge.queued {
    background: #d69e2e;
    color: #1a202c;
  }

  .badge.stopping {
    background: #ed8936;
    color: #1a202c;
  }

  .badge.idle {
    background: rgba(255, 255, 255, 0.25);
    color: #1a202c;
  }

  .job-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.75rem;
    margin: 0;
    padding: 0;
  }

  .job-metrics div {
    background: rgba(255, 255, 255, 0.06);
    padding: 0.75rem;
    border-radius: 12px;
  }

  .job-metrics dt {
    margin: 0;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    opacity: 0.7;
  }

  .job-metrics dd {
    margin: 0.25rem 0 0;
    font-size: 1.25rem;
    font-weight: 600;
  }

  .job-detail {
    margin: 0;
    color: rgba(255, 255, 255, 0.85);
  }

  .progress {
    position: relative;
    width: 160px;
    height: 6px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.15);
    overflow: hidden;
  }

  .progress::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.85), rgba(255, 255, 255, 0));
    animation: progress-slide 1.4s infinite;
  }

  @keyframes progress-slide {
    0% {
      transform: translateX(-100%);
    }
    50% {
      transform: translateX(0%);
    }
    100% {
      transform: translateX(100%);
    }
  }

  .status {
    font-size: 0.9rem;
  }

  .status.success {
    color: #4caf50;
  }

  .status.error {
    color: #f44336;
  }

  .kpi-grid {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    justify-content: center;
  }

  .table-wrapper {
    width: min(960px, 100%);
    background: rgba(0, 0, 0, 0.15);
    border-radius: 1rem;
    padding: 1rem;
    overflow-x: auto;
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.75rem 1rem;
    text-align: left;
  }

  thead {
    background: rgba(255, 255, 255, 0.05);
  }

  tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.03);
  }

  .empty {
    text-align: center;
    margin: 0.5rem 0 0;
    opacity: 0.7;
  }
</style>
