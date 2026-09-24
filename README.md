# Laya Dataset Manager

Aplicação local para organizar conhecimento em Markdown, montar datasets auditáveis e preparar especializações do [Laya](https://github.com/NandhaKishorM/laya). Roda no Ubuntu do WSL2 com Docker e Docker Compose.

## Visão geral

| Serviço | Função | Endereço |
| --- | --- | --- |
| `web` | Aplicação Rust/Axum, interface e SQLite | <http://localhost:8080> |
| `laya` | Runtime oficial Laya em CUDA | <http://localhost:8000> |

O SQLite fica no volume `laya-dataset-manager-app-data` e os modelos no volume `laya-dataset-manager-model-cache`. Ambos ficam fora do Git. As portas são vinculadas somente a `127.0.0.1`.

## Recursos disponíveis

- Pastas recursivas e multinível.
- Conteúdos com assunto, título, breve e Markdown.
- Separação entre material de dataset e de treinamento.
- Pedidos de treinamento com snapshot dos conteúdos incluídos.
- Inferência Laya local com checkpoint multilíngue.

> O pedido de treinamento atual é rastreável, mas ainda não executa fine-tune. O estado `waiting_for_laya_training_api` não comprova treinamento do modelo.

## Pré-requisitos

- WSL2 com a distribuição `Ubuntu`.
- Docker Engine e Docker Compose.
- GPU NVIDIA e NVIDIA Container Toolkit para a inferência CUDA.
- Git.

## Início rápido

No PowerShell:

```powershell
wsl -d Ubuntu --cd /opt/projects/laya-dataset-manager
```

No Ubuntu:

```bash
cp .env.example .env
docker compose up -d --build --wait
```

Abra <http://localhost:8080>. O primeiro início baixa dependências e o checkpoint do Laya; os seguintes reutilizam o cache.

## Uso do sistema

1. Em **Conteúdo**, crie pastas raiz ou filhas. Exemplo: `Atendimento > Financeiro > Cancelamentos`.
2. Cadastre cada material com tipo, pasta, assunto, título, breve e Markdown.
3. Em **Treinamento**, crie um pedido. O sistema registra referências imutáveis aos itens existentes naquele instante; itens posteriores não entram no pedido anterior.

O conteúdo Markdown é preservado como texto. Ele não é executado pelo navegador.

## Operação e diagnóstico

```bash
docker compose config --quiet
docker compose ps
curl --fail http://localhost:8080/health
curl --fail http://localhost:8000/health
docker compose logs -f web
docker compose logs -f laya
docker compose down
```

Confirme o acesso da GPU dentro do container:

```bash
docker compose run --rm --entrypoint python laya -c \
  "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
```

Exemplo de inferência tipada:

```bash
curl --fail http://localhost:8000/v1/systemone \
  -H 'content-type: application/json' \
  --data '{"state":"Quero cancelar minha assinatura","questions":{"urgente":{"type":"noul","instructions":"O pedido exige atendimento imediato?"}}}'
```

## Fine-tuning com Kaggle

O Laya não aprende diretamente de Markdown livre. Cada exemplo de fine-tuning precisa conter:

1. **Estado**: texto ou documento a avaliar.
2. **Pergunta tipada**: `choice`, `score` ou `noul`.
3. **Critérios/opções**, quando aplicável.
4. **Resposta esperada**: rótulo de referência.

O notebook oficial executa a construção do dataset, RLCD, calibração e avaliação. A referência do projeto estima 4–5 horas em 2×T4 para quatro épocas e aproximadamente 30 mil perguntas. A GPU local de 8 GB não é indicada para esse processo completo; use Kaggle ou outra infraestrutura compatível.

### Credencial Kaggle

1. Entre em <https://www.kaggle.com/>.
2. Abra **Settings > API Tokens**.
3. Gere um token ou uma chave legada `kaggle.json`.
4. Armazene a chave somente no Ubuntu:

```bash
mkdir -p ~/.kaggle
cp /caminho/seguro/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json
test -f ~/.kaggle/kaggle.json && echo 'credencial Kaggle configurada'
```

Nunca envie `kaggle.json` pelo chat, nunca o versione e nunca o inclua em imagens Docker. A futura integração deve montá-lo somente em tempo de execução, como arquivo de leitura.

### Evidências de treinamento concluído

Um fine-tune só é considerado bem-sucedido quando houver:

- dataset tipado, exportado e versionado;
- execução Kaggle com logs;
- checkpoint produzido;
- avaliação em dados separados;
- comparação de métricas entre modelo base e especializado;
- carregamento do modelo especializado pelo runtime Laya.

Um pedido registrado, conteúdo salvo ou healthcheck verde não é evidência de fine-tuning.

## Estrutura

- `src/`: API Rust e regras de domínio.
- `static/`: interface web.
- `docker/laya/`: imagem do Laya.
- `compose.yaml`: serviços, volumes e healthchecks.
- `docs/`: especificações.
- `skills/github-workflow/`: fluxo versionado de PR e revisão.

## Segurança

Não versione datasets privados, modelos, checkpoints, `.env`, tokens ou `kaggle.json`. Use dados anonimizados quando houver informações pessoais ou comerciais e avalie o modelo em dados separados antes de uso em produção.
