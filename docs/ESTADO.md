# Estado do projeto

Documento de ponto de situação, escrito para ser lido por alguém sem contexto nenhum.
Atualizado em 2026-09-17.

---

## 1. O que se pretende

Uma organização tem documentação interna extensa em PDF — manuais, guias rápidos,
procedimentos operacionais, notas de versão, material de formação — distribuída por várias
releases de produto (7.1 a 7.4) e guardada em SharePoint. Parte tem screenshots, tabelas e
páginas digitalizadas.

O objetivo é que as pessoas possam fazer perguntas em linguagem natural e obter respostas
corretas, fundamentadas na documentação, que digam de onde vêm.

O requisito que define o problema, e que separa isto de um chatbot: **quando a
documentação não suporta a resposta, o sistema tem de o dizer em vez de inventar.**

Requisitos secundários, do briefing original: citar documento, release e página; abrir o
documento na página certa; mostrar o screenshot relevante; distinguir releases e nunca as
misturar em silêncio; exportar a resposta em PDF ou email.

---

## 2. Percurso, incluindo as mudanças de direção

Houve três mudanças de direção. Registadas porque são contexto necessário para avaliar o
estado atual.

**Fase 1 — aplicação própria.** Partiu-se de um briefing detalhado (51 secções) para
construir uma plataforma RAG dedicada: FastAPI, PostgreSQL com pgvector, pesquisa híbrida,
reranking, respostas estruturadas com citações validadas. Foi produzido um desenho técnico
completo e implementado o primeiro passo.

**Fase 2 — questão de infraestrutura.** Discutiu-se onde correr (PC local, Codespaces,
Supabase/Vercel) e que modelos usar, com uma preocupação central: se a documentação for
confidencial, o corpus não pode sair da rede. Decidiu-se embeddings locais e Claude para as
respostas.

**Fase 3 — mudança para o Copilot.** A organização já tem Microsoft Copilot disponível para
todos, com acesso ao SharePoint onde a documentação vive. Decidiu-se **em vez de** construir
a aplicação, melhorar as respostas do Copilot sobre a documentação existente.

Essa é a direção atual.

---

## 3. O que foi feito

### 3.1 Da aplicação (parado, não apagado)

- Desenho técnico completo, `docs/ARCHITECTURE.md`, cobrindo as 27 áreas exigidas pelo
  briefing e registando 15 pontos onde se discorda da especificação original.
- Quatro rondas de auditoria arquitetural independente, feitas por outro modelo.
- Implementação do STEP 1: esqueleto do projeto, política de egress de dados, 104 testes,
  lint e verificação de tipos limpos.

Dois achados desse trabalho valem por si, independentemente do veículo:

**A configuração `english` do PostgreSQL inverte estados operacionais.**
`to_tsvector('english', 'PNL NOT PROCESSED')` elimina o `NOT` como *stopword*. Uma página
que afirma que o PNL **está** processado passa a corresponder a uma pesquisa por
"NOT PROCESSED" — o sistema recuperaria evidência que afirma o oposto da pergunta, com
citação válida para uma página real. Verificado em PostgreSQL 16.13. Nenhuma camada a
jusante o deteta.

**Uma política de proteção de dados só vale se for imposta em runtime.** A primeira versão
usava tipos para impedir que conteúdo confidencial chegasse a fornecedores cloud; a
auditoria mostrou que os tipos não impedem nada em execução. Foi substituída por um
mecanismo em que o conteúdo só atravessa a fronteira com uma autorização que apenas o guard
consegue construir. Seis tentativas de contorno são agora testes.

### 3.2 Da direção atual — Copilot sobre SharePoint

Tudo em `docs/`:

- **`SHAREPOINT.md`** — plano de trabalho. Higiene da biblioteca, metadados, agente
  declarativo, o que a abordagem não resolve, e as duas secções sobre conteúdo: escrever os
  documentos em falta e escrever para ser recuperado.
- **`EVALUATION.md`** — como construir o conjunto de perguntas que mede se o Copilot chega.
- **`Avaliacao-Documentacao.xlsx`** — folha com 46 perguntas distribuídas por 11 categorias,
  registo de duas rondas e métricas calculadas.
- **`modelo-alteracoes-release.md`** — modelo para o documento de alterações entre releases.

A tese que orienta tudo isto, reformulada após uma segunda auditoria externa que pesquisou
a documentação da Microsoft:

> A recuperação está fortemente limitada pela qualidade, estrutura e seleção da biblioteca.
> As instruções e a configuração do agente melhoram significativamente a escolha das fontes
> e o comportamento da resposta, mas não substituem uma biblioteca bem organizada.

A versão anterior — "a biblioteca determina, as instruções não contam" — estava errada, e
não por ênfase. Havia **três** camadas e eu tinha colapsado duas: conteúdo (o que pode ser
recuperado), *knowledge sources* e metadados (o que é provável ser selecionado) e instruções
(como o agente usa o que recuperou). A camada do meio é configuração que atua **antes** da
resposta, e era a que eu ignorava.

A ordem de trabalhos em `SHAREPOINT.md` §5 mede as três em separado.

---

## 4. Lacunas

### 4.1 A lacuna principal

**Nada foi feito ainda no SharePoint, e nenhuma medição foi tomada.**

Tudo o que existe é preparação: planos, modelos, uma folha de cálculo vazia. Não houve uma
única alteração à biblioteca nem uma única pergunta feita ao Copilot e registada.

É a lacuna que importa, e o risco é ficar aqui. O trabalho seguinte não é de análise — é
operacional, e depende de pessoas da organização, não de mais desenho.

### 4.2 Inputs que faltam, e que ninguém além da organização pode fornecer

| O quê | Para quê | Bloqueia |
|---|---|---|
| 30–50 perguntas reais com resposta e origem conhecidas | Medir o estado atual | Tudo o resto |
| Procedimentos que mudaram entre releases | Categoria E da avaliação, e o documento de alterações | A parte mais perigosa da medição |
| Perguntas **sem resposta** na documentação | Testar se o Copilot recusa ou inventa | A métrica mais importante |
| Documentos representativos | Validar pressupostos sobre estrutura, OCR, imagens | Qualquer verificação técnica |

Nenhum destes foi fornecido. Sem os dois primeiros, a avaliação não pode arrancar.

### 4.2.1 Duas verificações que mudaram o plano

Confirmadas contra a documentação da Microsoft, e ambas alteram decisões:

**O arquivo tem de ser o mecanismo certo.** Mover para uma pasta `/arquivo` ou marcar
`Estado = Substituído` não retira nada do índice ativo. O **Microsoft 365 Archive** retira:
o conteúdo arquivado fica fora do *grounding* do Copilot e não é por ele pesquisável.

Mas isso traz uma tensão que não estava visível: retirar **por completo** resolve a mistura
de releases e, ao mesmo tempo, torna impossível responder a *"como se fazia na 7.2?"*. A
alternativa — site separado com fontes de conhecimento definidas — mantém o histórico
acessível mas depende de a orquestração escolher bem. **São alternativas, não complementos**,
e a escolha depende de saber se alguém precisa mesmo de consultar releases antigas por esta
via.

**Imagens e tabelas: eu tinha sido categórico a mais.** *Interpretar* uma tabela ou diagrama
para responder é possível conforme a fonte e a configuração — passa de "não atingível" a
"por testar", e entra na avaliação como categoria própria. *Mostrar* a imagem original dentro
da resposta, com a página de origem, continua fora de alcance — e era esse o requisito §6.

### 4.3 Decisões por tomar

- **A documentação é confidencial?** Nunca foi respondido formalmente. Na direção atual
  perde parte da urgência — a documentação já está no SharePoint, ou seja, já numa nuvem de
  terceiros. Mas continua a determinar o que pode ser feito no futuro.
- **Existe licenciamento de Copilot Studio?** Determina se o agente declarativo é possível,
  e também se as camadas de *scoping* e instruções chegam a ser testadas. Sem ele, mede-se
  apenas a biblioteca — e a conclusão terá de dizer "as outras camadas não foram testadas",
  não "a biblioteca era o fator dominante". Não confirmado.
- **Alguém precisa de consultar releases antigas através do Copilot?** Decide entre
  Microsoft 365 Archive e site separado com fontes scoped. Ver §4.2.1. Não respondido.
- **É organizacionalmente possível arquivar as releases antigas?** É a ação de maior
  retorno de todo o plano e pressupõe que alguém tem autoridade para mover documentos e que
  ninguém depende de aceder às versões antigas pela mesma via. Não validado.
- **Quem é o dono disto?** Não está definido quem trata da biblioteca, quem reúne as
  perguntas, quem escreve os documentos em falta.

### 4.4 Riscos

| Risco | Porquê importa |
|---|---|
| A medição nunca acontecer | Sem ela, "o Copilot chega?" decide-se por impressão — e a impressão falha no caso perigoso: resposta fluente, bem citada, tirada da release errada |
| Recolher só perguntas fáceis | Um conjunto reunido sem critério dá 90% de acerto e não diz nada. Por isso a folha impõe categorias e proporções |
| Arquivar as releases antigas ser adiado | É a única ação que resolve mesmo a mistura de versões. Sem ela, o resto são melhorias marginais |
| Escrever documentos de síntese que se desatualizam | Uma síntese desatualizada é pior do que nenhuma, porque parece autoritativa |
| A quarta mudança de direção | Três mudanças em poucos dias. Cada uma foi defensável; a próxima devia exigir dados, não intuição |
| Adiar a medição à espera de mais análise | A linha de base não depende de nenhuma auditoria: não altera nada, não custa nada, e é input obrigatório para testar a hipótese. Análise e medição são paralelas |

### 4.5 O que esta direção não vai dar

Registado no `SHAREPOINT.md` §3, repetido aqui porque é fácil esquecer:

- citar a página exata e abrir o documento nela — **não atingível**
- mostrar o screenshot original da documentação — **não atingível**
- comparar automaticamente o que mudou entre releases — **não atingível** (mitigável
  escrevendo o documento de alterações à mão)
- garantir a recusa quando falta evidência — **melhora, sem garantia**

As três primeiras exigem indexar por página, extrair imagens com contexto e alinhar secções
entre versões. Nenhuma é acessível a partir de instruções, porque não são falhas de
comportamento — são falhas da camada de recuperação, que nesta abordagem pertence à
Microsoft.

---

## 5. O passo seguinte

Um, e não depende de mais análise:

**Reunir 30 a 50 perguntas reais e fazê-las ao Copilot como ele está hoje, registando os
resultados.**

Antes de mexer na biblioteca — deliberadamente. Sem medição inicial não se sabe o que as
mudanças trouxeram, e a discussão volta a ser de opinião.

Melhor fonte: pedidos de apoio reais — tickets, emails, mensagens a perguntar como se faz
alguma coisa. São perguntas que alguém precisou mesmo de fazer, com a linguagem real das
pessoas. Fonte a evitar: perguntas inventadas por quem escreveu os manuais, que sem dar por
isso as formula com as palavras do documento e torna a recuperação artificialmente fácil.

---

## 6. Perguntas em que uma opinião externa seria útil

1. A tese de que a arrumação da biblioteca vale mais do que as instruções ao assistente
   está certa, ou está a subestimar o que um agente declarativo bem configurado consegue?
2. Arquivar as releases antigas resolve mesmo a mistura de versões no Copilot, ou há
   caminhos pelos quais ele continua a alcançá-las?
3. A composição do conjunto de avaliação (11 categorias, com ênfase em versão implícita e
   perguntas sem resposta) mede o que interessa, ou falta alguma categoria?
4. Há alguma alavanca no M365 que não esteja a ser considerada — conectores, colunas
   geridas, tipos de conteúdo, qualquer coisa que altere a recuperação e que não conste do
   plano?
5. Dado que três das exigências originais ficam por cumprir, esta abordagem é suficiente
   para o problema, ou é uma solução parcial que vai voltar dentro de seis meses?
