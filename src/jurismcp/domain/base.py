"""Base classes and utilities for legal precedents.

This module contains the base classes and utilities used by the legal precedents
domain models, including validation and common fields."""

import textwrap
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from patchright.async_api import Page


class BaseLegalPrecedent(BaseModel):
    """Base class for legal precedents."""

    summary: str = Field(
        title="Ementa",
        description="A ementa da decisão. É a síntese do acórdão, na qual normalmente se resumem os seus pontos fundamentais.",
        examples=[
            textwrap.dedent("""
                TRIBUTÁRIO E PROCESSUAL CIVIL. RECURSO ESPECIAL REPRESENTATIVO DE CONTROVÉRSIA DE NATUREZA REPETITIVA. EXECUÇÃO FISCAL. DISSOLUÇÃO IRREGULAR DA PESSOA JURÍDICA EXECUTADA OU PRESUNÇÃO DE SUA OCORRÊNCIA. SÚMULA 435/STJ. REDIRECIONAMENTO A SÓCIO-GERENTE OU A ADMINISTRADOR. CONDIÇÃO: EXERCÍCIO DA ADMINISTRAÇÃO DA PESSOA JURÍDICA EXECUTADA, NO MOMENTO DE SUA DISSOLUÇÃO IRREGULAR. INEXISTÊNCIA DE EXERCÍCIO DA ADMINISTRAÇÃO, QUANDO DA OCORRÊNCIA DO FATO GERADOR DO TRIBUTO INADIMPLIDO OU DO SEU VENCIMENTO. IRRELEVÂNCIA. RECURSO ESPECIAL PROVIDO.
                I. Recurso Especial, interposto pela Fazenda Nacional, contra acórdão publicado na vigência do CPC/72, aplicando-se, no caso, o Enunciado Administrativo 2/2016, do STJ, aprovado na sessão plenária de 09/03/2016 ("Aos recursos interpostos com fundamento no CPC/1973 (relativos a decisões publicadas até 17 de março de 2016) devem ser exigidos os requisitos de admissibilidade na forma nele prevista, com as interpretações dadas, até então, pela jurisprudência do Superior Tribunal de Justiça").
                II. Trata-se de Recurso Especial, interposto pela Fazenda Nacional, contra acórdão do Tribunal de origem que, ao negar provimento ao Agravo de Instrumento, manteve a decisão que, em Execução Fiscal, havia indeferido o requerimento de inclusão, no polo passivo do feito executivo, de sócios-gerentes que, embora hajam ingressado no quadro social em 03/12/2007, após a ocorrência do fato gerador do tributo inadimplido, de fevereiro de 2003 a janeiro de 2004, detinham poderes de administração da pessoa jurídica executada, à época em que presumida a sua dissolução irregular, em 01/07/2013, quando não localizada no seu domicílio fiscal, conforme certidão do Oficial de Justiça.
                III. O tema ora em apreciação, submetido ao rito dos recursos especiais representativos de controvérsia, nos termos dos arts.
                1.036 a 1.041 do CPC/2015, restou assim delimitado: "À luz do art. 135, III, do CTN, o redirecionamento da Execução Fiscal, quando fundado na hipótese de dissolução irregular da sociedade empresária executada ou de presunção de sua ocorrência (Súmula 435/STJ), pode ser autorizado contra: (i) o sócio com poderes de administração da sociedade, na data em que configurada a sua dissolução irregular ou a presunção de sua ocorrência (Súmula 435/STJ), e que, concomitantemente, tenha exercido poderes de gerência, na data em que ocorrido o fato gerador da obrigação tributária não adimplida;
                ou (ii) o sócio com poderes de administração da sociedade, na data em que configurada a sua dissolução irregular ou a presunção de sua ocorrência (Súmula 435/STJ), ainda que não tenha exercido poderes de gerência, na data em que ocorrido o fato gerador do tributo não adimplido".
                IV. No exercício da atividade econômica, ocorre amiúde, em razão de injunções várias, o inadimplemento de obrigações assumidas por pessoas jurídicas. Não é diferente na esfera tributária. Embora se trate inegavelmente de uma ofensa a bem jurídico da Administração tributária, o desvalor jurídico do inadimplemento não autoriza, por si só, a responsabilização do sócio-gerente. Nesse sentido, aliás, o enunciado 430 da Súmula do STJ - em cuja redação se lê que "o inadimplemento da obrigação tributária pela sociedade não gera, por si só, a responsabilidade solidária do sócio-gerente" -, bem como a tese firmada no REsp repetitivo 1.101.728/SP (Rel. Ministro TEORI ZAVASCKI, PRIMEIRA SEÇÃO, DJe de 23/03/2009), que explicita que "a simples falta de pagamento do tributo não configura, por si só, nem em tese, circunstância que acarreta a responsabilidade subsidiária do sócio, prevista no art. 135 do CTN. É indispensável, para tanto, que tenha agido com excesso de poderes ou infração à lei, ao contrato social ou ao estatuto da empresa" (Tema 97 do STJ).
                V. Tal conclusão é corolário da autonomia patrimonial da pessoa jurídica. Se, nos termos do art. 49-A, caput, do Código Civil, incluído pela Lei 13.874/2019, "a pessoa jurídica não se confunde com os seus sócios, associados, instituidores ou administradores", decorre que o simples inadimplemento de tributos não pode gerar, por si só, consequências negativas no patrimônio dos sócios. Como esclarece o parágrafo único do aludido artigo, a razão de ser da autonomia patrimonial, "instrumento lícito de alocação e segregação de riscos", é "estimular empreendimentos, para a geração de empregos, tributo, renda e inovação em benefício de todos".
                Naturalmente, a autonomia patrimonial não é um fim em si, um direito absoluto e inexpugnável. Por isso mesmo, a legislação, inclusive a civil, comercial, ambiental e tributária estabelece hipóteses de responsabilização dos sócios e administradores por obrigações da pessoa jurídica. No Código Tributário Nacional, entre outras hipóteses, destaca-se a do inciso III do seu art. 135, segundo o qual "são pessoalmente responsáveis pelos créditos correspondentes a obrigações tributárias resultantes de atos praticados com excesso de poderes ou infração de lei, contrato social ou estatutos (...) os diretores, gerentes ou representantes de pessoas jurídicas de direito privado".
                VI. A jurisprudência do Superior Tribunal de Justiça há muito consolidou o entendimento no sentido de que "a não-localização da empresa no endereço fornecido como domicílio fiscal gera presunção iuris tantum de dissolução irregular", o que torna possível a "responsabilização do sócio-gerente a quem caberá o ônus de provar não ter agido com dolo, culpa, fraude ou excesso de poder" (EREsp 852.437/RS, Rel. Ministro CASTRO MEIRA, PRIMEIRA SEÇÃO, DJe de 03/11/2008). A matéria, inclusive, é objeto do enunciado 435 da Súmula do STJ: "Presume-se dissolvida irregularmente a empresa que deixar de funcionar no seu domicílio fiscal, sem comunicação aos órgãos competentes, legitimando o redirecionamento da execução fiscal para o sócio-gerente".
                VII. O Plenário do STF, ao julgar, sob o regime de repercussão geral, o Recurso Extraordinário 562.276/PR (Rel. Ministra ELLEN GRACIE, TRIBUNAL PLENO, DJe de 10/02/2011), correspondente ao tema 13 daquela Corte, deixou assentado que "essencial à compreensão do instituto da responsabilidade tributária é a noção de que a obrigação do terceiro, de responder por dívida originariamente do contribuinte, jamais decorre direta e automaticamente da pura e simples ocorrência do fato gerador do tributo (...) O pressuposto de fato ou hipótese de incidência da norma de responsabilidade, no art. 135, III, do CTN, é a prática de atos, por quem esteja na gestão ou representação da sociedade com excesso de poder ou infração à lei, contrato social ou estatutos e que tenham implicado, se não o surgimento, ao menos o inadimplemento de obrigações tributárias".
                VIII. No Recurso Especial repetitivo 1.371.128/RS (Rel. Ministro MAURO CAMPBELL MARQUES, DJe de 17/09/2014), sob a rubrica do tema 630, a Primeira Seção do STJ assentou a possibilidade de redirecionamento da execução fiscal ao sócio-gerente, nos casos de dissolução irregular da pessoa jurídica executada, não apenas nas execuções fiscais de dívida ativa tributária, mas também nas de dívida ativa não tributária. O voto condutor do respectivo acórdão registrou que a Súmula 435/STJ "parte do pressuposto de que a dissolução irregular da empresa é causa suficiente para o redirecionamento da execução fiscal para o sócio-gerente" e que "é obrigação dos gestores das empresas manter atualizados os respectivos cadastros, incluindo os atos relativos à mudança de endereço dos estabelecimentos e, especialmente, referentes à dissolução da sociedade. A regularidade desses registros é exigida para que se demonstre que a sociedade dissolveu-se de forma regular, em obediência aos ritos e formalidades previstas nos arts. 1.033 a 1.038 e arts. 1.102 a 1.112, todos do Código Civil de 2002 - onde é prevista a liquidação da sociedade com o pagamento dos credores em sua ordem de preferência - ou na forma da Lei 11.101/2005, no caso de falência. A desobediência a tais ritos caracteriza infração à lei".
                IX. No âmbito da Primeira Turma do STJ está consolidado entendimento no sentido de que, "embora seja necessário demonstrar quem ocupava o posto de gerente no momento da dissolução, é necessário, antes, que aquele responsável pela dissolução tenha sido também, simultaneamente, o detentor da gerência na oportunidade do vencimento do tributo". Isso porque "só se dirá responsável o sócio que, tendo poderes para tanto, não pagou o tributo (daí exigir-se seja demonstrada a detenção de gerência no momento do vencimento do débito) e que, ademais, conscientemente optou pela irregular dissolução da sociedade (por isso, também exigível a prova da permanência no momento da dissolução irregular)" (STJ, AgRg no REsp 1.034.238/SP, Rel. Ministra DENISE ARRUDA, PRIMEIRA TURMA, DJe de 04/05/2009). No mesmo sentido, os seguintes precedentes: STJ, AgRg no AREsp 647.563/PE, Rel. Ministro NAPOLEÃO NUNES MAIA FILHO, PRIMEIRA TURMA, DJe de 17/11/2020; AgInt no REsp 1.569.844/SP, Rel. Ministro BENEDITO GONÇALVES, PRIMEIRA TURMA, DJe de 04/10/2016;
                AREsp 838.948/SC, Rel. Ministro GURGEL DE FARIA, PRIMEIRA TURMA, DJe de 19/10/2016; AgInt no REsp 1.602.080/SP, Rel. Ministra REGINA HELENA COSTA, PRIMEIRA TURMA, DJe de 21/09/2016; AgInt no AgInt no AREsp 856.173/SC, Rel. Ministro SÉRGIO KUKINA, PRIMEIRA TURMA, DJe de 22/09/2016.
                X. A Segunda Turma do STJ, embora, num primeiro momento, adotasse entendimento idêntico, no sentido de que "não é possível o redirecionamento da execução fiscal em relação a sócio que não integrava a sociedade à época dos fatos geradores e no momento da dissolução irregular da empresa executada" (STJ, AgRg no AREsp 556.735/MG, Rel. Ministro HUMBERTO MARTINS, SEGUNDA TURMA, DJe de 06/10/2014), veio, posteriormente, a adotar ótica diversa. Com efeito, no julgamento, em 16/06/2015, do REsp 1.520.257/SP, de relatoria do Ministro OG FERNANDES (DJe de 23/06/2015), a Segunda Turma, ao enfrentar hipótese análoga à ora em julgamento, passou a condicionar a responsabilização pessoal do sócio-gerente a um único requisito, qual seja, encontrar-se o referido sócio no exercício da administração da pessoa jurídica executada no momento de sua dissolução irregular ou da prática de ato que faça presumir a dissolução irregular. O fundamento para tanto consiste na conjugação do art. 135, III, do CTN com o enunciado 435 da Súmula do Superior Tribunal de Justiça. De fato, na medida em que a hipótese que desencadeia a responsabilidade tributária é a infração à lei, evidenciada pela dissolução irregular da pessoa jurídica executada, revela-se indiferente o fato de o sócio-gerente responsável pela dissolução irregular não estar na administração da pessoa jurídica à época do fato gerador do tributo inadimplido. Concluiu a Segunda Turma, no aludido REsp 1.520.257/SP, alterando sua jurisprudência sobre o assunto, que "o pedido de redirecionamento da execução fiscal, quando fundado na dissolução irregular ou em ato que presuma sua ocorrência - encerramento das atividades empresariais no domicílio fiscal, sem comunicação aos órgãos competentes (Súmula 435/STJ) -, pressupõe a permanência do sócio na administração da sociedade no momento dessa dissolução ou do ato presumidor de sua ocorrência, uma vez que, nos termos do art. 135, caput, III, CTN, combinado com a orientação constante da Súmula 435/STJ, o que desencadeia a responsabilidade tributária é a infração de lei evidenciada na existência ou presunção de ocorrência de referido fato. Consideram-se irrelevantes para a definição da responsabilidade por dissolução irregular (ou sua presunção) a data da ocorrência do fato gerador da obrigação tributária, bem como o momento em que vencido o prazo para pagamento do respectivo débito".
                Após a mudança jurisprudencial, o novo entendimento foi reafirmado noutras oportunidades: STJ, REsp 1.726.964/RJ, Rel. Ministro HERMAN BENJAMIN, SEGUNDA TURMA, DJe de 21/11/2018; AgInt no AREsp 948.795/AM, Rel. Ministro FRANCISCO FALCÃO, SEGUNDA TURMA, DJe de 21/08/2017; AgRg no REsp 1.541.209/PE, Rel. Ministra ASSUSETE MAGALHÃES, SEGUNDA TURMA, DJe de 11/05/2016; AgRg no REsp 1.545.342/GO, Rel. Ministro MAURO CAMPBELL MARQUES, SEGUNDA TURMA, DJe de 28/09/2015.
                XI. Além das pertinentes considerações feitas pelo Ministro OG FERNANDES, no sentido de que o fato ensejador da responsabilidade tributária é a dissolução irregular da pessoa jurídica executada ou a presunção de sua ocorrência - o que configura infração à lei, para fins do art. 135, III, do CTN -, é preciso observar que a posição da Primeira Turma pode gerar uma estrutura de incentivos não alinhada com os valores subjacentes à ordem tributária, sobretudo o dever de pagar tributos. Com efeito, o entendimento pode criar situação em que, mesmo diante da ocorrência de um ilícito, previsto no art. 135, III, do CTN, inexistirá sanção, em hipótese em que, sendo diversos os sócios-gerentes ou administradores, ao tempo do fato gerador do tributo inadimplido e ao tempo da dissolução irregular da pessoa jurídica executada, a responsabilidade tributária não poderia ser imputada a qualquer deles.
                XII. Ademais, o entendimento da Segunda Turma encontra respaldo nas razões de decidir do Recurso Especial repetitivo 1.201.993/SP (Rel.
                Ministro HERMAN BENJAMIN, PRIMEIRA SEÇÃO, DJe de 12/12/2019), no qual se discutiu a prescrição para o redirecionamento da execução fiscal e no qual o Relator consignou que "o fundamento que justificou a orientação adotada é que a responsabilidade tributária de terceiros, para os fins do art. 135 do CTN, pode resultar tanto do ato de infração à lei do qual resulte diretamente a obrigação tributária, como do ato infracional praticado em momento posterior ao surgimento do crédito tributário que inviabilize, porém, a cobrança do devedor original. (...) ou seja, a responsabilidade dos sócios com poderes de gerente, pelos débitos empresariais, pode decorrer tanto da prática de atos ilícitos que resultem no nascimento da obrigação tributária como da prática de atos ilícitos ulteriores à ocorrência do fato gerador que impossibilitem a recuperação do crédito tributário contra o seu devedor original".
                XIII. Tese jurídica firmada: "O redirecionamento da execução fiscal, quando fundado na dissolução irregular da pessoa jurídica executada ou na presunção de sua ocorrência, pode ser autorizado contra o sócio ou o terceiro não sócio, com poderes de administração na data em que configurada ou presumida a dissolução irregular, ainda que não tenha exercido poderes de gerência quando ocorrido o fato gerador do tributo não adimplido, conforme art. 135, III, do CTN."
                XIV. Caso concreto: Recurso Especial provido.
                XV. Recurso julgado sob a sistemática dos recursos especiais representativos de controvérsia (art. 1.036 e seguintes do CPC/2015 e art. 256-N e seguintes do RISTJ).
                (REsp n. 1.643.944/SP, relatora Ministra Assusete Magalhães, Primeira Seção, julgado em 25/5/2022, DJe de 28/6/2022.)""")
        ],
        min_length=1,
    )
    """The summary of the legal precedent."""

    full_text: str | None = Field(
        default=None,
        title="Inteiro teor",
        description=(
            "Texto integral do acórdão (ementa + relatório + voto + dispositivo), quando "
            "disponibilizado pelo portal do tribunal na mesma resposta da pesquisa. None "
            "quando o tribunal não expõe esse conteúdo na busca, exigindo requisição "
            "adicional ou consulta processual com credencial."
        ),
    )
    """The full text of the decision when available from the court's search response."""

    full_text_url: str | None = Field(
        default=None,
        title="URL do inteiro teor",
        description=(
            "URL absoluta do inteiro teor do acórdão (PDF, HTML ou página de "
            "detalhes da decisão). Útil quando o tribunal expõe o link para "
            "download/visualização mas não devolve o texto direto na resposta "
            "da pesquisa. Ex.: STJ retorna PDF em "
            "https://processo.stj.jus.br/SCON/GetInteiroTeorDoAcordao?... ; STF "
            "retorna a página de detalhamento em "
            "https://jurisprudencia.stf.jus.br/pages/search/.../false. None "
            "quando o tribunal não expõe esse link no resultado da busca."
        ),
    )
    """The URL pointing to the full text of the decision (PDF or HTML), when exposed by the court."""

    relator_original: str | None = Field(
        default=None,
        title="Relator original",
        description=(
            "Nome do relator original do recurso, quando diferente do redator do "
            "acórdão. Útil em casos de divergência vencedora, onde o portal do "
            "tribunal indexa o acórdão pelo redator (voto vencedor) e não pelo "
            "relator originário. None quando o relator é o próprio redator do "
            "acórdão (caso comum, sem divergência)."
        ),
    )
    """The original rapporteur's name when the decision was decided by a winning dissent."""

    divergencia_vencedora: bool = Field(
        default=False,
        title="Divergência vencedora",
        description=(
            "True quando o acórdão foi decidido por voto vencedor inaugurado por "
            "divergência (o redator do acórdão venceu o relator original). False "
            "no caso comum em que o relator e o redator são a mesma pessoa."
        ),
    )
    """True when the decision was rendered by a winning dissent."""

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, v: str) -> str:
        """Validate the summary of the legal precedent."""
        return v.strip()

    @classmethod
    async def research(
        cls,
        browser: "Page",  # pyright: ignore[reportUnusedParameter]
        *,
        summary_search_prompt: str,  # pyright: ignore[reportUnusedParameter]
        desired_page: int = 1,  # pyright: ignore[reportUnusedParameter]
    ) -> "Sequence[Self]":
        """Scrape legal precedents from the Court's search engine.

        :param browser: The browser to use.
        :param summary_search_prompt: The summary to search for.
        :param desired_page: The page of results to scrape.
        :return: A list of legal precedents."""
        raise NotImplementedError("This method must be implemented by the subclass.")
