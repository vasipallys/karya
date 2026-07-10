export default function StatusBadge({ status = 'unknown', children }) {
  const tone = ['ok', 'configured', 'completed'].includes(status) ? 'good' : status === 'running' ? 'busy' : 'bad'
  return <span className={`status-badge ${tone}`}><span aria-hidden="true" />{children || status}</span>
}
