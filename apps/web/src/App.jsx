import { useEffect, useState } from "react";

export default function App() {
  const [health, setHealth] = useState(null);
  const [disclaimer, setDisclaimer] = useState("");
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [activeCite, setActiveCite] = useState(null);
  const [events, setEvents] = useState([]);

  useEffect(() => {
    Promise.all([
      fetch("/health").then((r) => r.json()),
      fetch("/v1/meta/disclaimer").then((r) => r.json()),
      fetch("/v1/meta/stats").then((r) => r.json()),
    ])
      .then(([h, d, s]) => {
        setHealth(h);
        setDisclaimer(d.disclaimer_short || "");
        setStats(s);
      })
      .catch((e) => setError(String(e)));
  }, []);

  function track(name) {
    setEvents((prev) => [...prev, { name, at: Date.now() }]);
  }

  async function ask() {
    if (!query.trim() || loading) return;
    setLoading(true);
    setActiveCite(null);
    try {
      const res = await fetch("/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          conversation_id: conversationId,
          top_k: 5,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAnswer(data);
      setConversationId(data.conversation_id);
      if (data.state === "uncertain") track("uncertain_shown");
      if (data.expert_cta) track("expert_cta_shown");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="hero">
        <p className="brand">条款问税</p>
        <h1>增值税口径，先看依据再决策</h1>
        <p className="sub">
          强制引用 RAG：无检索命中不硬答。未配置大模型时使用摘录式答复。
        </p>
      </header>

      <section className="panel">
        <h2>系统状态</h2>
        {error ? (
          <p className="err">接口异常：{error}</p>
        ) : (
          <ul>
            <li>API：{health ? health.status : "…"} · v{health?.version ?? "?"}</li>
            <li>已发布条款：{stats?.clauses_published ?? "…"}</li>
            <li>已发布切块：{stats?.chunks_published ?? "…"}</li>
            <li>
              LLM：{stats?.llm_configured ? "已配置" : "摘录回退"} · Prompt{" "}
              {stats?.prompt_version ?? "—"}
            </li>
            <li>会话：{conversationId ?? "尚未开始"}</li>
          </ul>
        )}
      </section>

      <section className="panel">
        <h2>提问</h2>
        <textarea
          className="ask"
          rows={3}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="例如：制造业一般纳税人如何申请留抵退税？"
        />
        <button type="button" onClick={ask} disabled={loading || !query.trim()}>
          {loading ? "检索中…" : "提问"}
        </button>
        <button
          type="button"
          className="ghost"
          onClick={() => track("expert_cta_click")}
        >
          转专家（M2 占位）
        </button>
      </section>

      {answer && (
        <section className="panel answer-card">
          <div className="state-row">
            <span className={`pill state-${answer.state}`}>{answer.state}</span>
            {answer.uncertainty && <span className="pill warn">不确定</span>}
          </div>
          <h2>结论</h2>
          <p className="conclusion">{answer.conclusion}</p>
          {answer.boundary && (
            <>
              <h3>适用边界</h3>
              <p className="muted">{answer.boundary}</p>
            </>
          )}
          <h3>依据条款</h3>
          {answer.citations?.length ? (
            <ul className="cites">
              {answer.citations.map((c) => (
                <li key={c.chunk_id}>
                  <button
                    type="button"
                    className="linkish"
                    onClick={() => setActiveCite(c)}
                  >
                    [{c.corpus_id}] {c.doc_no || ""} {c.clause_no || ""} · chunk#
                    {c.chunk_id}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">无引用（不确定态）</p>
          )}
          <p className="muted small">{answer.disclaimer}</p>
          {answer.meta?.search && (
            <p className="muted small">
              检索 {answer.meta.search.latency_ms}ms · candidates{" "}
              {answer.meta.search.candidates}
            </p>
          )}
        </section>
      )}

      {activeCite && (
        <section className="panel cite-panel">
          <h2>原文预览</h2>
          <p className="muted">
            {activeCite.doc_no} {activeCite.clause_no}
            {activeCite.source_url ? (
              <>
                {" "}
                ·{" "}
                <a href={activeCite.source_url} target="_blank" rel="noreferrer">
                  来源
                </a>
              </>
            ) : null}
          </p>
          <pre className="body">{activeCite.body}</pre>
          <button type="button" className="ghost" onClick={() => setActiveCite(null)}>
            关闭
          </button>
        </section>
      )}

      <footer className="foot">{disclaimer}</footer>
    </div>
  );
}
