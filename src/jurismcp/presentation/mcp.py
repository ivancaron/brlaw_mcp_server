import asyncio
import logging
import textwrap
from typing import Any, Final

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field

from jurismcp.domain.base import BaseLegalPrecedent
from jurismcp.domain.bnp import BnpLegalPrecedent
from jurismcp.domain.jurisprudencias_ai import JurisprudenciasAiLegalPrecedent
from jurismcp.domain.lexml import LexmlLegalPrecedent
from jurismcp.domain.stf import StfLegalPrecedent
from jurismcp.domain.stj import StjLegalPrecedent
from jurismcp.domain.tjes import TjesLegalPrecedent
from jurismcp.domain.tst import TstLegalPrecedent
from jurismcp.utils import browser_factory

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
    """Requisicao dos precedentes judiciais do Tribunal de Justica do Espirito Santo (TJES) que satisfacam os criterios passados.

    O TJES e o orgao de cupula do Poder Judiciario do Estado do Espirito Santo. Julga recursos
    contra decisoes de primeira instancia, incluindo apelacoes civeis e criminais, agravos de
    instrumento, habeas corpus, mandados de seguranca e demais acoes de competencia originaria
    do segundo grau.

    As decisoes do TJES sao particularmente relevantes para a atuacao da Defensoria Publica do
    Estado do Espirito Santo, pois refletem o entendimento local sobre temas como direito penal,
    familia, consumidor, moradia e direitos fundamentais.

    Esta ferramenta pesquisa acordaos colegiados do 2o grau do PJe-TJES."""

    summary: str = Field(
        title="Ementa",
        description=textwrap.dedent("""
        Criterios que serao buscados nas decisoes do TJES.

        A busca e feita por texto livre no banco de dados de acordaos colegiados do 2o grau.
        Os termos sao combinados com AND: TODOS os termos significativos precisam
        aparecer no acordao (conectores como "de"/"do"/"e" sao ignorados). Por isso,
        quanto MAIS termos, MENOS resultados — se vier vazio, remova termos e amplie.

        EXEMPLOS:
        - "dano moral consumidor banco" - acordaos que contenham dano E moral E consumidor E banco
        - "habeas corpus prisao preventiva" - HC sobre prisao preventiva
        - "alimentos provisorios" - decisoes sobre alimentos
        - "usucapiao extraordinaria" - sobre usucapiao

        DICA: comece com 2-3 termos tecnicos distintivos. Para frase exata ou busca
        avancada, use aspas/operadores ("expressao exata", +obrigatorio, -excluir, AND/OR/NOT)
        — nesse caso a query e enviada como voce escreveu, sem reescrita automatica."""),
        min_length=1,
        examples=[
            "dano moral consumidor",
            "habeas corpus prisao preventiva fundamentacao",
            "alimentos provisorios revisional",
            "usucapiao extraordinaria posse mansa",
            "execucao penal progressao regime",
        ],
    )


class LexmlLegalPrecedentsRequest(BaseLegalPrecedentsRequest):
    """Requisição de precedentes judiciais agregados pelo portal LexML (multi-tribunal).

    O LexML (https://www.lexml.gov.br) é a Rede de Informação Legislativa e Jurídica do
    governo brasileiro. Sua busca de jurisprudência é FEDERADA: agrega acórdãos, súmulas e
    orientações jurisprudenciais de muitos tribunais (STF, STJ, TST, TSE, STM, TRFs e
    Tribunais de Justiça estaduais) num único índice.

    Use esta ferramenta quando quiser AMPLITUDE — descobrir precedentes de tribunais que as
    ferramentas dedicadas (STF, STJ, TST, TJES) não cobrem, ou ter uma visão panorâmica de um
    tema em várias cortes de uma só vez. Para profundidade num tribunal específico, prefira a
    ferramenta dedicada daquele tribunal.

    Cada resultado traz metadados (tribunal/órgão de origem, localidade, data), a ementa
    quando o portal a indexa, e o link resolvedor da URN (urn:lex:br:...) que aponta para o
    inteiro teor na fonte oficial."""

    summary: str = Field(
        title="Termos de busca",
        description=textwrap.dedent("""
        Termos a serem buscados na jurisprudência federada do LexML.

        A busca é por palavras-chave (texto livre) sobre ementa e metadados, combinadas com
        operador E implícito. Use termos técnicos do direito brasileiro para resultados mais
        precisos e evite termos genéricos demais.

        EXEMPLOS:
        - "alimentos provisórios execução"
        - "prisão preventiva tráfico fundamentação"
        - "usucapião extraordinária posse"
        - "improbidade administrativa dano ao erário" """),
        min_length=1,
        examples=[
            "alimentos provisórios execução",
            "prisão preventiva tráfico fundamentação",
            "usucapião extraordinária posse",
            "improbidade administrativa dano ao erário",
        ],
    )


class JurisprudenciasAiLegalPrecedentsRequest(BaseLegalPrecedentsRequest):
    """Requisição de precedentes via Jurisprudencias.ai — fonte ADICIONAL multi-tribunal (opcional).

    Fonte de amplitude complementar, agregadora terceirizada (não é raspagem de portal
    oficial). Cobre tribunais que as ferramentas dedicadas NÃO alcançam em profundidade —
    grandes Tribunais de Justiça estaduais (TJSP, TJRS, TJMG, TJPR, TJSC, TJRJ, TJCE, TJGO,
    TJMA, TJMT), Tribunais Regionais Federais (TRF3, TRF4) e o CARF (matéria fiscal). Use-a
    para PRECEDENTE PERSUASIVO de fora do ES e para o CARF em temas tributários.

    NÃO cobre o TJES — para o tribunal-casa use a ferramenta dedicada `TjesLegalPrecedentsRequest`.

    IMPORTANTE: esta fonte só funciona quando o servidor tem a variável de ambiente
    `JURISPRUDENCIAS_AI_TOKEN` configurada (token gerado em jurisprudencias.ai/api-tokens).
    Sem token, a chamada retorna um erro explicativo e as demais fontes seguem funcionando."""

    court: str = Field(
        title="Tribunal",
        description=textwrap.dedent("""
        Identificador do tribunal a ser pesquisado (obrigatório). Ids disponíveis:

        - Superiores/federais: `stf`, `stj`, `tst`, `trf3`, `trf4`
        - Administrativo fiscal: `carf`
        - Tribunais de Justiça estaduais: `tjsp`, `tjrs`, `tjmg`, `tjpr`, `tjsc`,
          `tjrj`, `tjce`, `tjgo`, `tjma`, `tjmt`

        Escolha o tribunal cuja jurisprudência você quer como precedente persuasivo.
        Para STF/STJ/TST prefira as ferramentas dedicadas (mais completas); use aqui
        sobretudo os TJs estaduais e o CARF, que não têm ferramenta própria."""),
        examples=["tjsp", "tjrs", "tjmg", "carf", "trf4"],
        min_length=2,
    )

    summary: str = Field(
        title="Termos de busca",
        description=textwrap.dedent("""
        Termos a serem buscados nas decisões do tribunal escolhido.

        Busca por texto livre. Dica: use 2-4 termos técnicos distintivos. Acentos são
        removidos automaticamente antes do envio (a busca é acento-insensível), então
        `usucapião` e `usucapiao` são equivalentes.

        EXEMPLOS:
        - "usucapiao extraordinaria posse"
        - "prisao preventiva trafico fundamentacao"
        - "dano moral consumidor banco"
        - "ITCMD base de calculo" (com court=carf ou um TJ estadual)"""),
        min_length=1,
        examples=[
            "usucapiao extraordinaria posse",
            "prisao preventiva trafico fundamentacao",
            "dano moral consumidor negativacao indevida",
            "ITCMD base de calculo",
        ],
    )


class BnpLegalPrecedentsRequest(BaseLegalPrecedentsRequest):
    """Requisição de precedentes QUALIFICADOS no BNP — Banco Nacional de Precedentes do CNJ.

    O BNP (bnp.pdpj.jus.br) é o registro oficial do CNJ dos precedentes qualificados de
    60+ tribunais: súmulas, súmulas vinculantes, temas de repercussão geral, temas
    repetitivos, IRDR, IAC, IRR, PUIL, OJ e controle concentrado (ADI/ADC/ADO/ADPF).
    Cobre STF, STJ, TST, STM, TNU, os 27 Tribunais de Justiça estaduais, os 6 TRFs e os
    24 TRTs — inclusive tribunais sem ferramenta dedicada neste servidor.

    QUANDO USAR: para localizar/verificar TESE VINCULANTE ou precedente qualificado —
    "existe tema repetitivo sobre X?", "qual a tese do Tema 1234 do STJ?", "há IRDR
    sobre isso no TJSP?", "a Súmula N segue vigente?". Cada resultado traz a SITUAÇÃO
    viva do precedente (Vigente, Afetado, Cancelado, Superado...).

    LIMITAÇÃO honesta: o BNP devolve a TESE FIXADA (e a questão submetida), NÃO a
    ementa nem o inteiro teor do acórdão. Para acórdãos completos use as ferramentas
    dedicadas (STJ/STF/TST/TJES) ou o LexML. Alguns precedentes (sobretudo ADI/ADPF e
    parte dos IRDR) ainda não têm tese publicada no BNP — o resultado indica isso e a
    situação continua valendo como informação."""

    summary: str = Field(
        title="Termos de busca",
        description=textwrap.dedent("""
            Busca textual livre sobre a tese e a questão submetida dos precedentes
            (campo `buscaGeral` do BNP). Sem operadores documentados — use 2-4 termos
            técnicos distintivos. Pode ser vazia ("") quando a pesquisa for por
            `numero` + `especie` (lookup exato).

            EXEMPLOS:
            - "honorarios fazenda publica"
            - "dissolucao irregular redirecionamento"
            - "juros abusivos taxa media"
            """),
        examples=[
            "fraude execução",
            "honorários fazenda pública",
            "prisão preventiva fundamentação",
        ],
    )

    tribunal: str = Field(
        title="Tribunal",
        description=textwrap.dedent("""
            Sigla BNP do tribunal (opcional). Vazio = TODOS os tribunais com
            precedentes (pesquisa federada).

            Principais siglas: `STF`, `STJ`, `TST`, `STM`, `TNU`, `TJES`, `TJSP`,
            `TJRJ`, `TJMG`, `TJRS`, `TJDF` (aceita `tjdft`), demais TJs (`TJ` + UF),
            `TRF01`..`TRF06` (aceita `trf1`), `TRT01`..`TRT24` (aceita `trt1`)."""),
        examples=["STJ", "STF", "TJES", "trf2"],
        default="",
    )

    especie: str = Field(
        title="Espécie do precedente",
        description=textwrap.dedent("""
            Sigla da espécie (opcional). Vazio = todas. Legenda:

            - `SUM` = Súmula · `SV` = Súmula Vinculante (STF)
            - `RG` = Tema de Repercussão Geral (STF) · `RR` = Tema Repetitivo (STJ)
            - `IRR` = Incidente de Recursos Repetitivos (TST) · `PUIL` = Pedido de
              Uniformização (TNU)
            - `IRDR` = Incidente de Resolução de Demandas Repetitivas · `SIRDR` =
              Suspensão em IRDR · `IAC` = Incidente de Assunção de Competência
            - `OJ` = Orientação Jurisprudencial · `CT` = Controvérsia · `NT` = Nota
              Técnica
            - `ADI`/`ADC`/`ADO`/`ADPF` = controle concentrado (STF)

            Tradução comum: "Tema repetitivo do STJ" → `RR`; "Tema de repercussão
            geral" → `RG`; "Tema do TST" → `IRR`; "Tema da TNU" → `PUIL`."""),
        examples=["SUM", "RR", "RG", "IRDR"],
        default="",
    )

    numero: str = Field(
        title="Número do precedente",
        description=textwrap.dedent("""
            Número do precedente para lookup exato (opcional) — ex.: "1234" para o
            Tema 1234, "375" para a Súmula 375. Combine com `especie` (e `tribunal`,
            para evitar homônimos de outros tribunais). Vazio = sem filtro."""),
        examples=["1234", "375"],
        default="",
    )

    incluir_cancelados: bool = Field(
        title="Incluir cancelados",
        description=(
            "Se True (padrão), precedentes cancelados/superados aparecem com a "
            "situação marcada — importante para detectar superação de tese. "
            "False os oculta."
        ),
        default=True,
    )


_TOOLS_AND_MODELS: Final[
    list[
        tuple[
            Tool,
            type[BaseLegalPrecedent],
            type[StjLegalPrecedentsRequest]
            | type[TstLegalPrecedentsRequest]
            | type[StfLegalPrecedentsRequest]
            | type[TjesLegalPrecedentsRequest]
            | type[LexmlLegalPrecedentsRequest]
            | type[JurisprudenciasAiLegalPrecedentsRequest]
            | type[BnpLegalPrecedentsRequest],
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
        (LexmlLegalPrecedentsRequest, LexmlLegalPrecedent),
        (JurisprudenciasAiLegalPrecedentsRequest, JurisprudenciasAiLegalPrecedent),
        (BnpLegalPrecedentsRequest, BnpLegalPrecedent),
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

    # Extra request fields beyond the common summary/page are forwarded as
    # keyword arguments to research(). For single-court tools this is empty (they
    # only define summary+page), so their research signatures are untouched;
    # multi-court tools (e.g. Jurisprudencias.ai) carry a `court` field that is
    # passed through here. Keeps the "new HTTP court = no dispatcher change" rule
    # for single-court sources while supporting parameterized ones.
    extra = request.model_dump(exclude={"summary", "page"}, exclude_none=True)

    # HTTP-based courts (STJ, TJES, LexML, SAJ, TJRS, ...) set
    # requires_browser=False and are called with browser=None; browser-driven
    # courts (STF, TST) launch Chromium. New HTTP courts need no change here.
    try:
        if not domain_model.requires_browser:
            precedents = await method(
                None,  # pyright: ignore[reportArgumentType] — browser not used
                summary_search_prompt=request.summary,
                desired_page=request.page,
                **extra,
            )
        else:
            async with (
                browser_factory(headless=True) as browser,
                await browser.new_page() as page,
            ):
                precedents = await method(
                    page,
                    summary_search_prompt=request.summary,
                    desired_page=request.page,
                    **extra,
                )
    except Exception as exc:
        _LOGGER.exception("Error calling tool", extra={"tool_name": name})
        tribunal = name.replace("LegalPrecedentsRequest", "").upper()
        return [
            TextContent(
                type="text",
                text=f"[ERRO] {tribunal}: {exc}. Tente novamente com uma query diferente ou mais simples.",
            )
        ]

    return (
        [
            TextContent(type="text", text=precedent.model_dump_json())
            for precedent in precedents
        ]
        if precedents
        else [TextContent(type="text", text="Nenhum resultado encontrado")]
    )


async def _serve() -> None:
    server = Server("jurismcp")

    server.list_tools()(list_tools)
    server.call_tool()(call_tool)

    options = server.create_initialization_options()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)


def serve() -> None:
    """Starts the MCP server."""
    asyncio.run(_serve())
