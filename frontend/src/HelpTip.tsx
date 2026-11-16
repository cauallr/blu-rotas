export default function HelpTip({ title, children }: { title: string; children: React.ReactNode }) {
  return <details className="help-tip">
    <summary aria-label={`Ajuda: ${title}`} title={`Ajuda: ${title}`}>?</summary>
    <div className="help-tip-content"><strong>{title}</strong><p>{children}</p></div>
  </details>;
}
