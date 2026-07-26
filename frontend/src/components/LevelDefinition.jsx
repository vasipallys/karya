export default function LevelDefinition({ definition }) {
  if (!definition) return null
  return <section className={`level-definition level-${definition.level}`} aria-label={`${definition.level} ${definition.focus} definition`}>
    <div className="level-definition-title">
      <span>{definition.level}</span>
      <div><strong>{definition.focus}</strong><small>{definition.artifact}</small></div>
    </div>
    <div className="level-definition-outcomes" aria-label="Required outcomes">
      {definition.outcomes.map((outcome) => <span key={outcome}>{outcome}</span>)}
    </div>
  </section>
}
