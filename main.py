from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
import uuid
import os
import json
import shutil
import sys
import zipfile
import time
from typing import Dict, List
from pydantic import BaseModel
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), "principal"))
from principal.AME import processar_documento_final
from principal.pdf_generator import PDFGenerator

app = FastAPI()

UPLOAD_DIR = "uploads"
PDF_DIR = "output_pdfs"
USER_DB_PATH = "usuarios.json"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

jobs: Dict[str, dict] = {}
user_history = []

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

def carregar_usuarios():
    if not os.path.exists(USER_DB_PATH):
        initial_users = [{"username": "Rafael", "password": "123", "role": "admin", "created_at": datetime.now().strftime("%Y-%m-%d")}]
        with open(USER_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(initial_users, f, indent=4)
        return initial_users
    try:
        with open(USER_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def salvar_usuario(novo_usuario):
    usuarios = carregar_usuarios()
    usuarios.append(novo_usuario)
    with open(USER_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, indent=4)

def deletar_usuario_db(username: str):
    usuarios = carregar_usuarios()
    usuarios = [u for u in usuarios if u["username"] != username]
    with open(USER_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, indent=4)

def get_current_user(token: str = Depends(oauth2_scheme)):
    if not token.startswith("token_"):
        raise HTTPException(status_code=401, detail="Token inválido")
    username = token.replace("token_", "")
    usuarios = carregar_usuarios()
    user = next((u for u in usuarios if u["username"] == username), None)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user

def get_current_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Acesso negado. Apenas administradores.")
    return current_user

@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    with open("frontend/login.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/app", response_class=HTMLResponse)
async def serve_app():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin():
    with open("frontend/admin.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/token")
async def login(username: str = Form(...), password: str = Form(...)):
    usuarios = carregar_usuarios()
    user = next((u for u in usuarios if u["username"] == username and u["password"] == password), None)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
    return {"access_token": f"token_{username}", "token_type": "bearer"}

@app.get("/users/me")
async def get_user_me(current_user: dict = Depends(get_current_user)):
    return {"username": current_user["username"], "role": current_user["role"]}

@app.put("/users/me/password", status_code=204)
async def change_password(data: PasswordChange, current_user: dict = Depends(get_current_user)):
    usuarios = carregar_usuarios()
    user_idx = next((i for i, u in enumerate(usuarios) if u["username"] == current_user["username"]), None)
    if user_idx is None or usuarios[user_idx]["password"] != data.current_password:
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    
    usuarios[user_idx]["password"] = data.new_password
    with open(USER_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, indent=4)
    return

@app.get("/users/me/uploads")
async def get_user_uploads(current_user: dict = Depends(get_current_user)):
    user_uploads = [h for h in user_history if h.get("owner", {}).get("username") == current_user["username"]]
    return user_uploads

@app.get("/admin/users")
async def list_users(admin: dict = Depends(get_current_admin)):
    return carregar_usuarios()

@app.post("/admin/users")
async def create_user(user: UserCreate, admin: dict = Depends(get_current_admin)):
    usuarios = carregar_usuarios()
    if any(u['username'] == user.username for u in usuarios):
        raise HTTPException(status_code=400, detail="Usuário já existe")
    
    novo_user = {
        "username": user.username,
        "password": user.password,
        "role": user.role,
        "created_at": datetime.now().strftime("%Y-%m-%d")
    }
    salvar_usuario(novo_user)
    return {"message": "Usuário criado com sucesso"}

@app.delete("/admin/users/{username}")
async def delete_user(username: str, admin: dict = Depends(get_current_admin)):
    deletar_usuario_db(username)
    return {"message": "Usuário removido"}

@app.get("/admin/dashboard")
async def get_dashboard_data(admin: dict = Depends(get_current_admin)):
    return {
        "user_stats": [{"user": {"username": "Rafael"}, "files_uploaded_count": len(user_history), "request_count": len(user_history), "last_activity": datetime.now().isoformat()}],
        "recent_uploads": user_history
    }

def tarefa_em_background(tracking_code: str, file_path: str, filename: str, username: str):
    start_time = time.time()
    log_messages = []
    log_messages.append(f"[{datetime.now().isoformat()}] Iniciando processamento do arquivo: {filename}")
    
    ocr_path = os.path.join(PDF_DIR, f"ocr_{tracking_code}.txt")
    log_path = os.path.join(PDF_DIR, f"log_{tracking_code}.txt")
    
    try:
        jobs[tracking_code]["status"] = "summarizing"
        texto_resultado, texto_ocr, caminho_events_txt = processar_documento_final(file_path)
        
        # Salva o conteúdo do OCR em um arquivo de texto
        with open(ocr_path, "w", encoding="utf-8") as f:
            f.write(texto_ocr if texto_ocr.strip() else "Nenhum texto extraído via OCR.")
            
        log_messages.append(f"[{datetime.now().isoformat()}] Resumo gerado e OCR extraído com sucesso.")
        
        jobs[tracking_code]["status"] = "generating_pdf"
        gerador = PDFGenerator(output_dir=PDF_DIR)
        caminho_pdf = gerador.create_summary_pdf(texto_resultado, tracking_code)
        
        log_messages.append(f"[{datetime.now().isoformat()}] PDF gerado com sucesso.")
        
        jobs[tracking_code]["status"] = "finished"
        jobs[tracking_code]["pdf_path"] = caminho_pdf
        jobs[tracking_code]["ocr_path"] = ocr_path
        jobs[tracking_code]["log_path"] = log_path
        jobs[tracking_code]["events_path"] = caminho_events_txt
        
        user_history.append({
            "owner": {"username": username},
            "original_filename": filename,
            "upload_time": datetime.now().isoformat(),
            "status": "finished",
            "tracking_code": tracking_code
        })
    except Exception as e:
        log_messages.append(f"[{datetime.now().isoformat()}] ERRO durante o processamento: {str(e)}")
        jobs[tracking_code]["status"] = "error"
        jobs[tracking_code]["log_path"] = log_path 
    finally:
        elapsed_time = time.time() - start_time
        log_messages.append(f"[{datetime.now().isoformat()}] Tempo total da operação: {elapsed_time:.2f} segundos.")
        
        # Salva o arquivo de log no final da operação
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_messages))

@app.post("/process-pdf")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    tracking_code = uuid.uuid4().hex
    file_path = os.path.join(UPLOAD_DIR, f"{tracking_code}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    jobs[tracking_code] = {"status": "preparing", "pdf_path": None, "original_path": file_path, "owner": current_user["username"]}
    
    background_tasks.add_task(tarefa_em_background, tracking_code, file_path, file.filename, current_user["username"])
    return {"tracking_code": tracking_code}

@app.get("/processing-status/{code}")
async def get_status(code: str, current_user: dict = Depends(get_current_user)):
    if code not in jobs:
        raise HTTPException(status_code=404, detail="Não encontrado")
    if jobs[code].get("owner") != current_user["username"] and current_user["role"] not in ["admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Acesso negado")
    return {"status": jobs[code]["status"]}

@app.get("/download/pdf/{code}")
async def download_pdf(code: str, current_user: dict = Depends(get_current_user)):
    if code not in jobs or jobs[code]["status"] != "finished":
        raise HTTPException(status_code=400, detail="Não concluído")
    if jobs[code].get("owner") != current_user["username"] and current_user["role"] not in ["admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Acesso negado")
    return FileResponse(jobs[code]["pdf_path"], media_type='application/pdf', filename=f"resumo_{code}.pdf")

@app.get("/download/zip/{code}")
async def download_zip(code: str, admin: dict = Depends(get_current_admin)):
    if code not in jobs or jobs[code]["status"] != "finished":
        raise HTTPException(status_code=400, detail="Não concluído")
    
    pdf_path = jobs[code]["pdf_path"]
    original_path = jobs[code].get("original_path") 
    ocr_path = jobs[code].get("ocr_path")
    log_path = jobs[code].get("log_path")
    events_path = jobs[code].get("events_path")
    
    zip_filename = f"processado_{code}.zip"
    zip_path = os.path.join(PDF_DIR, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        if pdf_path and os.path.exists(pdf_path):
            zipf.write(pdf_path, f"resumo_{code}.pdf")
            
        if original_path and os.path.exists(original_path):
            zipf.write(original_path, os.path.basename(original_path))
            
        if ocr_path and os.path.exists(ocr_path):
            zipf.write(ocr_path, "ocr_extraido.txt")
            
        if log_path and os.path.exists(log_path):
            zipf.write(log_path, "log.txt")
        
        if events_path and os.path.exists(events_path):
            zipf.write(events_path, "events.txt")
            
    return FileResponse(zip_path, media_type='application/zip', filename=zip_filename)