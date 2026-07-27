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
  const [history, setHistory] = useState([]);
  const [answer, setAnswer] = useState(null);
  const [activeCite, setActiveCite] = useState(null);
  const [plan, setPlan] = useState("standard");
  const [ticket, setTicket] = useState(null);
  const [queue, setQueue] = useState([]);
  const [reply, setReply] = useState("");
  const [rating, setRating] = useState(5);
  const [metrics, setMetrics] = useState(null);
  const [clauses, setClauses] = useState([]);
  const [paymentMeta, setPaymentMeta] = useState(null);

  async function refreshMeta() {
    const [h, d, s, m, p] = await Promise.all([
      fetch("/health").then((r) => r.json()),
      fetch("/v1/meta/disclaimer").then((r) => r.json()),
      fetch("/v1/meta/stats").then((r) => r.json()),
      fetch("/v1/metrics/kr").then((r) => r.json()),
      fetch("/v1/meta/payment").then((r) => r.json()),
    ]);
    setHealth(h);
    setDisclaimer(d.disclaimer_short || "");
    setStats(s);
    setMetrics(m);
    setPaymentMeta(p);
  }

  useEffect(() => {
    refreshMeta().catch((e) => setError(String(e)));
  }, []);

  async function loadHistory(cid) {
    if (!cid) return;
    const data = await fetch(`/v1/conversations/${cid}/export`).then((r) => r.json());
    setHistory(data.messages || []);
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
      await loadHistory(data.conversation_id);
      setQuery("");
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
        body: JSON.stringify({ conversation_id: conversationId, plan_code: plan }),
      }).then((r) => r.json());
      if (created.detail) throw new Error(JSON.stringify(created.detail));
      const paid = await fetch(`/v1/tickets/${created.id}/pay/mock`, {
        method: "POST",
      }).then((r) => r.json());
      if (paid.detail) throw new Error(JSON.stringify(paid.detail));
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

  async function loadAdminClauses() {
    const data = await fetch("/v1/knowledge/clauses?status=published&limit=50").then((r) =>
      r.json()
    );
    setClauses(data.items || []);
  }

  async function setClauseStatus(id, status) {
    await fetch(`/v1/knowledge/clauses/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, actor: "ops-ui" }),
    });
    await loadAdminClauses();
    await refreshMeta();
  }

  async function claimAndReply(id) {
    setLoading(true);
    try {
      await fetch(`/v1/expert/tickets/${id}/claim`, { method: "POST" });
      const done = await fetch(`/v1/expert/tickets/${id}/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reply:
            reply ||
            "（试接）经复核，建议以检索条款为准，并结合主管税务机关口径办理。",
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
      body: JSON.stringify({ rating, comment: "ok" }),
    }).then((r) => r.json());
    setTicket(data);
  }

  return (
    <div className="page">
      <header className="hero">
        <p className="brand">条款问税</p>
        <h1>增值税口径，先看依据再决策</h1>
        <p className="sub">功能持续迭代：强制引用问答 · 转专家 · 知识运营</p>
        <div className="tabs">
          {[
            ["ask", "用户问答"],
            ["expert", "专家工作台"],
            ["admin", "知识运营"],
            ["ops", "指标"],
          ].map(([k, label]) => (
            <button
              key={k}
              type="button"
              className={tab === k ? "" : "ghost"}
              onClick={() => {
                setTab(k);
                if (k === "expert") refreshQueue();
                if (k === "admin") loadAdminClauses();
                if (k === "ops") refreshMeta();
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <section className="panel">
          <p className="err">{error}</p>
          <button type="button" className="ghost" onClick={() => setError("")}>
            清除
          </button>
        </section>
      )}

      {tab === "ask" && (
        <>
          <section className="panel">
            <h2>状态</h2>
            <ul>
              <li>
                API {health?.status} · v{health?.version}
              </li>
              <li>切块 {stats?.chunks_published ?? "…"} · 支付 {paymentMeta?.provider}</li>
              <li>会话 {conversationId ?? "新会话"}</li>
            </ul>
          </section>

          {!!history.length && (
            <section className="panel">
              <h2>对话历史</h2>
              <ul className="cites">
                {history.map((m) => (
                  <li key={m.id}>
                    <strong>{m.role}</strong>: {String(m.content).slice(0, 180)}
                    {String(m.content).length > 180 ? "…" : ""}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="panel">
            <h2>提问</h2>
            <textarea
              className="ask"
              rows={3}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="例如：小规模纳税人月销售额不超过多少免征增值税？"
            />
            <button type="button" onClick={ask} disabled={loading || !query.trim()}>
              {loading ? "处理中…" : "提问"}
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setConversationId(null);
                setHistory([]);
                setAnswer(null);
                setTicket(null);
              }}
            >
              新会话
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
              <h3>依据</h3>
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
              <h3>转专家</h3>
              <select value={plan} onChange={(e) => setPlan(e.target.value)}>
                <option value="standard">标准 ¥99</option>
                <option value="complex">复杂 ¥199</option>
              </select>
              <button type="button" onClick={createAndPay} disabled={loading}>
                下单并支付
              </button>
              {ticket?.expert_reply && (
                <>
                  <h3>专家答复</h3>
                  <p className="conclusion">{ticket.expert_reply}</p>
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={rating}
                    onChange={(e) => setRating(Number(e.target.value))}
                  />
                  <button type="button" className="ghost" onClick={submitRating}>
                    评价
                  </button>
                </>
              )}
            </section>
          )}

          {activeCite && (
            <section className="panel">
              <h2>原文</h2>
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
            placeholder="书面答复"
          />
          {queue.map((t) => (
            <div key={t.id}>
              <p>
                #{t.id} · {t.plan_code} · ¥{t.price_yuan}
              </p>
              <button type="button" onClick={() => claimAndReply(t.id)} disabled={loading}>
                领单并答复
              </button>
              <pre className="body">{t.context_summary || ""}</pre>
            </div>
          ))}
        </section>
      )}

      {tab === "admin" && (
        <section className="panel">
          <h2>已发布条款（可下架）</h2>
          <button type="button" className="ghost" onClick={loadAdminClauses}>
            刷新
          </button>
          <ul className="cites">
            {clauses.map((c) => (
              <li key={c.id}>
                [{c.corpus_id}] {c.clause_no} · {c.tags}
                <div>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => setClauseStatus(c.id, "draft")}
                  >
                    下架为 draft
                  </button>
                </div>
                <p className="muted small">{c.preview}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {tab === "ops" && (
        <section className="panel">
          <h2>KR / 支付</h2>
          <pre className="body">{JSON.stringify({ metrics, paymentMeta }, null, 2)}</pre>
          <a href="/v1/ledger.csv" target="_blank" rel="noreferrer">
            分账 CSV
          </a>
        </section>
      )}

      <footer className="foot">{disclaimer}</footer>
    </div>
  );
}
