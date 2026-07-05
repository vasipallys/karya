import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Check, ChevronDown, Code2, Copy, Download, Expand,
  FileCode2, Play, RotateCcw, Search, Sparkles,
} from "lucide-react";
import { mermaidCatalog, mermaidCategories } from "../mermaidCatalog";
import type { ThemeName } from "../types";

let externalDiagramsRegistered = false;

async function loadMermaid() {
  const { default: mermaid } = await import("mermaid");
  if (!externalDiagramsRegistered) {
    const { default: zenuml } = await import("@mermaid-js/mermaid-zenuml");
    await mermaid.registerExternalDiagrams([zenuml]);
    externalDiagramsRegistered = true;
  }
  return mermaid;
}

interface Props {
  theme: ThemeName;
  onToast: (message: string) => void;
}

const themeConfig = (theme: ThemeName) => theme === "midnight"
  ? { theme: "dark" as const, darkMode: true, background: "#202a35", primaryColor: "#293746", primaryTextColor: "#d5e2e8", lineColor: "#57c7ff" }
  : theme === "sand"
    ? { theme: "base" as const, darkMode: false, background: "#f3eee5", primaryColor: "#e9dfd0", primaryTextColor: "#74675a", lineColor: "#d89545" }
    : { theme: "base" as const, darkMode: false, background: "#f0f4f8", primaryColor: "#e3eaf2", primaryTextColor: "#546e7a", lineColor: "#29b6f6" };

export default function MermaidStudio({ theme, onToast }: Props) {
  const [selectedId, setSelectedId] = useState("flowchart");
  const selected = mermaidCatalog.find((item) => item.id === selectedId) || mermaidCatalog[0];
  const [code, setCode] = useState(() => localStorage.getItem("karya:mermaid:flowchart") || selected.template);
  const [query, setQuery] = useState("");
  const [svg, setSvg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);
  const [editorOnly, setEditorOnly] = useState(false);
  const [catalogCheck, setCatalogCheck] = useState("30 types");
  const [catalogFailures, setCatalogFailures] = useState("");
  const renderSequence = useRef(0);

  const filtered = useMemo(() => mermaidCatalog.filter((item) =>
    `${item.name} ${item.description} ${item.category}`.toLowerCase().includes(query.toLowerCase())
  ), [query]);

  const renderDiagram = async (source = code) => {
    const sequence = ++renderSequence.current;
    setRendering(true);
    try {
      const mermaid = await loadMermaid();
      const palette = themeConfig(theme);
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: palette.theme,
        themeVariables: {
          darkMode: palette.darkMode,
          background: palette.background,
          primaryColor: palette.primaryColor,
          primaryTextColor: palette.primaryTextColor,
          lineColor: palette.lineColor,
          fontFamily: "Inter, Segoe UI, sans-serif",
        },
        flowchart: { htmlLabels: false, curve: "basis" },
      });
      await mermaid.parse(source);
      const result = await mermaid.render(`karya-mermaid-${sequence}`, source);
      if (sequence !== renderSequence.current) return;
      setSvg(result.svg);
      setError(null);
      localStorage.setItem(`karya:mermaid:${selected.id}`, source);
    } catch (reason) {
      if (sequence !== renderSequence.current) return;
      const message = reason instanceof Error ? reason.message : String(reason);
      setError(message.split("\n").slice(0, 4).join("\n"));
    } finally {
      if (sequence === renderSequence.current) setRendering(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => renderDiagram(code), 450);
    return () => window.clearTimeout(timer);
  }, [code, theme, selected.id]);

  const chooseDiagram = (id: string) => {
    const definition = mermaidCatalog.find((item) => item.id === id);
    if (!definition) return;
    setSelectedId(id);
    setCode(localStorage.getItem(`karya:mermaid:${id}`) || definition.template);
    setError(null);
  };

  const copyCode = async () => {
    await navigator.clipboard.writeText(code);
    onToast("Mermaid source copied");
  };

  const exportSvg = () => {
    if (!svg) return;
    const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `karya-${selected.id}.svg`;
    link.click();
    URL.revokeObjectURL(link.href);
    onToast("Mermaid SVG exported");
  };

  const validateCatalog = async () => {
    setCatalogCheck("Checking…");
    const mermaid = await loadMermaid();
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
    const failures: string[] = [];
    for (const definition of mermaidCatalog) {
      try { await mermaid.parse(definition.template); } catch { failures.push(definition.name); }
    }
    setCatalogCheck(failures.length ? `${30 - failures.length}/30 valid` : "30/30 valid");
    setCatalogFailures(failures.join(", "));
    onToast(failures.length ? `Templates needing attention: ${failures.join(", ")}` : "All 30 Mermaid templates are valid");
  };

  return (
    <section className="mermaid-studio">
      <aside className="mermaid-catalog">
        <div className="mermaid-brand"><span><Sparkles size={16} /></span><div><strong>Mermaid studio</strong><small>v11.16 · 30 diagram types</small></div></div>
        <div className="mermaid-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find diagram type" /></div>
        <div className="catalog-scroll">
          {mermaidCategories.map((category) => {
            const items = filtered.filter((item) => item.category === category);
            if (!items.length) return null;
            return (
              <div className="catalog-group" key={category}>
                <span>{category}</span>
                {items.map((item) => (
                  <button className={selected.id === item.id ? "active" : ""} key={item.id} onClick={() => chooseDiagram(item.id)}>
                    <FileCode2 size={14} />
                    <div><strong>{item.name}</strong><small>{item.description}</small></div>
                    {item.experimental && <em>beta</em>}
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      </aside>

      <div className="mermaid-workbench">
        <div className="mermaid-toolbar">
          <div><Code2 size={16} /><strong>{selected.name}</strong>{selected.experimental && <span>Experimental syntax</span>}</div>
          <div>
            <button className="catalog-check" title={catalogFailures || "Validate all diagram templates"} onClick={validateCatalog}><Check size={13} /> {catalogCheck}</button>
            <button title="Reset template" onClick={() => setCode(selected.template)}><RotateCcw size={14} /></button>
            <button title="Copy Mermaid source" onClick={copyCode}><Copy size={14} /></button>
            <button title="Toggle editor focus" onClick={() => setEditorOnly(!editorOnly)}><Expand size={14} /></button>
            <button className="render-button" onClick={() => renderDiagram()}><Play size={13} fill="currentColor" /> Render</button>
            <button className="mermaid-export" disabled={!svg} onClick={exportSvg}><Download size={14} /> SVG</button>
          </div>
        </div>
        <div className={`mermaid-split ${editorOnly ? "editor-only" : ""}`}>
          <div className="mermaid-editor">
            <div className="pane-label"><span>MERMAID SOURCE</span><small>Changes render automatically</small></div>
            <div className="code-wrap"><pre aria-hidden="true">{code.split("\n").map((_, index) => `${String(index + 1).padStart(2, " ")}\n`)}</pre><textarea aria-label="Mermaid source" spellCheck={false} value={code} onChange={(event) => setCode(event.target.value)} /></div>
          </div>
          {!editorOnly && (
            <div className="mermaid-preview">
              <div className="pane-label"><span>LIVE PREVIEW</span><small>{rendering ? "Rendering…" : error ? "Syntax needs attention" : "Valid Mermaid"}</small></div>
              {error ? (
                <div className="mermaid-error"><span><AlertTriangle size={18} /></span><div><strong>Couldn’t render this diagram</strong><pre>{error}</pre></div></div>
              ) : svg ? (
                <div className="mermaid-svg" dangerouslySetInnerHTML={{ __html: svg }} />
              ) : (
                <div className="mermaid-loading"><Sparkles size={22} /><span>Preparing preview…</span></div>
              )}
              {!error && svg && <div className="valid-badge"><Check size={12} /> Syntax valid</div>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
