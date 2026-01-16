# 🗣️ Conversation Practice - AI Language Learning App

Uma aplicação interativa para prática de conversação em inglês usando IA (Google Gemini) com reconhecimento de voz, tradução em tempo real e feedback personalizado.

## ✨ Funcionalidades

### 🎯 Principais
- **34 cenários de conversação** (cafeteria, aeroporto, hospital, etc.)
- **Reconhecimento de voz** com Web Speech API
- **Text-to-Speech** com Google Cloud TTS Standard Voices em português brasileiro
- **Traduções em tempo real** para português
- **Relatórios de performance** com correções gramaticais
- **Exportação de relatórios** em PDF e JSON
- **Persistência automática** de conversas no navegador

### 🔒 Segurança
- Autenticação JWT com tokens de 7 dias
- CORS configurável por ambiente
- Rate limiting (30 req/min para chat, 60 req/min para TTS)
- Validação de entrada (máx 500 caracteres)
- Variáveis de ambiente protegidas

### 📱 Responsividade
- Design mobile-first com viewport dinâmico
- Suporte a teclado virtual sem sobreposição
- Fallback para input de texto em navegadores sem Speech API

## 🚀 Instalação e Configuração

### Pré-requisitos
- Python 3.8+
- Conta Google Cloud com Gemini API habilitada

### 1. Clone o repositório
```bash
git clone <seu-repositorio>
cd "IA de conversação"
```

### 2. Instale as dependências
```bash
pip install -r requirements.txt
```

### 3. Configure as variáveis de ambiente
Copie o arquivo de exemplo e preencha com suas credenciais:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:
```env
# Google Gemini API Key - Obtenha em: https://makersuite.google.com/app/apikey
GOOGLE_API_KEY=sua_chave_api_aqui

# Origens permitidas para CORS (separadas por vírgula)
ALLOWED_ORIGINS=http://localhost:4004,http://localhost:3000

# Chave secreta para sessões (gere uma aleatória forte)
SESSION_SECRET=sua_chave_secreta_aqui

# Rate Limiting
RATE_LIMIT_REQUESTS=30
RATE_LIMIT_WINDOW=60
```

**⚠️ IMPORTANTE:** Nunca commite o arquivo `.env` com suas chaves reais!

### 4. Execute o servidor
```bash
python api/index.py
```

O servidor estará rodando em `http://localhost:4004`

### 5. Acesse a aplicação
Abra o navegador e acesse: `http://localhost:4004`

## 📖 Como Usar

### Login
1. Acesse a página inicial
2. Digite seu nome e email
3. Clique em "Start Practice"

### Praticando Conversação
1. Escolha um cenário (ex: Coffee Shop, Airport, etc.)
2. Clique em "Start Conversation"
3. Use o botão do microfone para falar (ou digite se seu navegador não suportar voz)
4. Ouça a resposta da IA e veja a tradução
5. Continue a conversa naturalmente

### Gerando Relatório
1. Após algumas trocas de mensagens, clique em "Ver relatório"
2. Visualize:
   - ✏️ **Correções**: Seus erros gramaticais com sugestões
   - ⭐ **Elogios**: Pontos positivos da sua conversa
   - 🎯 **Dicas**: Sugestões de melhoria
   - ➡️ **Próxima frase**: Exercício para praticar

### Exportando Resultados
- **PDF**: Clique em "📄 Exportar PDF" para baixar um relatório formatado
- **JSON**: Clique em "💾 Exportar JSON" para análise programática

## 🏗️ Arquitetura

### Backend (Flask + Python)
```
api/
├── index.py          # Servidor Flask com todos os endpoints
```

**Endpoints principais:**
- `POST /api/auth/login` - Autenticação de usuário
- `POST /api/chat` - Envio de mensagem e resposta da IA
- `POST /api/report` - Geração de relatório de performance
- `POST /api/tts` - Text-to-speech
- `POST /api/export/pdf` - Exportação em PDF
- `GET /api/conversations` - Histórico de conversas
- `GET /api/health` - Status do serviço

### Frontend (Vanilla JS)
```
├── api-client.js     # Cliente API com gerenciamento de tokens
├── app.js            # Lógica principal da aplicação
├── style.css         # Estilos (glassmorphism design)
├── login.html        # Página de login
├── scenarios.html    # Seleção de cenários
├── practice.html     # Interface de conversação
└── scenarios_db.json # Base de dados de cenários
```

## 🔧 Melhorias Implementadas

### Segurança
✅ API key removida do código e movida para .env
✅ Autenticação JWT com expiração
✅ CORS restrito a origens específicas
✅ Rate limiting por IP
✅ Validação de entrada com limites de tamanho

### UX/UI
✅ Persistência de conversas no localStorage
✅ Recuperação automática após refresh
✅ Indicadores visuais de carregamento (spinner)
✅ Mensagens de erro descritivas
✅ Responsividade mobile com viewport dinâmico
✅ Fallback para input de texto (navegadores sem Speech API)

### Funcionalidades
✅ Exportação de relatórios em PDF e JSON
✅ Prompts de IA melhorados para correção gramatical
✅ Armazenamento de histórico no backend
✅ Traduções em todas as respostas da IA
✅ Health check endpoint

## 🌐 Deploy

### Vercel
A aplicação já está configurada para deploy no Vercel via `vercel.json`.

**Passos:**
1. Instale o Vercel CLI: `npm i -g vercel`
2. Configure as variáveis de ambiente no dashboard do Vercel
3. Execute: `vercel --prod`

**⚠️ Lembre-se:** Configure as variáveis de ambiente no painel do Vercel antes do deploy!

## 🛠️ Tecnologias Utilizadas

- **Backend:**
  - Flask 3.0
  - Google Generative AI (Gemini 3.0 Flash Preview)
  - Flask-CORS
  - Flask-Limiter
  - PyJWT
  - google-cloud-texttospeech
  - ReportLab (geração de PDF)

- **Frontend:**
  - Vanilla JavaScript
  - Web Speech API
  - Fetch API
  - LocalStorage API

## 📝 Estrutura de Dados

### Relatório de Performance
```json
{
  "titulo": "Ótimo progresso!",
  "emoji": "🎉",
  "tom": "positivo e encorajador",
  "correcoes": [
    {
      "ruim": "I go to store yesterday",
      "boa": "I went to the store yesterday"
    }
  ],
  "elogios": [
    "Boa pronúncia das palavras básicas",
    "Manteve a conversa fluindo naturalmente"
  ],
  "dicas": [
    "Pratique mais o past simple",
    "Adicione detalhes às suas respostas"
  ],
  "frase_pratica": "Can I get a medium latte with almond milk, please?"
}
```

## 🐛 Troubleshooting

### Problema: "AI service not configured"
**Solução:** Verifique se `GOOGLE_API_KEY` está definida no `.env`

### Problema: "Session expired"
**Solução:** Faça login novamente. Tokens expiram após 7 dias.

### Problema: Microfone não funciona
**Solução:**
- Use Chrome ou Edge (melhor suporte)
- Permita acesso ao microfone quando solicitado
- Use o fallback de texto input

### Problema: "CORS error"
**Solução:** Adicione a origem do frontend em `ALLOWED_ORIGINS` no `.env`

## 📊 Limites e Rate Limiting

| Endpoint | Limite | Janela |
|----------|--------|--------|
| `/api/auth/login` | 10 req | 1 min |
| `/api/chat` | 30 req | 1 min |
| `/api/tts` | 60 req | 1 min |
| `/api/report` | 10 req | 1 min |
| `/api/export/pdf` | 5 req | 1 min |

## 🔐 Segurança em Produção

**Checklist antes do deploy:**
- [ ] Altere `SESSION_SECRET` para uma chave aleatória forte
- [ ] Configure `ALLOWED_ORIGINS` apenas com domínios confiáveis
- [ ] Nunca exponha `GOOGLE_API_KEY` no frontend
- [ ] Habilite HTTPS no servidor
- [ ] Monitore uso da API Gemini para evitar custos inesperados
- [ ] Configure backup do histórico de conversas se necessário

## 📄 Licença

Este projeto é para fins educacionais. Sinta-se livre para usar e modificar conforme necessário.

## 🤝 Contribuindo

Melhorias são bem-vindas! Áreas de interesse:
- [ ] Adicionar suporte a mais idiomas
- [ ] Implementar sistema de níveis/gamificação
- [ ] Integrar banco de dados real (PostgreSQL/MongoDB)
- [ ] Adicionar gráficos de progresso ao longo do tempo
- [ ] Implementar PWA para uso offline

## 📧 Suporte

Para questões ou problemas, abra uma issue no repositório.

---

Desenvolvido com ❤️ para prática de conversação em inglês.
