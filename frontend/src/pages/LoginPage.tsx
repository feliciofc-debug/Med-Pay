import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Eye, EyeOff, Sparkles } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { getErrorMessage } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState(DEMO_MODE ? "demo@medpag.local" : "");
  const [password, setPassword] = useState(DEMO_MODE ? "demo123" : "");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const me = await login(email, password);
      // OPERADOR não tem Dashboard — mandamos direto pra tela de upload.
      navigate(me.role === "OPERADOR" ? "/app/upload" : "/app");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 via-white to-accent-50/40 px-4 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 opacity-40 pointer-events-none">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-brand-200 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-accent-200 rounded-full blur-3xl" />
      </div>

      <div className="w-full max-w-md relative">
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-sm text-brand-700 hover:text-brand-900 transition mb-6"
        >
          <ArrowLeft size={14} /> Voltar à página inicial
        </Link>

        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2.5 mb-4">
            <div className="w-11 h-11 bg-brand-900 rounded-xl flex items-center justify-center text-accent-300 font-bold text-lg border border-accent-400/40 shadow-md">
              M
            </div>
            <span className="text-2xl font-bold text-brand-900 tracking-[0.15em]">
              MEDPAG
            </span>
          </Link>
          <p className="text-sm text-brand-700/70 mt-2 italic">
            Pagamentos em massa, sem retrabalho.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="card space-y-4 relative border-brand-100 shadow-lg shadow-brand-100/40"
        >
          {/* Faixa dourada superior */}
          <div className="absolute top-0 left-6 right-6 h-px bg-gradient-to-r from-transparent via-accent-400 to-transparent" />

          <h2 className="text-lg font-semibold text-brand-900 pt-1">
            Entrar no sistema
          </h2>

          {DEMO_MODE && (
            <div className="rounded-lg border border-accent-300 bg-accent-50 p-3 text-xs text-brand-900">
              <div className="flex items-center gap-1.5 font-semibold text-accent-700 mb-1">
                <Sparkles size={12} />
                MODO DEMONSTRAÇÃO
              </div>
              <p className="text-brand-800/80 leading-relaxed">
                Backend real desativado. Os dados são de exemplo, gerados no navegador.
                Credenciais já preenchidas:{" "}
                <code className="font-mono bg-white px-1.5 py-0.5 rounded border border-accent-200">
                  demo@medpag.local
                </code>{" "}
                /{" "}
                <code className="font-mono bg-white px-1.5 py-0.5 rounded border border-accent-200">
                  demo123
                </code>
              </p>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              E-mail
            </label>
            <input
              type="email"
              required
              autoComplete="email"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              placeholder="seu@email.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Senha
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                tabIndex={-1}
                aria-label={showPassword ? "Esconder senha" : "Mostrar senha"}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-brand-700/60 hover:text-brand-900 transition rounded"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn-primary w-full"
            disabled={loading}
          >
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <p className="text-xs text-brand-700/50 text-center mt-6 tracking-wide">
          MedPag • Setor de Saúde • Conforme LGPD
        </p>
      </div>
    </div>
  );
}
