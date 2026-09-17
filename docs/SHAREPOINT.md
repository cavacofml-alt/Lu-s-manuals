# Melhorar as respostas do Copilot sobre a documentação no SharePoint

Direção adoptada em substituição da aplicação autónoma. Este documento é o plano de
trabalho; não requer programação.

A tese que o orienta, reformulada após auditoria externa que mostrou a primeira versão
demasiado categórica:

> **A recuperação está fortemente limitada pela qualidade, estrutura e seleção da
> biblioteca. As instruções e a configuração do agente podem melhorar significativamente a
> escolha das fontes e o comportamento da resposta, mas não substituem uma biblioteca bem
> organizada.**

A diferença face à formulação anterior — "a biblioteca determina, as instruções não contam"
— não é de ênfase. São três camadas distintas, e eu tinha colapsado as duas primeiras:

| Camada | O que controla |
|---|---|
| Conteúdo e documentos | O que **pode** ser recuperado |
| Metadados, estrutura, *knowledge sources* | O que é **mais provável** ser selecionado |
| Instruções e orquestração | Como o agente **decide usar** o que recuperou |

A camada do meio é a que eu tinha subestimado: no Copilot Studio, o nome e a descrição de
uma *knowledge source* influenciam a seleção feita pela orquestração generativa. Isso é
configuração, não conteúdo, e atua **antes** da resposta — não depois.

O que continua verdadeiro: nenhuma instrução cria evidência que não existe, e nenhuma
impede o sistema de recuperar uma release antiga que esteja no índice ativo. A secção 5
mede as camadas em separado em vez de as assumir.

---

## 1. Higiene da biblioteca — a intervenção de maior retorno

### 1.1 Retirar as versões antigas do conhecimento ativo

Continua a ser a intervenção de maior retorno. Mas **"arquivar" precisa de ser definido**,
porque as formas possíveis não são equivalentes e só uma tem efeito documentado sobre a
recuperação.

| Estratégia | Efeito sobre o Copilot |
|---|---|
| Pasta `/arquivo` na mesma biblioteca | **Nenhum garantido.** O conteúdo continua no índice ativo |
| Coluna `Estado = Substituído` | **Nenhum garantido.** É um sinal, não uma exclusão |
| **Site ou biblioteca separada**, fora das fontes do agente | Eficaz **se** houver um agente com fontes definidas |
| **Microsoft 365 Archive** | **Exclusão documentada.** Ficheiros arquivados ficam fora do *grounding* do Copilot e não são por ele pesquisáveis |

A última é a descoberta útil desta auditoria, e está verificada na documentação da
Microsoft: o conteúdo arquivado é retirado do índice ativo precisamente para não diluir as
respostas.

#### Mas há uma tensão que é preciso decidir, não contornar

As duas estratégias eficazes **não são complementares — são alternativas**, e a diferença
importa:

- **Microsoft 365 Archive** retira o conteúdo do Copilot **por completo**. A mistura de
  releases desaparece. Mas a pergunta legítima *"como é que isto se fazia na 7.2?"* deixa de
  ter resposta possível, porque o conteúdo já não é pesquisável.
- **Site separado + *knowledge source* dedicada** mantém o histórico acessível e scoped:
  uma fonte "atual" e uma "histórica", com descrições que orientam a orquestração a escolher
  a segunda apenas quando a pergunta o pedir explicitamente. Em troca, o histórico continua
  no índice — a separação depende da orquestração escolher bem, não de o conteúdo estar
  ausente.

A decisão depende de uma pergunta que a organização tem de responder: **alguém precisa de
consultar releases antigas através do Copilot?**

- Se não — Microsoft 365 Archive, e o problema fica estruturalmente resolvido.
- Se sim — site separado com fontes scoped, e a correção passa a depender de configuração
  que tem de ser medida.

Note-se também que o arquivo ao nível do ficheiro era ainda funcionalidade em pré-visualização
à data desta análise; convém confirmar o estado atual antes de desenhar o processo em cima
dela.

### 1.2 Metadados

Colunas a criar na biblioteca. São o mesmo modelo que a aplicação teria usado — a
modelação não se perde por mudarmos de veículo.

| Coluna | Tipo | Valores | Para quê |
|---|---|---|---|
| `Release` | Escolha | 7.1, 7.2, 7.3, 7.4 … | Filtrar e desambiguar |
| `TipoDocumento` | Escolha | Manual, Guia rápido, Procedimento operacional, Release notes, Formação | Autoridade relativa |
| `Estado` | Escolha | **Em vigor**, Substituído, Rascunho | O filtro que separa o que vale do que não vale |
| `DataEntradaVigor` | Data | | Resolver conflitos por recência |
| `Sistema` / `Área` | Escolha | ADL, PNL, … | Reduzir o espaço de pesquisa |
| `Proprietário` | Pessoa | | Quem confirma quando há dúvida |

Duas regras de utilização:

- **`Estado` é obrigatório.** Um documento sem estado deve ser tratado como suspeito.
- A vista por omissão da biblioteca filtra `Estado = Em vigor`. O que as pessoas veem por
  omissão deve ser o que o Copilot vê.

### 1.3 Títulos e ficheiros

O título é um dos sinais mais fortes na recuperação. Convenção sugerida:

```
ADL — Manual de Check-in — R7.4.pdf
PNL — Procedimento de Reprocessamento — R7.4.pdf
```

A evitar: `manual_v2_final_REV(3).pdf`, dois documentos com o mesmo título em releases
diferentes na mesma biblioteca, e PDFs digitalizados sem texto pesquisável — estes últimos
são invisíveis para o Copilot e precisam de OCR antes de entrar.

### 1.4 Estrutura interna

Não é preciso reescrever manuais, mas onde for barato:

- Cabeçalhos reais (estilos do Word), não texto a negrito. É o que permite localizar secções.
- Procedimentos numerados, um passo por linha.
- Legendas nos screenshots (`Figura 4 — Ecrã de check-in ADL`). Sem legenda, uma imagem é
  invisível para qualquer sistema de pesquisa.
- Um glossário de acrónimos num documento próprio, indexado.

---

## 2. Agente declarativo do Copilot

Um agente permite limitar o âmbito e definir comportamento. Requer Copilot Studio e
permissões de administração do M365 — a confirmar com quem administra o tenant.

**Âmbito:** apenas a biblioteca "Documentação atual". Nada mais.

**Instruções sugeridas** (a colar na configuração do agente):

> És um assistente de documentação operacional. Respondes exclusivamente com base nos
> documentos da biblioteca indexada.
>
> Regras:
>
> 1. Se os documentos não suportarem a resposta, diz exatamente: "Não encontrei informação
> suficiente na documentação disponível para responder a isto com fiabilidade." Não
> completes com conhecimento geral nem com suposições sobre como o sistema funciona.
> 2. Indica sempre o documento de onde vem a informação, e a release, se constar.
> 3. Nunca combines informação de releases diferentes numa única resposta. Se encontrares
> versões em conflito, apresenta as duas e identifica qual é a mais recente.
> 4. Não inventes nomes de botões, ecrãs, campos ou mensagens de erro. Usa apenas os que
> aparecem literalmente na documentação.
> 5. Para procedimentos, apresenta passos numerados pela ordem exata do documento. Não
> reordenes nem resumas passos.
> 6. Termos técnicos, códigos e estados (por exemplo `PNL NOT PROCESSED`) devem ser citados
> exatamente como aparecem, sem tradução nem reformulação.
> 7. Se a pergunta for ambígua quanto à release, pergunta qual antes de responder.
>
> Formato: resposta curta, depois passos se aplicável, depois avisos, depois a origem.

A regra 1 é a que mais importa e a que menos fiabilidade tem. Instruções reduzem a invenção
mas não a eliminam — ver secção 4.

---

## 3. O que isto não resolve

Registado para não haver surpresas mais tarde:

| Requisito do briefing | Estado nesta abordagem |
|---|---|
| Citar a página exata e abrir o documento nela (§23, §49-I/J) | **Suportado** em Copilot Studio, para PDFs via SharePoint — a validar no corpus real |
| *Interpretar* uma tabela ou imagem anotada para responder | **Suportado**, incluindo imagens anotadas em PDF — a validar |
| *Mostrar* o screenshot original dentro da resposta (§5, §6, §49-K) | **Não atingível** |
| Comparar automaticamente o que mudou entre releases (§10) | **Não atingível** — mitigável escrevendo o documento do §7.2 |
| Garantir a recusa quando falta evidência (§14, §49-O) | Melhora, sem garantia |
| Preferir a release atual (§9, §49-N) | Atingível **via arquivo**, não via instruções |
| Export PDF/email estruturado (§25, §26) | Fora de âmbito |

**Esta tabela encolheu duas vezes, e nas duas eu tinha sido categórico a mais.**

A correção maior é a das **citações por página**: verificado que, no Copilot Studio, um PDF
adicionado pelo caminho do SharePoint gera uma citação que aponta para a página onde está a
informação e abre o documento nessa página. Era o requisito §49-I/J, que eu dei por
impossível duas vezes seguidas. **Está suportado.**

Isto muda a avaliação global desta abordagem mais do que qualquer outra descoberta: dos três
requisitos que eu classificava como perdidos, um está disponível e outro (interpretar tabelas
e imagens anotadas) está suportado e por validar. O que resta genuinamente fora de alcance:

- **Mostrar a imagem original dentro da resposta.** Interpretar o conteúdo de uma imagem
  para responder é uma coisa; devolver o screenshot em si, como o §6 exigia, é outra.
- **Comparar automaticamente releases**, que exige alinhar secções entre versões. Mitigável
  escrevendo o documento do §7.2 à mão.

**Consequência prática:** as citações por página dependem do Copilot Studio e do caminho
certo de configuração. A pergunta "existe licenciamento de Copilot Studio?" deixa de ser um
detalhe sobre o agente e passa a ser o que decide se o requisito mais valioso do briefing
está ou não ao alcance. Passa ao topo das decisões pendentes.

---

## 4. Como saber se chega — e isto continua a ser necessário

A parte do trabalho original que **não** deve ser abandonada.

Sem medição, a avaliação de "o Copilot é suficientemente bom" será feita por impressão, e a
impressão falha precisamente no caso perigoso: uma resposta plausível, bem escrita, com a
release errada.

**O que fazer, e custa apenas tempo:**

1. Reunir **30 a 50 perguntas reais** de quem usa a documentação, com a resposta correta
   conhecida e o documento e release de onde vem.
2. Fazer cada pergunta ao Copilot, antes e depois das mudanças da secção 1.
3. Registar, por pergunta: acertou? citou o documento certo? usou a release certa? inventou
   alguma coisa? recusou quando devia?

Duas métricas acima de todas:

- **Taxa de release errada** — respostas certas para a versão errada. É o erro mais perigoso,
  porque parece correto.
- **Taxa de invenção** — respostas sem suporte nos documentos, sobretudo em perguntas cuja
  resposta não está em lado nenhum. Vale a pena incluir de propósito 5 a 10 perguntas
  **sem resposta na documentação**, só para ver se ele recusa.

Este conjunto de perguntas serve para qualquer caminho que venham a seguir. Se um dia a
abordagem do Copilot se revelar insuficiente, é o mesmo instrumento que o demonstrará, e
com dados em vez de opiniões.

---

## 5. Ordem de trabalhos — desenhada para testar a hipótese

A primeira versão desta secção tinha um defeito: mandava arrumar a biblioteca **e**
configurar o agente, medindo no fim. Isso mede o efeito conjunto e não distingue o que cada
intervenção trouxe — exatamente a pergunta que a hipótese da secção introdutória levanta.

As duas alavancas têm de ser medidas **em separado**, e podem sê-lo sem custo adicional,
porque o esforço é o mesmo e só muda a ordem.

Três camadas, três intervenções, uma medição depois de cada. A auditoria separou a camada
que eu tinha colapsado — *knowledge sources* não é a mesma coisa que instruções, nem a
mesma coisa que arrumar a biblioteca.

| | Intervenção | Camada que isola | Depende de |
|---|---|---|---|
| **0** | Reunir as perguntas | — | Pessoas da organização |
| **1** | **Medir como está hoje** | Linha de base | Nada |
| **2** | Definir *knowledge sources* com âmbito e descrições explícitas | Seleção de fontes | Copilot Studio |
| **3** | Medir | Efeito isolado do *scoping* | |
| **4** | Retirar releases antigas do conhecimento ativo (§1.1) + metadados | Conteúdo recuperável | Autoridade sobre a biblioteca |
| **5** | Medir | Efeito isolado da biblioteca | |
| **6** | Instruções e orquestração | Comportamento da resposta | Copilot Studio |
| **7** | Medir | Efeito isolado das instruções | |
| **8** | Comparar tudo | Que camada move o quê | |

Se não houver licenciamento de Copilot Studio, os passos 2 e 6 caem e mede-se apenas a
biblioteca. Nesse caso **não se conclui que a biblioteca era o fator dominante** — conclui-se
que as outras camadas não foram testadas. É uma distinção que se perde com facilidade.

Três resultados possíveis, e cada um leva a um sítio diferente:

- **A biblioteca move muito mais** — a tese confirma-se; o esforço vai para conteúdo e
  metadados.
- **O *scoping* ou as instruções movem tanto ou mais** — eu estava errado, e vale mais
  investir em configuração do agente do que em reorganizar centenas de documentos. Seria a
  conclusão mais barata de todas.
- **Nenhum move o suficiente** — a limitação é estrutural, e a decisão de não construir um
  sistema próprio volta à mesa, agora com dados em vez de intuição.

Três resultados possíveis, e cada um leva a um sítio diferente:

- **A biblioteca move muito mais do que o prompt** — a hipótese confirma-se, o esforço vai
  para conteúdo e metadados.
- **O prompt move tanto ou mais** — a hipótese estava errada, e vale mais investir no agente
  e menos em reorganizar centenas de documentos. Seria a conclusão mais barata de todas.
- **Nenhum move o suficiente** — o problema não é de arrumação nem de instruções, e a
  limitação é estrutural. Aí a decisão de não construir um sistema próprio é que volta à
  mesa, com dados.

O passo 1 antes de tudo mantém-se, e não depende de nenhuma análise prévia: sem linha de
base, nenhuma das três conclusões acima é possível.

---

## 7. Escrever os documentos que faltam

Ideia adaptada de uma proposta de "camada de reflexão" para sistemas RAG: sintetizar
previamente informação dispersa, para que a pesquisa encontre **um** documento bom em vez
de seis fragmentos desconexos.

Na versão automatizada, um LLM escreve essas sínteses e elas são indexadas com prioridade.
Isso é perigoso — texto gerado passa a ser tratado como fonte, os erros ficam guardados e
promovidos, e não há forma de saber que uma síntese ficou desatualizada quando o documento
de origem mudou.

**No SharePoint a mesma ideia é segura, porque a síntese é escrita e revista por uma
pessoa, e versionada como qualquer outro documento.** O Copilot indexa-a como indexa tudo
o resto. O efeito é o mesmo; o risco desaparece.

O que vale a pena escrever, por ordem de retorno:

**7.1 Uma página de visão geral por sistema ou processo.** Meia página: o que é, quando se
usa, quais são os documentos relevantes e para que serve cada um. Responde às perguntas
panorâmicas que hoje devolvem fragmentos soltos, e serve de mapa para as outras.

**7.2 Um documento de alterações por release.** Modelo pronto a preencher em
[`modelo-alteracoes-release.md`](modelo-alteracoes-release.md). O que mudou na 7.4 face à 7.3, em linguagem
de quem usa: "a confirmação manual no check-in ADL foi removida". Isto responde à pergunta
que nenhum retriever consegue responder sozinho, porque exige comparar dois documentos que
nunca estão ambos no resultado.

**7.3 Um glossário de acrónimos e estados.** ADL, PNL, `NOT PROCESSED`, códigos de erro —
cada um com o significado e o documento onde é tratado a sério. Barato de escrever e
melhora a recuperação de tudo o resto, porque dá ao sistema uma ponte entre o vocabulário
das pessoas e o dos manuais.

**7.4 Um FAQ a partir das perguntas reais.** À medida que reunirem as perguntas para a
avaliação (`EVALUATION.md`), as que o Copilot falha repetidamente são candidatas a um
documento próprio. É a forma mais direta de corrigir uma falha: se a resposta não está
escrita em lado nenhum de forma encontrável, escreva-se.

Regra para todos: **são documentos normais, com `Release`, `Estado` e dono.** Quando a
release muda, são revistos como os outros. Uma síntese desatualizada é pior do que nenhuma,
porque parece autoritativa.

---

## 8. Escrever para ser recuperado

O Copilot não lê um documento inteiro para responder — recupera pedaços. A qualidade da
resposta depende de cada pedaço fazer sentido **sozinho**, fora do documento onde estava.
É o fator que mais gente desconhece e que mais barato é de corrigir na escrita.

**Cada secção tem de se explicar a si própria.** Um parágrafo que diz *"Clique em Confirmar
para concluir o processo"* é inútil quando recuperado isolado: que processo, em que ecrã,
de que sistema? A versão recuperável é *"Para concluir o check-in ADL, clique em Confirmar
no ecrã de check-in."* Repetir o nome do sistema e do procedimento em cada secção parece
redundante a ler o documento de fio a pavio, e é exatamente o que torna o pedaço
encontrável e utilizável.

**A resposta vem primeiro, o contexto depois.** Uma secção que começa com três parágrafos
de enquadramento antes de dizer o que fazer perde-se no corte. Primeiro a instrução, depois
a explicação.

**Cabeçalhos a sério.** Estilos do Word, não texto a negrito. São eles que delimitam as
secções; sem eles, o documento é cortado a meio de procedimentos.

**Uma pergunta como cabeçalho funciona melhor do que um substantivo.** "Como fazer o
check-in ADL" é encontrado por mais formulações do que "Procedimento de check-in".

**Documentos grandes recuperam pior do que documentos focados.** Um manual de 400 páginas
sobre oito assuntos compete consigo próprio: vários pedaços parecidos, nenhum claramente
melhor. Oito documentos de 50 páginas recuperam melhor do que um de 400. Quando for viável
dividir, divida.

**Duplicados dividem o sinal.** Duas versões quase iguais do mesmo procedimento fazem o
sistema hesitar entre elas e às vezes escolher a pior. Um documento por assunto.

**Tabelas com cabeçalhos repetidos em cada página**, e evitar tabelas que atravessam várias
páginas quando possível — uma tabela cortada perde os cabeçalhos e as linhas ficam
ininterpretáveis.

**Legendas nas imagens.** Sem legenda, uma imagem é invisível. *"Figura 4 — Ecrã de
check-in ADL com o campo Estado do PNL"* torna-a encontrável e diz ao sistema o que ela
mostra.

**PDFs digitalizados precisam de OCR antes de entrar.** Sem texto pesquisável são invisíveis
— não aparecem mal, simplesmente não existem para o Copilot.

---

## 9. O que não é possível controlar

Para gerir expectativas: o retriever é da Microsoft. Não se escolhe o número de pedaços
recuperados, nem como são cortados, nem os pesos de ordenação, nem se há reordenação. Todas
as alavancas estão do lado do **conteúdo e dos metadados**.

É por isso que a secção 1 (arquivar releases antigas) continua a valer mais do que tudo o
resto junto: não é possível dizer ao Copilot para preferir a release atual — só é possível
tirar-lhe as outras da frente.

Também não se controlam as permissões a partir daqui: o Copilot só devolve a cada pessoa o
que essa pessoa já podia abrir. Um documento com permissões restritas não aparece nas
respostas de quem não lhe acede — o que é correto, mas explica respostas incompletas que de
outra forma parecem inexplicáveis.


---

## 10. Alavancas do M365 identificadas em auditoria externa

Acrescentadas depois de uma auditoria que pesquisou a documentação da Microsoft. São a área
onde eu tinha menos conhecimento e onde a auditoria acrescentou mais.

### 10.1 *Knowledge sources* com âmbito definido

Em vez de deixar o agente procurar em toda a biblioteca, podem definir-se fontes específicas
— sites, bibliotecas, pastas, ficheiros, listas. É a diferença entre **controlar a superfície
de recuperação** e **pedir ao modelo que prefira o mais recente**. A primeira é estrutural;
a segunda é uma sugestão.

### 10.2 As descrições das fontes influenciam a seleção

O ponto que eu tinha subestimado por completo. O nome e a descrição de uma *knowledge source*
entram na decisão da orquestração generativa sobre qual usar. Isto é configuração a atuar
**antes** da resposta, não depois — e contradiz a minha formulação inicial de que só o
conteúdo conta.

Na prática, duas descrições assim são hipótese testável, não teoria:

> "Documentação operacional em vigor, release 7.4. Usar para qualquer procedimento aplicável hoje."

> "Documentação histórica, releases 7.1 a 7.3. Usar apenas quando a pergunta mencione explicitamente uma release anterior."

### 10.3 Agent Builder não chega para um requisito forte de isolamento

Para o requisito *"nunca responder fora da documentação"*, o Agent Builder não permite
bloquear por completo o conhecimento geral do modelo. Para controlo mais rigoroso de
abstenção, é Copilot Studio.

Isto é relevante porque a recusa é **o requisito que define este projeto** desde o briefing
original. Se ele for inegociável, a escolha da ferramenta não é indiferente.

### 10.4 Avaliação automatizada no Copilot Studio

Existe avaliação de agentes com métricas que coincidem quase exatamente com o que a folha
manual mede: *relevance*, *groundedness*, *completeness* e *abstention* — esta última sendo
se o agente tentou responder. Há conjuntos de teste que podem ser construídos a partir das
próprias fontes de conhecimento.

**Isto não substitui a folha manual — complementa-a**, e a divisão de trabalho é clara:

| Automático | Humano |
|---|---|
| Respondeu? | **Usou a release certa?** |
| Está fundamentado nas fontes? | O procedimento está correto na prática? |
| Está completo? | Contradiz outra release? |
| Absteve-se? | É operacionalmente seguro seguir isto? |

A coluna da direita não é automatizável, e contém a métrica que mais importa. Um avaliador
automático que verifique *groundedness* dá resposta positiva a um texto perfeitamente
fundamentado — na release errada.

### 10.5 Permissões são parte da recuperação

O Copilot só devolve a cada pessoa o que ela já podia abrir. Uma resposta incompleta pode
não ser falha de recuperação — pode ser a pessoa não ter acesso ao documento. Ao registar
resultados da avaliação, convém anotar quem fez a pergunta: duas pessoas com permissões
diferentes podem obter respostas diferentes à mesma pergunta, e isso não é um defeito.

### 10.6 Não confundir recuperação com resposta

A formulação é do auditor e merece ficar como princípio do projeto:

> A métrica principal não é *"o Copilot respondeu?"* mas **"o Copilot recuperou e usou a
> evidência certa, para a versão certa?"**. Só depois: a resposta estava bem escrita?

É o mesmo erro contra o qual todo este projeto foi desenhado, noutra roupagem: uma resposta
fluente, com citação real, tirada da release errada passa em qualquer métrica automática de
fundamentação e está operacionalmente errada.


---

## 11. Segunda ronda de auditoria — o que falta incorporar

### 11.1 Hierarquia de conhecimento, não apenas âmbito

A camada de *scoping* é mais rica do que "dar menos documentos ao agente". No Copilot Studio,
as fontes definidas num **nó de generative answers** têm prioridade sobre as fontes ao nível
do agente, que funcionam como *fallback*.

Isso permite uma hierarquia em vez de uma lista:

```
Pergunta
   │
   ├─ nó específico ──► Documentação atual (7.4)      ← prioridade
   │
   └─ nível do agente ─► Documentação histórica        ← fallback
```

É conceptualmente muito superior a instruir *"prefere a release mais recente"*: a preferência
passa a ser estrutural em vez de uma sugestão que o modelo pode ou não seguir. Entra na
experiência 1.

### 11.2 Fonte de conhecimento própria — o plano C

O Copilot Studio permite ligar uma **fonte de conhecimento personalizada**, servida por uma
API de pesquisa da organização. Isso abre uma terceira posição entre as duas que estávamos a
tratar como exclusivas:

| | Interface | Recuperação |
|---|---|---|
| **A** | Copilot | Microsoft |
| **B** | Aplicação própria | Própria |
| **C** | **Copilot** | **Própria** |

A opção C importa por uma razão concreta: se a experiência mostrar *"o Copilot funciona bem,
exceto na distinção entre releases"*, não é preciso abandonar o Copilot nem reconstruir tudo.
Substitui-se exatamente a peça que falha — a recuperação — mantendo a interface que toda a
gente já usa e sem pedir a ninguém que adote uma aplicação nova.

E tem uma consequência para o trabalho parado: **o desenho da camada de recuperação em
`ARCHITECTURE.md` deixa de ser plano B abandonado e passa a ser um componente possível da
opção C.** Consciência de versões, citações com página, recuperação híbrida — é precisamente
o que uma fonte de conhecimento própria teria de fazer.

Não implementar agora. Registar como saída arquitetural, para que a decisão, se vier, seja
tomada com isto em cima da mesa.

### 11.3 Três métricas, não uma

*Groundedness* automático responde "a resposta está suportada pela evidência recuperada?" —
e dá positivo a um texto perfeitamente fundamentado na release errada. São três perguntas
distintas e só a primeira é automatizável:

| Métrica | Pergunta | Automatizável |
|---|---|---|
| **Groundedness** | A resposta é suportada pela evidência recuperada? | Sim |
| **Source correctness** | A evidência recuperada é a fonte que devia ter sido usada? | Não |
| **Version correctness** | A evidência pertence à release temporalmente correta? | **Não** |

O caso que define o projeto tem este aspeto:

```
Qualidade da resposta   ✅
Groundedness            ✅
Citação                 ✅
Source correctness      ❌
Version correctness     ❌
```

Tudo verde no avaliador automático, e operacionalmente errado. As duas últimas colunas da
folha de avaliação são a razão de ela existir.

### 11.4 Trios de perguntas em vez de perguntas soltas

Cada procedimento que mudou entre releases gera três perguntas, não uma:

| | Pergunta | Testa |
|---|---|---|
| **A** | "Como faço X?" | Recuperação da versão atual |
| **B** | "Como se fazia X na 7.2?" | Recuperação histórica |
| **C** | "O procedimento de X mudou entre a 7.2 e a 7.4?" | Comparação entre versões |

Com perguntas soltas, uma falha marca-se como "errada". Com o trio, vê-se **onde** falhou:

```
A ✅   B ❌   C ❌    →  o histórico não é alcançável
A ✅   B ✅   C ❌    →  alcança ambos mas não os compara
A ❌   B ✅   C ❌    →  está a responder com a release errada — o caso perigoso
```

E o trio é também o instrumento da decisão do §1.1: no cenário Microsoft 365 Archive, a
pergunta **B não tem resposta possível por construção**. Se ninguém na organização precisar
de fazer perguntas do tipo B, o Archive resolve o problema estruturalmente; se precisarem, a
resposta está no que o trio mostrar.

### 11.5 Experiência 4 — decidir o arquivo com dados

Em vez de escolher entre Archive e histórico acessível por argumentação, montar os dois e
fazer as mesmas perguntas:

| Cenário | Configuração |
|---|---|
| **A** | 7.4 ativa · 7.1–7.3 em Microsoft 365 Archive |
| **B** | 7.4 atual · 7.1–7.3 como fonte histórica com âmbito definido |

O cenário A deve falhar todas as perguntas B do trio, e é isso que se quer verificar: que
falha **por recusa clara**, não por resposta inventada. O cenário B deve responder às
perguntas B — e a questão é se acerta nas A sem contaminação.

---

## Princípio do projeto

Formulação vinda da auditoria externa, adotada porque é a melhor síntese de tudo o que foi
aprendido aqui:

> **A pergunta não é se o Copilot consegue produzir uma resposta fundamentada. É se consegue
> recuperar e utilizar a evidência correta, da fonte correta e da release correta — e recusar
> quando essa evidência não existe.**
