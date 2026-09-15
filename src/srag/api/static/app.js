"use strict";

const INTERVALO_DE_CONSULTA = 2000;

const elementos = {
  formulario: document.getElementById("formulario"),
  botao: document.getElementById("gerar"),
  erro: document.getElementById("erro-formulario"),
  uf: document.getElementById("uf"),
  janela: document.getElementById("janela"),
  classificacao: document.getElementById("classificacao"),
  observacao: document.getElementById("observacao"),
  verMetricas: document.getElementById("ver-metricas"),
  painelExecucao: document.getElementById("painel-execucao"),
  runId: document.getElementById("run-id"),
  etapas: document.getElementById("etapas"),
  painelResultado: document.getElementById("painel-resultado"),
  relatorio: document.getElementById("relatorio"),
  baixarPdf: document.getElementById("baixar-pdf"),
  guardrails: document.getElementById("lista-guardrails"),
  auditoria: document.getElementById("lista-auditoria"),
  historico: document.getElementById("historico"),
  saude: document.getElementById("saude"),
};

let acompanhamento = null;

document.addEventListener("DOMContentLoaded", () => {
  carregarSaude();
  carregarOpcoes();
  carregarHistorico();
  ligarAbas();
  elementos.formulario.addEventListener("submit", solicitar);
  [elementos.uf, elementos.janela].forEach((campo) =>
    campo.addEventListener("change", atualizarLinkDeMetricas)
  );
});

async function carregarSaude() {
  try {
    const situacao = await buscarJson("/health");
    const detalhes = [situacao.banco, situacao.modelo].filter(Boolean).join(" | ");
    elementos.saude.textContent = `${situacao.status} — ${detalhes}`;
    elementos.saude.classList.add(situacao.status === "ok" ? "ok" : "degradado");
  } catch (erro) {
    elementos.saude.textContent = "serviço indisponível";
    elementos.saude.classList.add("degradado");
  }
}

async function carregarOpcoes() {
  const opcoes = await buscarJson("/api/opcoes");
  for (const uf of opcoes.ufs) {
    elementos.uf.append(new Option(`${uf.nome} (${uf.sigla})`, uf.sigla));
  }
  for (const classificacao of opcoes.classificacoes) {
    elementos.classificacao.append(new Option(classificacao, classificacao));
  }
  atualizarLinkDeMetricas();
}

function atualizarLinkDeMetricas() {
  const parametros = new URLSearchParams({ janela_dias: elementos.janela.value });
  if (elementos.uf.value) {
    parametros.set("uf", elementos.uf.value);
  }
  elementos.verMetricas.href = `/api/metricas?${parametros}`;
}

async function solicitar(evento) {
  evento.preventDefault();
  esconderErro();
  elementos.botao.disabled = true;
  elementos.botao.textContent = "Gerando...";

  const corpo = {
    uf: elementos.uf.value || null,
    janela_dias: Number(elementos.janela.value),
    classificacao_final: elementos.classificacao.value || null,
    observacao: elementos.observacao.value.trim() || null,
  };

  try {
    const resposta = await fetch("/api/relatorios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    if (!resposta.ok) {
      throw new Error(await mensagemDeErro(resposta));
    }
    const { run_id } = await resposta.json();
    iniciarAcompanhamento(run_id);
  } catch (erro) {
    mostrarErro(erro.message);
    liberarBotao();
  }
}

function iniciarAcompanhamento(runId) {
  elementos.runId.textContent = runId;
  elementos.etapas.innerHTML = "<li>solicitação registrada</li>";
  elementos.painelExecucao.hidden = false;
  elementos.painelResultado.hidden = true;

  clearInterval(acompanhamento);
  acompanhamento = setInterval(() => consultar(runId), INTERVALO_DE_CONSULTA);
  consultar(runId);
}

async function consultar(runId) {
  let execucao;
  try {
    execucao = await buscarJson(`/api/relatorios/${runId}`);
  } catch (erro) {
    return;
  }

  desenharEtapas(execucao.etapas || []);

  if (execucao.status === "em_andamento") {
    return;
  }

  clearInterval(acompanhamento);
  liberarBotao();

  if (execucao.status !== "concluido") {
    mostrarErro(execucao.erro || "a execução não foi concluída");
    carregarHistorico();
    return;
  }

  elementos.relatorio.srcdoc = execucao.relatorio_html || "";
  elementos.baixarPdf.href = `/api/relatorios/${runId}/pdf`;
  desenharGuardrails(execucao.guardrails || []);
  await carregarAuditoria(runId);
  elementos.painelResultado.hidden = false;
  carregarHistorico();
}

function desenharEtapas(etapas) {
  if (!etapas.length) {
    return;
  }
  elementos.etapas.innerHTML = "";
  for (const etapa of etapas) {
    const item = document.createElement("li");
    const duracao = etapa.duracao_ms ? ` (${etapa.duracao_ms} ms)` : "";
    item.textContent = `${etapa.etapa} · ${etapa.acao}${duracao}`;
    if (etapa.status === "erro") item.classList.add("erro-etapa");
    if (etapa.status === "bloqueado") item.classList.add("bloqueado");
    elementos.etapas.append(item);
  }
}

function desenharGuardrails(guardrails) {
  elementos.guardrails.innerHTML = "";
  for (const item of guardrails) {
    const linha = elementos.guardrails.insertRow();
    linha.insertCell().textContent = item.guardrail;
    const situacao = linha.insertCell();
    situacao.textContent = item.aprovado ? "aprovado" : "bloqueou";
    situacao.className = `marca ${item.aprovado ? "aprovado" : "reprovado"}`;
    linha.insertCell().textContent = item.detalhe || "—";
  }
}

async function carregarAuditoria(runId) {
  const dados = await buscarJson(`/api/execucoes/${runId}/auditoria`);
  elementos.auditoria.innerHTML = "";
  for (const passo of dados.trilha) {
    const linha = elementos.auditoria.insertRow();
    linha.insertCell().textContent = passo.sequencia;
    linha.insertCell().textContent = passo.etapa;
    linha.insertCell().textContent = passo.acao;
    linha.insertCell().textContent = passo.status;
    linha.insertCell().textContent = passo.duracao_ms ? `${passo.duracao_ms} ms` : "—";
    const tokens = (passo.tokens_entrada || 0) + (passo.tokens_saida || 0);
    linha.insertCell().textContent = tokens ? tokens : "—";
  }
}

async function carregarHistorico() {
  const execucoes = await buscarJson("/api/relatorios?limite=10");
  elementos.historico.innerHTML = "";
  for (const execucao of execucoes) {
    const linha = elementos.historico.insertRow();
    const identificador = linha.insertCell();
    const link = document.createElement("a");
    link.href = "#";
    link.textContent = execucao.run_id;
    link.addEventListener("click", (evento) => {
      evento.preventDefault();
      iniciarAcompanhamento(execucao.run_id);
    });
    identificador.append(link);
    linha.insertCell().textContent = execucao.parametros?.uf || "Brasil";
    linha.insertCell().textContent = execucao.status;
    linha.insertCell().textContent = formatarData(execucao.criada_em);
  }
}

function ligarAbas() {
  for (const aba of document.querySelectorAll(".aba")) {
    aba.addEventListener("click", () => {
      document.querySelectorAll(".aba").forEach((outra) => outra.classList.remove("ativa"));
      document.querySelectorAll(".conteudo-aba").forEach((painel) => (painel.hidden = true));
      aba.classList.add("ativa");
      document.getElementById(aba.dataset.alvo).hidden = false;
    });
  }
}

async function buscarJson(caminho) {
  const resposta = await fetch(caminho);
  if (!resposta.ok) {
    throw new Error(await mensagemDeErro(resposta));
  }
  return resposta.json();
}

async function mensagemDeErro(resposta) {
  try {
    const corpo = await resposta.json();
    if (Array.isArray(corpo.detail)) {
      return corpo.detail.map((item) => item.msg).join("; ");
    }
    return corpo.detail || `erro ${resposta.status}`;
  } catch (erro) {
    return `erro ${resposta.status}`;
  }
}

function formatarData(valor) {
  if (!valor) return "—";
  return new Date(valor).toLocaleString("pt-BR");
}

function mostrarErro(mensagem) {
  elementos.erro.textContent = mensagem;
  elementos.erro.hidden = false;
}

function esconderErro() {
  elementos.erro.hidden = true;
}

function liberarBotao() {
  elementos.botao.disabled = false;
  elementos.botao.textContent = "Gerar relatório";
}
