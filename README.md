# Laya Dataset Manager

Aplicação para gerenciamento de datasets e apoio ao treinamento do Laya.

## Estado atual

Estrutura inicial com uma página provisória e o runtime oficial Laya 0.3.11 em CUDA. O Laya é executado como API local com o checkpoint multilíngue. As funcionalidades do gerenciador e o fluxo de treinamento serão definidos na próxima etapa; o runtime instalado atualmente fornece inferência.

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

Acesse a página provisória em <http://localhost:8080> e a documentação da API Laya em <http://localhost:8000/docs>. As portas são publicadas somente no endereço local. Ajuste `APP_PORT` e `LAYA_PORT` no `.env` para alterá-las.

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

- `public/`: página provisória.
- `docker/laya/`: imagem reproduzível do runtime Laya.
- `docker/`: configuração do container.
- `compose.yaml` e `Dockerfile`: ambiente reproduzível; imagem base fixada por digest.
- `docs/`: especificações do projeto.
- `data/`: reservado para arquivos locais, ignorados pelo Git.

O repositório é destinado a ser público. Datasets, modelos, checkpoints e segredos não devem ser versionados. O `.env.example` contém apenas configuração de exemplo. Modelos são armazenados em volume Docker; o serviço não monta nem processa datasets nesta etapa.

## Próxima etapa

Detalhar o fluxo de trabalho, formatos de dataset, integração com Laya, requisitos de GPU e critérios de aceite em `docs/specifications.md`.
