# PB Minuto — sistema mais rápido e dinâmico (design)

Data: 21/11/2026 · Pedido do Arthur (@pbminuto) · Caminho escolhido: **A — melhorar por etapas, sem parar o perfil**

## 1. Intenção e porquê

O Arthur quer o sistema inteiro **mais rápido e dinâmico**, com **coleta e postagem de conteúdo mais fáceis**.
Ele pediu explicitamente para não atacar um ponto isolado. A melhoria deve valer para o sistema como um todo
e seguir o processo das skills: design → plano → execução com testes → verificação.

Medição feita em 21/11 (rodadas reais do GitHub Actions):

| Onde | O que acontece hoje |
|---|---|
| Notícias (`publicar.yml`) | 1 rodada a cada ~5 min; ~4,5 min da rodada é `sleep` esperando a próxima. Trabalho real é curto. |
| Parceiros (`parceiro.yml`) | Rodada das 13h04: 14 min, 1 vídeo publicado; 4 vídeos gastaram ~3 min cada (baixar + Whisper + 3 tentativas de IA) e falharam com "a IA não conseguiu escrever sem repetir o original". |
| Parceiros | `@paraibabussines_` não existe mais ("usuário não encontrado"); toda rodada tenta. |
| Parceiros | Com post há < ~15 min, o vídeo espera a próxima rodada (~20 min depois). Dois vídeos ficaram parados assim às 13h19. |
| Estado | 4 rodadas de parceiro falharam hoje no `git push` do estado (as duas sequências gravam `state/` ao mesmo tempo). |
| Código | Lógica em 4 arquivos grandes na raiz (`parceiro.py` 1053, `audiograma.py` 950, `editor.py` 764, `main.py` 756 linhas). |
| Editoria | Não existe `MUNDO`; notícia do México saiu como `BRASIL`. |
| Prévia | Vídeos do cavalo e do meteoro (12h20/12h23) saíram sem prévia no ramo `previa-parceiro`. |

Conclusão: a lentidão vem mais de **desperdício e espera** do que de máquina lenta.

## 2. Objetivos

1. **Coleta mais esperta:** nada caro (download, Whisper, montagem) para conteúdo que será descartado; perfis mortos não travam a rodada.
2. **Postagem coordenada:** uma única decisão de "quem ocupa a próxima vaga" (notícia ou parceiro). Vídeo pronto sai na vaga seguinte, sem esperar 20 min.
3. **Estado sem atropelo:** nenhuma rodada perde trabalho por conflito de `git push`.
4. **Código organizado:** partes claras (coleta, escrita, montagem, publicação, orquestração). Mudanças futuras devem ser rápidas e seguras.
5. **Comandos simples para o Arthur:** aprovar, refazer, pausar/retomar parceiro, ver fila e status. Tudo por uma ação, sem decorar IDs ou variáveis.
6. **Toda publicação com prévia** e com relatório legível (perfil de origem, editoria, manchete, id do post).

## 3. Não-objetivos

- Trocar de plataforma (continua GitHub Actions + API oficial do Instagram).
- Banco de dados externo ou serviço pago novo.
- Mudar a identidade visual, as fontes (Regra 1) ou o texto humanizado (Regra 2).
- Aumentar o teto diário de posts. O ritmo de ~1 post a cada ~14 min continua; o que muda é não desperdiçar vagas.

## 4. Anti-objetivos (seria fracasso mesmo funcionando)

- Perfil parado por qualquer período por causa da migração (Regra 6: perfil nunca parado).
- Publicar collab, vídeo repetido ou notícia repetida.
- Quebrar qualquer regra do `REGRAS.md`, ou qualquer dos 164 testes atuais.
- Publicar duas vezes o mesmo vídeo depois de uma rodada cortada no meio.
- O Arthur ter mais trabalho manual que hoje.

## 5. Restrições

- Produção roda em `main`. Cada etapa entra **separada**, com testes verdes, e pode ser revertida com um `git revert`.
- Segredos só via GitHub Secrets; nada de chave no código, log ou chat.
- Limite de 24h de publicações da API do Instagram e tempo máximo das rodadas do Actions.
- O agendamento `cron` do GitHub atrasa ou pula; a autocadeia (rodada chama a próxima) continua necessária.
- Mudanças de comportamento combinadas com o Arthur viram regra no `REGRAS.md` com teste.

## 6. Abordagens consideradas

| | Abordagem | Troca | Decisão |
|---|---|---|---|
| A | Melhorar por etapas sobre o sistema atual | Mais lento que reescrever no papel, mas cada passo dá ganho sozinho e é reversível | **Escolhida pelo Arthur** |
| B | Reescrever com orquestrador único e banco externo | Mais limpo no fim; semanas com dois sistemas, risco de perfil parado e regras perdidas | Descartada |
| C | Só reorganizar o código | Fica fácil de mexer, mas nada fica mais rápido nem mais fácil no dia a dia | Descartada |

## 7. Design (abordagem A), em etapas

Cada etapa é independente, entra em `main` sozinha e tem teste próprio.

### Etapa 1 — Coleta de parceiro sem desperdício
- **Ordem barata → cara:** filtros sem custo (antigo, não é vídeo, já usado, collab pela legenda/coautores) antes de qualquer download.
- **Checar repetição antes de montar:** `ja_postado` roda logo depois da escrita (já é assim), mas a transcrição é guardada por id e reaproveitada nas novas tentativas. A transcrição não é refeita a cada rodada.
- **Falha de escrita custa menos:** o resultado de "IA não conseguiu escrever" fica registrado com a transcrição. A próxima tentativa (máx. 3 no total, como hoje) não baixa nem transcreve de novo.
- **Perfil morto:** erro "usuário não encontrado" marca o perfil como `inativo` no estado. Ele é pulado por 24h e aparece no relatório para o Arthur. Não é removido da lista sozinho.
- **Orçamento por rodada:** a rodada para de tentar vídeos novos quando passar de ~8 min, deixando o resto para a próxima. Assim um vídeo pronto não espera vídeos problemáticos.

### Etapa 2 — Vaga única e coordenada
- Um só módulo `ritmo` decide a próxima vaga com uma regra: intervalo mínimo entre posts (`INTERVALO_POSTS`) + alternância notícia/vídeo quando há vídeo esperando (comportamento atual de `vez_do_video`, sem mudar a regra).
- **Vídeo espera a vaga dentro da própria rodada (decisão do construtor, revisada após a checagem):** hoje `_cedo_demais()` é checado *antes* de baixar, então a rodada sai e o vídeo só é feito 20 min depois. Novo: se faltar até ~10 min para a vaga abrir, a rodada de parceiro já baixa, escreve e monta o vídeo, espera a vaga dentro da mesma execução, roda `ja_postado` de novo e publica. Se faltar mais, sai como hoje e marca `aguardando`.
- **Só a sequência de parceiro publica vídeo de parceiro.** Nada de MP4 pronto versionado em `main` e nada de duas sequências disputando o mesmo vídeo (evita publicação dupla).
- O vigia que hoje mora em `publicar.yml` continua, mas chama `python main.py vaga` (decisão em Python, testável) no lugar de lógica em shell.

### Etapa 3 — Estado sem atropelo
- Um único comando `python main.py salvar-estado` faz o commit do estado com mescla. Hoje `publicar.yml` já mescla o `posts.db`; a mescla passa a valer também para `state/parceiro.json` (união de `vistos`, maior `ts` vence) e `queue/`.
- Os dois workflows usam esse mesmo comando, com retentativas. Nenhuma rodada termina como `failure` só por conflito de push.

### Etapa 4 — Código organizado
Pacote `pbminuto/` com responsabilidades claras; os arquivos atuais da raiz viram fachadas finas (reexportam) até que testes e workflows apontem para o lugar novo:

```
pbminuto/
  coleta/      fontes de notícia (sources), parceiros (buscar, baixar, filtros)
  escrita/     editor, humanizar, checagem de cópia, semântico
  montagem/    layout, render, vídeo, audiograma, legenda/Whisper
  publicacao/  Instagram, hospedagem, prévia
  orquestra/   ritmo/vaga, rodada de notícia, rodada de parceiro
  estado/      db, parceiro.json, fila, mescla
main.py        só a linha de comando
```

- Mover **sem mudar comportamento**, um módulo por vez, com os 164 testes verdes a cada passo.

### Etapa 5 — Comandos simples para o Arthur
- Um workflow `painel.yml` (Run workflow com lista de opções): `status`, `fila`, `aprovar`, `aprovar-todos`, `descartar`, `refazer`, `pausar-parceiro`, `retomar-parceiro`, `pausar-perfil <@>`.
- `status` escreve um resumo no *Job Summary* do Actions: últimos posts, fila, perfis inativos, próximas vagas.
- `pausar` grava no estado (não em variável do GitHub). Assim a routine de acompanhamento também consegue ler.

### Etapa 6 — Prévia e relatório sempre
- Todo vídeo publicado gera prévia no ramo `previa-parceiro`, inclusive os de rodadas de `refazer`, que hoje ficaram sem.
- O ramo passa a **acumular** (soma arquivos, não força por cima) e apaga prévias com mais de 3 dias. Só o `parceiro.yml` grava nele. (Decisão do construtor.)
- O log de cada publicação traz numa linha só: `[parceiro] publicado <id_post> | @<perfil> | <EDITORIA> | <manchete>`. Isso facilita a routine horária.

## 8. Decisões que ficam com o construtor
- Nomes internos de funções e arquivos dentro do pacote.
- Formato exato do cache de transcrição (sugestão: `state/transcricoes/<id>.txt`, apagado após 3 dias).
- Valor do orçamento por rodada (sugestão: 8 min) e se vira variável.
- Ordem dos módulos na Etapa 4.

## 8b. Entrega
- Cada etapa só começa depois que a anterior estiver em produção e tiver rodado ~1 dia sem erro novo. As metas de uma semana (seção 10) são acompanhadas, mas não seguram a próxima etapa. (Decisão do construtor.)

## 9. Decisões do Arthur (21/11/2026)
- **Entrega por PR:** cada etapa vira um pull request; só entra em `main` com a aprovação do Arthur.
- **Editoria `MUNDO`:** criar. Notícia de fora do Brasil sai como `MUNDO`. Entra como **Etapa 0** (prompts do editor/parceiro, `editor.EDITORIAS`, layout, `REGRAS.md`, teste).
- **`@paraibabussines_`:** sai de `LISTA_PADRAO` e da Regra 4 (com teste), na Etapa 0. O marcador `inativo` da Etapa 1 continua para casos futuros.
- **Painel:** o alvo é indicado **colando o link** do Reel do parceiro ou do post do @pbminuto. O sistema acha o vídeo pelo link (shortcode → id). `pausar-perfil`/`retomar-perfil` recebem o @. O `painel.yml` convive com `aprovar-fila.yml` e as ações manuais do `parceiro.yml` até estar provado; depois os antigos saem num PR próprio. Aprovar/descartar vale para as duas filas (notícia e parceiro). Pausa de perfil vale até retomar.

## 10. Como saber que deu certo
- Rodada de parceiro com vídeo pronto: publicado em ≤ 1 vaga (~15 min) após ficar pronto, sem refazer.
- Rodadas de parceiro com `failure` por push: 0 numa semana.
- Tempo médio de rodada de parceiro sem vídeo novo: < 2 min. Com falhas repetidas: sem reprocessar download/transcrição.
- Todos os testes atuais + novos verdes; nenhuma regra do `REGRAS.md` quebrada.
- Arthur consegue aprovar, refazer e pausar pelo `painel.yml` sem digitar comando.
