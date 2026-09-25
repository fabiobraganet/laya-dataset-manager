import json
import logging
import os
import re
import threading
import uuid
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import uvicorn
from fastapi import HTTPException, Request
from huggingface_hub import HfApi, get_token, hf_hub_download, login, snapshot_download
from laya import Agent, Router
from laya.serve import create_app
from tqdm.auto import tqdm

MODELS_ROOT = Path("/models").resolve()
ACTIVE_FILE = Path(os.environ.get("LAYA_ACTIVE_FILE", "/home/laya/.cache/huggingface/laya-active.json"))
PUBLISH_ROOT = Path(os.environ.get("LAYA_PUBLISH_ROOT", "/home/laya/.cache/huggingface/publish-jobs"))
START_ROOT = Path(os.environ.get("LAYA_START_ROOT", "/home/laya/.cache/huggingface/start-jobs"))
DOWNLOAD_CONTEXT = threading.local()


def checked_model_path(value: str) -> Path:
    path = Path(value).resolve()
    if MODELS_ROOT not in path.parents or not (path / "model.safetensors").is_file():
        raise ValueError("checkpoint fora do volume autorizado ou incompleto")
    return path


def active_path():
    if not ACTIVE_FILE.is_file():
        return None
    try:
        value = json.loads(ACTIVE_FILE.read_text())
        return checked_model_path(value["model_path"]) if value.get("source", "local") == "local" else None
    except Exception:
        return None


def active_model():
    if not ACTIVE_FILE.is_file():
        return None
    try:
        value = json.loads(ACTIVE_FILE.read_text())
        if value.get("model_path") and not value.get("source"):
            value.update({"source": "local", "model_id": "typed-decisions"})
        return value
    except Exception:
        return None


def huggingface_laya_models():
    token = get_token()
    if not token:
        return []
    account = HfApi().whoami(token=token).get("name")
    models = HfApi().list_models(author=account, token=token, full=True)
    result = []
    for model in models:
        tags = list(model.tags or [])
        library = getattr(model, "library_name", None)
        if "laya" not in model.id.lower() and library != "laya" and not any("laya" in tag.lower() for tag in tags):
            continue
        result.append({"model_id": model.id, "private": bool(model.private), "updated_at": str(model.last_modified or ""), "source": "huggingface"})
    return result


def save_publish_job(job_id, **values):
    PUBLISH_ROOT.mkdir(parents=True, exist_ok=True)
    path = PUBLISH_ROOT / f"{job_id}.json"
    current = json.loads(path.read_text()) if path.exists() else {"id": job_id}
    current.update(values)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2))
    temp.replace(path)
    return current


def save_start_job(job_id, **values):
    START_ROOT.mkdir(parents=True, exist_ok=True)
    path = START_ROOT / f"{job_id}.json"
    current = json.loads(path.read_text()) if path.exists() else {"id": job_id}
    current.update(values)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2))
    temp.replace(path)
    return current


class DownloadProgress(tqdm):
    def update(self, amount=1):
        result = super().update(amount)
        context = getattr(DOWNLOAD_CONTEXT, "value", None)
        if context:
            downloaded = min(context["base"] + self.n, context["total"])
            percent = min(85, 5 + round(downloaded * 80 / max(context["total"], 1)))
            save_start_job(context["job_id"], status="downloading", percent=percent,
                           downloaded_bytes=downloaded, total_bytes=context["total"],
                           current_file=context["filename"], message="Baixando arquivos do Hugging Face")
        return result


def start_remote_model(job_id, model_id):
    try:
        token = get_token()
        api = HfApi(token=token)
        info = api.model_info(model_id, files_metadata=True)
        files = [item for item in info.siblings if getattr(item, "size", None) and not item.rfilename.startswith(".")]
        total = sum(item.size for item in files)
        completed = 0
        save_start_job(job_id, status="downloading", percent=5, downloaded_bytes=0,
                       total_bytes=total, message="Preparando download")
        for item in files:
            DOWNLOAD_CONTEXT.value = {"job_id": job_id, "base": completed, "total": total,
                                      "filename": item.rfilename}
            hf_hub_download(repo_id=model_id, filename=item.rfilename, token=token,
                            tqdm_class=DownloadProgress)
            completed += item.size
            save_start_job(job_id, status="downloading", percent=min(85, 5 + round(completed * 80 / max(total, 1))),
                           downloaded_bytes=completed, total_bytes=total,
                           current_file=item.rfilename, message="Download em andamento")
        DOWNLOAD_CONTEXT.value = None
        model_path = snapshot_download(repo_id=model_id, token=token, local_files_only=True)
        save_start_job(job_id, status="loading", percent=90, downloaded_bytes=total,
                       total_bytes=total, message="Carregando o modelo no runtime LAYA")
        agent = Agent(model_path, device=device)
        router.attach("typed-decisions", agent)
        value = {"source": "huggingface", "model_id": model_id}
        ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = ACTIVE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(value))
        temp.replace(ACTIVE_FILE)
        save_start_job(job_id, status="ready", percent=100, downloaded_bytes=total,
                       total_bytes=total, message="Modelo ativo no localhost", active=value)
    except Exception as exc:
        logging.exception("Hugging Face model activation failed")
        save_start_job(job_id, status="failed", message="Não foi possível iniciar o modelo", error=str(exc))
    finally:
        DOWNLOAD_CONTEXT.value = None


def publish_model(job_id, body):
    try:
        path = checked_model_path(body["model_path"])
        api = HfApi(token=get_token())
        account = api.whoami().get("name")
        slug = re.sub(r"[^a-z0-9-]+", "-", body["repo_name"].lower()).strip("-")[:80]
        repo_id = f"{account}/{slug}"
        save_publish_job(job_id, status="creating", repo_id=repo_id, logs=["Criando repositório privado no Hugging Face"])
        api.create_repo(repo_id=repo_id, repo_type="model", private=True, exist_ok=True)
        save_publish_job(job_id, status="uploading", repo_id=repo_id, logs=["Repositório criado", "Enviando checkpoint LAYA"])
        commit = api.upload_folder(repo_id=repo_id, repo_type="model", folder_path=str(path), commit_message=f"Publish LAYA checkpoint {body['sha256'][:12]}")
        card = f"---\nlibrary_name: laya\ntags:\n- laya\n- text-classification\n---\n\n# {body['title']}\n\nCheckpoint LAYA gerado pelo Laya Dataset Manager.\n\n- Dataset: {body['dataset_name']} v{body['version_number']}\n- SHA-256: `{body['sha256']}`\n- Kaggle run: `{body['training_run_id']}`\n"
        manifest = json.dumps({k: body[k] for k in ("sha256", "dataset_name", "version_number", "training_run_id")}, ensure_ascii=False, indent=2).encode()
        api.upload_file(repo_id=repo_id, repo_type="model", path_or_fileobj=card.encode(), path_in_repo="README.md", commit_message="Add LAYA model card")
        final = api.upload_file(repo_id=repo_id, repo_type="model", path_or_fileobj=manifest, path_in_repo="laya-manifest.json", commit_message="Add provenance manifest")
        info = api.model_info(repo_id, files_metadata=True)
        weights = next((item for item in info.siblings if item.rfilename == "model.safetensors"), None)
        if not weights or not getattr(weights, "size", 0):
            raise RuntimeError("publicação concluída sem model.safetensors verificável")
        save_publish_job(job_id, status="published", repo_id=repo_id, url=f"https://huggingface.co/{repo_id}", revision=final.oid or commit.oid, bytes=weights.size, logs=["Checkpoint enviado", "Arquivos e tamanho verificados", "Publicação concluída"])
    except Exception as exc:
        logging.exception("Hugging Face publish failed")
        save_publish_job(job_id, status="failed", error=str(exc), logs=["Falha na publicação", str(exc)])


device = os.environ.get("LAYA_DEVICE") or None
saved_active = active_model()
configured = saved_active.get("model_id") if saved_active and saved_active.get("source") == "huggingface" else active_path()
models = {"typed-decisions": str(configured)} if configured else None
router = Router(models=models, device=device, max_loaded=2, auto_task_detection=False)
preload = [name.strip() for name in os.environ.get("LAYA_MODELS", "multilingual").split(",") if name.strip()]
if configured and "typed-decisions" not in preload:
    preload.append("typed-decisions")
router.preload(preload)
app = create_app(router)


def huggingface_status():
    token = get_token()
    if not token:
        return {"configured": False, "connected": False, "account": None, "message": "Token Hugging Face não configurado."}
    try:
        info = HfApi().whoami(token=token)
        return {"configured": True, "connected": True, "account": info.get("name"), "message": "Conexão com o Hugging Face validada."}
    except Exception as exc:
        return {"configured": True, "connected": False, "account": None, "message": f"Não foi possível validar o token: {exc}"}


@app.get("/admin/settings")
async def settings():
    return {"huggingface": huggingface_status()}


@app.post("/admin/settings/huggingface")
async def save_huggingface(request: Request):
    body = await request.json()
    token = str(body.get("token", "")).strip()
    if not token:
        raise HTTPException(status_code=422, detail="Informe o token do Hugging Face.")
    try:
        info = HfApi().whoami(token=token)
        login(token=token, add_to_git_credential=False)
        return {"configured": True, "connected": True, "account": info.get("name"), "message": "Token salvo e conexão validada."}
    except Exception:
        raise HTTPException(status_code=422, detail="Token Hugging Face inválido ou sem acesso à API.")


@app.post("/admin/activate")
async def activate(request: Request):
    try:
        if active_model():
            raise HTTPException(status_code=409, detail="Pare o modelo LAYA ativo antes de iniciar outro.")
        body = await request.json()
        path = checked_model_path(body.get("model_path", ""))
        agent = Agent(str(path), device=device)
        router.attach("typed-decisions", agent)
        ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = ACTIVE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps({"source": "local", "model_id": "typed-decisions", "model_path": str(path), "sha256": body.get("sha256")}))
        temp.replace(ACTIVE_FILE)
        return {"active": True, "model": "typed-decisions", "model_path": str(path), "sha256": body.get("sha256")}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logging.exception("checkpoint activation failed")
        raise HTTPException(status_code=500, detail="não foi possível carregar o checkpoint")


@app.get("/admin/models")
async def models_status():
    try:
        remote = huggingface_laya_models()
        return {"active": active_model(), "huggingface": remote}
    except Exception as exc:
        return {"active": active_model(), "huggingface": [], "huggingface_error": str(exc)}


@app.post("/admin/models/huggingface/start")
async def start_huggingface_model(request: Request):
    if active_model():
        raise HTTPException(status_code=409, detail="Pare o modelo LAYA ativo antes de iniciar outro.")
    model_id = str((await request.json()).get("model_id", "")).strip()
    allowed = {item["model_id"] for item in huggingface_laya_models()}
    if model_id not in allowed:
        raise HTTPException(status_code=422, detail="O repositório não foi reconhecido como um modelo LAYA desta conta.")
    job_id = str(uuid.uuid4())
    state = save_start_job(job_id, status="queued", percent=0, downloaded_bytes=0,
                           total_bytes=0, model_id=model_id, message="Preparando o modelo")
    threading.Thread(target=start_remote_model, args=(job_id, model_id), daemon=True).start()
    return state


@app.get("/admin/models/huggingface/start/{job_id}")
async def start_huggingface_status(job_id: str):
    path = START_ROOT / f"{job_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Inicialização não encontrada.")
    return json.loads(path.read_text())


@app.post("/admin/models/stop")
async def stop_model():
    current = active_model()
    if not current:
        return {"active": False}
    router.unload("typed-decisions")
    ACTIVE_FILE.unlink(missing_ok=True)
    return {"active": False, "stopped": current}


@app.post("/admin/publish")
async def queue_publish(request: Request):
    body = await request.json()
    checked_model_path(body.get("model_path", ""))
    if not get_token():
        raise HTTPException(status_code=422, detail="Configure uma credencial Hugging Face com escrita.")
    job_id = str(uuid.uuid4())
    state = save_publish_job(job_id, status="queued", logs=["Publicação agendada"])
    threading.Thread(target=publish_model, args=(job_id, body), daemon=True).start()
    return state


@app.get("/admin/publish/{job_id}")
async def publish_status(job_id: str):
    path = PUBLISH_ROOT / f"{job_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Publicação não encontrada.")
    return json.loads(path.read_text())


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("LAYA_HOST", "0.0.0.0"), port=int(os.environ.get("LAYA_PORT", "8000")), log_level=os.environ.get("LAYA_LOG_LEVEL", "info"))
