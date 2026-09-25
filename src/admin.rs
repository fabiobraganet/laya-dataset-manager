use super::*;

#[derive(Deserialize)]
pub struct PageQuery {
    search: Option<String>,
    page: Option<i64>,
    per_page: Option<i64>,
    sort: Option<String>,
    kind: Option<String>,
    status: Option<String>,
    source: Option<String>,
}

#[derive(Serialize)]
pub struct PageResult<T> {
    items: Vec<T>,
    page: i64,
    per_page: i64,
    total: i64,
    pages: i64,
}

#[derive(Serialize)]
pub struct DatasetRow {
    id: i64,
    name: String,
    description: String,
    example_count: i64,
    valid_count: i64,
    current_version: Option<i64>,
    updated_at: String,
}

#[derive(Serialize)]
pub struct DatasetSummary {
    dataset: Dataset,
    example_count: i64,
    valid_count: i64,
    type_count: i64,
    current_version: Option<DatasetVersion>,
}

#[derive(Serialize)]
pub struct ExampleRow {
    example_id: String,
    primary_type: String,
    question_count: i64,
    has_gold: bool,
    validation_status: String,
    source: String,
    updated_at: String,
}

#[derive(Serialize)]
pub struct ExampleDetail {
    example_id: String,
    state: Value,
    questions: Value,
    gold: Value,
    validation_status: String,
    validation_errors: Value,
    source: String,
    updated_at: String,
}

#[derive(Serialize)]
pub struct ImportRow {
    id: i64,
    file_name: String,
    total_lines: i64,
    valid_lines: i64,
    invalid_lines: i64,
    duplicate_lines: i64,
    created_at: String,
}

#[derive(Serialize)]
pub struct QualityReport {
    total: i64,
    valid: i64,
    invalid: i64,
    empty_questions: i64,
    missing_gold: i64,
    choice: i64,
    score: i64,
    noul: i64,
    duplicate_ids: i64,
}

#[derive(Serialize)]
pub struct Preflight {
    trainable: bool,
    version_id: i64,
    immutable: bool,
    example_count: i64,
    schema_valid: bool,
    unique_ids: bool,
    questions_valid: bool,
    gold_valid: bool,
    types_supported: bool,
    problems: Vec<String>,
}

#[derive(Serialize)]
pub struct ModelRow {
    id: i64,
    artifact_id: i64,
    name: String,
    training_run_id: i64,
    dataset_name: String,
    version_number: i64,
    sha256: String,
    bytes: i64,
    tensor_count: i64,
    created_at: String,
    active: bool,
}

fn paging(query: &PageQuery) -> (i64, i64, i64) {
    let page = query.page.unwrap_or(1).max(1);
    let per_page = query.per_page.unwrap_or(25).clamp(10, 100);
    (page, per_page, (page - 1) * per_page)
}

pub async fn list_datasets_page(State(state): State<AppState>, Query(query): Query<PageQuery>) -> ApiResult<PageResult<DatasetRow>> {
    let (page, per_page, offset) = paging(&query);
    let search = format!("%{}%", query.search.unwrap_or_default());
    let order = match query.sort.as_deref() {
        Some("name") => "d.name COLLATE NOCASE ASC",
        Some("oldest") => "d.updated_at ASC",
        _ => "d.updated_at DESC, d.id DESC",
    };
    let (total, items) = with_db(&state, |db| {
        let total = db.query_row("SELECT COUNT(*) FROM datasets d WHERE d.name LIKE ?1 OR d.description LIKE ?1", [&search], |r| r.get(0))?;
        let sql = format!("SELECT d.id,d.name,d.description,COUNT(e.id),COALESCE(SUM(CASE WHEN e.validation_status='valid' THEN 1 ELSE 0 END),0),(SELECT MAX(number) FROM dataset_versions WHERE dataset_id=d.id),d.updated_at FROM datasets d LEFT JOIN dataset_examples e ON e.dataset_id=d.id WHERE d.name LIKE ?1 OR d.description LIKE ?1 GROUP BY d.id ORDER BY {order} LIMIT ?2 OFFSET ?3");
        let mut statement = db.prepare(&sql)?;
        let rows = statement.query_map(params![search, per_page, offset], |r| Ok(DatasetRow { id:r.get(0)?, name:r.get(1)?, description:r.get(2)?, example_count:r.get(3)?, valid_count:r.get(4)?, current_version:r.get(5)?, updated_at:r.get(6)? }))?.collect::<rusqlite::Result<Vec<_>>>()?;
        Ok((total, rows))
    })?;
    Ok(Json(PageResult { items, page, per_page, total, pages: (total + per_page - 1) / per_page }))
}

pub async fn dataset_summary(State(state): State<AppState>, Path(id): Path<i64>) -> ApiResult<DatasetSummary> {
    let result = with_db(&state, |db| {
        let dataset = db.query_row("SELECT id,name,description,created_at,updated_at FROM datasets WHERE id=?1", [id], |r| Ok(Dataset{id:r.get(0)?,name:r.get(1)?,description:r.get(2)?,created_at:r.get(3)?,updated_at:r.get(4)?}))?;
        let (example_count, valid_count) = db.query_row("SELECT COUNT(*),COALESCE(SUM(validation_status='valid'),0) FROM dataset_examples WHERE dataset_id=?1", [id], |r| Ok((r.get(0)?,r.get(1)?)))?;
        let type_count = db.query_row("SELECT COUNT(DISTINCT value) FROM dataset_examples, json_tree(questions_json) WHERE dataset_id=?1 AND json_tree.key='type'", [id], |r| r.get(0)).unwrap_or(0);
        let current_version = db.query_row("SELECT id,dataset_id,number,example_count,content_sha256,contract_version,created_at FROM dataset_versions WHERE dataset_id=?1 ORDER BY number DESC LIMIT 1",[id],|r|Ok(DatasetVersion{id:r.get(0)?,dataset_id:r.get(1)?,number:r.get(2)?,example_count:r.get(3)?,content_sha256:r.get(4)?,contract_version:r.get(5)?,created_at:r.get(6)?})).ok();
        Ok(DatasetSummary { dataset, example_count, valid_count, type_count, current_version })
    }).map_err(|_| error(StatusCode::NOT_FOUND, "Dataset não encontrado."))?;
    Ok(Json(result))
}

pub async fn update_dataset(State(state): State<AppState>, Path(id): Path<i64>, Json(input): Json<CreateDataset>) -> ApiResult<Dataset> {
    let name=trim(&input.name,"Nome do dataset",120).map_err(|e|error(StatusCode::UNPROCESSABLE_ENTITY,e))?;
    let description=trim(&input.description,"Descrição",1000).map_err(|e|error(StatusCode::UNPROCESSABLE_ENTITY,e))?;
    let dataset=with_db(&state,|db|{if db.execute("UPDATE datasets SET name=?1,description=?2,updated_at=CURRENT_TIMESTAMP WHERE id=?3",params![name,description,id])?==0{return Err(rusqlite::Error::QueryReturnedNoRows)}db.query_row("SELECT id,name,description,created_at,updated_at FROM datasets WHERE id=?1",[id],|r|Ok(Dataset{id:r.get(0)?,name:r.get(1)?,description:r.get(2)?,created_at:r.get(3)?,updated_at:r.get(4)?}))}).map_err(|_|error(StatusCode::UNPROCESSABLE_ENTITY,"Dataset inexistente ou nome duplicado."))?;
    Ok(Json(dataset))
}

pub async fn list_examples(State(state):State<AppState>,Path(dataset):Path<i64>,Query(query):Query<PageQuery>)->ApiResult<PageResult<ExampleRow>>{
    let(page,per_page,offset)=paging(&query);let search=format!("%{}%",query.search.unwrap_or_default());let kind=query.kind.unwrap_or_default();let status=query.status.unwrap_or_default();let source=query.source.unwrap_or_default();
    let(total,items)=with_db(&state,|db|{
        let filter="dataset_id=?1 AND (example_id LIKE ?2 OR state_json LIKE ?2 OR questions_json LIKE ?2 OR gold_json LIKE ?2) AND (?3='' OR EXISTS(SELECT 1 FROM json_tree(dataset_examples.questions_json) WHERE json_tree.key='type' AND json_tree.value=?3)) AND (?4='' OR validation_status=?4) AND (?5='' OR source=?5)";
        let total=db.query_row(&format!("SELECT COUNT(*) FROM dataset_examples WHERE {filter}"),params![dataset,search,kind,status,source],|r|r.get(0))?;
        let sql=format!("SELECT example_id,state_json,questions_json,gold_json,validation_status,source,updated_at FROM dataset_examples WHERE {filter} ORDER BY example_id LIMIT ?6 OFFSET ?7");let mut s=db.prepare(&sql)?;
        let rows=s.query_map(params![dataset,search,kind,status,source,per_page,offset],|r|{let questions:String=r.get(2)?;let gold:String=r.get(3)?;let q:Value=serde_json::from_str(&questions).unwrap_or(Value::Null);let types:Vec<&str>=q.as_object().into_iter().flat_map(|m|m.values()).filter_map(|v|v.get("type").and_then(Value::as_str)).collect();Ok(ExampleRow{example_id:r.get(0)?,primary_type:types.first().copied().unwrap_or("—").to_string(),question_count:types.len() as i64,has_gold:serde_json::from_str::<Value>(&gold).ok().and_then(|v|v.as_object().cloned()).map_or(false,|m|!m.is_empty()),validation_status:r.get(4)?,source:r.get(5)?,updated_at:r.get(6)?})})?.collect::<rusqlite::Result<Vec<_>>>()?;Ok((total,rows))
    })?;Ok(Json(PageResult{items,page,per_page,total,pages:(total+per_page-1)/per_page}))
}

pub async fn get_example(State(state):State<AppState>,Path((dataset,id)):Path<(i64,String)>)->ApiResult<ExampleDetail>{let item=with_db(&state,|db|db.query_row("SELECT example_id,state_json,questions_json,gold_json,validation_status,validation_errors_json,source,updated_at FROM dataset_examples WHERE dataset_id=?1 AND example_id=?2",params![dataset,id],|r|Ok(ExampleDetail{example_id:r.get(0)?,state:serde_json::from_str(&r.get::<_,String>(1)?).unwrap_or(Value::Null),questions:serde_json::from_str(&r.get::<_,String>(2)?).unwrap_or(Value::Null),gold:serde_json::from_str(&r.get::<_,String>(3)?).unwrap_or(Value::Null),validation_status:r.get(4)?,validation_errors:serde_json::from_str(&r.get::<_,String>(5)?).unwrap_or(Value::Array(vec![])),source:r.get(6)?,updated_at:r.get(7)?}))).map_err(|_|error(StatusCode::NOT_FOUND,"Exemplo não encontrado."))?;Ok(Json(item))}

pub async fn list_versions(State(state):State<AppState>,Path(dataset):Path<i64>)->ApiResult<Vec<DatasetVersion>>{Ok(Json(with_db(&state,|db|{let mut s=db.prepare("SELECT id,dataset_id,number,example_count,content_sha256,contract_version,created_at FROM dataset_versions WHERE dataset_id=?1 ORDER BY number DESC")?;let rows=s.query_map([dataset],|r|Ok(DatasetVersion{id:r.get(0)?,dataset_id:r.get(1)?,number:r.get(2)?,example_count:r.get(3)?,content_sha256:r.get(4)?,contract_version:r.get(5)?,created_at:r.get(6)?}))?.collect::<rusqlite::Result<Vec<_>>>()?;Ok(rows)})?))}

pub async fn list_imports(State(state):State<AppState>,Path(dataset):Path<i64>)->ApiResult<Vec<ImportRow>>{Ok(Json(with_db(&state,|db|{let mut s=db.prepare("SELECT id,file_name,total_lines,valid_lines,invalid_lines,duplicate_lines,created_at FROM dataset_imports WHERE dataset_id=?1 ORDER BY id DESC")?;let rows=s.query_map([dataset],|r|Ok(ImportRow{id:r.get(0)?,file_name:r.get(1)?,total_lines:r.get(2)?,valid_lines:r.get(3)?,invalid_lines:r.get(4)?,duplicate_lines:r.get(5)?,created_at:r.get(6)?}))?.collect::<rusqlite::Result<Vec<_>>>()?;Ok(rows)})?))}

pub async fn quality(State(state):State<AppState>,Path(dataset):Path<i64>)->ApiResult<QualityReport>{let report=with_db(&state,|db|{let(total,valid,invalid,empty,missing)=db.query_row("SELECT COUNT(*),COALESCE(SUM(validation_status='valid'),0),COALESCE(SUM(validation_status='invalid'),0),COALESCE(SUM(NOT EXISTS(SELECT 1 FROM json_each(dataset_examples.questions_json))),0),COALESCE(SUM(NOT EXISTS(SELECT 1 FROM json_each(dataset_examples.gold_json))),0) FROM dataset_examples WHERE dataset_id=?1",[dataset],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?)))?;let count_kind=|kind:&str|db.query_row("SELECT COUNT(DISTINCT dataset_examples.id) FROM dataset_examples,json_tree(dataset_examples.questions_json) WHERE dataset_id=?1 AND json_tree.key='type' AND json_tree.value=?2",params![dataset,kind],|r|r.get(0));let duplicates=db.query_row("SELECT COUNT(*) FROM (SELECT example_id FROM dataset_examples WHERE dataset_id=?1 GROUP BY example_id HAVING COUNT(*)>1)",[dataset],|r|r.get(0))?;Ok(QualityReport{total,valid,invalid,empty_questions:empty,missing_gold:missing,choice:count_kind("choice")?,score:count_kind("score")?,noul:count_kind("noul")?,duplicate_ids:duplicates})})?;Ok(Json(report))}

pub async fn preflight(State(state):State<AppState>,Path(version):Path<i64>)->ApiResult<Preflight>{let result=with_db(&state,|db|{let exists:bool=db.query_row("SELECT EXISTS(SELECT 1 FROM dataset_versions WHERE id=?1)",[version],|r|r.get(0))?;if !exists{return Err(rusqlite::Error::QueryReturnedNoRows)}let mut s=db.prepare("SELECT example_id,state_json,questions_json,gold_json FROM dataset_version_examples WHERE dataset_version_id=?1")?;let rows=s.query_map([version],|r|Ok(CreateDatasetExample{id:r.get(0)?,state:r.get(1)?,questions:r.get(2)?,gold:r.get(3)?}))?.collect::<rusqlite::Result<Vec<_>>>()?;let mut problems=Vec::new();for row in &rows{if let Err(e)=validate_example(row){problems.push(format!("{}: {}",row.id,e));}}let count=rows.len() as i64;Ok(Preflight{trainable:count>0&&problems.is_empty(),version_id:version,immutable:true,example_count:count,schema_valid:problems.is_empty(),unique_ids:true,questions_valid:problems.is_empty(),gold_valid:problems.is_empty(),types_supported:problems.is_empty(),problems})}).map_err(|_|error(StatusCode::NOT_FOUND,"DatasetVersion não encontrada."))?;Ok(Json(result))}

pub async fn list_models(State(state):State<AppState>)->ApiResult<Vec<ModelRow>>{Ok(Json(with_db(&state,|db|{let mut s=db.prepare("SELECT a.id,a.id,a.name,a.training_run_id,d.name,dv.number,a.sha256,a.bytes,a.tensor_count,a.created_at,EXISTS(SELECT 1 FROM active_models am WHERE am.artifact_id=a.id) FROM model_artifacts a JOIN training_runs tr ON tr.id=a.training_run_id JOIN dataset_versions dv ON dv.id=tr.dataset_version_id JOIN datasets d ON d.id=dv.dataset_id ORDER BY a.id DESC")?;let rows=s.query_map([],|r|Ok(ModelRow{id:r.get(0)?,artifact_id:r.get(1)?,name:r.get(2)?,training_run_id:r.get(3)?,dataset_name:r.get(4)?,version_number:r.get(5)?,sha256:r.get(6)?,bytes:r.get(7)?,tensor_count:r.get(8)?,created_at:r.get(9)?,active:r.get(10)?}))?.collect::<rusqlite::Result<Vec<_>>>()?;Ok(rows)})?))}
