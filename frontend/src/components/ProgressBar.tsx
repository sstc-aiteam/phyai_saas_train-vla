import type { JobProgress } from '../api/types'

export function ProgressBar({ progress }: { progress: JobProgress }) {
  const pct = progress.total_steps > 0 ? Math.min(100, (progress.step / progress.total_steps) * 100) : 0
  return (
    <div>
      <div
        role="progressbar"
        aria-valuenow={progress.step}
        aria-valuemin={0}
        aria-valuemax={progress.total_steps}
        style={{
          height: 8,
          borderRadius: 4,
          background: 'var(--border)',
          overflow: 'hidden',
        }}
      >
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)' }} />
      </div>
      <small>
        step {progress.step} / {progress.total_steps} · loss {progress.loss.toFixed(4)}
      </small>
    </div>
  )
}
