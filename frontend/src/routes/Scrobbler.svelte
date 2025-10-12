<script lang="ts">
  /** Scrobbler dashboard for inspecting listening history and running imports. */
  import { onDestroy, onMount } from 'svelte';
  import Albums from './Albums.svelte';
  import Artists from './Artists.svelte';
  import Genres from './Genres.svelte';
  import Home from './Home.svelte';

  type Tab = 'listens' | 'artists' | 'albums' | 'genres';

  type JobMeta = {
    status?: string;
    processed?: number;
    imported?: number;
    skipped?: number;
    pages?: number;
    registered?: number;
    current_path?: string | null;
    current_track?: { title?: string | null; artist?: string | null } | null;
    cancel_requested?: boolean;
    error?: string;
    result?: Record<string, unknown> | null;
  };

  type JobStatus = {
    job_id: string;
    status: string;
    state: string;
    queued_at: string | null;
    started_at: string | null;
    ended_at: string | null;
    meta: JobMeta;
    result?: Record<string, unknown> | null;
  };

  const tabOrder: { id: Tab; label: string }[] = [
    { id: 'listens', label: 'Listens' },
    { id: 'artists', label: 'Artists' },
    { id: 'albums', label: 'Albums' },
    { id: 'genres', label: 'Genres' }
  ];

  let tab: Tab = 'listens';
  let loadingConfig = false;
  let config: Record<string, string> = {};
  let importJob: JobStatus | null = null;
  let startingImport = false;
  let stoppingImport = false;
  let importError: string | null = null;
  let statusTimer: ReturnType<typeof setInterval> | null = null;
  let refreshTimer: ReturnType<typeof setInterval> | null = null;
  let wasImportActive = false;
  let refreshSignal = 0;

  async function loadConfig() {
    loadingConfig = true;
    try {
      const response = await fetch('/api/v1/config');
      if (!response.ok) {
        throw new Error('Failed to load configuration');
      }
      const data = await response.json();
      config = data.values ?? {};
    } catch (error) {
      console.error(error);
    } finally {
      loadingConfig = false;
    }
  }

  function buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const auth = buildAuthHeaders();
    return { ...headers, ...auth };
  }

  function buildAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};
    if (config.api_key) {
      headers['X-Api-Key'] = config.api_key;
    }
    return headers;
  }

  function buildPayload(): Record<string, string> {
    const payload: Record<string, string> = {};
    if (config.listenbrainz_user) {
      payload.user = config.listenbrainz_user;
    }
    if (config.listenbrainz_token) {
      payload.token = config.listenbrainz_token;
    }
    return payload;
  }

  async function startImport() {
    if (startingImport || isImportActive(importJob)) {
      return;
    }
    startingImport = true;
    try {
      const response = await fetch('/api/v1/import/listenbrainz', {
        method: 'POST',
        headers: buildHeaders(),
        body: JSON.stringify(buildPayload())
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || response.statusText);
      }
      const data = await response.json();
      importJob = {
        job_id: data.job_id,
        status: data.status ?? 'queued',
        state: data.status ?? 'queued',
        queued_at: new Date().toISOString(),
        started_at: null,
        ended_at: null,
        meta: { status: data.status ?? 'queued' },
        result: null
      };
      importError = null;
      updateImportTimers();
      await loadImportStatus(data.job_id);
    } catch (error) {
      importError = error instanceof Error ? error.message : 'Import failed';
    } finally {
      startingImport = false;
    }
  }

  async function stopImport() {
    if (!importJob || stoppingImport) {
      return;
    }
    stoppingImport = true;
    try {
      const params = new URLSearchParams();
      if (importJob.job_id) {
        params.set('job_id', importJob.job_id);
      }
      const query = params.toString();
      const response = await fetch(`/api/v1/import/listenbrainz/stop${query ? `?${query}` : ''}`, {
        method: 'POST',
        headers: buildAuthHeaders()
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || response.statusText);
      }
      const data = await response.json();
      assignImportJob(data.job ?? null);
    } catch (error) {
      importError = error instanceof Error ? error.message : 'Failed to stop import';
    } finally {
      stoppingImport = false;
    }
  }

  async function loadImportStatus(explicitJobId?: string) {
    try {
      const params = new URLSearchParams();
      const jobId = explicitJobId ?? importJob?.job_id;
      if (jobId) {
        params.set('job_id', jobId);
      }
      const response = await fetch(
        `/api/v1/import/listenbrainz/status${params.toString() ? `?${params.toString()}` : ''}`,
        { headers: buildAuthHeaders() }
      );
      if (!response.ok) {
        throw new Error('Failed to fetch import status');
      }
      const payload = await response.json();
      assignImportJob((payload.job as JobStatus) ?? null);
      importError = null;
    } catch (error) {
      importError = error instanceof Error ? error.message : 'Failed to fetch import status';
    }
  }

  function isImportActive(job: JobStatus | null): boolean {
    if (!job) {
      return false;
    }
    const status = (job.meta?.status ?? job.status ?? job.state ?? '').toLowerCase();
    return ['queued', 'running', 'started', 'cancelling'].includes(status);
  }

  function assignImportJob(job: JobStatus | null) {
    importJob = job;
    updateImportTimers();
  }

  function updateImportTimers() {
    const active = isImportActive(importJob);
    if (active) {
      if (!statusTimer) {
        statusTimer = setInterval(() => {
          loadImportStatus().catch((error) => console.error(error));
        }, 5000);
      }
      if (!refreshTimer) {
        refreshTimer = setInterval(() => {
          refreshSignal += 1;
        }, 15000);
      }
    } else {
      if (statusTimer) {
        clearInterval(statusTimer);
        statusTimer = null;
      }
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
      if (wasImportActive) {
        refreshSignal += 1;
      }
    }
    wasImportActive = active;
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

  function formatTrack(meta: JobMeta): string {
    const track = meta.current_track;
    if (!track) {
      return '—';
    }
    const artist = track.artist?.trim();
    const title = track.title?.trim();
    if (artist && title) {
      return `${artist} — ${title}`;
    }
    return title || artist || '—';
  }

  function importStatusLabel(job: JobStatus | null): string {
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

  function statusClass(job: JobStatus | null): string {
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

  onMount(() => {
    loadConfig();
    loadImportStatus();
  });

  onDestroy(() => {
    if (statusTimer) {
      clearInterval(statusTimer);
    }
    if (refreshTimer) {
      clearInterval(refreshTimer);
    }
  });
</script>

<section class="scrobbler">
  <header class="page-header">
    <div class="heading">
      <h1>Scrobbler</h1>
      <p>Explore your listening history and queue new ListenBrainz imports.</p>
    </div>
    <div class="actions">
      <button on:click={startImport} disabled={startingImport || loadingConfig || isImportActive(importJob)}>
        {startingImport
          ? 'Starting…'
          : isImportActive(importJob)
            ? 'Import running'
            : 'Start ListenBrainz import'}
      </button>
      {#if isImportActive(importJob)}
        <button class="secondary" on:click={stopImport} disabled={stoppingImport}>
          {stoppingImport ? 'Stopping…' : 'Stop import'}
        </button>
      {/if}
      {#if startingImport || isImportActive(importJob)}
        <div class="progress" role="status" aria-live="polite">
          <span class="visually-hidden">Import in progress…</span>
        </div>
      {/if}
    </div>
    <section class="job-status" aria-live="polite">
      <header class="job-status__header">
        <span class="job-status__title">ListenBrainz import</span>
        <span class={`badge ${statusClass(importJob)}`}>{importStatusLabel(importJob)}</span>
      </header>
      {#if importJob}
        <dl class="job-metrics">
          <div>
            <dt>Processed</dt>
            <dd>{formatCount(importJob.meta?.processed ?? (importJob.result?.processed as number | undefined))}</dd>
          </div>
          <div>
            <dt>Imported</dt>
            <dd>{formatCount(importJob.meta?.imported ?? (importJob.result?.imported as number | undefined))}</dd>
          </div>
          <div>
            <dt>Skipped</dt>
            <dd>{formatCount(importJob.meta?.skipped ?? (importJob.result?.skipped as number | undefined))}</dd>
          </div>
          <div>
            <dt>Pages</dt>
            <dd>{formatCount(importJob.meta?.pages ?? (importJob.result?.pages as number | undefined))}</dd>
          </div>
        </dl>
        <p class="job-detail"><strong>Current track:</strong> {formatTrack(importJob.meta)}</p>
        <p class="job-detail">
          <strong>Updated:</strong> {formatTimestamp(importJob.ended_at ?? importJob.started_at ?? importJob.queued_at)}
        </p>
        {#if importJob.meta?.error}
          <p class="status error">Error: {importJob.meta.error}</p>
        {/if}
      {:else}
        <p class="job-detail">No import running.</p>
      {/if}
      {#if importError}
        <p class="status error">{importError}</p>
      {/if}
    </section>
  </header>

  <nav class="tabs" aria-label="Scrobbler sections">
    {#each tabOrder as item}
      <button
        type="button"
        class:active={tab === item.id}
        on:click={() => (tab = item.id)}
      >
        {item.label}
      </button>
    {/each}
  </nav>

  <div class="content">
    {#if tab === 'listens'}
      <Home {refreshSignal} />
    {:else if tab === 'artists'}
      <Artists
        title="Top artists by listens"
        description="See which artists dominate your listening history."
        {refreshSignal}
      />
    {:else if tab === 'albums'}
      <Albums
        title="Top albums by listens"
        description="Your most played records across different periods."
        {refreshSignal}
      />
    {:else}
      <Genres
        title="Top genres by listens"
        description="Discover which genres you gravitate towards over time."
        {refreshSignal}
      />
    {/if}
  </div>
</section>

<style>
  .scrobbler {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
  }

  .page-header {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    align-items: center;
    text-align: center;
  }

  .heading h1 {
    font-size: clamp(2rem, 4vw, 2.75rem);
    margin: 0;
  }

  .heading p {
    margin: 0;
    max-width: 48ch;
    color: rgba(255, 255, 255, 0.75);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 1rem;
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

  .actions .secondary {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.5);
    color: rgba(255, 255, 255, 0.9);
  }

  .actions button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .job-status {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 1rem 1.5rem;
    width: min(680px, 100%);
    margin: 0 auto;
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
    text-transform: uppercase;
    letter-spacing: 0.08em;
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
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
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
    margin: 0;
    font-size: 0.95rem;
  }

  .status.success {
    color: #4caf50;
  }

  .status.error {
    color: #ff5252;
  }

  .tabs {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    justify-content: center;
  }

  .tabs button {
    background: rgba(255, 255, 255, 0.05);
    border: none;
    color: var(--text-color);
    padding: 0.5rem 1.25rem;
    border-radius: 999px;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .tabs button.active {
    background: var(--accent-color);
    color: white;
  }

  .content {
    min-height: 320px;
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
</style>
