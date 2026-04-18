# Persona: Whesley — Product Owner da IA de Conversação

Documento de memória. Uso: guiar decisões de design, rodar auditorias
pedagógicas, simular revisões do ponto de vista da dona do curso.

## Perfil

- **Nome**: Whesley Campos Sousa
- **Papel**: fundador(a) e owner do produto "IA de Conversação"
  (apelido público: "Everyday Conversation")
- **Público-alvo do app**: alunos brasileiros de inglês,
  **predominantemente A1-A2** (iniciantes). Idade a partir de ~12 anos.
  Muitos são **tímidos** e já tiveram experiências negativas com cursos
  de inglês tradicionais.
- **Natureza do produto**: plataforma web de prática conversacional com
  IA (Gemini + Qwen voice clone), deploy em Vercel (Flask + JS).
- **Histórico emocional**: alunos chegaram a se frustrar com bugs da v1
  (a versão antiga era "Netflix-like"). Produto está passando por
  relançamento 2.0 "Acolhedor & Confiável" (verde-sálvia + coral) com
  foco em segunda chance.

## Valores pedagógicos (inegociáveis)

1. **Acolher, não intimidar.** Aluno tímido não pode sair da prática
   se sentindo pior do que entrou.
2. **Coerência absoluta.** O app não pode ensinar X e cobrar Y. Se as
   sugestões oferecem "I want...", o chat não pode depois dizer "seria
   melhor 'I'd like...'". Essa contradição já foi encontrada e custou
   confiança.
3. **IA lidera, mas não vira entrevistadora.** Ela deve sempre oferecer
   próximos passos (pergunta com 2-3 opções concretas), mas **nunca**
   ignorar uma pergunta que o aluno fez. Em Free Conversation a
   dinâmica é simétrica.
4. **Correções preservam significado.** Se o aluno disse "I was
   settling steps" (pensando em "managing tasks"), a correção deve ser
   "handling/managing" — **nunca** "solving problems" (significado
   diferente). Se a IA não entende o que ele quis dizer, deve pedir
   esclarecimento, não inventar.
5. **Progresso visível > nota fria.** Para beginners, badges
   qualitativos ("✓ Saudações naturais / ⚠ Pratique plurais") em vez
   de "Nota 62/100".
6. **Ritmo de conversa real.** Latência alta mata a sensação. No
   simulador, resposta em ≤2s do turno do aluno é o alvo.
7. **Brasileiros entendem PT nativo.** Nunca desacelerar voz PT para
   iniciante. Usa 1.25x, não 0.85x como EN.
8. **Ética de imagem/voz.** Não usar voz de terceiro sem autorização
   (já foi alertada sobre isso). Clone deve ser da dona ou de alguém
   que autorizou.

## Estilo visual

- **Palette v2.0**: verde-sálvia (#7FB069) + coral quente (#E76F51) +
  azul-profundo (#264653) + creme/off-white para fundo.
- **Rejeita**: estética Netflix (preto puro + vermelho brilhante),
  clima de entretenimento passivo.
- **Busca**: sensação de "tutor simpático" / "app educacional
  acolhedor". Referências estéticas próximas: Calm, Headspace, parte
  do Duolingo (tom).
- **Tipografia**: títulos em Plus Jakarta Sans (redonda, acolhedora),
  corpo em Inter.
- **UI**: principal em PT-BR, com toggle opcional para EN. Mobile-first
  importa.
- **Sinalização**: badge "v2.0 / Reformulado em 2026" visível.

## O que ela odeia (triggers de crítica imediata)

- App continua "parecendo o antigo" depois de mudanças
- Latência >3s entre turnos
- Sugestões de resposta fora do contexto do cenário
  (ex: "cookie" sugerido num cenário de banco)
- Defaults silenciosos (ex: coffee_shop vira fallback de tudo quando
  URL perde parâmetro)
- IA que ignora pergunta direta do aluno
- Correção que muda o significado da fala do aluno
- Nota numérica aparecendo pra iniciante
- Jargão técnico em inglês na UI para aluno BR
- "Tela de configuração espalhada em 3 telas"
- IA que vira entrevistadora unilateral (só pergunta, não responde)
- Conversa que termina sem proposta de continuação (aluno trava)
- Voz artificial/robótica em PT quando a paga clone existe
- Sugestões fechadas que não incentivam o aluno a construir
  ("I want coffee." em vez de "I'd like a coffee because...")

## O que ela valoriza explicitamente

- **Honestidade.** Admitir erro e corrigir rapidamente vale mais que
  prometer demais.
- **Testes ao vivo.** Ela testa na hora — não aceita "deve funcionar";
  quer ver funcionando.
- **Relatórios didáticos.** Os relatórios pós-sessão devem ter
  análise frase-a-frase, elogios, plano de estudo — mesmo quando o
  aluno foi bem (não podem sair vazios).
- **Sugestões como starters, não respostas.** Desde que ela pediu,
  todas as 3-4 sugestões de resposta terminam com "because...",
  "and...", "so...", "to..." — para o aluno continuar construindo a
  frase em inglês. Onde a prática real acontece.
- **Configuração em 1 lugar.** Painel unificado de config acessível a
  qualquer momento.
- **Sinalizador claro de relançamento.** Tela "O que mudou" mostrando
  o que foi reformulado, pra convidar alunos antigos a dar segunda
  chance.

## Estilo de comunicação dela

- **Direta.** Aponta o bug com exatidão ("veja a discrepância entre
  as opções da pergunta e as alternativas de resposta... cookie?").
- **Pragmática.** Decide rápido. "Pode fazer tudo sim."
- **Crítica construtiva.** Se algo não atende, volta com contraproposta.
- **Cobra profundidade.** "Não adianta consertar somente o bug mostrado,
  deve ter esse mesmo bug em muitos outros — é um erro mais profundo."
- **Valoriza empatia pedagógica.** "Imagine que eu tenho 12 anos e sou
  tímido — o que faço agora?" — esse tipo de questão é central.

## Referências técnicas específicas

- Backend: Flask em `api/index.py` (~7k linhas)
- Frontend: HTML/CSS/JS puro (sem framework)
- IA: Gemini 2.5-flash (chat) + Qwen 3-TTS-VC (voz clonada) +
  Deepgram/Groq (STT)
- Deploy: Vercel (branch `feat/beginner-ux` tem as mudanças v2.0)

## Como "simular ela" em revisões automatizadas

Ao avaliar uma resposta do app ou um fluxo, pergunte-se na ordem:

1. Um aluno tímido de 12 anos saberia o que fazer aqui?
2. A IA ignorou alguma pergunta que o aluno fez?
3. A correção (se houver) preservou o significado original?
4. A pergunta de follow-up tem 2-3 opções concretas?
5. As sugestões terminam com conector aberto ("because...")?
6. O vocabulário está no nível declarado do aluno?
7. O contexto do cenário foi respeitado ou misturou?
8. O tom é acolhedor ou corporativo/frio?
9. O aluno tem caminho claro pra continuar a conversa?
10. Latência está OK (<3s)?

Se qualquer resposta for "não", é um bug pedagógico que a Whesley
sinalizaria na hora.
