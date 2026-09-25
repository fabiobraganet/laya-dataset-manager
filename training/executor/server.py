import hashlib, json, os, shutil, subprocess, tarfile, tempfile, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from generate_kernel import prepare

ROOT=Path('/state/runs'); CREDENTIALS=Path('/state/credentials/kaggle'); LOCK=threading.Lock(); TERMINAL={'succeeded','failed','downloading'}
def credential_mode():
    if (CREDENTIALS/'token').is_file(): return 'token'
    if (CREDENTIALS/'kaggle.json').is_file(): return 'legacy'
    return None
def kaggle_env(directory=None,token=None):
    env=os.environ.copy(); env['KAGGLE_CONFIG_DIR']=str(directory or CREDENTIALS)
    stored=CREDENTIALS/'token'
    if token is not None: env['KAGGLE_API_TOKEN']=token
    elif stored.is_file(): env['KAGGLE_API_TOKEN']=stored.read_text().strip()
    else: env.pop('KAGGLE_API_TOKEN',None)
    return env
def save(run,**values):
    with LOCK:
        path=ROOT/run/'state.json'; data=json.loads(path.read_text()) if path.exists() else {'id':run,'logs':[]}
        data.update(values); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,ensure_ascii=False,indent=2)); return data
def command(args,timeout=600,env=None):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env=env or kaggle_env()); lines=(result.stdout+result.stderr).splitlines()
    if result.returncode: raise RuntimeError('\n'.join(lines[-100:]))
    return lines
def connection_status():
    mode=credential_mode()
    if not mode: return {'configured':False,'connected':False,'mode':None,'account':None,'message':'Credencial Kaggle não configurada.'}
    try:
        lines=command(['python','-m','kaggle','datasets','list','--page-size','1'],60)
        return {'configured':True,'connected':True,'mode':mode,'account':None,'message':'Conexão com o Kaggle validada.'}
    except Exception as exc:
        return {'configured':True,'connected':False,'mode':mode,'account':None,'message':str(exc)}
def save_kaggle_credential(payload):
    token=str(payload.get('token','')).strip(); username=str(payload.get('username','')).strip(); key=str(payload.get('key','')).strip()
    if token and (username or key): raise ValueError('Informe um token ou usuário e chave, não ambos.')
    if not token and not (username and key): raise ValueError('Informe o token ou o usuário e a chave do Kaggle.')
    with tempfile.TemporaryDirectory() as raw:
        directory=Path(raw); env=kaggle_env(directory,token if token else None)
        if not token:
            candidate=directory/'kaggle.json'; candidate.write_text(json.dumps({'username':username,'key':key})); candidate.chmod(0o600)
        command(['python','-m','kaggle','datasets','list','--page-size','1'],60,env)
    CREDENTIALS.mkdir(parents=True,exist_ok=True); CREDENTIALS.chmod(0o700)
    for path in (CREDENTIALS/'token',CREDENTIALS/'kaggle.json'):
        if path.exists(): path.unlink()
    target=CREDENTIALS/('token' if token else 'kaggle.json')
    target.write_text(token if token else json.dumps({'username':username,'key':key})); target.chmod(0o600)
    return connection_status()
def validate_safetensors(archive,member):
    stream=archive.extractfile(member)
    if stream is None or member.size<=8: raise RuntimeError('model.safetensors está vazio')
    header_size=int.from_bytes(stream.read(8),'little')
    if header_size<=2 or header_size>member.size-8: raise RuntimeError('cabeçalho safetensors inválido')
    header=json.loads(stream.read(header_size)); tensors=[name for name in header if name!='__metadata__']
    if not tensors: raise RuntimeError('checkpoint sem tensores')
    return len(tensors)
def collect_outputs(run,state):
    try:
        output=ROOT/run/'output'; output.mkdir(parents=True,exist_ok=True); logs=list(state.get('logs',[]))+['Baixando outputs do Kaggle']
        manifest_path=output/'checkpoint_manifest.json'; archive_path=output/'laya_checkpoint.tar.gz'
        cached=manifest_path.is_file() and archive_path.is_file()
        if cached:
            expected=json.loads(manifest_path.read_text()).get('bytes'); cached=archive_path.stat().st_size==expected
        if cached: logs.append('Checkpoint já baixado; validando arquivo local')
        else: logs+=command(['python','-m','kaggle','kernels','output',state['kernel_ref'],'-p',str(output),'--force'],1800)[-100:]
        if not manifest_path.is_file() or not archive_path.is_file(): raise RuntimeError('Kaggle concluiu sem o manifesto ou arquivo do checkpoint')
        manifest=json.loads(manifest_path.read_text()); digest=hashlib.sha256(archive_path.read_bytes()).hexdigest()
        if archive_path.stat().st_size<=0 or digest!=manifest.get('sha256'): raise RuntimeError('arquivo de checkpoint vazio ou com SHA-256 divergente')
        with tarfile.open(archive_path,'r:gz') as archive:
            members=[m for m in archive.getmembers() if m.name.endswith('/model.safetensors') and '/checkpoint_' not in m.name]
            if len(members)!=1: raise RuntimeError('checkpoint não contém um único model.safetensors')
            tensor_count=validate_safetensors(archive,members[0])
            target=Path('/models')/digest; staging=Path('/models')/(digest+'.tmp')
            if not target.exists():
                shutil.rmtree(staging,ignore_errors=True); staging.mkdir(parents=True)
                archive.extractall(staging,filter='data'); staging.rename(target)
        model_path=target/'laya_finetuned_typed_decisions'
        if not (model_path/'model.safetensors').is_file(): raise RuntimeError('modelo extraído sem model.safetensors')
        for directory in [target, *[path for path in target.rglob('*') if path.is_dir()]]:
            directory.chmod(0o755)
        for file_path in [path for path in target.rglob('*') if path.is_file()]:
            file_path.chmod(0o644)
        artifact={'kind':'laya_checkpoint','name':archive_path.name,'path':str(archive_path),'model_path':str(model_path),'bytes':archive_path.stat().st_size,'sha256':digest,'tensor_count':tensor_count}
        logs.append(f"Checkpoint validado: {artifact['bytes']} bytes, {tensor_count} tensores, SHA-256 {digest}")
        save(run,status='succeeded',artifacts=[artifact],manifest=manifest,logs=logs)
    except Exception as exc: save(run,status='failed',error=str(exc),logs=state.get('logs',[])+[str(exc)])
def refresh(run):
    path=ROOT/run/'state.json'
    if not path.exists(): return None
    state=json.loads(path.read_text())
    if state.get('status') in TERMINAL or not state.get('kernel_ref'): return state
    try:
        lines=command(['python','-m','kaggle','kernels','status',state['kernel_ref']],60); text='\n'.join(lines)
        if 'COMPLETE' in text:
            pending=save(run,status='downloading',logs=state.get('logs',[])+['Treinamento concluído; download do checkpoint iniciado'])
            threading.Thread(target=collect_outputs,args=(run,pending),daemon=True).start(); return pending
        if 'ERROR' in text or 'CANCEL' in text: return save(run,status='failed',error=text,logs=state.get('logs',[])+lines)
        return save(run,status='running' if 'RUNNING' in text else 'queued',logs=state.get('logs',[])+[text])
    except Exception as exc: return save(run,status='failed',error=str(exc),logs=state.get('logs',[])+[str(exc)])
def execute(run,payload):
    try:
        save(run,status='preparing',logs=['Preparando exportação imutável da DatasetVersion']); folder=ROOT/run/'kernel'; prepare(folder,payload['kernel_ref'],payload['jsonl'])
        save(run,status='submitting',logs=['Pacote preparado','Enviando kernel privado ao Kaggle']); logs=command(['python','-m','kaggle','kernels','push','-p',str(folder)],600)
        url=next((line.split('progress at ',1)[1] for line in logs if 'progress at ' in line),None); save(run,status='submitted',kernel_ref=payload['kernel_ref'],kaggle_url=url,logs=logs[-100:])
    except Exception as exc: save(run,status='failed',error=str(exc),logs=[str(exc)])
class H(BaseHTTPRequestHandler):
    def reply(self,code,value):
        body=json.dumps(value,ensure_ascii=False).encode(); self.send_response(code); self.send_header('content-type','application/json'); self.send_header('content-length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path=='/health': return self.reply(200,{'status':'ok','credential':credential_mode() is not None})
        if self.path=='/connection':
            status=connection_status(); return self.reply(200 if status['connected'] else 503,status)
        if self.path=='/settings': return self.reply(200,connection_status())
        if self.path=='/runs': return self.reply(200,[refresh(p.parent.name) for p in sorted(ROOT.glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True)])
        if self.path.startswith('/runs/'):
            state=refresh(self.path.split('/')[-1]); return self.reply(200,state) if state else self.reply(404,{'error':'run not found'})
        return self.reply(404,{'error':'not found'})
    def do_POST(self):
        if self.path=='/settings/kaggle':
            try:
                payload=json.loads(self.rfile.read(int(self.headers.get('content-length','0')))); return self.reply(200,save_kaggle_credential(payload))
            except Exception as exc: return self.reply(422,{'error':str(exc)})
        if self.path!='/runs': return self.reply(404,{'error':'not found'})
        try:
            payload=json.loads(self.rfile.read(int(self.headers.get('content-length','0'))))
            for key in ('dataset_version_id','jsonl','kernel_ref'):
                if not payload.get(key): raise ValueError(f'{key} is required')
            run=str(uuid.uuid4()); state=save(run,status='queued',dataset_version_id=payload['dataset_version_id'],kernel_ref=payload['kernel_ref'],logs=[]); threading.Thread(target=execute,args=(run,payload),daemon=True).start(); return self.reply(202,state)
        except Exception as exc: return self.reply(422,{'error':str(exc)})
    def log_message(self,*args): pass
ThreadingHTTPServer(('0.0.0.0',8090),H).serve_forever()
