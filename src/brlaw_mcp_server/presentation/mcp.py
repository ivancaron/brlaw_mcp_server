import asyncio
import logging
import textwrap
from typing import Any, Final

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field

from brlaw_mcp_server.domain.base import BaseLegalPrecedent
from brlaw_mcp_server.domain.stf import StfLegalPrecedent
from brlaw_mcp_server.domain.stj import StjLegalPrecedent
from brlaw_mcp_server.domain.tjes import TjesLegalPrecedent
from brlaw_mcp_server.domain.tst import TstLegalPrecedent
from brlaw_mcp_server.utils import browser_factory, stealth_browser_factory

_LOGGER = logging.getLogger(__name__)


class BaseLegalPrecedentsRequest(BaseModel):
    """Common model for all legal precedents requests."""

    page: int = Field(
        title="Página",
        description=textwrap.dedent("""
            A página dos resultados a ser retornada. 
            
            Cada página contém uma fração dos resultados da pesquisa. A página 1 é a primeira 
            página dos resultados.

            É útil requisitar mais de uma página para conseguir mais informações, se necessário.
            Por exemplo, se os resultados retornados pela página anteriormente requisitada forem 
            pertinentes, mas não satisfatórios, é adequado requisitar a página seguinte para obter 
            mais precedentes relacionados."""),
        ge=1,
        default=1,
    )


class StjLegalPrecedentsRequest(BaseLegalPrecedentsRequest):
    """Requisição dos precedentes judiciais do Superior Tribunal de Justiça (STJ) que satisfaçam os critérios passados.

    O STJ é a instância máxima da justiça brasileira no âmbito infraconstitucional. É a Corte
    responsável por uniformizar a interpretação da lei federal em todo o País.

    Produz decisões que influenciam todos os aspectos da vida cotidiana dos cidadãos, a maioria
    envolvendo causas de competência da chamada Justiça Comum.

    É de sua responsabilidade a solução definitiva de casos civis e criminais que não envolvam
    matéria constitucional, sob reserva do Supremo Tribunal Federal (STF), nem questões afetas ao
    âmbito específico da Justiça do Trabalho, da Justiça Eleitoral ou da Justiça Militar.

    Cabe também ao STJ a apreciação de decisões judiciais emitidas no exterior, entre as quais
    cartas rogatórias, pedidos de homologação de decisões estrangeiras e ações em que há contestação
    de sentença proferida fora do país."""

    summary: str = Field(
        title="Ementa",
        description=textwrap.dedent("""
        Critérios que serão buscados na ementa das decisões desejadas.

        É possível utilizar operadores textuais para aumentar a assertividade da busca. Na ausência 
        de qualquer operador explícito entre duas palavras, o sistema presumirá o operador `e`.
        Ou seja, `supermercado furto veículo` é o mesmo que `supermercado e furto e veículo`.

        ## Operadores lógicos
        ### `e`
        Localiza termos em qualquer ordem ou campo do documento.

        EXEMPLO: supermercado e furto e veículo

        RESULTADO: o sistema buscará documentos que contenham as três palavras, em qualquer ordem ou 
        distância.

        ATENÇÃO: esse é o operador presumido entre duas palavras, quando não houver outro operador 
        explícito. Assim, não é necessário explicitá-lo nesses casos. Por exemplo, `supermercado e 
        furto` é o mesmo que `supermercado furto`.

        ### `ou`
        Localiza um e/ou outro termo. Os termos devem vir sempre entre parênteses.

        EXEMPLO: (carro ou automóvel ou veículo)

        RESULTADO: o sistema buscará documentos que contenham qualquer uma das três palavras.

        ### `não`
        Exclui determinado termo da pesquisa.

        EXEMPLO: (seguro não automóvel)

        RESULTADO: o sistema buscará apenas os documentos que contenham a palavra “seguro”, mas 
        excluirá do resultado aqueles que tragam a palavra “automóvel”.

        ### `mesmo`
        Localiza termos em um mesmo campo do documento.

        EXEMPLO: (FGTS mesmo súmula mesmo civil)

        RESULTADO: o sistema buscará os documentos que contenham as três palavras indicadas, em 
        qualquer ordem ou distância, dentro de um mesmo campo.

        ### `com`
        Localiza termos em um mesmo parágrafo.
        
        EXEMPLO: recurso com STJ com furto com veículo

        RESULTADO: o sistema buscará os documentos que contenham as quatro palavras em qualquer 
        ordem ou distância, dentro do mesmo parágrafo.

        ## Operadores de proximidade
        ### `PROX(N)`
        Localiza termos PROXimos, em qualquer ordem. (N) limita a distância entre os termos pesquisados. 
        O segundo termo poderá ser até a enésima palavra antes ou depois do primeiro termo.

        EXEMPLO: nega prox2 provimento prox5 recursos

        RESULTADO: O sistema buscará os documentos que contenham as três palavras em qualquer ordem, 
        até a distância determinada. No exemplo, serão recuperadas as expressões: “recursos a que se 
        nega provimento” “nega-se provimento ao recurso” “recursos especiais a que se nega provimento”

        ### `ADJ(N)`
        Localiza termos ADJacentes, na ordem estabelecida na pesquisa. (N) limita a distância entre
        os termos pesquisados. O segundo termo poderá ser até a enésima palavra após o primeiro
        termo. adj = adj1 (busca os termos conjugados sem qualquer outra palavra entre eles).

        EXEMPLO: causa adj3 aumento adj2 pena

        RESULTADO: O sistema buscará os documentos que contenham as três palavras, na ordem digitada, 
        até a distância delimitada. Serão resgatadas expressões como: “Causa de aumento de pena” 
        “causas especiais de aumento de pena”

        ## Símbolos auxiliares
        ### `$`
        Substitui vários caracteres, podendo vir no início, meio ou fim da palavra. É possível 
        limitar o número máximo de caracteres utilizando valores numéricos.

        EXEMPLO 1: constitui$

        RESULTADO 1: Constitui; Constituir; Constituído; Constituição.

        EXEMPLO 2: $classificado

        RESULTADO 2: Classificado; Reclassificado; Desclassificado; Não-classificado.

        EXEMPLO 3: des$cao

        RESULTADO 3: Deserção; Descrição; designação.

        EXEMPLO 4: p$3

        RESULTADO 4: PG; Para; PAR; Pode; Pena.

        ### `?`
        Substitui um único carácter, podendo vir no início, meio ou fim da palavra. Cada 
        interrogação corresponde a um carácter.

        EXEMPLO: d?sc?r??

        RESULTADO: Deserção; Descrição; designação; descrição.

        ### `( )`
        Usado para o operador OU e para agrupar itens da pesquisa. A alteração poderá ser feita 
        manualmente.

        EXEMPLO: ((menor ou criança) e infrator) com pena

        RESULTADO: o sistema buscará os documentos que contenham as combinações: menor e infrator 
        com pena ou criança e infrator com pena

        ### `" "`
        Utilizado para transformar um operador em palavra a ser pesquisada e para localizar expressões 
        exatas.

        EXEMPLO: “não” adj previsto “tribunal de origem”

        RESULTADO: o sistema buscará documentos que contenham a expressão “não previsto”. O sistema 
        buscará documentos que contenham a expressão “tribunal de origem”."""),
        min_length=1,
        examples=[
            "supermercado e furto e veículo",
            "(carro ou automóvel ou veículo)",
            "(seguro não automóvel)",
            "(FGTS mesmo súmula mesmo civil)",
            "recurso com STJ com furto com veículo",
            "nega prox2 provimento prox5 recursos",
            "causa adj3 aumento adj2 pena",
            "$classificado",
            "d?sc?r??",
            "((menor ou criança) e infrator) com pena",
            "“não” adj previsto “tribunal de origem”",
        ],
    )


class TstLegalPrecedentsRequest(BaseLegalPrecedentsRequest):
    """Requisição dos precedentes judiciais do Tribunal Superior do Trabalho (TST) que satisfaçam os critérios passados.

    O TST é o órgão de cúpula da Justiça do Trabalho. Tem a função precípua de uniformizar a
    jurisprudência trabalhista brasileira."""

    summary: str = Field(
        title="Ementa",
        description=textwrap.dedent("""
        Critérios que serão buscados na ementa das decisões desejadas.

        É admitido o uso de aspas e elas devem ser empregadas para pesquisas exatas de expressões ou 
        palavras compostas."""),
        min_length=1,
        examples=[
            "trabalho temporário jornada “adicional de periculosidade”",
        ],
    )


class StfLegalPrecedentsRequest(BaseLegalPrecedentsRequest):
    """Requisição dos precedentes judiciais do Supremo Tribunal Federal (STF) que satisfaçam os critérios passados.

    O STF é o órgão máximo do Poder Judiciário brasileiro, e a ele compete, precipuamente, zelar
    pelo cumprimento da Constituição, conforme definido em seu art. 102. Por esse motivo, o STF é
    conhecido como o Guardião da Constituição Federal.

    Entre suas principais atribuições está a de julgar a ação direta de inconstitucionalidade de
    lei ou ato normativo federal ou estadual, a ação declaratória de constitucionalidade de lei ou
    ato normativo federal, a arguição de descumprimento de preceito fundamental decorrente da
    própria Constituição e a extradição solicitada por Estado estrangeiro.

    Na área penal, destaca-se a competência para julgar, nas infrações penais comuns, o presidente
    da República, o vice-presidente, os membros do Congresso Nacional, seus próprios ministros e o
    procurador-geral da República, entre outros."""

    summary: str = Field(
        title="Ementa",
        description=textwrap.dedent("""
        Critérios que serão buscados na ementa das decisões desejadas.

        É possível utilizar operadores textuais para aumentar a assertividade da busca. Na ausência 
        de qualquer operador explícito entre duas palavras, o sistema presumirá o operador `e`.
        Ou seja, `supermercado furto veículo` é o mesmo que `supermercado e furto e veículo`.

        ## `e`
        Todos os termos devem necessariamente aparecer no documento.

        EXEMPLO: direitos E humanos

        ATENÇÃO: por se tratar do operador padrão, não é necessário explicitar o E na expressão de 
        busca.

        ## `ou`
        Ao menos um dos termos deve aparecer no documento.

        EXEMPLO: droga OU entorpecente

        ## `não`
        O termo adjacente não pode aparecer no documento.

        EXEMPLO: prisão NÃO preventiva

        EFEITO: no caso do exemplo, o sistema buscará documentos que envolvam prisões que NÃO sejam 
        preventivas.

        ## `" "`
        Os termos devem aparecer no documento na exata ordem e com a exata grafia indicadas.

        EXEMPLO: "princípio da presunção de inocência"

        ATENÇÃO: os operadores contidos dentro das aspas perdem a função de operador lógico. Assim, 
        `"direitos E humanos"` não é o mesmo que `direitos E humanos`.

        ## `" "~`
        Os termos podem aparecer no documento em qualquer ordem, desde que estejam separados, no 
        máximo, pelo número de palavras indicado após o til.

        EXEMPLO: "provimento cargo"~5

        EFEITO: no caso do exemplo, o sistema buscará quaisquer documentos que contenham as palavras 
        `provimento` e `cargo` separadas por entre zero e cinco palavras. As seguintes expressões 
        seriam consideradas válidas:
        - provimento cargo
        - cargo provimento
        - provimento de cargo
        - cargo teve o seu provimento

        ATENÇÃO: dentro dessa estrutura (aspas duplas + til), os únicos operadores admitidos são o 
        `OU` e os parênteses; todos os demais (`E`, `NÃO`, `~`, `$`, `?`) são anulados.

        ## `~`
        Quando posicionado logo após determinada palavra, o til permite o resgate de documentos que 
        contenham pequenas variações do termo pesquisado.

        O número de variações toleradas depende do número de caracteres do termo pesquisado: 
        - até 3 caracteres, o operador til não produz efeito
        - entre 4 e 6 caracteres, o operador admite 1 variação
        - com mais de 6 caracteres, a busca contempla 2 variações

        Conta-se como 1 variação: 
        - a troca de um caractere por outro (exemplo: de triagem para friagem)
        - a remoção de um caractere (exemplo: de místico para mítico)
        - a inserção de um caractere (exemplo: de recorre para recorrer)
        - a troca de posição de dois caracteres adjacentes (exemplo: de 598356 para 598365)

        EXEMPLO: amaldiçoado~

        EFEITO: no caso do exemplo, o sistema buscará documentos que contenham a palavra 
        `amaldiçoado` e outras que possam ser criadas a partir de até duas variações, pois a 
        palavra-base tem mais de 6 caracteres. As seguintes expressões seriam consideradas válidas:
        - amaldiçoado
        - amaldiçoados
        - amaldiçoada
        - amaldiçoadas

        ## `$`
        O sinal de dólar substitui um, nenhum ou mais de um caractere no início, no meio ou no final 
        do termo.

        EXEMPLO: $classificado

        ## `?`
        O ponto de interrogação substitui um único caractere no início, no meio ou no final do 
        termo.

        EXEMPLO: RE 56394?

        ## `( )`
        Os parênteses indicam a ordem de prioridade das operações, quando utilizado mais de um 
        operador.

        EXEMPLO: direito E (privacidade OU intimidade)

        EFEITO: no caso do exemplo, o sistema buscará documentos que contenham tanto a palavra 
        `direito` quanto uma das duas palavras `privacidade` ou `intimidade`."""),
        min_length=1,
        examples=[
            "direito E (privacidade OU intimidade)",
            "amaldiçoado~",
            "$classificado",
            "RE 56394?",
        ],
    )


class TjesLegalPrecedentsRequest(BaseLegalPrecedentsRequest):
    """Requisição dos precedentes judiciais do Tribunal de Justiça do Espírito Santo (TJES) que satisfaçam os critérios passados.

    O TJES é o órgão de cúpula do Poder Judiciário estadual do Espírito Santo, responsável por julgar
    recursos e ações originárias no âmbito da justiça comum estadual.

    Atua em matéria cível, criminal, família, fazenda pública, entre outras, sendo a última instância
    recursal estadual antes dos tribunais superiores (STJ e STF).

    Os resultados incluem acórdãos colegiados do 2º grau (Câmaras Cíveis, Câmaras Criminais,
    Tribunal Pleno e Turmas Recursais), com ementas e metadados estruturados."""

    summary: str = Field(
        title="Ementa",
        description=textwrap.dedent("""
        Critérios que serão buscados nas decisões do TJES.

        Operadores de busca suportados:

        ## Busca exata
        Use aspas para buscar frases exatas.

        EXEMPLO: "dano moral"

        ## Operadores lógicos
        ### `AND`
        Todos os termos devem aparecer no documento.

        EXEMPLO: contrato AND rescisão

        ### `OR`
        Ao menos um dos termos deve aparecer no documento.

        EXEMPLO: dano OR prejuízo

        ## Curinga
        ### `*`
        Substitui parte de uma palavra para buscar variações.

        EXEMPLO: trabalh* (retorna trabalho, trabalhista, trabalhador, etc.)"""),
        min_length=1,
        examples=[
            '"dano moral"',
            "contrato AND rescisão",
            "habeas corpus AND prisão preventiva",
            "trabalh* AND vínculo",
        ],
    )


_TOOLS_AND_MODELS: Final[
    list[
        tuple[
            Tool,
            type[BaseLegalPrecedent],
            type[StjLegalPrecedentsRequest]
            | type[TstLegalPrecedentsRequest]
            | type[StfLegalPrecedentsRequest]
            | type[TjesLegalPrecedentsRequest],
        ]
    ]
] = [
    (
        Tool(
            name=request_model.__name__,
            description=request_model.__doc__,
            inputSchema=request_model.model_json_schema(),
        ),
        domain_model,
        request_model,
    )
    for request_model, domain_model in [
        (StjLegalPrecedentsRequest, StjLegalPrecedent),
        (TstLegalPrecedentsRequest, TstLegalPrecedent),
        (StfLegalPrecedentsRequest, StfLegalPrecedent),
        (TjesLegalPrecedentsRequest, TjesLegalPrecedent),
    ]
]


async def list_tools() -> list["Tool"]:
    """List all tools available in the MCP server."""
    return [i[0] for i in _TOOLS_AND_MODELS]


async def call_tool(
    name: str,
    arguments: dict[str, "Any"],  # pyright: ignore[reportExplicitAny]
) -> list[TextContent]:
    """Handles a tool call from a MCP client."""
    _LOGGER.info(
        "Received tool call",
        extra={"arguments": arguments, "tool_name": name},
    )

    for tool, domain_model, request_model in _TOOLS_AND_MODELS:
        if tool.name == name:
            request = request_model(**arguments)  # pyright: ignore[reportAny]
            method = domain_model.research
            break
    else:
        raise ValueError(f"Tool {name} not found")

    factory = (
        stealth_browser_factory if domain_model is StjLegalPrecedent else browser_factory
    )

    async with (
        factory(headless=True) as browser,
        await browser.new_page() as page,
    ):
        try:
            precedents = await method(
                page,
                summary_search_prompt=request.summary,
                desired_page=request.page,
            )
        except Exception:
            _LOGGER.exception("Error calling tool", extra={"tool_name": name})
            raise

    return (
        [
            TextContent(type="text", text=precedent.model_dump_json())
            for precedent in precedents
        ]
        if precedents
        else [TextContent(type="text", text="Nenhum resultado encontrado")]
    )


async def _serve() -> None:
    server = Server("brlaw_mcp_server")

    server.list_tools()(list_tools)
    server.call_tool()(call_tool)

    options = server.create_initialization_options()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)


def serve() -> None:
    """Starts the MCP server."""
    asyncio.run(_serve())
