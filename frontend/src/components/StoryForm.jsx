import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

const empty = { title: '', user_story: '', acceptance_criteria: [''], technical_breakdown: '', source: 'manual' }

export default function StoryForm({ onSubmit, disabled }) {
  const [story, setStory] = useState(empty)
  const set = (field, value) => setStory((current) => ({ ...current, [field]: value }))
  const setCriterion = (index, value) => set('acceptance_criteria', story.acceptance_criteria.map((item, i) => i === index ? value : item))
  const submit = (event) => {
    event.preventDefault()
    onSubmit({ ...story, acceptance_criteria: story.acceptance_criteria.filter((item) => item.trim()) })
  }
  return (
    <form className="input-card" onSubmit={submit}>
      <div className="section-heading"><div><span className="eyebrow">One story</span><h2>Describe the work</h2></div></div>
      <label>Title<input required value={story.title} onChange={(event) => set('title', event.target.value)} placeholder="What outcome are we delivering?" /></label>
      <label>User story<textarea required rows="3" value={story.user_story} onChange={(event) => set('user_story', event.target.value)} placeholder="As a..., I want..., so that..." /></label>
      <fieldset>
        <legend>Acceptance criteria</legend>
        <div className="criteria-list">
          {story.acceptance_criteria.map((criterion, index) => (
            <div className="criterion" key={index}>
              <span>{index + 1}</span>
              <input value={criterion} onChange={(event) => setCriterion(index, event.target.value)} placeholder="Observable condition of success" />
              <button type="button" className="icon-button" aria-label={`Remove criterion ${index + 1}`} disabled={story.acceptance_criteria.length === 1} onClick={() => set('acceptance_criteria', story.acceptance_criteria.filter((_, i) => i !== index))}><Trash2 size={16} /></button>
            </div>
          ))}
        </div>
        <button type="button" className="text-button" onClick={() => set('acceptance_criteria', [...story.acceptance_criteria, ''])}><Plus size={16} /> Add criterion</button>
      </fieldset>
      <label>Technical breakdown <span className="optional">Optional</span><textarea rows="2" value={story.technical_breakdown} onChange={(event) => set('technical_breakdown', event.target.value)} placeholder="Known services, components, migrations, or constraints" /></label>
      <button className="button primary" disabled={disabled}>Build justified estimate</button>
    </form>
  )
}
