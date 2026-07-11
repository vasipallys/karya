import mermaid from 'mermaid'

let initialized = false

export function getMermaid() {
  if (!initialized) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      themeVariables: {
        primaryColor: '#d3e3fd', primaryTextColor: '#1f1f1f', primaryBorderColor: '#0b57d0',
        lineColor: '#5f6368', secondaryColor: '#e6f4ea', tertiaryColor: '#fef7e0',
        fontFamily: 'Roboto, sans-serif',
      },
    })
    initialized = true
  }
  return mermaid
}

export async function renderMermaid(source, id) {
  return getMermaid().render(id, source)
}
