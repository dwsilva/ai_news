"""Indice vetorial das noticias.

As materias coletadas viram trechos, os trechos viram embeddings e ficam no proprio Postgres
via pgvector. Nao usei um vector store pronto de biblioteca: sao duas consultas SQL, e ter o
indice numa tabela minha significa que a trilha de auditoria consegue mostrar exatamente qual
trecho de qual materia entrou no contexto de cada comentario.

O volume aqui e pequeno (dezenas de materias por execucao), entao a busca e exaustiva por
distancia de cosseno. Um indice HNSW so faria sentido com ordens de grandeza a mais.
"""

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import text

from srag.config import get_config
from srag.db import engine_escrita, engine_leitura
from srag.noticias.modelos import Artigo, Trecho

logger = logging.getLogger(__name__)

TAMANHO_TRECHO = 900
SOBREPOSICAO = 150


class Embeddings:
    """Fachada sobre o modelo de embeddings do Gemini.

    Existe para que os testes possam injetar uma implementacao falsa sem chamar a API.
    """

    def __init__(self, modelo: str | None = None) -> None:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        cfg = get_config()
        self._cliente = GoogleGenerativeAIEmbeddings(
            model=modelo or cfg.modelo_embedding,
            google_api_key=cfg.google_api_key,
        )

    def documentos(self, textos: list[str]) -> list[list[float]]:
        return self._cliente.embed_documents(textos)

    def pergunta(self, texto: str) -> list[float]:
        return self._cliente.embed_query(texto)


def indexar(run_id: str, artigos: list[Artigo], embeddings: Embeddings | None = None) -> int:
    """Grava as materias e seus trechos. Devolve quantos trechos foram indexados."""
    if not artigos:
        return 0

    embeddings = embeddings or Embeddings()
    divisor = RecursiveCharacterTextSplitter(
        chunk_size=TAMANHO_TRECHO,
        chunk_overlap=SOBREPOSICAO,
        separators=["\n\n", "\n", ". ", " "],
    )

    total = 0
    with engine_escrita().begin() as conexao:
        for artigo in artigos:
            noticia_id = _gravar_noticia(conexao, run_id, artigo)
            trechos = divisor.split_text(artigo.conteudo)
            if not trechos:
                continue
            vetores = embeddings.documentos(trechos)
            _gravar_trechos(conexao, run_id, noticia_id, trechos, vetores)
            total += len(trechos)

    logger.info("indexados %d trechos de %d materias", total, len(artigos))
    return total


def recuperar(
    run_id: str, pergunta: str, quantidade: int = 4, embeddings: Embeddings | None = None
) -> list[Trecho]:
    """Busca os trechos mais proximos da pergunta dentro desta execucao."""
    embeddings = embeddings or Embeddings()
    vetor = _como_vetor(embeddings.pergunta(pergunta))

    consulta = text(
        """
        SELECT t.noticia_id, n.titulo, n.url, n.veiculo, n.publicado_em, t.texto,
               t.embedding <=> CAST(:vetor AS vector) AS distancia
        FROM srag.noticia_trecho t
        JOIN srag.noticia n ON n.id = t.noticia_id
        WHERE t.run_id = :run_id AND n.aceita
        ORDER BY distancia
        LIMIT :quantidade
        """
    )
    with engine_leitura().connect() as conexao:
        linhas = conexao.execute(
            consulta, {"vetor": vetor, "run_id": run_id, "quantidade": quantidade}
        ).all()

    return [Trecho(**linha._mapping) for linha in linhas]


def _gravar_noticia(conexao, run_id: str, artigo: Artigo) -> int:
    return conexao.execute(
        text(
            "INSERT INTO srag.noticia (run_id, url, titulo, veiculo, publicado_em, texto, "
            "aceita, motivo_recusa) "
            "VALUES (:run_id, :url, :titulo, :veiculo, :publicado_em, :texto, :aceita, :motivo) "
            "RETURNING id"
        ),
        {
            "run_id": run_id,
            "url": artigo.url,
            "titulo": artigo.titulo,
            "veiculo": artigo.veiculo,
            "publicado_em": artigo.publicado_em,
            "texto": artigo.conteudo,
            "aceita": artigo.aceito,
            "motivo": artigo.motivo_recusa or None,
        },
    ).scalar_one()


def _gravar_trechos(conexao, run_id, noticia_id, trechos, vetores) -> None:
    conexao.execute(
        text(
            "INSERT INTO srag.noticia_trecho (noticia_id, run_id, ordem, texto, embedding) "
            "VALUES (:noticia_id, :run_id, :ordem, :texto, CAST(:embedding AS vector))"
        ),
        [
            {
                "noticia_id": noticia_id,
                "run_id": run_id,
                "ordem": ordem,
                "texto": trecho,
                "embedding": _como_vetor(vetor),
            }
            for ordem, (trecho, vetor) in enumerate(zip(trechos, vetores, strict=True))
        ],
    )


def _como_vetor(valores: list[float]) -> str:
    """O pgvector aceita o literal no formato '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{valor:.6f}" for valor in valores) + "]"
