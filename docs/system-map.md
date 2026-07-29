# System map: System Explorer

<!-- generated-by: system-explorer -->
<!-- source-fingerprint: c581c2cfd65d66e9d3c4518966b39fa0612116583d699130e46acb796931bce6 -->

Diese Datei wird deterministisch aus dem Repository- bzw. Bundle-Vertrag
erzeugt. Änderungen erfolgen über `system-explorer diagrams`.

```mermaid
flowchart LR
  N1["System Explorer"]
  N2[".github/"]
  N3["_tools/"]
  N4["docs/"]
  N5["examples/"]
  N6["schemas/"]
  N7["src/"]
  N8["tests/"]
  N9["workflows/"]
  N10["cli: system-explorer --help"]
  N11["ui: system-explorer serve --config <path>"]
  N12["api-prober.evidence-adapter"]
  N13["change.proposal.readonly"]
  N14["database.schema.mapping"]
  N15["document.registry"]
  N16["evidence.registry"]
  N17["registry.discovery"]
  N18["system.architecture.diff"]
  N19["system.cloud-topology"]
  N20["system.control-document.mapping"]
  N21["system.cost-local-comparison"]
  N22["system.coverage"]
  N23["system.crystallized-intelligence.mapping"]
  N24["system.data-topology"]
  N25["system.deployment-purpose-analysis"]
  N26["system.directory-tree"]
  N27["system.discovery"]
  N28["system.explainer-video.handoff"]
  N29["system.llm-action-surface"]
  N30["system.llm-readiness-analysis"]
  N31["system.llm-trace-analysis"]
  N32["system.map.export"]
  N33["system.map.federation"]
  N34["system.map.import"]
  N35["system.mapping"]
  N36["system.repository-diagram.sync"]
  N37["system.server-privacy-check"]
  N38["system.software-resource.mapping"]
  N39["system.token-saving-endpoint.analysis"]
  N40["trampelpfad.probe-plan"]
  N1 -->|contains| N2
  N1 -->|contains| N3
  N1 -->|contains| N4
  N1 -->|contains| N5
  N1 -->|contains| N6
  N1 -->|contains| N7
  N1 -->|contains| N8
  N1 -->|contains| N9
  N10 -->|enters| N1
  N11 -->|enters| N1
  N1 -->|provides| N12
  N1 -->|provides| N13
  N1 -->|provides| N14
  N1 -->|provides| N15
  N1 -->|provides| N16
  N1 -->|provides| N17
  N1 -->|provides| N18
  N1 -->|provides| N19
  N1 -->|provides| N20
  N1 -->|provides| N21
  N1 -->|provides| N22
  N1 -->|provides| N23
  N1 -->|provides| N24
  N1 -->|provides| N25
  N1 -->|provides| N26
  N1 -->|provides| N27
  N1 -->|provides| N28
  N1 -->|provides| N29
  N1 -->|provides| N30
  N1 -->|provides| N31
  N1 -->|provides| N32
  N1 -->|provides| N33
  N1 -->|provides| N34
  N1 -->|provides| N35
  N1 -->|provides| N36
  N1 -->|provides| N37
  N1 -->|provides| N38
  N1 -->|provides| N39
  N1 -->|provides| N40
```
