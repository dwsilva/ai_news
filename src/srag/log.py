import logging


def configurar_logging(verboso: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # As bibliotecas HTTP logam cada requisicao em INFO e isso polui a saida da ingestao.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # O SDK do Gemini avisa sobre function calling automatico em toda chamada estruturada.
    logging.getLogger("google_genai.models").setLevel(logging.ERROR)
