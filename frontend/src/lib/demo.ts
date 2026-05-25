// =============================================================================
// MODO DEMO — simula o backend completo dentro do navegador.
// Ativado quando VITE_DEMO_MODE=true OU quando a API real não está acessível.
//
// Use as credenciais:
//   email: demo@medpag.local
//   senha: demo123
// =============================================================================

import type {
  AxiosAdapter,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from "axios";
import type {
  AprovacaoResponse,
  Cliente,
  ConfiguracaoCobranca,
  ConfiguracaoCusto,
  ContratoConfig,
  LoteDetalhe,
  LoteResumo,
  Pagamento,
  User,
} from "@/types";

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

// =============================================================================
// Credenciais demo
// =============================================================================

export const DEMO_CREDENTIALS = [
  { email: "demo@medpag.local", senha: "demo123", role: "ADMIN" as const },
  { email: "operador@medpag.local", senha: "demo123", role: "OPERADOR" as const },
  { email: "aprovador@medpag.local", senha: "demo123", role: "APROVADOR" as const },
];

// =============================================================================
// Estado em memória — simula o banco de dados
// =============================================================================

const demoUser: User = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@medpag.local",
  nome: "Felício (Demo)",
  role: "ADMIN",
  ativo: true,
  created_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
  last_login_at: new Date().toISOString(),
};

const clientes: Cliente[] = [
  {
    id: "c1",
    nome: "Hospital Santa Casa",
    cnpj: "12.345.678/0001-90",
    email_contato: "financeiro@santacasa.com.br",
    ativo: true,
  },
  {
    id: "c2",
    nome: "Clínica VidaPlena",
    cnpj: "98.765.432/0001-10",
    email_contato: "pagamentos@vidaplena.com.br",
    ativo: true,
  },
  {
    id: "c3",
    nome: "Cooperativa MédicaCoop",
    cnpj: "11.222.333/0001-44",
    email_contato: "rh@medicacoop.coop.br",
    ativo: true,
  },
];

function nomesMedicos(): string[] {
  return [
    "Dr. José Silva",
    "Dra. Ana Costa",
    "Dr. Marcos Pereira",
    "Dra. Beatriz Almeida",
    "Dr. Carlos Eduardo Santos",
    "Dra. Helena Ribeiro",
    "Dr. Rafael Mendes",
    "Dra. Juliana Castro",
    "Dr. Felipe Lima",
    "Dra. Mariana Souza",
    "Dr. Bruno Oliveira",
    "Dra. Camila Ferreira",
    "Dr. Eduardo Martins",
    "Dra. Patricia Gomes",
    "Dr. André Cardoso",
    "Dra. Cristina Vieira",
    "Dr. Thiago Correa",
    "Dra. Renata Pimentel",
    "Dr. Vinicius Rocha",
    "Dra. Larissa Nogueira",
  ];
}

function gerarPagamentos(quantidade: number, seed: number): Pagamento[] {
  const nomes = nomesMedicos();
  const pagamentos: Pagamento[] = [];
  for (let i = 0; i < quantidade; i++) {
    const idx = (seed + i) % nomes.length;
    const nome = nomes[idx];
    const valor = 150000 + ((seed * 31 + i * 71) % 80000) * 10; // R$ 1.500 - R$ 9.500
    let status: Pagamento["status"] = "VALIDO";
    let cpfSugerido: string | null = null;
    let codigosErro: string | null = null;
    let mensagens: string | null = null;

    // distribui alguns problemas
    if (i % 23 === 5) {
      status = "CORRIGIVEL";
      cpfSugerido = "111.444.777-35";
      mensagens = "CPF possivelmente inválido — sugestão automática disponível.";
    }
    if (i % 47 === 11) {
      status = "BLOQUEADO";
      codigosErro = "CPF_INVALIDO";
      mensagens = "CPF inválido — necessário corrigir manualmente.";
    }

    pagamentos.push({
      id: `p${seed}-${i}`,
      linha_planilha: i + 2,
      nome,
      cpf_mascarado: `***.${String(100 + ((seed + i) % 900)).padStart(3, "0")}.${String(((seed * 7 + i * 13) % 900) + 100).padStart(3, "0")}-**`,
      cpf_sugerido: cpfSugerido,
      cpf_original: null,
      banco_codigo: i % 17 === 3 ? "341" : "136",
      conta_mascarada: `****-${String(1000 + ((seed * 11 + i) % 9000))}`,
      valor_centavos: valor,
      modalidade: "TED",
      chave_pix: null,
      status,
      codigos_erro: codigosErro,
      mensagens_validacao: mensagens,
    });
  }
  return pagamentos;
}

function calcularTotais(pagamentos: Pagamento[]) {
  return pagamentos.reduce(
    (acc, p) => {
      acc.total_pagamentos += 1;
      acc.valor_total_centavos += p.valor_centavos;
      if (p.status === "VALIDO" || p.status === "APROVADO" || p.status === "PAGO")
        acc.total_validos += 1;
      else if (p.status === "CORRIGIVEL") acc.total_corrigiveis += 1;
      else if (p.status === "BLOQUEADO" || p.status === "REJEITADO")
        acc.total_bloqueados += 1;
      return acc;
    },
    {
      total_pagamentos: 0,
      total_validos: 0,
      total_corrigiveis: 0,
      total_bloqueados: 0,
      valor_total_centavos: 0,
    },
  );
}

function montarLote(
  id: string,
  cliente: Cliente,
  arquivo: string,
  referencia: string,
  status: LoteResumo["status"],
  pagamentos: Pagamento[],
  diasAtras: number,
  aprovado = false,
): LoteDetalhe {
  const totais = calcularTotais(pagamentos);
  const created = new Date(Date.now() - diasAtras * 24 * 60 * 60 * 1000);
  return {
    id,
    cliente: { id: cliente.id, nome: cliente.nome, cnpj: cliente.cnpj },
    nome_arquivo: arquivo,
    referencia,
    status,
    ...totais,
    created_at: created.toISOString(),
    aprovado_at: aprovado
      ? new Date(created.getTime() + 2 * 60 * 60 * 1000).toISOString()
      : null,
    hash_conteudo: `a7f3b9e2${id}c4d8f1`,
    hash_arquivo_cnab: aprovado ? `cnab${id}9f2b1e3` : null,
    nome_arquivo_cnab: aprovado ? `MEDPAG${id.toUpperCase()}.REM` : null,
    pagamentos,
  };
}

const lotes: LoteDetalhe[] = [
  montarLote(
    "l001",
    clientes[0],
    "santa-casa-junho-2026.xlsx",
    "Junho/2026",
    "AGUARDANDO_REVISAO",
    gerarPagamentos(437, 1),
    0,
  ),
  montarLote(
    "l002",
    clientes[1],
    "vidaplena-junho-2026.xlsx",
    "Junho/2026",
    "AGUARDANDO_REVISAO",
    gerarPagamentos(82, 7),
    0,
  ),
  montarLote(
    "l003",
    clientes[2],
    "medicacoop-junho-2026.xlsx",
    "Junho/2026 - 1ª quinzena",
    "APROVADO",
    gerarPagamentos(214, 3),
    1,
    true,
  ),
  montarLote(
    "l004",
    clientes[0],
    "santa-casa-maio-2026.xlsx",
    "Maio/2026",
    "ENVIADO_BANCO",
    gerarPagamentos(412, 5),
    3,
    true,
  ),
  montarLote(
    "l005",
    clientes[1],
    "vidaplena-maio-2026.xlsx",
    "Maio/2026",
    "CONCILIADO",
    gerarPagamentos(78, 9),
    8,
    true,
  ),
  montarLote(
    "l006",
    clientes[2],
    "medicacoop-maio-2026-q2.xlsx",
    "Maio/2026 - 2ª quinzena",
    "CONCILIADO",
    gerarPagamentos(231, 13),
    12,
    true,
  ),
];

// =============================================================================
// Helpers
// =============================================================================

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function makeResponse<T>(
  config: InternalAxiosRequestConfig,
  data: T,
  status = 200,
): AxiosResponse<T> {
  return {
    data,
    status,
    statusText: status === 200 ? "OK" : status === 201 ? "Created" : "Error",
    headers: {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config: config as any,
  };
}

function loteResumoFrom(lote: LoteDetalhe): LoteResumo {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { pagamentos: _p, hash_conteudo: _h, hash_arquivo_cnab: _hc, ...resumo } =
    lote;
  return resumo;
}

// =============================================================================
// Contratos — configuração comercial editável pelo BPO
// =============================================================================

/**
 * Cálculo de receita unificado:
 *   Receita = mensalidade fixa
 *           + (pagamentos do mês × taxa por pagamento)
 *           + (volume médio × percentual de volume)
 * Qualquer campo zerado simplesmente não entra na soma — flexível pra qualquer modelo comercial.
 */
export function calcularReceitaContrato(
  cobranca: ConfiguracaoCobranca,
  pagamentosMes: number,
): number {
  const mensalidade = cobranca.mensalidade_centavos;
  const variavelPgto = pagamentosMes * cobranca.taxa_por_pagamento_centavos;
  const variavelVolume = Math.round(
    (cobranca.volume_medio_mensal_centavos * cobranca.percentual_volume_bp) /
      10_000,
  );
  return mensalidade + variavelPgto + variavelVolume;
}

/**
 * Cálculo de custo:
 *   Custo = custo fixo mensal + (receita × custo variável %)
 */
export function calcularCustoContrato(
  custo: ConfiguracaoCusto,
  receitaCentavos: number,
): number {
  return (
    custo.custo_fixo_mensal_centavos +
    Math.round((receitaCentavos * custo.custo_variavel_pct) / 100)
  );
}

/**
 * Estado em memória dos contratos. Em produção isso vem do banco.
 * Os valores aqui foram calibrados pra um cenário de BPO realista:
 *
 *   • Santa Casa  — 1,20% sobre R$ 2.000.000 movimentados/mês  →  R$ 24.000 receita
 *   • VidaPlena   — 2,50% sobre R$   500.000 movimentados/mês  →  R$ 12.500 receita
 *   • MédicaCoop  — 2,00% sobre R$   800.000 movimentados/mês  →  R$ 16.000 receita
 */
const contratos: ContratoConfig[] = [
  {
    cliente_id: "c1",
    cliente_nome: "Hospital Santa Casa",
    cliente_cnpj: "12.345.678/0001-90",
    cobranca: {
      mensalidade_centavos: 0,
      taxa_por_pagamento_centavos: 0,
      percentual_volume_bp: 120, // 1,20%
      volume_medio_mensal_centavos: 200_000_000, // R$ 2.000.000
    },
    custo: {
      custo_fixo_mensal_centavos: 350_000, // R$ 3.500 (operação dedicada)
      custo_variavel_pct: 20, // 20% de tarifa de banco e infra
    },
    meta_mensal_centavos: 2_400_000, // R$ 24.000
    vencimento: new Date(Date.now() + 18 * 24 * 60 * 60 * 1000).toISOString(),
    ativo: true,
  },
  {
    cliente_id: "c2",
    cliente_nome: "Clínica VidaPlena",
    cliente_cnpj: "98.765.432/0001-10",
    cobranca: {
      mensalidade_centavos: 0,
      taxa_por_pagamento_centavos: 0,
      percentual_volume_bp: 250, // 2,50%
      volume_medio_mensal_centavos: 50_000_000, // R$ 500.000
    },
    custo: {
      custo_fixo_mensal_centavos: 180_000, // R$ 1.800
      custo_variavel_pct: 18,
    },
    meta_mensal_centavos: 1_250_000, // R$ 12.500
    vencimento: new Date(Date.now() + 47 * 24 * 60 * 60 * 1000).toISOString(),
    ativo: true,
  },
  {
    cliente_id: "c3",
    cliente_nome: "Cooperativa MédicaCoop",
    cliente_cnpj: "11.222.333/0001-44",
    cobranca: {
      mensalidade_centavos: 0,
      taxa_por_pagamento_centavos: 0,
      percentual_volume_bp: 200, // 2,00%
      volume_medio_mensal_centavos: 80_000_000, // R$ 800.000
    },
    custo: {
      custo_fixo_mensal_centavos: 750_000, // R$ 7.500 (sangrando: contrato pesado)
      custo_variavel_pct: 35, // tarifas altas: muitos pagamentos pequenos
    },
    meta_mensal_centavos: 1_600_000, // R$ 16.000
    vencimento: new Date(Date.now() + 9 * 24 * 60 * 60 * 1000).toISOString(),
    ativo: true,
  },
];

// =============================================================================
// Dashboard Executivo — REMOVIDO do demo mode.
// O dashboard agora vem 100% do backend real (/api/dashboard/executivo),
// agregando lotes + fichas + contratos persistidos.
// =============================================================================

// =============================================================================
// Adapter principal — intercepta todas as requests do axios
// =============================================================================

let isLoggedIn = false;

export const demoAdapter: AxiosAdapter = async (config) => {
  const fullUrl = config.url ?? "";
  // Separa path de query string
  const [pathRaw, queryRaw] = fullUrl.split("?");
  const path = pathRaw;
  // Combina params da URL string com params do axios config
  const queryParams = new URLSearchParams(queryRaw ?? "");
  if (config.params && typeof config.params === "object") {
    for (const [k, v] of Object.entries(config.params as Record<string, unknown>)) {
      if (v !== undefined && v !== null) queryParams.set(k, String(v));
    }
  }
  const method = (config.method ?? "get").toLowerCase();
  const url = path; // pra usar nos matches sem se preocupar com query

  // Simula latência de rede
  await delay(150 + Math.random() * 250);

  // -------- AUTH --------
  if (url.endsWith("/api/auth/login") && method === "post") {
    let body: { email: string; password: string };
    try {
      body =
        typeof config.data === "string"
          ? JSON.parse(config.data)
          : (config.data ?? {});
    } catch {
      body = { email: "", password: "" };
    }
    const ok = DEMO_CREDENTIALS.some(
      (c) => c.email === body.email && c.senha === body.password,
    );
    if (!ok) {
      return makeResponse(
        config,
        { error: { code: "INVALID_CREDENTIALS", message: "E-mail ou senha incorretos" } },
        401,
      );
    }
    const cred = DEMO_CREDENTIALS.find((c) => c.email === body.email)!;
    isLoggedIn = true;
    demoUser.email = cred.email;
    demoUser.role = cred.role;
    demoUser.last_login_at = new Date().toISOString();
    return makeResponse(config, {
      access_token: "demo-access-token-" + Date.now(),
      refresh_token: "demo-refresh-token-" + Date.now(),
    });
  }

  if (url.endsWith("/api/auth/me") && method === "get") {
    const authHeader =
      config.headers?.Authorization ??
      (config.headers as Record<string, unknown> | undefined)?.authorization;
    const hasToken = typeof authHeader === "string"
      ? authHeader.startsWith("Bearer demo-access-token")
      : false;
    if (!isLoggedIn && !hasToken) {
      return makeResponse(
        config,
        { error: { code: "UNAUTHORIZED", message: "Sessão não encontrada" } },
        401,
      );
    }
    isLoggedIn = true;
    return makeResponse(config, demoUser);
  }

  if (url.endsWith("/api/auth/logout") && method === "post") {
    isLoggedIn = false;
    return makeResponse(config, { success: true });
  }

  if (url.endsWith("/api/auth/refresh") && method === "post") {
    return makeResponse(config, {
      access_token: "demo-access-token-" + Date.now(),
      refresh_token: "demo-refresh-token-" + Date.now(),
    });
  }

  // -------- FICHAS (módulo OCR) --------
  // Em modo demo, retornamos lista vazia: o módulo de fichas exige OCR real.
  if (url.match(/\/api\/fichas\/?$/) && method === "get") {
    return makeResponse(config, [] as unknown[]);
  }
  if (url.match(/\/api\/fichas\/upload$/) && method === "post") {
    return makeResponse(
      config,
      {
        error: {
          code: "DEMO_INDISPONIVEL",
          message:
            "Upload de fichas não disponível no modo demonstração. Conecte-se ao ambiente real para usar o OCR.",
        },
      },
      503,
    );
  }
  if (url.match(/\/api\/fichas\/[^/?]+/) && method === "get") {
    return makeResponse(
      config,
      { error: { code: "NOT_FOUND", message: "Ficha não encontrada (modo demo)" } },
      404,
    );
  }

  // -------- LOTES --------
  if (url.match(/\/api\/lotes\/?$/) && method === "get") {
    const status = queryParams.get("status");
    let filtered = lotes;
    if (status) {
      filtered = lotes.filter((l) => l.status === status);
    }
    // Frontend espera array direto, não envelopado
    return makeResponse(config, filtered.map(loteResumoFrom));
  }

  // -------- CLIENTES --------
  if (url.match(/\/api\/clientes\/?$/) && method === "get") {
    return makeResponse(config, { clientes });
  }

  const matchLoteId = url.match(/\/api\/lotes\/([^/?]+)$/);
  if (matchLoteId && method === "get") {
    const id = matchLoteId[1];
    const lote = lotes.find((l) => l.id === id);
    if (!lote) {
      return makeResponse(
        config,
        { error: { code: "NOT_FOUND", message: "Lote não encontrado" } },
        404,
      );
    }
    return makeResponse(config, lote);
  }

  if (url.endsWith("/api/lotes/upload") && method === "post") {
    // Simula upload e cria lote novo
    const novo = montarLote(
      "l" + Date.now(),
      clientes[Math.floor(Math.random() * clientes.length)],
      `upload-demo-${new Date().toISOString().slice(0, 10)}.xlsx`,
      `Demo ${new Date().toLocaleDateString("pt-BR")}`,
      "AGUARDANDO_REVISAO",
      gerarPagamentos(120 + Math.floor(Math.random() * 300), Date.now() % 1000),
      0,
    );
    lotes.unshift(novo);
    return makeResponse(
      config,
      {
        lote_id: novo.id,
        nome_arquivo: novo.nome_arquivo,
        total_pagamentos: novo.total_pagamentos,
        ja_existia: false,
      },
      201,
    );
  }

  const matchAprovar = url.match(/\/api\/lotes\/([^/]+)\/aprovar$/);
  if (matchAprovar && method === "post") {
    const id = matchAprovar[1];
    const lote = lotes.find((l) => l.id === id);
    if (!lote) {
      return makeResponse(
        config,
        { error: { code: "NOT_FOUND", message: "Lote não encontrado" } },
        404,
      );
    }
    lote.status = "APROVADO";
    lote.aprovado_at = new Date().toISOString();
    lote.hash_arquivo_cnab = `cnab${id}${Date.now()}`;
    const resp: AprovacaoResponse = {
      success: true,
      lote_id: lote.id,
      nome_arquivo: lote.nome_arquivo.replace(/\.\w+$/, ".rem"),
      hash_arquivo: lote.hash_arquivo_cnab,
      quantidade_pagamentos: lote.total_pagamentos,
      valor_total_centavos: lote.valor_total_centavos,
      download_url: `/api/lotes/${lote.id}/cnab`,
    };
    return makeResponse(config, resp);
  }

  const matchCnab = url.match(/\/api\/lotes\/([^/]+)\/cnab$/);
  if (matchCnab && method === "get") {
    const id = matchCnab[1];
    const lote = lotes.find((l) => l.id === id);
    const conteudoFake = [
      `136000010000010001MEDPAG DEMO CNAB`,
      ...Array.from({ length: lote?.total_pagamentos ?? 0 }, (_, i) =>
        `1360001300${String(i + 1).padStart(5, "0")}A000018${"".padEnd(220, " ")}`,
      ),
      `136000159999999999`,
    ].join("\n");
    return makeResponse(config, conteudoFake, 200);
  }

  const matchEnviado = url.match(/\/api\/lotes\/([^/]+)\/marcar-enviado$/);
  if (matchEnviado && method === "post") {
    const id = matchEnviado[1];
    const lote = lotes.find((l) => l.id === id);
    if (lote) lote.status = "ENVIADO_BANCO";
    return makeResponse(config, { success: true });
  }

  // -------- PAGAMENTOS --------
  const matchAceitar = url.match(
    /\/api\/pagamentos\/([^/]+)\/aceitar-sugestao-cpf$/,
  );
  if (matchAceitar && method === "post") {
    const pid = matchAceitar[1];
    for (const lote of lotes) {
      const p = lote.pagamentos.find((x) => x.id === pid);
      if (p) {
        p.status = "VALIDO";
        p.cpf_sugerido = null;
        p.mensagens_validacao = null;
        // recalcula totais
        Object.assign(lote, calcularTotais(lote.pagamentos));
      }
    }
    return makeResponse(config, { success: true });
  }

  // -------- CONTRATOS (configuração comercial editável) --------
  if (url.match(/\/api\/contratos\/?$/) && method === "get") {
    return makeResponse(config, contratos);
  }

  const matchContratoId = url.match(/\/api\/contratos\/([^/?]+)$/);
  if (matchContratoId && method === "get") {
    const id = matchContratoId[1];
    const contrato = contratos.find((c) => c.cliente_id === id);
    if (!contrato) {
      return makeResponse(
        config,
        { error: { code: "NOT_FOUND", message: "Contrato não encontrado" } },
        404,
      );
    }
    return makeResponse(config, contrato);
  }

  if (matchContratoId && method === "put") {
    const id = matchContratoId[1];
    const idx = contratos.findIndex((c) => c.cliente_id === id);
    if (idx === -1) {
      return makeResponse(
        config,
        { error: { code: "NOT_FOUND", message: "Contrato não encontrado" } },
        404,
      );
    }
    let body: Partial<ContratoConfig>;
    try {
      body =
        typeof config.data === "string"
          ? JSON.parse(config.data)
          : (config.data ?? {});
    } catch {
      body = {};
    }
    contratos[idx] = {
      ...contratos[idx],
      ...body,
      cobranca: { ...contratos[idx].cobranca, ...(body.cobranca ?? {}) },
      custo: { ...contratos[idx].custo, ...(body.custo ?? {}) },
    };
    return makeResponse(config, contratos[idx]);
  }

  // -------- FALLBACK --------
  return makeResponse(config, { success: true, demo: true });
};
