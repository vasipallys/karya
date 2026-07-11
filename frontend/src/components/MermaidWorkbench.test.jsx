import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import MermaidWorkbench from './MermaidWorkbench'

vi.mock('../api/client', () => ({ api: { assistProjectDiagram: vi.fn() } }))
vi.mock('./MermaidView', () => ({
  default: ({ source, onError, onSvg }) => <button onClick={() => { onError?.(null); onSvg?.('<svg />') }}>{source}</button>,
}))

afterEach(cleanup)

describe('MermaidWorkbench', () => {
  it('provides consistent edit, split, preview, studio and save controls', () => {
    const onChange = vi.fn(); const onSave = vi.fn(); const onOpenStudio = vi.fn()
    render(<MermaidWorkbench projectId="p1" source="flowchart LR\n A-->B" onChange={onChange} onSave={onSave} onOpenStudio={onOpenStudio} />)
    expect(screen.getByLabelText('Mermaid diagram source')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    expect(screen.queryByLabelText('Mermaid diagram source')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByLabelText('Mermaid diagram source')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Studio' }))
    expect(onOpenStudio).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalled()
  })

  it('uses the shared project AI endpoint to generate or edit Mermaid', async () => {
    api.assistProjectDiagram.mockResolvedValue({ mermaid: 'sequenceDiagram\n A->>B: hello', message: 'Updated' })
    const onChange = vi.fn()
    render(<MermaidWorkbench projectId="p1" source="" onChange={onChange} diagramType="sequence" aiContext="Checkout" />)
    fireEvent.click(screen.getByRole('button', { name: 'AI generate/edit' }))
    fireEvent.change(screen.getByPlaceholderText('Describe the diagram to generate…'), { target: { value: 'Show the request flow' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('sequenceDiagram\n A->>B: hello'))
    expect(api.assistProjectDiagram).toHaveBeenCalledWith('p1', expect.objectContaining({ diagram_type: 'sequence' }))
    expect(screen.getByText('Updated')).toBeInTheDocument()
  })
})
