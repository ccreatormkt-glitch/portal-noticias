# Guia de configuração do PB Minuto

Tempo total: cerca de 1 hora, uma única vez. Depois disso o portal roda sozinho.

Você vai precisar de: o Instagram @pbminuto, um perfil pessoal no Facebook (o seu),
a conta do GitHub e um computador.

---

## Parte 1 — Instagram e Facebook (15 min)

1. **Conta profissional.** No app do Instagram, logado no @pbminuto:
   Configurações → Tipo de conta e ferramentas → **Mudar para conta profissional** →
   **Empresa** → categoria **Site de notícias e mídia**.
2. **Página do Facebook.** Em facebook.com/pages/create, crie a página **PB Minuto**
   (categoria: Site de notícias e mídia). Use a mesma foto de perfil (`brand/avatar.png`).
3. **Ligar as duas.** Na Página do Facebook: Configurações → **Contas vinculadas** →
   Instagram → Conectar → entre com o @pbminuto.
4. **Perfil do Instagram:**
   - Foto: `brand/avatar.png`
   - Nome: `PB Minuto | Notícias de CG e JP`
   - Bio:
     ```
     Notícias de Campina Grande, João Pessoa e toda a Paraíba, no minuto em que acontecem.
     📍 Conferido em 2+ fontes · Errou? Corrigimos em público.
     ```
   - Destaque fixo **"Como trabalhamos"** (story com o texto da seção *Transparência*, no fim deste guia).

## Parte 2 — Chaves gratuitas (10 min)

Guarde cada chave num bloco de notas por enquanto. **Nunca mande chaves por chat.**

| Chave | Onde criar | Para quê |
|---|---|---|
| `GEMINI_API_KEY` | aistudio.google.com/apikey → *Create API key* | A IA que escreve as notícias |
| `PEXELS_API_KEY` | pexels.com/api → criar conta → *Your API Key* | Fotos ilustrativas do tema |
| `IMGBB_API_KEY` | api.imgbb.com → *Get API key* | Link público da capa do Reels |

## Parte 3 — App da Meta e token que não expira (25 min)

1. Acesse **developers.facebook.com** → *Meus apps* → **Criar app** →
   caso de uso *Outro* → tipo **Empresa** → nome `PB Minuto Bot`.
2. No painel do app, adicione o produto **Instagram** → opção
   **"API com login do Facebook"** (é a que permite enviar vídeo direto).
3. Abra o **Graph API Explorer** (developers.facebook.com/tools/explorer):
   - Selecione o app `PB Minuto Bot`.
   - Em *Permissões*, marque: `instagram_basic`, `instagram_content_publish`,
     `instagram_manage_comments`, `instagram_manage_insights`, `pages_show_list`,
     `pages_read_engagement`, `business_management`.
   - Clique **Gerar token de acesso** e autorize a Página PB Minuto e o @pbminuto.
4. **Token de longa duração** — no Explorer, cole no campo de consulta (troque os 3 valores;
   ID e chave secreta do app ficam em *Configurações do app → Básico*):
   ```
   oauth/access_token?grant_type=fb_exchange_token&client_id=ID_DO_APP&client_secret=CHAVE_SECRETA&fb_exchange_token=TOKEN_DO_PASSO_3
   ```
   Copie o `access_token` que voltar.
5. **Token da Página (não expira)** — com o token do passo 4 no campo de token, consulte:
   ```
   me/accounts?fields=name,access_token,instagram_business_account
   ```
   Na linha da Página PB Minuto, copie:
   - `access_token` → este é o **IG_ACCESS_TOKEN** (não expira);
   - `instagram_business_account.id` → este é o **IG_USER_ID**.
6. Confira em developers.facebook.com/tools/debug/accesstoken: colando o token,
   *Expira* deve mostrar **Nunca**.

> O app pode ficar em modo de desenvolvimento: para publicar na **sua própria** conta
> não é preciso enviar o app para revisão da Meta.

## Parte 4 — GitHub (10 min)

1. Crie o repositório **privado** `portal-noticias` (sem README) e avise o Claude:
   ele envia o código.
2. No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
   Crie um por um:
   `GEMINI_API_KEY`, `PEXELS_API_KEY`, `IMGBB_API_KEY`, `IG_USER_ID`, `IG_ACCESS_TOKEN`.
3. Na aba **Variables** (opcional), para mudar o padrão:
   | Variável | Padrão | Opções |
   |---|---|---|
   | `POST_MODE` | `auto` | `review` = espera sua aprovação |
   | `MAX_POSTS_PER_DAY` | `14` | qualquer número |
   | `PIPER_VOICE` | `pt_BR-faber-medium` | `pt_BR-cadu-medium`, `pt_BR-jeff-medium` |
   | `SENSITIVE_MODE` | `careful` | `skip` = não publica polícia/tragédia |

## Parte 5 — Primeiro teste (5 min)

Na aba **Actions** do repositório:

1. **checar-configuracao → Run workflow.** Precisa aparecer `ok` em IA, Instagram e
   hospedagem, e a lista de fontes respondendo.
2. **publicar-noticias → Run workflow → modo `dry`.** Gera até 3 Reels sem publicar.
   Baixe em *Artifacts → cards* e assista.
3. **boletim-bom-dia → Run workflow → teste `true`.** Gera o boletim sem publicar.
4. Gostou? Pronto: a partir daí tudo roda sozinho.
   - Notícias: de hora em hora, das 6h às 23h.
   - Boletim "Bom dia, Paraíba": todo dia às 6h40.
   - Métricas e aprendizado: a cada rodada.

## No dia a dia

| Situação | O que fazer |
|---|---|
| Uma notícia saiu com erro | Actions → **corrigir-noticia** → ID do post + texto da correção |
| Quero pausar o portal | Actions → publicar-noticias → *⋯* → **Disable workflow** |
| Quero aprovar antes de sair | Variável `POST_MODE` = `review`; aprovar em Actions → **aprovar-fila** |
| Uma rodada ficou vermelha | O GitHub manda e-mail. Abra o log: a última linha diz o motivo |

## Transparência (texto para o destaque "Como trabalhamos")

> **Como o PB Minuto trabalha**
> • Só publicamos notícia confirmada por pelo menos 2 veículos ou por fonte oficial.
> • Os textos são escritos com apoio de inteligência artificial e seguem regras rígidas:
>   nada é inventado, nada é copiado.
> • Fotos de banco de imagens levam o selo "Imagem ilustrativa".
> • A narração dos vídeos usa voz gerada por IA.
> • Em casos policiais, não divulgamos nomes de vítimas nem de suspeitos.
> • Errou? Corrigimos em público, no próprio post.
> • Fale com a gente pelo direct.

## Segurança (resumo)

- **Chaves só nos Secrets do GitHub.** Nunca no código, no chat, em e-mail ou em print. O GitHub esconde os Secrets nos logs.
- **O token do Instagram vai no cabeçalho das chamadas, nunca na URL.** Mensagens de erro passam por um filtro que troca qualquer chave por `***`.
- **Permissões mínimas.** O token só precisa das permissões listadas acima. Os workflows de teste e checagem só leem o repositório.
- **Entradas manuais** (modo, teste, errata) passam por variáveis de ambiente e são validadas: o ID da errata aceita só números.
- **A legenda nunca leva links nem @ de terceiros.** O texto vem de IA lendo notícias, então isso é removido antes de publicar.
- **O repositório é privado.** Deixe a verificação em duas etapas ligada no GitHub, no Facebook e no Instagram.
- **Se uma chave vazar:** gere outra no site de origem e troque o Secret. Para o token da Meta, remova o app em Configurações › Integrações comerciais do Facebook e gere um novo.
