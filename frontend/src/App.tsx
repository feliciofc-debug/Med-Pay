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

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
