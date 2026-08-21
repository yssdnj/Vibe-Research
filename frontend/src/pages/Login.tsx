import { FormEvent, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Activity, ArrowRight, Eye, EyeOff, LineChart, LockKeyhole, Radar, ShieldCheck, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/auth";

const FEATURES = [
  { icon: Activity, title: "市场全景", text: "A 股、美股与港股行情、财务和资金数据集中呈现" },
  { icon: Radar, title: "资讯雷达", text: "公开资讯、公告与研报汇入同一研究工作流" },
  { icon: Sparkles, title: "你的 AI", text: "接入自己的模型或本机 Codex，保留分析控制权" },
];

export function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "登录 · Vibe-Research";
    return () => {
      document.title = previousTitle;
    };
  }, []);

  if (!auth.loading && (!auth.enabled || auth.authenticated)) {
    return <Navigate to="/daily-review" replace />;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("请输入账号和密码");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await auth.login(username.trim(), password, remember);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from || "/daily-review", { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden px-4 py-6 sm:px-6 lg:grid lg:place-items-center lg:py-10">
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute -left-28 top-12 h-72 w-72 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -right-32 bottom-0 h-96 w-96 rounded-full bg-blue-500/10 blur-3xl" />
      </div>

      <section className="glass relative mx-auto grid w-full max-w-5xl overflow-hidden rounded-2xl lg:grid-cols-[1.08fr_0.92fr]" aria-label="Vibe-Research 登录">
        <div className="relative flex flex-col justify-between overflow-hidden border-b border-border/60 bg-[linear-gradient(145deg,hsl(222_43%_10%),hsl(222_48%_7%))] p-7 sm:p-10 lg:min-h-[620px] lg:border-b-0 lg:border-r">
          <div className="relative z-10">
            <div className="mb-12 flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl border border-primary/25 bg-primary/10">
                <LineChart className="h-5 w-5 text-primary" />
              </span>
              <div>
                <p className="text-xl font-extrabold tracking-tight">Vibe-<span className="text-primary">Research</span></p>
                <p className="text-xs text-muted-foreground">个人 AI 投研系统</p>
              </div>
            </div>

            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-primary">Research with evidence</p>
            <h1 className="max-w-md text-3xl font-bold leading-tight tracking-[-0.025em] text-white sm:text-4xl">
              让数据先说话，<br />再让 AI 参与研究。
            </h1>
            <p className="mt-5 max-w-md text-sm leading-7 text-slate-400">
              聚合行情、财务、资讯与研究记录，构建属于你自己的投资研究工作台。
            </p>
          </div>

          <div className="relative z-10 mt-10 space-y-5">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="flex gap-4">
                <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/[0.055] text-primary">
                  <Icon className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-slate-200">{title}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">{text}</p>
                </div>
              </div>
            ))}
          </div>

          <p className="relative z-10 mt-10 text-[11px] leading-5 text-slate-600">仅供学习与研究，不构成任何投资建议。</p>
        </div>

        <div className="flex items-center bg-card/65 p-7 sm:p-10 lg:p-12">
          <div className="w-full">
            <div className="mb-9">
              <span className="mb-5 grid h-11 w-11 place-items-center rounded-xl bg-primary/10 text-primary">
                <LockKeyhole className="h-5 w-5" />
              </span>
              <h2 className="text-2xl font-bold tracking-tight">欢迎回来</h2>
              <p className="mt-2 text-sm text-muted-foreground">登录后进入你的投研工作台</p>
            </div>

            <form onSubmit={submit} className="space-y-5" noValidate>
              <div>
                <label htmlFor="username" className="mb-2 block text-sm font-medium">账号</label>
                <input
                  id="username"
                  name="username"
                  autoComplete="username"
                  autoFocus
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  className="h-12 w-full rounded-xl border bg-background/55 px-4 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                  placeholder="请输入账号"
                />
              </div>

              <div>
                <label htmlFor="password" className="mb-2 block text-sm font-medium">密码</label>
                <div className="relative">
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="h-12 w-full rounded-xl border bg-background/55 px-4 pr-12 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                    placeholder="请输入密码"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((shown) => !shown)}
                    className="absolute right-1.5 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <label className="flex cursor-pointer items-center gap-3 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => setRemember(event.target.checked)}
                  className="h-4 w-4 rounded border-border accent-[hsl(var(--primary))]"
                />
                记住我，30 天内自动登录
              </label>

              <div className="min-h-6" aria-live="polite">
                {error && <p className="text-sm text-destructive">{error}</p>}
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-[0_10px_28px_hsl(var(--primary)/0.22)] transition hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:ring-offset-2 focus:ring-offset-background disabled:cursor-wait disabled:opacity-65"
              >
                {submitting ? "正在验证…" : "登录"}
                {!submitting && <ArrowRight className="h-4 w-4" />}
              </button>
            </form>

            <div className="mt-8 flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="h-4 w-4 text-success" />
              登录凭证通过 HttpOnly Cookie 安全保存
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
