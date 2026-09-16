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
