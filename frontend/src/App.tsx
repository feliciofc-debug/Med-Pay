import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "@/hooks/useAuth";
import { Layout } from "@/components/Layout";
import { LandingPage } from "@/pages/LandingPage";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DashboardExecutivoPage } from "@/pages/DashboardExecutivoPage";
import { ContratosPage } from "@/pages/ContratosPage";
import { UploadPage } from "@/pages/UploadPage";
import { LoteDetalhePage } from "@/pages/LoteDetalhePage";
import { LotesListPage } from "@/pages/LotesListPage";
import { AdminUsuariosPage } from "@/pages/AdminUsuariosPage";
import { AdminRelatorioErrosPage } from "@/pages/AdminRelatorioErrosPage";
import { AdminDevolucoesPage } from "@/pages/AdminDevolucoesPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Carregando...
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <Layout>{children}</Layout>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Carregando...
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (user.role !== "ADMIN") {
    return <Navigate to="/app" replace />;
  }
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      {/* Público */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />

      {/* Área autenticada */}
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/executivo"
        element={
          <ProtectedRoute>
            <DashboardExecutivoPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/contratos"
        element={
          <ProtectedRoute>
            <ContratosPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/upload"
        element={
          <ProtectedRoute>
            <UploadPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/lotes"
        element={
          <ProtectedRoute>
            <LotesListPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/lotes/:id"
        element={
          <ProtectedRoute>
            <LoteDetalhePage />
          </ProtectedRoute>
        }
      />

      {/* Área Admin (gestão do BPO) — restrita a role=ADMIN */}
      <Route
        path="/app/admin/usuarios"
        element={
          <AdminRoute>
            <AdminUsuariosPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/relatorio-erros"
        element={
          <AdminRoute>
            <AdminRelatorioErrosPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/devolucoes"
        element={
          <AdminRoute>
            <AdminDevolucoesPage />
          </AdminRoute>
        }
      />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
