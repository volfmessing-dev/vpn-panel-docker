interface Props {
  config: string;
}

export function ConfigPreview({ config }: Props) {
  return (
    <section className="panel">
      <h3>Generated dry-run config</h3>
      <pre className="code-preview">{config || "# Add nodes to build a preview."}</pre>
    </section>
  );
}
