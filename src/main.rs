use std::{env, net::SocketAddr, path::Path, sync::{Arc, Mutex}};

use axum::{extract::{Query, State}, http::StatusCode, response::Html, routing::get, Json, Router};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

const APP_HTML: &str = include_str!("../static/index.html");
type ApiResult<T> = Result<Json<T>, (StatusCode, Json<ErrorBody>)>;

#[derive(Clone)] struct AppState { db: Arc<Mutex<Connection>> }
#[derive(Serialize)] struct ErrorBody { error: String }
fn error(status: StatusCode, message: impl Into<String>) -> (StatusCode, Json<ErrorBody>) { (status, Json(ErrorBody { error: message.into() })) }

#[derive(Clone, Serialize)] struct Folder { id: i64, parent_id: Option<i64>, name: String, created_at: String }
#[derive(Serialize)] struct FolderNode { #[serde(flatten)] folder: Folder, children: Vec<FolderNode> }
#[derive(Deserialize)] struct CreateFolder { parent_id: Option<i64>, name: String }
#[derive(Serialize)] struct ContentItem { id: i64, folder_id: Option<i64>, folder_name: Option<String>, kind: String, subject: String, title: String, brief: String, markdown: String, created_at: String }
#[derive(Deserialize)] struct CreateContent { folder_id: Option<i64>, kind: String, subject: String, title: String, brief: String, markdown: String }
#[derive(Deserialize)] struct ContentQuery { kind: Option<String> }
#[derive(Serialize)] struct TrainingJob { id: i64, name: String, status: String, source_count: i64, created_at: String }
#[derive(Deserialize)] struct CreateTraining { name: Option<String> }
#[derive(Serialize)] struct Overview { folders: i64, dataset_content: i64, training_content: i64, training_jobs: i64 }

fn trim(value: &str, field: &str, max: usize) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty() { return Err(format!("{field} é obrigatório.")); }
    if value.chars().count() > max { return Err(format!("{field} aceita no máximo {max} caracteres.")); }
    Ok(value.to_owned())
}
fn with_db<T>(state: &AppState, f: impl FnOnce(&Connection) -> rusqlite::Result<T>) -> Result<T, (StatusCode, Json<ErrorBody>)> {
    let db = state.db.lock().map_err(|_| error(StatusCode::INTERNAL_SERVER_ERROR, "Banco indisponível."))?;
    f(&db).map_err(|e| error(StatusCode::INTERNAL_SERVER_ERROR, format!("Erro no banco: {e}")))
}
fn folder_exists(db: &Connection, id: i64) -> rusqlite::Result<bool> { db.query_row("SELECT EXISTS(SELECT 1 FROM folders WHERE id = ?1)", [id], |row| row.get(0)) }
fn init_db(path: &str) -> rusqlite::Result<Connection> {
    if let Some(parent) = Path::new(path).parent() { std::fs::create_dir_all(parent).map_err(|_| rusqlite::Error::InvalidPath(Path::new(path).to_owned()))?; }
    let db = Connection::open(path)?;
    db.execute_batch("PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS folders (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE, name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(parent_id, name));
        CREATE TABLE IF NOT EXISTS content (id INTEGER PRIMARY KEY, folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL, kind TEXT NOT NULL CHECK(kind IN ('dataset','training')), subject TEXT NOT NULL, title TEXT NOT NULL, brief TEXT NOT NULL, markdown TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS training_jobs (id INTEGER PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, source_count INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS training_job_items (training_job_id INTEGER NOT NULL REFERENCES training_jobs(id) ON DELETE CASCADE, content_id INTEGER NOT NULL REFERENCES content(id), PRIMARY KEY(training_job_id, content_id));")?;
    Ok(db)
}
fn build_tree(parent: Option<i64>, folders: &[Folder]) -> Vec<FolderNode> {
    folders.iter().filter(|folder| folder.parent_id == parent).cloned().map(|folder| FolderNode { children: build_tree(Some(folder.id), folders), folder }).collect()
}

async fn health() -> &'static str { "ok\n" }
async fn app() -> Html<&'static str> { Html(APP_HTML) }
async fn list_folders(State(state): State<AppState>) -> ApiResult<Vec<FolderNode>> {
    let folders: Vec<Folder> = with_db(&state, |db| { let mut s = db.prepare("SELECT id, parent_id, name, created_at FROM folders ORDER BY name COLLATE NOCASE")?; let rows = s.query_map([], |r| Ok(Folder { id:r.get(0)?, parent_id:r.get(1)?, name:r.get(2)?, created_at:r.get(3)? }))?; rows.collect::<rusqlite::Result<Vec<Folder>>>() })?;
    Ok(Json(build_tree(None, &folders)))
}
async fn create_folder(State(state): State<AppState>, Json(input): Json<CreateFolder>) -> ApiResult<Folder> {
    let name = trim(&input.name, "Nome da pasta", 120).map_err(|e| error(StatusCode::UNPROCESSABLE_ENTITY, e))?;
    let result = with_db(&state, |db| {
        if let Some(parent) = input.parent_id { if !folder_exists(db, parent)? { return Err(rusqlite::Error::QueryReturnedNoRows); } }
        db.execute("INSERT INTO folders (parent_id,name) VALUES (?1,?2)", params![input.parent_id,name])?; let id=db.last_insert_rowid();
        db.query_row("SELECT id,parent_id,name,created_at FROM folders WHERE id=?1",[id],|r|Ok(Folder{id:r.get(0)?,parent_id:r.get(1)?,name:r.get(2)?,created_at:r.get(3)?}))
    });
    match result { Ok(item)=>Ok(Json(item)), Err(_)=>Err(error(StatusCode::UNPROCESSABLE_ENTITY,"Pasta pai inválida ou já existe uma pasta com esse nome neste nível.")) }
}
async fn list_content(State(state): State<AppState>, Query(query): Query<ContentQuery>) -> ApiResult<Vec<ContentItem>> {
    if let Some(kind)=&query.kind { if kind!="dataset"&&kind!="training" { return Err(error(StatusCode::BAD_REQUEST,"Tipo de conteúdo inválido.")); } }
    let items: Vec<ContentItem>=with_db(&state,|db|{let mut s=db.prepare("SELECT c.id,c.folder_id,f.name,c.kind,c.subject,c.title,c.brief,c.markdown,c.created_at FROM content c LEFT JOIN folders f ON f.id=c.folder_id WHERE (?1 IS NULL OR c.kind=?1) ORDER BY c.id DESC")?;let rows=s.query_map([query.kind],|r|Ok(ContentItem{id:r.get(0)?,folder_id:r.get(1)?,folder_name:r.get(2)?,kind:r.get(3)?,subject:r.get(4)?,title:r.get(5)?,brief:r.get(6)?,markdown:r.get(7)?,created_at:r.get(8)?}))?;rows.collect::<rusqlite::Result<Vec<ContentItem>>>()})?;
    Ok(Json(items))
}
async fn create_content(State(state): State<AppState>, Json(input): Json<CreateContent>) -> ApiResult<ContentItem> {
    if input.kind!="dataset"&&input.kind!="training" { return Err(error(StatusCode::UNPROCESSABLE_ENTITY,"Tipo deve ser dataset ou training.")); }
    let subject=trim(&input.subject,"Assunto",160).map_err(|e|error(StatusCode::UNPROCESSABLE_ENTITY,e))?; let title=trim(&input.title,"Título",180).map_err(|e|error(StatusCode::UNPROCESSABLE_ENTITY,e))?; let brief=trim(&input.brief,"Breve",500).map_err(|e|error(StatusCode::UNPROCESSABLE_ENTITY,e))?; let markdown=trim(&input.markdown,"Conteúdo Markdown",100_000).map_err(|e|error(StatusCode::UNPROCESSABLE_ENTITY,e))?;
    let result=with_db(&state,|db|{if let Some(folder)=input.folder_id {if !folder_exists(db,folder)? {return Err(rusqlite::Error::QueryReturnedNoRows);}}db.execute("INSERT INTO content (folder_id,kind,subject,title,brief,markdown) VALUES (?1,?2,?3,?4,?5,?6)",params![input.folder_id,input.kind,subject,title,brief,markdown])?;let id=db.last_insert_rowid();db.query_row("SELECT c.id,c.folder_id,f.name,c.kind,c.subject,c.title,c.brief,c.markdown,c.created_at FROM content c LEFT JOIN folders f ON f.id=c.folder_id WHERE c.id=?1",[id],|r|Ok(ContentItem{id:r.get(0)?,folder_id:r.get(1)?,folder_name:r.get(2)?,kind:r.get(3)?,subject:r.get(4)?,title:r.get(5)?,brief:r.get(6)?,markdown:r.get(7)?,created_at:r.get(8)?}))});
    match result { Ok(item)=>Ok(Json(item)), Err(_)=>Err(error(StatusCode::UNPROCESSABLE_ENTITY,"Pasta selecionada não existe.")) }
}
async fn list_training(State(state): State<AppState>) -> ApiResult<Vec<TrainingJob>> { let jobs: Vec<TrainingJob>=with_db(&state,|db|{let mut s=db.prepare("SELECT id,name,status,source_count,created_at FROM training_jobs ORDER BY id DESC")?;let rows=s.query_map([],|r|Ok(TrainingJob{id:r.get(0)?,name:r.get(1)?,status:r.get(2)?,source_count:r.get(3)?,created_at:r.get(4)?}))?;rows.collect::<rusqlite::Result<Vec<TrainingJob>>>()})?;Ok(Json(jobs)) }
async fn create_training(State(state): State<AppState>, Json(input): Json<CreateTraining>) -> ApiResult<TrainingJob> {
    let name=trim(&input.name.unwrap_or_else(||"Treinamento Laya".into()),"Nome do treinamento",160).map_err(|e|error(StatusCode::UNPROCESSABLE_ENTITY,e))?;
    let result=with_db(&state,|db|{let ids={let mut s=db.prepare("SELECT id FROM content ORDER BY id")?;let rows=s.query_map([],|r|r.get(0))?;rows.collect::<rusqlite::Result<Vec<i64>>>()?};if ids.is_empty(){return Err(rusqlite::Error::QueryReturnedNoRows);}let status="waiting_for_laya_training_api";db.execute("INSERT INTO training_jobs (name,status,source_count) VALUES (?1,?2,?3)",params![name,status,ids.len() as i64])?;let id=db.last_insert_rowid();for content_id in ids{db.execute("INSERT INTO training_job_items (training_job_id,content_id) VALUES (?1,?2)",params![id,content_id])?;}db.query_row("SELECT id,name,status,source_count,created_at FROM training_jobs WHERE id=?1",[id],|r|Ok(TrainingJob{id:r.get(0)?,name:r.get(1)?,status:r.get(2)?,source_count:r.get(3)?,created_at:r.get(4)?}))});
    match result { Ok(job)=>Ok(Json(job)), Err(_)=>Err(error(StatusCode::UNPROCESSABLE_ENTITY,"Inclua ao menos um conteúdo antes de solicitar treinamento.")) }
}
async fn overview(State(state): State<AppState>) -> ApiResult<Overview> { let value=with_db(&state,|db|db.query_row("SELECT (SELECT count(*) FROM folders),(SELECT count(*) FROM content WHERE kind='dataset'),(SELECT count(*) FROM content WHERE kind='training'),(SELECT count(*) FROM training_jobs)",[],|r|Ok(Overview{folders:r.get(0)?,dataset_content:r.get(1)?,training_content:r.get(2)?,training_jobs:r.get(3)?})))?;Ok(Json(value)) }

#[tokio::main]
async fn main() {
    let database_url=env::var("APP_DATABASE_URL").unwrap_or_else(|_|"data/laya-dataset-manager.db".into()); let host=env::var("APP_HOST").unwrap_or_else(|_|"127.0.0.1".into()); let port=env::var("APP_PORT").unwrap_or_else(|_|"8080".into()).parse::<u16>().expect("APP_PORT deve ser uma porta válida");
    let database=init_db(&database_url).expect("não foi possível preparar o banco SQLite");
    let app=Router::new().route("/",get(app)).route("/health",get(health)).route("/api/overview",get(overview)).route("/api/folders",get(list_folders).post(create_folder)).route("/api/content",get(list_content).post(create_content)).route("/api/training",get(list_training).post(create_training)).with_state(AppState{db:Arc::new(Mutex::new(database))});
    let address:SocketAddr=format!("{host}:{port}").parse().expect("APP_HOST deve ser um endereço válido"); println!("Laya Dataset Manager em http://{address}"); axum::serve(tokio::net::TcpListener::bind(address).await.expect("não foi possível abrir a porta"),app).await.expect("servidor interrompido");
}
#[cfg(test)] mod tests { use super::*; #[test] fn tree_keeps_nested_folders(){let folders=vec![Folder{id:1,parent_id:None,name:"Raiz".into(),created_at:"".into()},Folder{id:2,parent_id:Some(1),name:"Filha".into(),created_at:"".into()},Folder{id:3,parent_id:Some(2),name:"Neta".into(),created_at:"".into()}];let tree=build_tree(None,&folders);assert_eq!(tree[0].children[0].children[0].folder.name,"Neta");} #[test] fn database_creates_schema(){let db=init_db(":memory:").unwrap();db.execute("INSERT INTO folders (name) VALUES ('Dados')",[]).unwrap();assert!(folder_exists(&db,1).unwrap());}}
