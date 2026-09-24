# Laya Dataset Manager

Aplicação para gerenciamento de datasets e apoio ao treinamento do Laya.

## Estado atual

Aplicativo Rust com SQLite para organizar material de dataset e conteúdo de treinamento do Laya. O runtime oficial Laya 0.3.11 continua disponível como API local CUDA com o checkpoint multilíngue.

## Ambiente

- Ubuntu no WSL2 (distribuição `Ubuntu`).
- Docker Engine e Docker Compose disponíveis dentro do Ubuntu.
- NVIDIA Container Toolkit 1.20.0 e GPU NVIDIA acessível pelo Docker.
- Projeto local em `/opt/projects/laya-dataset-manager`.

No PowerShell, entre no projeto:

```powershell
wsl -d Ubuntu --cd /opt/projects/laya-dataset-manager
```

No Ubuntu:

```bash
cp .env.example .env
docker compose up -d --build --wait
```

Acesse o gerenciador em <http://localhost:8080> e a documentação da API Laya em <http://localhost:8000/docs>. As portas são publicadas somente no endereço local. Ajuste `APP_PORT` e `LAYA_PORT` no `.env` para alterá-las.

## Comandos

```bash
docker compose config --quiet
docker compose ps
curl --fail http://localhost:8080/health
curl --fail http://localhost:8000/health
docker compose logs -f
docker compose down
```

O primeiro start baixa as dependências da imagem e o checkpoint público do Hugging Face. O cache fica no volume `laya-dataset-manager-model-cache`, portanto os próximos starts não repetem o download.

Para conferir CUDA dentro do container sem iniciar a API:

```bash
docker compose run --rm --entrypoint python laya -c \
  "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
```

Para testar uma decisão tipada, envie uma requisição compatível com a API Jev/Laya:

```bash
curl --fail http://localhost:8000/v1/systemone \
  -H 'content-type: application/json' \
  --data '{"state":"Quero cancelar minha assinatura","questions":{"urgente":{"type":"noul","instructions":"O pedido exige atendimento imediato?"}}}'
```

Após editar a página, a configuração do Nginx ou o container Laya, execute novamente `docker compose up -d --build --wait`.

## Organização

- `src/`: API Rust e esquema SQLite.
- `static/`: interface web do gerenciador.
- `docker/laya/`: imagem reproduzível do runtime Laya.
- `compose.yaml` e `Dockerfile`: ambiente reproduzível; imagem base fixada por digest.
- `docs/`: especificações do projeto.

O banco SQLite fica no volume Docker `laya-dataset-manager-app-data`; modelos ficam em `laya-dataset-manager-model-cache`. Ambos ficam fora do Git. Datasets, modelos, checkpoints e segredos não devem ser versionados.

## Próxima etapa

Detalhar o fluxo de trabalho, formatos de dataset, integração com Laya, requisitos de GPU e critérios de aceite em `docs/specifications.md`.
