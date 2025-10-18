<script lang="ts">
  /** Analyzer label coverage page showing catalog number completeness. */
  import { onMount } from 'svelte';
  import DetailPanel from '../lib/components/DetailPanel.svelte';

  interface LabelRow {
    label_id: number;
    label: string;
    total_tracks: number;
    catalog_tracks: number;
    missing_tracks: number;
  }

  interface MissingTrackRow {
    track_id: number;
    track: string;
    artist: string | null;
    album: string | null;
    catalog_id: string | null;
  }

  interface CatalogGapRow {
    catalog_id: string;
    prefix: string;
    number: number;
    sequence_start: string;
    sequence_end: string;
    sequence_expected: number;
    sequence_observed: number;
    sequence_coverage: number;
    release_title: string | null;
    release_artist: string | null;
    release_year: number | null;
    release_date: string | null;
    release_url: string | null;
  }

  const pageSize = 50;
  const missingPageSize = 25;

  let loading = false;
  let error: string | null = null;
  let rows: LabelRow[] = [];
  let total = 0;
  let page = 1;

  let activeLabel: LabelRow | null = null;
  let panelOpen = false;
  let panelTitle = '';
  let missingLoading = false;
  let missingError: string | null = null;
  let missingRows: MissingTrackRow[] = [];
  let missingTotal = 0;
  let missingPage = 1;
  let catalogGaps: CatalogGapRow[] = [];
  let catalogGapTotal = 0;

  async function loadData() {
    loading = true;
    error = null;
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize)
      });
      const response = await fetch(`/api/v1/library/labels?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Failed to load label statistics');
      }
      const data: { items: LabelRow[]; total: number } = await response.json();
      rows = data.items;
      total = data.total;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unknown error';
      rows = [];
      total = 0;
    } finally {
      loading = false;
    }
  }

  function changePage(newPage: number) {
    if (newPage < 1 || newPage > totalPages) {
      return;
    }
    page = newPage;
    loadData();
  }

  function coverage(row: LabelRow): number {
    if (row.total_tracks === 0) {
      return 0;
    }
    return row.catalog_tracks / row.total_tracks;
  }

  function coverageWidth(row: LabelRow): number {
    return Math.min(100, Math.round(coverage(row) * 100));
  }

  function formatPercentage(value: number): string {
    if (!Number.isFinite(value) || value <= 0) {
      return '0%';
    }
    if (value >= 1) {
      return '100%';
    }
    return `${Math.round(value * 1000) / 10}%`;
  }

  async function openMissing(row: LabelRow) {
    if (row.missing_tracks === 0) {
      return;
    }
    activeLabel = row;
    panelTitle = `${row.label} missing catalog IDs`;
    panelOpen = true;
    missingPage = 1;
    await loadMissing(true);
  }

  async function loadMissing(resetRows = false) {
    if (!activeLabel) {
      return;
    }
    missingLoading = true;
    missingError = null;
    if (resetRows) {
      missingRows = [];
      missingTotal = 0;
      catalogGaps = [];
      catalogGapTotal = 0;
    }
    try {
      const params = new URLSearchParams({
        page: String(missingPage),
        page_size: String(missingPageSize)
      });
      const response = await fetch(
        `/api/v1/library/labels/${activeLabel.label_id}/missing-catalog?${params.toString()}`
      );
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Label not found');
        }
        throw new Error('Failed to load missing catalog numbers');
      }
      const data: { items: MissingTrackRow[]; total: number; label: string } = await response.json();
      missingRows = data.items;
      missingTotal = data.total;
      catalogGaps = data.catalog_gaps?.items ?? [];
      catalogGapTotal = data.catalog_gaps?.total ?? catalogGaps.length;
      panelTitle = `${data.label} missing catalog IDs`;
    } catch (err) {
      missingError = err instanceof Error ? err.message : 'Unknown error';
      missingRows = [];
      missingTotal = 0;
    } finally {
      missingLoading = false;
    }
  }

  function changeMissingPage(newPage: number) {
    if (newPage < 1 || newPage > missingTotalPages) {
      return;
    }
    missingPage = newPage;
    loadMissing();
  }

  function closePanel() {
    panelOpen = false;
    activeLabel = null;
    missingRows = [];
    missingError = null;
    missingTotal = 0;
    catalogGaps = [];
    catalogGapTotal = 0;
  }

  $: totalPages = Math.max(1, Math.ceil(total / pageSize));
  $: showingStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  $: showingEnd = total === 0 ? 0 : Math.min(total, page * pageSize);
  $: missingTotalPages = Math.max(1, Math.ceil(missingTotal / missingPageSize));
  $: missingShowingStart = missingTotal === 0 ? 0 : (missingPage - 1) * missingPageSize + 1;
  $: missingShowingEnd = missingTotal === 0 ? 0 : Math.min(missingTotal, missingPage * missingPageSize);
  

  onMount(() => {
    loadData();
  });
</script>

<section class="page">
  <header>
    <h2>Label catalog coverage</h2>
    <p>See how many tracks per label include catalog identifiers.</p>
  </header>

  {#if loading}
    <p class="status">Loading…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else}
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Label</th>
            <th>Catalog IDs</th>
            <th>Missing</th>
            <th>Coverage</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#if rows.length === 0}
            <tr>
              <td colspan="5" class="empty">No labels found.</td>
            </tr>
          {:else}
            {#each rows as row}
              <tr>
                <td>{row.label}</td>
                <td class="numeric">
                  {row.catalog_tracks.toLocaleString()} / {row.total_tracks.toLocaleString()}
                </td>
                <td class="numeric">{row.missing_tracks.toLocaleString()}</td>
                <td>
                    <div class="coverage">
                      <div class="bar">
                        <span class="fill" style={`width: ${coverageWidth(row)}%`} />
                      </div>
                      <span class="value">{formatPercentage(coverage(row))}</span>
                    </div>
                </td>
                <td class="actions">
                  <button type="button" disabled={row.missing_tracks === 0} on:click={() => openMissing(row)}>
                    View missing
                  </button>
                </td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
      <footer class="pagination">
        {#if total === 0}
          <span>No label data available yet.</span>
        {:else}
          <span>Showing {showingStart}–{showingEnd} of {total}</span>
        {/if}
        <div class="controls">
          <button type="button" on:click={() => changePage(page - 1)} disabled={page === 1}>
            Previous
          </button>
          <span>Page {page} / {totalPages}</span>
          <button type="button" on:click={() => changePage(page + 1)} disabled={page === totalPages}>
            Next
          </button>
        </div>
      </footer>
    </div>
  {/if}

  <DetailPanel
    title={panelTitle}
    open={panelOpen}
    loading={missingLoading}
    error={missingError}
    on:close={closePanel}
  >
    <div class="panel-content">
      <section class="catalog-gap-section">
        <h3>Missing catalog IDs</h3>
        {#if catalogGapTotal === 0}
          <p class="status muted">No sequential catalog gaps detected for this label.</p>
        {:else}
          <table class="gap-table">
            <thead>
              <tr>
                <th>Catalog ID</th>
                <th>Artist</th>
                <th>Release</th>
                <th>Sequence</th>
                <th>Coverage</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              {#each catalogGaps as gap}
                <tr>
                  <td>{gap.catalog_id}</td>
                  <td>{gap.release_artist ?? '—'}</td>
                  <td>
                    {#if gap.release_title}
                      <span class="release-title">{gap.release_title}</span>
                      {#if gap.release_year}
                        <span class="release-meta">{gap.release_year}</span>
                      {/if}
                    {:else}
                      <span class="muted">Unknown release</span>
                    {/if}
                  </td>
                  <td>
                    <span class="sequence-range">{gap.sequence_start} – {gap.sequence_end}</span>
                    <span class="sequence-meta">{gap.sequence_observed}/{gap.sequence_expected} present</span>
                  </td>
                  <td>{formatPercentage(gap.sequence_coverage)}</td>
                  <td>
                    {#if gap.release_url}
                      <a href={gap.release_url} target="_blank" rel="noreferrer">Discogs</a>
                    {:else}
                      <span class="muted">—</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>

      <section class="missing-tracks-section">
        <h3>Tracks missing catalog IDs</h3>
        {#if missingTotal === 0}
          <p>All tracks for this label include catalog identifiers. 🎉</p>
        {:else}
          <table class="missing-table">
            <thead>
              <tr>
                <th>Track</th>
                <th>Artist</th>
                <th>Album</th>
                <th>Catalog ID</th>
              </tr>
            </thead>
            <tbody>
              {#if missingRows.length === 0}
                <tr>
                  <td colspan="4" class="empty">No tracks found for this page.</td>
                </tr>
              {:else}
                {#each missingRows as track}
                  <tr>
                    <td>{track.track}</td>
                    <td>{track.artist ?? '—'}</td>
                    <td>{track.album ?? '—'}</td>
                    <td>{track.catalog_id ?? '—'}</td>
                  </tr>
                {/each}
              {/if}
            </tbody>
          </table>
          <footer class="pagination">
            <span>Showing {missingShowingStart}–{missingShowingEnd} of {missingTotal}</span>
            <div class="controls">
              <button
                type="button"
                on:click={() => changeMissingPage(missingPage - 1)}
                disabled={missingPage === 1}
              >
                Previous
              </button>
              <span>Page {missingPage} / {missingTotalPages}</span>
              <button
                type="button"
                on:click={() => changeMissingPage(missingPage + 1)}
                disabled={missingPage === missingTotalPages}
              >
                Next
              </button>
            </div>
          </footer>
        {/if}
      </section>
    </div>
  </DetailPanel>
</section>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  header h2 {
    margin: 0;
    font-size: 1.75rem;
  }

  header p {
    margin: 0.25rem 0 0;
    color: rgba(255, 255, 255, 0.75);
  }

  .status {
    color: rgba(255, 255, 255, 0.8);
  }

  .status.error {
    color: #ff9090;
  }

  .table-wrapper {
    background: rgba(255, 255, 255, 0.04);
    border-radius: 1rem;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.75rem 1rem;
    text-align: left;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  thead {
    background: rgba(255, 255, 255, 0.05);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
  }

  tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.03);
  }

  tbody tr:hover {
    background: rgba(255, 255, 255, 0.05);
  }

  .numeric {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .empty {
    text-align: center;
    padding: 2rem 1rem;
    color: rgba(255, 255, 255, 0.65);
  }

  .coverage {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .coverage .bar {
    flex: 1;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 999px;
    overflow: hidden;
    height: 0.5rem;
  }

  .coverage .fill {
    display: block;
    height: 100%;
    background: var(--accent-color);
    transition: width 0.3s ease;
  }

  .coverage .value {
    min-width: 3.5rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .actions {
    text-align: right;
  }

  button {
    background: rgba(255, 255, 255, 0.1);
    border: none;
    border-radius: 999px;
    padding: 0.4rem 1rem;
    color: var(--text-color);
    cursor: pointer;
    transition: background 0.2s ease;
  }

  button:hover:enabled {
    background: rgba(255, 255, 255, 0.2);
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .pagination {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
    color: rgba(255, 255, 255, 0.75);
  }

  .pagination .controls {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .panel-content {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .panel-content p {
    margin: 0;
  }

  .catalog-gap-section,
  .missing-tracks-section {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .catalog-gap-section h3,
  .missing-tracks-section h3 {
    margin: 0;
  }

  .gap-table {
    width: 100%;
    border-collapse: collapse;
  }

  .gap-table th,
  .gap-table td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .gap-table tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.03);
  }

  .release-title {
    display: block;
    font-weight: 600;
  }

  .release-meta {
    display: block;
    font-size: 0.8rem;
    color: rgba(255, 255, 255, 0.6);
    margin-top: 0.2rem;
  }

  .sequence-range {
    display: block;
    font-weight: 600;
  }

  .sequence-meta {
    display: block;
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.6);
    margin-top: 0.15rem;
  }

  .muted {
    color: rgba(255, 255, 255, 0.6);
  }

  .missing-table {
    width: 100%;
    border-collapse: collapse;
  }

  .missing-table th,
  .missing-table td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .missing-table tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.03);
  }
</style>
