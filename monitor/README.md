# Sistema de Monitoramento Automatizado

Sistema poderoso de monitoramento que testa automaticamente todos os endpoints, funcionalidades e APIs da aplicação IA de Conversação.

## Características

✅ **Testa todos os endpoints da API** (~25+ endpoints)
✅ **Detecta problemas comuns** (encoding UTF-8, APIs falhando, traduções faltando)
✅ **Correção automática** de erros quando possível
✅ **Relatórios detalhados** em JSON
✅ **Suporta múltiplos deployments** (production + clones)
✅ **Roda automaticamente** via Windows Task Scheduler

## Setup Rápido

### 1. Configurar URLs dos Clones

Edite `monitor/config/deployment_urls.json` e preencha os URLs dos seus clones:

```json
{
  "environments": [
    {
      "name": "production",
      "url": "https://ia-de-conversacao.vercel.app",
      "enabled": true
    },
    {
      "name": "clone1",
      "url": "https://seu-clone-1.vercel.app",
      "enabled": true
    }
  ]
}
```

### 2. Configurar Senha (Variável de Ambiente)

Crie/edite variável de ambiente `MONITOR_PASSWORD`:

```batch
setx MONITOR_PASSWORD "sua_senha_admin"
```

Ou adicione ao `.env` do projeto.

### 3. Testar Execução Manual

```batch
cd "C:\Users\whesl\OneDrive\Documentos\Projetos\_Projetos_Ativos\IA de conversação"
.venv\Scripts\python.exe monitor\monitor_app.py --env production
```

### 4. Ver Relatório

Relatório é salvo em: `monitor/reports/latest/summary.json`

## Uso

### Testar um ambiente específico:
```batch
python monitor\monitor_app.py --env production
```

### Testar todos os ambientes habilitados:
```batch
python monitor\monitor_app.py --all-envs
```

### Rodar via launcher (recomendado):
```batch
MONITOR.bat
```

## Configurar Task Scheduler (Execução Automática)

1. Abra **Task Scheduler** (Agendador de Tarefas)
2. Clique em **Criar Tarefa**
3. Configure:
   - **Nome:** MonitorEnglishApp
   - **Disparadores:** Novo → Repetir a cada **1 hora**, indefinidamente
   - **Ações:** Iniciar programa → `C:\Users\whesl\OneDrive\Documentos\Projetos\_Projetos_Ativos\IA de conversação\MONITOR.bat`
   - **Condições:** ✅ Acordar computador para executar
   - **Configurações:**
     - ✅ Permitir execução sob demanda
     - ✅ Parar tarefa se executar por mais de **1 hora**
4. Salvar

## Códigos de Saída

- **0:** ✅ Todos os testes passaram
- **1:** ⚠️ Alguns testes falharam (warnings)
- **2:** 🔴 Falha crítica (API down, autenticação quebrada)

## Estrutura de Arquivos

```
monitor/
├── config/
│   ├── deployment_urls.json    # URLs dos clones
│   └── monitor_config.json     # Configurações gerais
├── utils/
│   ├── logger.py               # Sistema de logging
│   ├── api_client.py           # Cliente HTTP
│   ├── validators.py           # Validadores de resposta
│   ├── auto_fix.py             # Auto-correção
│   ├── fixtures.py             # Dados de teste
│   └── audio_generator.py      # Gerador de áudio
├── suites/
│   └── test_suite_endpoints.py # Suite de testes de endpoints
├── reports/                     # Relatórios (git-ignored)
│   └── latest/                 # Link simbólico para último relatório
└── monitor_app.py              # Orquestrador principal
```

## Próximos Passos (Expansão)

O sistema está funcional com teste de endpoints. Para adicionar mais funcionalidades:

1. **Implementar suites restantes:**
   - `test_suite_scenarios.py` - Testar cenários de conversação
   - `test_suite_audio.py` - Testar TTS/STT
   - `test_suite_grammar.py` - Testar tópicos gramaticais
   - `test_suite_e2e.py` - Testes end-to-end completos

2. **Gerar relatórios HTML** (atualmente apenas JSON)

3. **Integração com GitHub Issues** (auto-criar issues para falhas persistentes)

4. **Notificações por email** (opcional)

## Logs

- **Sucesso:** `monitor_success.log`
- **Warnings:** `monitor_warnings.log`
- **Erros críticos:** `monitor_errors.log`
- **Detalhado:** `monitor/reports/latest/monitor.log`

## Troubleshooting

### Erro: "No password found"
Certifique-se que a variável `MONITOR_PASSWORD` está configurada.

### Erro: "Authentication failed"
Verifique se o email/senha em `deployment_urls.json` estão corretos.

### Symlink não funciona
Normal no Windows sem privilégios admin. Os relatórios ainda são salvos corretamente em `monitor/reports/<timestamp>/`.

## Suporte

Para problemas ou dúvidas, verifique:
- Logs em `monitor/reports/latest/`
- Configurações em `monitor/config/`
