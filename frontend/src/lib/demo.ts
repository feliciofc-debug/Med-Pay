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
  Alerta,
  AprovacaoResponse,
  Cliente,
  ConfiguracaoCobranca,
  ConfiguracaoCusto,
  ContratoConfig,
  ContratoFinanceiro,
  DashboardExecutivo,
  KPIOperacional,
  LoteDetalhe,
  LoteResumo,
  Pagamento,
  ProjecaoMensal,
  RenovacaoProxima,
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

/**
 * Margem do mês anterior (mock fixo só pra simular delta no Dashboard).
 * Em produção isso vem do snapshot histórico do banco.
 */
const margemMesAnterior: Record<string, number> = {
  c1: 71,
  c2: 70,
  c3: 51,
};

// =============================================================================
// Dashboard Executivo — usa o motor de cálculo + dados dos lotes
// =============================================================================

function montarDashboardExecutivo(): DashboardExecutivo {
  const agora = new Date();
  const mesAtual = agora.getMonth();
  const anoAtual = agora.getFullYear();

  const lotesAtivos = lotes.filter((l) => {
    const created = new Date(l.created_at);
    return (
      (created.getMonth() === mesAtual && created.getFullYear() === anoAtual) ||
      l.status === "AGUARDANDO_REVISAO" ||
      l.status === "APROVADO" ||
      l.status === "ENVIADO_BANCO"
    );
  });

  const contratosFinanceiros: ContratoFinanceiro[] = clientes.map((cliente) => {
    const config = contratos.find((c) => c.cliente_id === cliente.id)!;
    const lotesCliente = lotesAtivos.filter((l) => l.cliente.id === cliente.id);
    const pagamentosMes = lotesCliente.reduce(
      (acc, l) => acc + l.total_pagamentos,
      0,
    );

    const receita_mes_centavos = calcularReceitaContrato(
      config.cobranca,
      pagamentosMes,
    );
    const custo_mes_centavos = calcularCustoContrato(
      config.custo,
      receita_mes_centavos,
    );
    const lucro = receita_mes_centavos - custo_mes_centavos;
    const margem_pct =
      receita_mes_centavos > 0
        ? Math.round((lucro / receita_mes_centavos) * 100)
        : 0;
    const margem_delta_pp =
      margem_pct - (margemMesAnterior[cliente.id] ?? margem_pct);

    let saude: ContratoFinanceiro["saude"] = "saudavel";
    if (margem_pct < 40) saude = "critico";
    else if (margem_pct < 55 || margem_delta_pp <= -5) saude = "atencao";

    const ultimaAtividade =
      lotesCliente.length > 0
        ? lotesCliente
            .map((l) => l.created_at)
            .sort()
            .reverse()[0]
        : new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

    return {
      cliente_id: cliente.id,
      cliente_nome: cliente.nome,
      receita_mes_centavos,
      custo_mes_centavos,
      margem_pct,
      margem_delta_pp,
      saude,
      lotes_mes: lotesCliente.length,
      pagamentos_mes: pagamentosMes,
      ultima_atividade: ultimaAtividade,
    };
  });

  const receita_total = contratosFinanceiros.reduce(
    (acc, c) => acc + c.receita_mes_centavos,
    0,
  );
  const custo_total = contratosFinanceiros.reduce(
    (acc, c) => acc + c.custo_mes_centavos,
    0,
  );
  const lucro_total = receita_total - custo_total;
  const margem_media =
    receita_total > 0 ? Math.round((lucro_total / receita_total) * 100) : 0;
  const meta_mes = contratos.reduce(
    (acc, c) => acc + c.meta_mensal_centavos,
    0,
  );

  // Projeção 12 meses — usa receita do mês atual como base e adiciona crescimento
  const meses = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
  ];
  const projecao_12m: ProjecaoMensal[] = [];
  for (let i = -3; i < 9; i++) {
    const data = new Date(anoAtual, mesAtual + i, 1);
    const realizado = i <= 0;
    // crescimento médio 8% ao mês a partir da base
    const fator = realizado
      ? 1 + 0.05 * i // meses passados crescem mais devagar
      : Math.pow(1.08, i);
    const receita = Math.round(receita_total * fator);
    const meta = Math.round(meta_mes * Math.pow(1.05, i));
    projecao_12m.push({
      mes: `${meses[data.getMonth()]}/${String(data.getFullYear()).slice(-2)}`,
      receita_centavos: receita,
      meta_centavos: meta,
      realizado,
    });
  }

  // KPIs operacionais
  const lotes_processados = lotes.filter((l) =>
    ["APROVADO", "ENVIADO_BANCO", "CONCILIADO"].includes(l.status),
  ).length;
  const lotes_aguardando = lotes.filter((l) =>
    l.status === "AGUARDANDO_REVISAO",
  ).length;
  const total_pgto_mes = contratosFinanceiros.reduce(
    (acc, c) => acc + c.pagamentos_mes,
    0,
  );
  const conciliados = lotes.filter((l) => l.status === "CONCILIADO").length;
  const enviados = lotes.filter((l) =>
    ["ENVIADO_BANCO", "CONCILIADO"].includes(l.status),
  ).length;

  const kpis: KPIOperacional = {
    lotes_processados,
    lotes_aguardando,
    tempo_medio_processamento_min: 14,
    taxa_erro_pct: 2.3,
    pagamentos_mes: total_pgto_mes,
    conciliados_pct: enviados > 0
      ? Math.round((conciliados / enviados) * 100)
      : 0,
  };

  // Alertas — derivados dos contratos com saúde ruim
  const alertas: Alerta[] = [];
  for (const contrato of contratosFinanceiros) {
    if (contrato.saude === "critico") {
      alertas.push({
        id: `a-margin-${contrato.cliente_id}`,
        severidade: "critico",
        titulo: `Margem crítica: ${contrato.cliente_nome}`,
        descricao: `Margem caiu pra ${contrato.margem_pct}% (${contrato.margem_delta_pp > 0 ? "+" : ""}${contrato.margem_delta_pp}pp vs mês anterior). Custo operacional desproporcional ao faturamento.`,
        cliente_nome: contrato.cliente_nome,
        acao_sugerida: "Renegociar contrato ou reduzir escopo de processamento",
        created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      });
    } else if (contrato.saude === "atencao" && contrato.margem_delta_pp <= -5) {
      alertas.push({
        id: `a-trend-${contrato.cliente_id}`,
        severidade: "atencao",
        titulo: `Tendência negativa: ${contrato.cliente_nome}`,
        descricao: `Margem em queda — perdeu ${Math.abs(contrato.margem_delta_pp)}pp em 30 dias. Revisar volume e ticket médio.`,
        cliente_nome: contrato.cliente_nome,
        acao_sugerida: "Agendar reunião com o cliente",
        created_at: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
      });
    }
  }
  // Alerta sobre anomalia de valor (mock)
  alertas.push({
    id: "a-anomaly-1",
    severidade: "atencao",
    titulo: "Valor anômalo detectado",
    descricao:
      "Dr. José Silva (Santa Casa) está com R$ 25.000 — média histórica é R$ 2.500. Provável erro de vírgula na linha 47.",
    cliente_nome: "Hospital Santa Casa",
    acao_sugerida: "Pausar lote e confirmar com o cliente",
    created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
  });
  alertas.push({
    id: "a-bank-1",
    severidade: "info",
    titulo: "Itaú com latência elevada",
    descricao:
      "Tempo médio de retorno do Itaú está em 5h hoje (média histórica: 2h). 3 lotes aguardando.",
    cliente_nome: null,
    acao_sugerida: "Avisar clientes afetados sobre o atraso do banco",
    created_at: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
  });

  // Renovações próximas — recomendação derivada da saúde do contrato
  const renovacoes: RenovacaoProxima[] = clientes.map((cliente) => {
    const config = contratos.find((c) => c.cliente_id === cliente.id)!;
    const financeiro = contratosFinanceiros.find(
      (c) => c.cliente_id === cliente.id,
    )!;
    const venc = new Date(config.vencimento);
    const dias = Math.round(
      (venc.getTime() - Date.now()) / (24 * 60 * 60 * 1000),
    );

    let recomendacao: RenovacaoProxima["recomendacao"] = "manter";
    let reajusteSugerido: number | null = null;
    if (financeiro.saude === "critico") {
      recomendacao = "renegociar_urgente";
      reajusteSugerido = 25;
    } else if (financeiro.saude === "atencao") {
      recomendacao = "reajustar";
      reajusteSugerido = 12;
    }

    return {
      cliente_id: cliente.id,
      cliente_nome: cliente.nome,
      vencimento: config.vencimento,
      dias_restantes: dias,
      margem_atual_pct: financeiro.margem_pct,
      recomendacao,
      reajuste_sugerido_pct: reajusteSugerido,
    };
  });

  return {
    periodo: `${meses[mesAtual]}/${anoAtual}`,
    receita_mes_centavos: receita_total,
    custo_mes_centavos: custo_total,
    lucro_mes_centavos: lucro_total,
    margem_media_pct: margem_media,
    lucro_delta_pct: 12, // mock
    meta_mes_centavos: meta_mes,
    meta_atingida_pct: meta_mes > 0
      ? Math.round((receita_total / meta_mes) * 100)
      : 0,
    contratos: contratosFinanceiros,
    projecao_12m,
    kpis,
    alertas,
    renovacoes,
  };
}

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

  // -------- DASHBOARD EXECUTIVO --------
  if (url.endsWith("/api/dashboard/executivo") && method === "get") {
    return makeResponse(config, montarDashboardExecutivo());
  }

  // -------- FALLBACK --------
  return makeResponse(config, { success: true, demo: true });
};
