# Regras fixas do PB Minuto

Valem para tudo o que o sistema produz. Cada regra tem um teste que falha se ela for quebrada.

## 1. Letra: só Inter
- Capa, vídeo, legenda do vídeo, logo, avatar e qualquer arte nova usam **só a Inter** (Inter e
  Inter Display, arquivos em `fonts/`). Destaque é peso, tamanho ou caixa, nunca outra família.
- Exceção: os ícones (`MaterialIcons`), que são desenhos, não letras.
- Onde mexer: `layout.py` (`FONTE`, `FONTE_DISPLAY`, `FONTE_LOGO`, `PAPEIS`).
- Teste: `tests/test_regra_fonte.py`.

## 2. Texto: skill STE80 Humanizer em toda escrita e reescrita
- A skill fica em `skills/ste80-humanizer/` (MIT). Atualizar o `SKILL.md` atualiza a regra.
- Na escrita: o prompt do editor (`editor.SYSTEM`) e o do revisor de originalidade
  (`editor.REESCRITOR`) trazem a REGRA DE ESCRITA da skill: uma ideia por frase, frases curtas, voz
  ativa, palavras simples, sem marcas de texto de IA (travessão, "não é só X, é Y", palavras infladas,
  gerúndio pendurado...).
- Depois da escrita: toda notícia, inclusive pauta pedida, "refazer" e os vídeos do parceiro
  (`parceiro.escrever`), passa por `editor.humanizar`,
  que revisa manchete, linha fina, resumo, tópicos e legenda. A narração é montada desses campos, então
  o áudio sai revisado junto.
- Fidelidade: se a revisão perder ou inventar número, estourar a manchete ou ficar parecida com a
  fonte, fica o texto original (a notícia sai do mesmo jeito).
- Só desligar em emergência: variável `HUMANIZAR=0` no GitHub.
- Teste: `tests/test_humanizar.py`.

## 3. Visual: editoria só em texto (pedido do Arthur, 21/11/2026)
- Na capa e nos Reels a editoria vai só como texto branco em CAIXA ALTA, sem o quadrado colorido do
  tema (`layout.EDITORIA_CAIXA = False`). As cores de `COR_EDITORIA` ficam guardadas, sem uso.

## 4. Vídeos dos parceiros autorizados (padrão desde 21/11/2026)
- Parceiros: @jornaldapb, @paraibabussines_, @portalresumopb, @noticiacertapb e @blognewspb
  (`parceiro.LISTA_PADRAO` ou a variável `PARCEIRO_LISTA`). Só entram Reels publicados depois da data
  em que cada perfil entrou na lista.
- @blognewspb e @portalresumopb usam moldura ("grade") com a marca deles: o sistema grava só a parte
  do vídeo que mexe.
- Só vídeos que NÃO são collab (a autorização cobre só esses).
- Verifica o Instagram de cada um a cada 20 min (agendamento do `parceiro.yml` + vigia no `publicar.yml`).
- Antes de montar, confere se o fato já saiu no perfil (mesma checagem das notícias: banco, legendas
  dos últimos posts e IA). Se já saiu, pula.
- Sem link pela API, baixa o Reel pela página do post (yt-dlp). Se o Instagram pedir login, salvar os
  cookies de uma conta secundária no segredo `PARCEIRO_IG_COOKIES`.
- Layout no vídeo e na capa do Reels: barra do PB Minuto, degradê preto que esconde a manchete antiga,
  etiqueta nova e desfoque automático da marca d'água/texto parado (`PARCEIRO_AUTO_MARCA=0` desliga).
- Publica direto, sem aprovação (`PARCEIRO_MODO=review` volta à fila de aprovação).

## 5. Hashtags só em letras minúsculas (pedido do Arthur, 21/11/2026)
- Toda hashtag sai em minúsculas: `#joaopessoa`, `#campinagrande`, `#cultura` (nunca `#JoaoPessoa`).
- Vale para notícias, vídeos dos parceiros, boletim e qualquer post novo: `publish.post` e
  `publish.post_reel` passam toda legenda por `publish.hashtags_minusculas` antes de enviar, e
  `build_caption` já monta as hashtags em minúsculas. Os prompts do editor e do parceiro pedem o mesmo.
- Teste: `tests/test_regra_hashtag.py`.

## 6. Perfil nunca parado: sem vídeo, sai notícia (pedido do Arthur, 21/11/2026)
- Vídeo de parceiro e notícia dividem o mesmo ritmo (1 post a cada ~14 min) e o mesmo limite de 24h.
- A notícia nunca espera vídeo: a sequência de notícias confere a cada ~5 min e, se não saiu vídeo de
  parceiro (nenhum novo, repetido, collab ou falhou), a vaga vai para a melhor notícia nova.
- Só fica sem post quando o limite de 24h do Instagram está cheio (cerca de 100 posts por dia).
- Quando há vídeo de parceiro esperando vaga, notícia e vídeo alternam: se o último post foi notícia,
  a próxima vaga é do vídeo (`parceiro.vez_do_video`; o vigia do `publicar.yml` chama o parceiro na hora).
- Onde: `main.cmd_run` (ritmo e limite contam notícias + `parceiro.publicados_24h()`), `parceiro._cedo_demais`.
- Teste: `tests/test_fluxo.py::test_sem_video_de_parceiro_sai_noticia`.

## 7. Mix de publicações (pedido do Arthur, 22/11/2026)
- Meta nos últimos 20 posts (notícias + vídeos de parceiro): **Campina Grande 30%, João Pessoa 20%,
  Brasil 30%, Mundo 20%**. Muda pela variável `MIX` (ex.: `cg:30,jp:20,brasil:30,mundo:20`).
- O público que importa é o de Campina Grande e João Pessoa: notícia que cita a cidade vem antes. O
  interior (Agreste, Brejo, Cariri, Curimataú, Sertão) entra na cota de Campina; litoral e Grande João
  Pessoa, na de João Pessoa; notícia do estado todo completa a que estiver mais atrasada.
- Cada rodada escolhe a categoria mais atrasada; sem notícia nova confirmada nela, passa para a
  próxima (regra 6: o perfil nunca fica parado).
- Vídeos de parceiro contam pela cidade do fato (a IA marca a abrangência: Paraíba, Brasil ou Mundo).
- Fontes de Mundo: g1 Mundo, Agência Brasil Internacional e BBC News Brasil.
- Onde: `sources.categoria`, `main._ordem_do_mix`, `parceiro.categoria_do_card`. Testes em `tests/test_fluxo.py`.

## 8. Stories só dos posts da Paraíba (pedido do Arthur, 22/11/2026)
- Todo post da Paraíba (Campina Grande, João Pessoa, interior e estado), notícia ou vídeo de parceiro,
  sai no feed e também nos Stories, com o mesmo vídeo (cortado em 59 s se for mais longo).
- Brasil e Mundo saem só no feed.
- Cada Story conta como 1 publicação no limite de 100 por 24h da API do Instagram: o ritmo e o
  limite diário contam os Stories (post com Story gasta 2 vagas; a próxima vaga demora o dobro).
- Story que falha ou sem vaga no limite não derruba o post do feed.
- Variável `STORIES`: `paraiba` (padrão), `todos` ou `nenhum`.
- Onde: `publish.story_se_paraiba`, `publish.post_story`, `parceiro.espera_ritmo`. Testes: `tests/test_stories.py`.

## 9. Parceiro de imagem @bombaparaiba_ (pedido do Arthur, 22/11/2026)
- Só postagens estáticas de imagem; nunca Reels, carrossel ou Stories do parceiro; nunca collab.
- A foto central sai da moldura (cartão branco, manchete, logo e site ficam de fora) e vira a foto do
  nosso Reels e da capa. Recorte com sobra branca da moldura é recusado.
- O texto passa pelas mesmas regras das notícias (`editor.make_card`: original, sem copiar, STE80).
- Fidelidade: números/datas do nosso texto precisam estar no post; a IA confere se o texto novo é fiel
  e se o original deixa algo duvidoso. Qualquer dúvida: vai para a fila de aprovação, não publica direto.
- Polícia e temas sensíveis: foto ilustrativa, nunca a foto do caso (regra de credibilidade).
  (Atualizado em 23/11/2026, regra 13: a foto vem primeiro do Google Imagens, mesmo em polícia.)
- As fontes não aparecem no post (regra do PB Minuto), como nos outros parceiros.

## 10. Parceiro @destaques.dodia (pedido do Arthur, 22/11/2026)
- Autorizado; usa Reels e posts de imagem, só os publicados a partir de 22/11/2026 13h40 (Fortaleza); nunca collab.
- Remove as marcas d'água DELE (autorizado): a faixa roxa fixa com a manchete, "DESTAQUES DO DIA" e o
  telefone (flag `faixa`: o post é cortado acima dela) e o logo translúcido do "play" no meio de alguns
  vídeos (flag `marca`: máscara do logo fixo + removelogo).
- Marca de terceiros (agência, fotógrafo, outro perfil) não é removida.
- Texto e manchete sempre reescritos pelas regras do PB Minuto; fontes não aparecem no post.
- Para outros parceiros: skill `pb-minuto-novo-parceiro` (ações amostra, calibrar-marca e teste-parceiro).


## 11. Encerramento "Siga o PB Minuto" (pedido do Arthur, 22/11/2026)
- Toda narração (notícia, vídeo de parceiro e boletim) termina com a frase fixa "Siga o PB Minuto."
- Toda legenda termina com "👉 Siga o PB Minuto: @pbminuto" (antes das hashtags).
- A IA não escreve "siga" nos textos: o sistema acrescenta o encerramento.
- Onde: `video.roteiro`, `boletim.py`, `publish.build_caption`. Teste: `tests/test_publicacao.py`.

## 12. Posts de imagem do @noticiacertapb e alternância (pedido do Arthur, 22/11/2026)
- Além dos Reels, entram as notícias em carrossel do @noticiacertapb desde 21/11/2026 00h de Fortaleza
  (linha `noticiacertapb|...|imagem|carrossel|faixa=vermelha|topo=15`).
- Usa só a 1ª foto do carrossel: corta a faixa vermelha dele (editoria, manchete, telefone e patrocinadores)
  e 15% do alto (logo Notícia Certa). As imagens soltas dele são anúncios de clientes e nunca entram.
- A foto vira Reels do PB Minuto com locução e o texto é reescrito pelas regras das notícias.
- Vídeo e post de imagem dos parceiros se alternam: depois de um vídeo, as linhas de imagem pegam a vaga
  primeiro, e vice-versa (`est["ultimo_tipo"]`). Se o tipo da vez não tiver nada novo, o outro usa a vaga.

## 12. Uma fonte basta (pedido do Arthur, 23/11/2026)
- Antes: a notícia só entrava se 2 veículos diferentes dessem o mesmo fato (ou 1 grande/oficial).
- Agora: basta 1 veículo da nossa lista de fontes (`MIN_SOURCES=1`).
- Polícia também com uma fonte só (Arthur liberou em 23/11/2026, `MIN_SOURCES_POLICIA=1`).
  Para voltar a exigir 2 veículos em crime/prisão/acusação de site pequeno: variável
  `MIN_SOURCES_POLICIA=2`. O filtro de temas sensíveis continua barrando acusação sem prova.
- Continuam valendo: filtro de temas sensíveis, trava contra repetição e reescrita sem cópia.
- Onde: `main._confirmada`, `sources.Cluster.policial`. Teste: `tests/test_fluxo.py`.

## 13. Foto do Google Imagens (pedido do Arthur, 23/11/2026)
- As imagens de banco/IA saíam diferentes do assunto. A foto de fundo passa a vir primeiro do próprio
  Google Imagens, sem filtro de licença, inclusive em polícia (escolha do Arthur, ciente do risco de
  direito autoral e de foto do caso).
- Como: o Chrome abre a busca pelo assunto (manchete + cidade; depois o lugar real ou os destaques), a IA
  olha as miniaturas e só aprova a que corresponde ao fato (nota >= 7), recusando texto, marca d'água, logo
  e rosto reconhecível; o Chrome abre a foto e tira um print dela. Sem chave de API. Até 2 buscas por notícia.
- Onde roda (`GOOGLE_VIA`): `mac` (padrão) = no Mac do Arthur, com o Chrome e a internet dele, para o
  Google não pedir captcha. O robô dispara `google-mac.yml` (runner próprio com o rótulo `pbminuto-mac`),
  espera até 3 min e baixa a foto do ramo `google-fotos`. Mac desligado: cancela o pedido, segue sem foto do
  Google e fica 20 min sem pedir. `aqui` = Chromium do servidor do GitHub (o Google costuma pedir captcha).
- Sem foto aprovada, segue a ordem antiga (vídeo/banco de fotos/IA/cidade).
- Crédito na arte e na legenda: "Foto: Reprodução / <site de origem>".
- Desliga com a variável `GOOGLE_IMAGENS=false`.
- Onde: `illustrate.foto_google` (começo de `illustrate.imagem_de_fundo`, notícias e parceiros),
  `google_mac.py`, `.github/workflows/google-mac.yml`. Instalação no Mac: SETUP.md, "Google Imagens pelo Mac".
  Teste: `tests/test_google_imagens.py`.

## 13. Foto da própria notícia primeiro (pedido do Arthur, 23/11/2026)
- Ordem da foto: 1) foto de capa das matérias que deram o fato; 2) Google Imagens; 3) vídeo/fotos de
  banco; 4) fotos livres; 5) ilustração por IA.
- A IA lê o TEXTO INTEIRO (manchete, linha fina, pontos, legenda, cidade) e só aprova foto que mostra
  este fato (nota 7 ou mais). Fontes abertas (Agência Brasil, sites .gov.br) são olhadas primeiro.
- Foto com marca d'água, logo ou assinatura de outro veículo por cima, ou arte com texto: recusada.
  Marca de terceiros nunca é apagada (é a identificação do dono da foto).
- Polícia: nada de rosto de suspeito, preso, vítima ou criança, nem cena chocante.
- Crédito na arte ("Foto: site") e na legenda ("📷 Foto: reprodução/site").
- As buscas do Google e a ilustração por IA usam a cena que a IA tirou do texto inteiro.

## 14. Gancho e teste A/B (23/11/2026)
- O título é a capa e os 3 primeiros segundos do vídeo: abre com o elemento mais forte e verdadeiro
  do próprio texto (número, lugar conhecido, prazo, efeito na vida do leitor), com regra por editoria
  no prompt do editor (`editor.SYSTEM`, bloco GANCHO).
- Proibido: "você não vai acreditar", "veja", "saiba", "entenda", "chocante", pergunta, mistério,
  exagero ou promessa que o texto não cumpre.
- Teste A/B: A = fato primeiro, B = efeito no leitor primeiro. Alterna post a post (`AB_GANCHO=ab`);
  o relatório semanal compara o alcance. Para fixar a vencedora: variável `AB_GANCHO=A` ou `B`.

## 15. SEO do Instagram (23/11/2026)
- A busca do Instagram (e do Google) lê o texto: a primeira linha da legenda (antes do "mais", ~125
  caracteres) traz cidade + tema como as pessoas digitam ("concurso em Campina Grande"), sem lista
  de palavras-chave.
- Hashtags viram rótulos: 3 a 5, minúsculas, locais primeiro (vale também para parceiros).
- No perfil (manual, no app): nome "PB Minuto | Notícias de Campina Grande e João Pessoa" e bio com
  Paraíba, Campina Grande e João Pessoa.

## 16. Vigia de comentários e pausa (23/11/2026)
- Toda hora o robô lê os comentários dos posts das últimas 48h e separa os que apontam erro
  (fake, mentira, informação errada, nome/cidade/foto errados, ameaça de processo).
  Ficam em `state/alertas_comentarios.json` e no log. O robô NÃO responde nem apaga comentário.
- Confirmado o erro: Actions > corrigir-noticia (comentário de correção fixado no post) ou
  Actions > apagar-post. Crítica legítima não se apaga; só spam, ofensa e ameaça (no app).
- Crise ou luto: variável `PAUSAR=true` para tudo (notícias e parceiros); `false` volta.
