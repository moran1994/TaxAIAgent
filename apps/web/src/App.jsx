import { useEffect, useState } from "react";

export default function App() {
  const [health, setHealth] = useState(null);
  const [disclaimer, setDisclaimer] = useState("");
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

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

  return (
    <div className="page">
      <header className="hero">
        <p className="brand">条款问税</p>
        <h1>增值税口径，先看依据再决策</h1>
        <p className="sub">
          Concierge MVP 壳页：强制引用问答与专家按单即将接入（M1–M2）。
        </p>
      </header>

      <section className="panel">
        <h2>系统状态</h2>
        {error ? (
          <p className="err">无法连接 API。请先启动 apps/api（{error}）</p>
        ) : (
          <ul>
            <li>API：{health ? health.status : "…"}</li>
            <li>环境：{health?.env ?? "…"}</li>
            <li>法规文档数：{stats?.policies ?? "…"}</li>
            <li>已发布条款：{stats?.clauses_published ?? "…"}</li>
            <li>草稿条款：{stats?.clauses_draft ?? "…"}</li>
            <li>LLM Key：{stats?.llm_configured ? "已配置" : "未配置"}</li>
          </ul>
        )}
      </section>

      <section className="panel">
        <h2>对话（占位）</h2>
        <textarea
          className="ask"
          rows={3}
          placeholder="例如：制造业一般纳税人如何申请留抵退税？"
          disabled
        />
        <button type="button" disabled>
          提问（M1-06 后启用）
        </button>
        <button type="button" className="ghost" disabled>
          转专家（M2 后启用）
        </button>
      </section>

      <footer className="foot">{disclaimer}</footer>
    </div>
  );
}
