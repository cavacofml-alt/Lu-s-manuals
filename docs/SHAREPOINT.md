# Melhorar as respostas do Copilot sobre a documentação no SharePoint

Direção adoptada em substituição da aplicação autónoma. Este documento é o plano de
trabalho; não requer programação.

A premissa que o orienta: **a qualidade das respostas do Copilot é determinada sobretudo
pelo que está na biblioteca, não por como se lhe pede.** Instruções controlam a forma da
resposta; a arrumação dos documentos controla o que ele encontra. A maior parte dos erros
que preocupam neste projeto — misturar releases, citar o manual errado, responder com um
procedimento revogado — são erros de recuperação, e resolvem-se na origem.

---

## 1. Higiene da biblioteca — a intervenção de maior retorno

### 1.1 Arquivar as versões antigas

É o passo mais importante de todo o documento. Se a release 7.3 não estiver na biblioteca
indexada, o Copilot não a pode misturar com a 7.4.

- Uma biblioteca **"Documentação atual"**, indexada, apenas com a release em vigor.
- Uma biblioteca **"Arquivo"**, excluída da indexação do Copilot, com tudo o resto.
- Quando sai uma release nova, o documento anterior move-se para o arquivo no mesmo dia.

Sem isto, nenhuma instrução impede respostas que combinam versões, porque ambas as versões
são evidência legítima aos olhos do sistema.

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
| Citar a página exata e abrir o documento nela (§23, §49-I/J) | **Não atingível** |
| Mostrar o screenshot original da documentação (§5, §6, §49-K) | **Não atingível** |
| Comparar o que mudou entre releases (§10) | **Não atingível** |
| Garantir a recusa quando falta evidência (§14, §49-O) | Melhora, sem garantia |
| Preferir a release atual (§9, §49-N) | Atingível **via arquivo**, não via instruções |
| Export PDF/email estruturado (§25, §26) | Fora de âmbito |

As três primeiras dependem de indexar por página, extrair imagens com contexto e alinhar
secções entre versões. Nenhuma é acessível a partir de instruções.

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

## 5. Ordem de trabalhos sugerida

| | Ação | Esforço | Impacto |
|---|---|---|---|
| 1 | Reunir as 30–50 perguntas e medir o Copilot **hoje** | 1 dia | Base de comparação |
| 2 | Separar biblioteca atual do arquivo | Horas | **Alto** |
| 3 | Criar as colunas de metadados e preenchê-las | Dias | Alto |
| 4 | Corrigir títulos, OCR nos digitalizados | Dias | Médio |
| 5 | Repetir a medição | Horas | Mostra o que ganharam |
| 6 | Agente declarativo, se houver licenciamento | Dias | Médio |
| 7 | Repetir a medição | Horas | Decide se chega |

O passo 1 antes do passo 2 é deliberado: sem uma medição inicial, não saberão o que as
mudanças trouxeram, e a discussão volta a ser de opinião.

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
