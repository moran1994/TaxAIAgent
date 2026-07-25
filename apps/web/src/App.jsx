import { useEffect, useState } from "react";

export default function App() {
  const [tab, setTab] = useState("ask");
  const [health, setHealth] = useState(null);
  const [disclaimer, setDisclaimer] = useState("");
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [activeCite, setActiveCite] = useState(null);
  const [plan, setPlan] = useState("standard");
  const [ticket, setTicket] = useState(null);
  const [queue, setQueue] = useState([]);
  const [reply, setReply] = useState("");
  const [rating, setRating] = useState(5);
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch("/health").then((r) => r.json()),
      fetch("/v1/meta/disclaimer").then((r) => r.json()),
      fetch("/v1/meta/stats").then((r) => r.json()),
      fetch("/v1/metrics/kr").then((r) => r.json()),
    ])
      .then(([h, d, s, m]) => {
        setHealth(h);
        setDisclaimer(d.disclaimer_short || "");
        setStats(s);
        setMetrics(m);
      })
      .catch((e) => setError(String(e)));
  }, []);

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
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function createAndPay() {
    setLoading(true);
    try {
      const created = await fetch("/v1/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          plan_code: plan,
        }),
      }).then((r) => r.json());
      if (created.detail) throw new Error(created.detail);
      const paid = await fetch(`/v1/tickets/${created.id}/pay/mock`, {
        method: "POST",
      }).then((r) => r.json());
      if (paid.detail) throw new Error(paid.detail);
      setTicket(paid);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function refreshQueue() {
    const data = await fetch("/v1/expert/queue").then((r) => r.json());
    setQueue(data.items || []);
  }

  async function claimAndReply(id) {
    setLoading(true);
    try {
      await fetch(`/v1/expert/tickets/${id}/claim`, { method: "POST" }).then((r) =>
        r.json()
      );
      const done = await fetch(`/v1/expert/tickets/${id}/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reply: reply || "（试接）经复核，建议以检索条款为准，并结合主管税务机关口径办理。",
          suggest_reflow: false,
        }),
      }).then((r) => r.json());
      setTicket(done);
      setReply("");
      await refreshQueue();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function submitRating() {
    if (!ticket?.id) return;
    const data = await fetch(`/v1/tickets/${ticket.id}/rate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating, comment: "con cierge test" }),
    }).then((r) => r.json());
    setTicket(data);
  }

  return (
    <div className="page">
      <header className="hero">
        <p className="brand">条款问税</p>
        <h1>增值税口径，先看依据再决策</h1>
        <p className="sub">M2：模拟支付转专家 · 专家台领单答复 · 分账可导出</p>
        <div className="tabs">
          <button
            type="button"
            className={tab === "ask" ? "" : "ghost"}
            onClick={() => setTab("ask")}
          >
            用户问答
          </button>
          <button
            type="button"
            className={tab === "expert" ? "" : "ghost"}
            onClick={() => {
              setTab("expert");
              refreshQueue();
            }}
          >
            专家工作台
          </button>
          <button
            type="button"
            className={tab === "ops" ? "" : "ghost"}
            onClick={() => setTab("ops")}
          >
            指标
          </button>
        </div>
      </header>

      {error && (
        <section className="panel">
          <p className="err">{error}</p>
        </section>
      )}

      {tab === "ask" && (
        <>
          <section className="panel">
            <h2>系统状态</h2>
            <ul>
              <li>
                API：{health?.status ?? "…"} · v{health?.version ?? "?"}
              </li>
              <li>已发布切块：{stats?.chunks_published ?? "…"}</li>
              <li>会话：{conversationId ?? "尚未开始"}</li>
              <li>
                当前工单：{ticket ? `#${ticket.id} ${ticket.status}` : "无"}
              </li>
            </ul>
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
              {loading ? "处理中…" : "提问"}
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
                        [{c.corpus_id}] {c.clause_no} · #{c.chunk_id}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">无引用</p>
              )}

              <h3>转专家（模拟支付）</h3>
              <select value={plan} onChange={(e) => setPlan(e.target.value)}>
                <option value="standard">标准书面答 ¥99</option>
                <option value="complex">复杂书面答 ¥199</option>
              </select>
              <button type="button" onClick={createAndPay} disabled={loading}>
                下单并模拟支付
              </button>
              {ticket?.expert_reply && (
                <>
                  <h3>专家书面答复</h3>
                  <p className="conclusion">{ticket.expert_reply}</p>
                  <label>
                    评分{" "}
                    <input
                      type="number"
                      min={1}
                      max={5}
                      value={rating}
                      onChange={(e) => setRating(Number(e.target.value))}
                    />
                  </label>
                  <button type="button" className="ghost" onClick={submitRating}>
                    提交评价
                  </button>
                </>
              )}
              <p className="muted small">{answer.disclaimer}</p>
            </section>
          )}

          {activeCite && (
            <section className="panel cite-panel">
              <h2>原文预览</h2>
              <pre className="body">{activeCite.body}</pre>
              <button type="button" className="ghost" onClick={() => setActiveCite(null)}>
                关闭
              </button>
            </section>
          )}
        </>
      )}

      {tab === "expert" && (
        <section className="panel">
          <h2>待接池</h2>
          <button type="button" className="ghost" onClick={refreshQueue}>
            刷新
          </button>
          <textarea
            className="ask"
            rows={3}
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="书面答复内容（可空则用默认试接答复）"
          />
          {!queue.length && <p className="muted">暂无待接工单</p>}
          <ul className="cites">
            {queue.map((t) => (
              <li key={t.id}>
                #{t.id} · {t.plan_code} · ¥{t.price_yuan} · SLA{" "}
                {t.sla_deadline || "—"}
                <div>
                  <button
                    type="button"
                    onClick={() => claimAndReply(t.id)}
                    disabled={loading}
                  >
                    领单并提交答复
                  </button>
                </div>
                <pre className="body">{t.context_summary || "（无上下文）"}</pre>
              </li>
            ))}
          </ul>
        </section>
      )}

      {tab === "ops" && (
        <section className="panel">
          <h2>KR 快照</h2>
          <pre className="body">{JSON.stringify(metrics, null, 2)}</pre>
          <p>
            <a href="/v1/ledger.csv" target="_blank" rel="noreferrer">
              下载分账 CSV
            </a>
          </p>
        </section>
      )}

      <footer className="foot">{disclaimer}</footer>
    </div>
  );
}
