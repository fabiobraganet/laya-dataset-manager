import json, os, subprocess, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from generate_kernel import prepare

ROOT=Path('/state/runs'); LOCK=threading.Lock()
def save(run, **values):
    with LOCK:
        path=ROOT/run/'state.json'; data=json.loads(path.read_text()) if path.exists() else {'id':run,'logs':[]}
        data.update(values); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data)); return data
def execute(run,payload):
    try:
        save(run,status='preparing',logs=['Preparing immutable DatasetVersion export'])
        folder=ROOT/run/'kernel'; prepare(folder,payload['kernel_ref'],payload['jsonl'])
        save(run,status='submitting',logs=['Package prepared','Submitting private Kaggle kernel'])
        p=subprocess.run(['python','-m','kaggle','kernels','push','-p',str(folder)],capture_output=True,text=True,timeout=600)
        logs=(p.stdout+p.stderr).splitlines()[-100:]
        if p.returncode: raise RuntimeError('\n'.join(logs))
        url=next((line.split('progress at ',1)[1] for line in logs if 'progress at ' in line),None)
        save(run,status='submitted',kernel_ref=payload['kernel_ref'],kaggle_url=url,logs=logs)
    except Exception as exc: save(run,status='failed',error=str(exc),logs=[str(exc)])
class H(BaseHTTPRequestHandler):
    def reply(self,c,v):
        b=json.dumps(v).encode();self.send_response(c);self.send_header('content-type','application/json');self.send_header('content-length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        if self.path=='/health':
            configured=os.path.isfile('/root/.kaggle/kaggle.json'); return self.reply(200,{'status':'ok','credential':configured})
        if self.path.startswith('/runs/'):
            p=ROOT/self.path.split('/')[-1]/'state.json'; return self.reply(200,json.loads(p.read_text())) if p.exists() else self.reply(404,{'error':'run not found'})
        self.reply(404,{'error':'not found'})
    def do_POST(self):
        if self.path!='/runs': return self.reply(404,{'error':'not found'})
        try:
            payload=json.loads(self.rfile.read(int(self.headers.get('content-length','0'))));
            for key in ('dataset_version_id','jsonl','kernel_ref'):
                if not payload.get(key): raise ValueError(f'{key} is required')
            run=str(uuid.uuid4()); state=save(run,status='queued',dataset_version_id=payload['dataset_version_id'],kernel_ref=payload['kernel_ref'],logs=[])
            threading.Thread(target=execute,args=(run,payload),daemon=True).start(); self.reply(202,state)
        except Exception as exc:self.reply(422,{'error':str(exc)})
    def log_message(self,*args): pass
ThreadingHTTPServer(('0.0.0.0',8090),H).serve_forever()
