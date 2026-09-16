# Conjunto de perguntas de avaliação

Como construir e usar o conjunto de perguntas que mede se o Copilot é suficientemente bom
sobre a documentação. Aplica-se igualmente a qualquer sistema que venha a substituí-lo.

O erro a evitar está logo no início: um conjunto reunido sem critério é composto por
perguntas que alguém se lembrou de fazer, e as pessoas lembram-se das perguntas fáceis. Um
sistema acerta 38 em 40, toda a gente conclui que funciona, e as duas falhas eram as
únicas que importavam.

---

## 1. Onde ir buscar as perguntas

Por ordem de qualidade:

1. **Pedidos de apoio reais** — tickets, emails, mensagens de Teams a perguntar como se faz
   alguma coisa. São perguntas que alguém precisou mesmo de fazer, com a linguagem real que
   as pessoas usam. É a melhor fonte, de longe.
2. **Quem faz o trabalho todos os dias.** Peça a três ou quatro pessoas: "quais são as cinco
   perguntas que os teus colegas te fazem mais vezes?"
3. **Quem entrou recentemente.** As perguntas de quem está a aprender expõem o que a
   documentação não explica bem.

Fonte a evitar: perguntas inventadas por quem escreveu os manuais. Essa pessoa conhece a
resposta e, sem dar por isso, formula a pergunta com as palavras do documento — o que torna
a recuperação artificialmente fácil.

**Para cada pergunta, registe a resposta correta e a origem *antes* de testar seja o que
for.** Se a resposta certa for decidida depois de ver o que o sistema respondeu, a avaliação
não vale nada.

---

## 2. Composição do conjunto

Cerca de 40 perguntas, distribuídas assim. As proporções importam mais do que o total.

| # | Categoria | Quantas | O que revela |
|---|---|---|---|
| A | Consulta simples | 6 | Linha de base. Se falhar aqui, pare e arrume a biblioteca |
| B | Procedimento com passos | 6 | Ordem, passos em falta, passos inventados |
| C | Termo técnico exato | 5 | Estados, códigos, mensagens de erro |
| D | Versão explícita | 4 | "Na 7.3, como é que…" |
| E | **Versão implícita** | 5 | **A categoria mais perigosa** — ver abaixo |
| F | **Sem resposta na documentação** | 6 | **Testa a recusa. Quase sempre esquecida** |
| G | Informação substituída | 3 | A resposta só existe num documento revogado |
| H | Documentos em conflito | 3 | Duas fontes discordam |
| I | Resposta numa imagem | 3 | Screenshots e diagramas |
| J | Resposta numa tabela | 3 | Tabelas partidas entre páginas |
| K | Acrónimos e jargão | 2 | Vocabulário interno |

### As duas categorias que decidem tudo

**E — versão implícita.** Perguntas normais, sem mencionar release, cuja resposta **mudou**
entre versões. O utilizador não sabe que existe ambiguidade. É o caso perigoso porque a
resposta errada é fluente, bem escrita e vem com uma fonte verdadeira — só está a descrever
a versão errada. Ninguém dá por isso, nem quem pergunta nem quem avalia distraidamente.

Para as construir: peça a quem conhece a documentação que identifique **cinco procedimentos
que mudaram entre releases**. Depois formule a pergunta como um utilizador a faria, sem
referir versão nenhuma.

**F — sem resposta.** Perguntas plausíveis, sobre o vosso domínio, cuja resposta **não está
em documento nenhum**. A resposta certa é: *"não encontrei informação suficiente."*

Esta categoria é a que quase todas as avaliações omitem, e é a que mede a propriedade mais
importante de todas. Um sistema que nunca recusa está a inventar — só que ninguém testou
onde. Sem estas seis perguntas, não se sabe se ele recusa, sabe-se apenas que nunca se
verificou.

Como construir: invente perguntas verosímeis sobre funcionalidades que não existem, sobre
procedimentos ainda não documentados, ou sobre configurações que nunca foram escritas. Se
alguém da equipa conseguir responder de cabeça mas não conseguir apontar o documento, serve
perfeitamente.

---

## 3. Formato de cada pergunta

```
ID          Q014
Categoria   E — versão implícita
Pergunta    "Como é que faço o check-in ADL?"
Resposta    O procedimento mudou na 7.4: o passo de confirmação manual foi removido.
correta     A resposta deve descrever o fluxo da 7.4.
Documento   Manual de Check-in ADL
Release     7.4
Página      42
Secção      Procedimento de Check-in ADL
Armadilha   O mesmo procedimento existe na 7.3 com um passo extra. Uma resposta que
            inclua a confirmação manual está errada, mesmo parecendo completa.
```

O campo **Armadilha** é o que torna o conjunto útil daqui a um ano, quando quem o construiu
já não se lembrar porque é que aquela pergunta lá estava.

Exemplos das outras categorias, com o vocabulário do briefing:

- **C:** "O que acontece se o PNL ficar em `NOT PROCESSED`?" — a resposta tem de citar o
  estado exatamente assim, não "não processado" nem "por processar".
- **F:** "Como configuro alertas automáticos para PNL bloqueados?" — se não existir
  documentação sobre isso, a resposta certa é recusar.
- **H:** um procedimento que o manual descreve de uma forma e o guia rápido de outra.

---

## 4. Como classificar cada resposta

Cinco juízos independentes por pergunta. Independentes é o ponto: uma resposta pode estar
substancialmente certa e ter usado a release errada, e isso conta como falha grave.

| Juízo | Critério |
|---|---|
| **Correta** | A informação está certa e completa |
| **Documento certo** | Citou a origem e é a origem certa |
| **Release certa** | Usou a versão aplicável |
| **Inventou** | Alguma afirmação não suportada por documento: um botão, um passo, um ecrã, um comportamento |
| **Recusou bem** | Nas perguntas F: recusou. Nas outras: não recusou indevidamente |

Duas regras de classificação:

- **Quem escreveu a pergunta não a classifica sozinho.** Conhece a resposta e lê a resposta
  do sistema com benevolência. Duas pessoas, ou pelo menos alguém diferente.
- **Não avalie pela redação.** O Copilot escreve bem. Uma resposta bem escrita e errada é
  pior do que uma mal escrita e certa, porque é mais convincente.

---

## 5. As duas métricas que decidem

De tudo o que sair, duas contam mais do que a percentagem global de acerto:

**Taxa de release errada** — respostas substancialmente corretas, tiradas da versão errada.
É o erro que passa despercebido, porque a resposta parece boa e a fonte é real. Se esta taxa
não for próxima de zero depois de arquivar as releases antigas, o arquivo não está bem feito.

**Taxa de invenção** — proporção das perguntas da categoria F em que o sistema respondeu em
vez de recusar. Se responder a 4 das 6 perguntas sem resposta, está a inventar de forma
sistemática, e o número de acertos nas outras categorias deixa de significar o que parece.

Uma percentagem global de 90% com 5 releases erradas é pior do que 80% sem nenhuma.

---

## 6. Quando usar

- **Antes** de mexer na biblioteca — a medição inicial. Sem ela não se sabe o que as
  mudanças trouxeram.
- **Depois** de arquivar as releases antigas e pôr os metadados.
- **Depois** de configurar o agente, se chegarem a esse ponto.
- **Sempre que alguém disser que o Copilot está a responder mal.** Uma queixa transforma-se
  numa pergunta nova no conjunto, e o conjunto cresce com o uso real.

O conjunto sobrevive a mudanças de tecnologia. Se um dia a via do Copilot se revelar
insuficiente, é o mesmo instrumento que o demonstra — com dados, não com impressões.
