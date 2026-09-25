import json
import logging
import os
from pathlib import Path

import uvicorn
from fastapi import HTTPException, Request
from huggingface_hub import HfApi, get_token, login
from laya import Agent, Router
from laya.serve import create_app

MODELS_ROOT = Path("/models").resolve()
ACTIVE_FILE = Path(os.environ.get("LAYA_ACTIVE_FILE", "/home/laya/.cache/huggingface/laya-active.json"))


def checked_model_path(value: str) -> Path:
    path = Path(value).resolve()
    if MODELS_ROOT not in path.parents or not (path / "model.safetensors").is_file():
        raise ValueError("checkpoint fora do volume autorizado ou incompleto")
    return path


def active_path():
    if not ACTIVE_FILE.is_file():
        return None
    try:
        return checked_model_path(json.loads(ACTIVE_FILE.read_text())["model_path"])
    except Exception:
        return None


device = os.environ.get("LAYA_DEVICE") or None
configured = active_path()
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
        body = await request.json()
        path = checked_model_path(body.get("model_path", ""))
        agent = Agent(str(path), device=device)
        router.attach("typed-decisions", agent)
        ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = ACTIVE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps({"model_path": str(path), "sha256": body.get("sha256")}))
        temp.replace(ACTIVE_FILE)
        return {"active": True, "model": "typed-decisions", "model_path": str(path), "sha256": body.get("sha256")}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logging.exception("checkpoint activation failed")
        raise HTTPException(status_code=500, detail="não foi possível carregar o checkpoint")


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("LAYA_HOST", "0.0.0.0"), port=int(os.environ.get("LAYA_PORT", "8000")), log_level=os.environ.get("LAYA_LOG_LEVEL", "info"))
