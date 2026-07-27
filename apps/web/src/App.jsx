import { useEffect, useState } from "react";

const EXPERT_TOKEN_KEY = "taxai_expert_token";

function formatSla(t) {
  if (t.sla_overdue) return "已超时";
  if (t.sla_remaining_hours == null) return "—";
  if (t.sla_remaining_hours < 0) return "已超时";
  return `剩 ${t.sla_remaining_hours}h`;
}

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
  const [mineInProgress, setMineInProgress] = useState([]);
  const [mineDone, setMineDone] = useState([]);
  const [activeExpertTicket, setActiveExpertTicket] = useState(null);
  const [reply, setReply] = useState("");
  const [suggestReflow, setSuggestReflow] = useState(false);
  const [rating, setRating] = useState(5);
  const [metrics, setMetrics] = useState(null);
  const [clauses, setClauses] = useState([]);
  const [paymentMeta, setPaymentMeta] = useState(null);
  const [expertToken, setExpertToken] = useState(
    () => localStorage.getItem(EXPERT_TOKEN_KEY) || ""
  );
  const [expert, setExpert] = useState(null);
  const [loginPhone, setLoginPhone] = useState("expert-demo");
  const [loginPassword, setLoginPassword] = useState("demo1234");
  const [expertDesk, setExpertDesk] = useState("queue"); // queue | mine

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

  useEffect(() => {
    if (!expertToken) {
      setExpert(null);
      return;
    }
    fetch("/v1/auth/me", {
      headers: { Authorization: `Bearer ${expertToken}` },
    })
      .then(async (r) => {
        if (!r.ok) throw new Error("session expired");
        return r.json();
      })
      .then((data) => setExpert(data.expert))
      .catch(() => {
        localStorage.removeItem(EXPERT_TOKEN_KEY);
        setExpertToken("");
        setExpert(null);
      });
  }, [expertToken]);

  function authHeaders(extra = {}) {
    return {
      ...extra,
      Authorization: `Bearer ${expertToken}`,
    };
  }

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

  async function refreshExpertDesk() {
    if (!expertToken) return;
    const [q, m] = await Promise.all([
      fetch("/v1/expert/queue", { headers: authHeaders() }).then(async (r) => {
        if (r.status === 401) throw new Error("请重新登录");
        return r.json();
      }),
      fetch("/v1/expert/mine", { headers: authHeaders() }).then((r) => r.json()),
    ]);
    setQueue(q.items || []);
    setMineInProgress(m.in_progress || []);
    setMineDone(m.completed || []);
    if (q.expert) setExpert(q.expert);
  }

  async function expertLogin(e) {
    e?.preventDefault?.();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: loginPhone.trim(), password: loginPassword }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "登录失败");
      localStorage.setItem(EXPERT_TOKEN_KEY, data.token);
      setExpertToken(data.token);
      setExpert(data.expert);
      await refreshExpertDesk();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  async function expertLogout() {
    try {
      await fetch("/v1/auth/logout", {
        method: "POST",
        headers: authHeaders(),
      });
    } catch {
      /* ignore */
    }
    localStorage.removeItem(EXPERT_TOKEN_KEY);
    setExpertToken("");
    setExpert(null);
    setQueue([]);
    setMineInProgress([]);
    setMineDone([]);
    setActiveExpertTicket(null);
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

  async function claimTicket(id) {
    setLoading(true);
    try {
      const res = await fetch(`/v1/expert/tickets/${id}/claim`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "领单失败");
      setActiveExpertTicket(data);
      setExpertDesk("mine");
      setReply("");
      await refreshExpertDesk();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  async function submitExpertReply() {
    if (!activeExpertTicket?.id || !reply.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`/v1/expert/tickets/${activeExpertTicket.id}/reply`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          reply: reply.trim(),
          suggest_reflow: suggestReflow,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "提交失败");
      setTicket(data);
      setActiveExpertTicket(null);
      setReply("");
      setSuggestReflow(false);
      await refreshExpertDesk();
    } catch (err) {
      setError(String(err.message || err));
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
                if (k === "expert" && expertToken) {
                  refreshExpertDesk().catch((e) => setError(String(e)));
                }
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
        <>
          {!expertToken || !expert ? (
            <section className="panel">
              <h2>专家登录</h2>
              <p className="muted small">
                试接账号：expert-demo / expert-demo-b，密码见 DEMO_EXPERT_PASSWORD（默认 demo1234）
              </p>
              <form className="login-form" onSubmit={expertLogin}>
                <label>
                  手机号 / 账号
                  <input
                    value={loginPhone}
                    onChange={(e) => setLoginPhone(e.target.value)}
                    autoComplete="username"
                  />
                </label>
                <label>
                  密码
                  <input
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    autoComplete="current-password"
                  />
                </label>
                <button type="submit" disabled={loading}>
                  {loading ? "登录中…" : "登录"}
                </button>
              </form>
            </section>
          ) : (
            <>
              <section className="panel expert-bar">
                <div>
                  <h2>专家工作台</h2>
                  <p className="muted small">
                    {expert.name} · {expert.phone}
                  </p>
                </div>
                <div className="tabs desk-tabs">
                  <button
                    type="button"
                    className={expertDesk === "queue" ? "" : "ghost"}
                    onClick={() => setExpertDesk("queue")}
                  >
                    待接池 ({queue.length})
                  </button>
                  <button
                    type="button"
                    className={expertDesk === "mine" ? "" : "ghost"}
                    onClick={() => setExpertDesk("mine")}
                  >
                    我的工单 ({mineInProgress.length})
                  </button>
                  <button type="button" className="ghost" onClick={() => refreshExpertDesk()}>
                    刷新
                  </button>
                  <button type="button" className="ghost" onClick={expertLogout}>
                    退出
                  </button>
                </div>
              </section>

              {expertDesk === "queue" && (
                <section className="panel">
                  <h2>待接池</h2>
                  {!queue.length && <p className="muted">暂无待接工单</p>}
                  {queue.map((t) => (
                    <article
                      key={t.id}
                      className={`ticket-card ${t.sla_overdue ? "overdue" : ""}`}
                    >
                      <header className="ticket-head">
                        <strong>#{t.id}</strong>
                        <span className="pill">{t.plan_code}</span>
                        <span className="pill">¥{t.price_yuan}</span>
                        <span className={`pill ${t.sla_overdue ? "warn" : ""}`}>
                          SLA {formatSla(t)}
                        </span>
                      </header>
                      <pre className="body">{t.context_summary || "（无会话上下文）"}</pre>
                      <button
                        type="button"
                        onClick={() => claimTicket(t.id)}
                        disabled={loading}
                      >
                        领单
                      </button>
                    </article>
                  ))}
                </section>
              )}

              {expertDesk === "mine" && (
                <section className="panel">
                  <h2>处理中</h2>
                  {!mineInProgress.length && !activeExpertTicket && (
                    <p className="muted">暂无进行中工单，请先从待接池领单</p>
                  )}
                  {mineInProgress.map((t) => (
                    <article
                      key={t.id}
                      className={`ticket-card ${t.sla_overdue ? "overdue" : ""} ${
                        activeExpertTicket?.id === t.id ? "active" : ""
                      }`}
                    >
                      <header className="ticket-head">
                        <strong>#{t.id}</strong>
                        <span className="pill state-answered">{t.status}</span>
                        <span className={`pill ${t.sla_overdue ? "warn" : ""}`}>
                          SLA {formatSla(t)}
                        </span>
                      </header>
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => {
                          setActiveExpertTicket(t);
                          setReply("");
                        }}
                      >
                        打开答复
                      </button>
                      <pre className="body">{t.context_summary || ""}</pre>
                    </article>
                  ))}

                  {activeExpertTicket && (
                    <div className="reply-box">
                      <h3>书面答复 · #{activeExpertTicket.id}</h3>
                      <textarea
                        className="ask"
                        rows={5}
                        value={reply}
                        onChange={(e) => setReply(e.target.value)}
                        placeholder="向用户交付的书面答复（必填）"
                      />
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={suggestReflow}
                          onChange={(e) => setSuggestReflow(e.target.checked)}
                        />
                        建议回流知识库
                      </label>
                      <button
                        type="button"
                        onClick={submitExpertReply}
                        disabled={loading || !reply.trim()}
                      >
                        提交答复
                      </button>
                    </div>
                  )}

                  {!!mineDone.length && (
                    <>
                      <h3>最近完成</h3>
                      <ul className="cites">
                        {mineDone.map((t) => (
                          <li key={t.id}>
                            #{t.id} · {t.status} · ¥{t.price_yuan}
                            {t.rating ? ` · 评分 ${t.rating}` : ""}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </section>
              )}
            </>
          )}
        </>
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
