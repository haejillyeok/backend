WEBSOCKET_DOCS_PAGE_STYLE = """
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --text: #17202a;
      --muted: #5f6b7a;
      --line: #d9dee7;
      --panel: #ffffff;
      --code: #101828;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }
    main {
      width: calc(100% - 32px);
      margin: 0 auto;
      padding: 44px 0 72px;
    }
    article {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 28px;
    }
    h1, h2, h3 { line-height: 1.25; margin: 28px 0 12px; }
    h1 { margin-top: 0; font-size: 32px; }
    h2 { font-size: 24px; }
    h3 { font-size: 19px; }
    p { margin: 10px 0; }
    code {
      border-radius: 5px;
      background: #eef2f7;
      padding: 2px 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.94em;
    }
    pre {
      overflow-x: auto;
      border-radius: 8px;
      background: var(--code);
      color: #f8fafc;
      padding: 16px;
    }
    pre code { background: transparent; color: inherit; padding: 0; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; }
    th, td { border: 1px solid var(--line); padding: 9px 11px; text-align: left; }
    th { background: #f0f3f8; }
    .meta { color: var(--muted); margin-bottom: 24px; }
    .toc {
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 0 0 28px;
      padding: 18px 20px;
    }
    .toc strong { display: block; margin-bottom: 8px; }
    .toc ol { margin: 0; padding-left: 20px; }
    .toc a { color: #1d4ed8; text-decoration: none; }
    .toc a:hover { text-decoration: underline; }
    .doc-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 18px;
    }
    .doc-toolbar button {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      cursor: pointer;
      font: inherit;
      padding: 6px 10px;
    }
    .doc-toolbar button:hover { background: #f0f3f8; }
    .doc-section {
      border-top: 1px solid var(--line);
      padding: 18px 0 0;
    }
    .doc-section + .doc-section { margin-top: 10px; }
    .doc-section > summary {
      align-items: center;
      cursor: pointer;
      display: flex;
      gap: 10px;
      list-style: none;
      padding: 6px 0 12px;
    }
    .doc-section > summary::-webkit-details-marker { display: none; }
    .doc-section > summary::before {
      border: solid var(--muted);
      border-width: 0 2px 2px 0;
      content: "";
      display: inline-block;
      height: 8px;
      transform: rotate(-45deg);
      transition: transform 0.15s ease;
      width: 8px;
    }
    .doc-section[open] > summary::before { transform: rotate(45deg); }
    .section-title {
      font-size: 24px;
      font-weight: 700;
      line-height: 1.25;
    }
    .mermaid {
      background: #ffffff;
      color: var(--text);
      border: 1px solid var(--line);
      text-align: center;
    }
    @media (max-width: 720px) {
      main { width: calc(100% - 20px); padding: 20px 0 48px; }
      article { padding: 18px; }
      h1 { font-size: 26px; }
      .section-title { font-size: 21px; }
    }
"""

WEBSOCKET_DOCS_PAGE_SCRIPTS = """
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({ startOnLoad: true, securityLevel: "strict" });
  </script>
  <script>
    function setDocSections(open) {
      document.querySelectorAll(".doc-section").forEach((section) => {
        section.open = open;
      });
    }
  </script>
"""
