"""
MDE / XDR Alert & Incident replication  -  LAW1 -> LAW2
--------------------------------------------------------
Timer Trigger (every 15 min).
- Reads SecurityAlert / SecurityIncident from the SOURCE Log Analytics workspace
  (pg-sentinel-log-cross-we).
- Host scope is built DYNAMICALLY from DeviceInfo (MachineGroup).
- Incremental via checkpoint blob, based on ingestion_time() to be resilient to
  Defender ingestion latency (no data loss).
- Writes to custom tables (SecurityAlertMDE_CL / SecurityIncidentMDE_CL) in the
  DESTINATION workspace (pg-siem-log-prod-we-law) via the Logs Ingestion API
  (DCE + DCR dcr-prd-mde-replication-we).
Auth: System-assigned Managed Identity (zero secrets).

Stream names and all endpoints are read from App Settings, so no value is
hard-coded here.
"""

import os
import json
import logging
import datetime as dt

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from azure.monitor.ingestion import LogsIngestionClient
from azure.storage.blob import BlobClient

app = func.FunctionApp()

# ----------------------------------------------------------------------
# Configuration (App Settings)  -- names match the Function App exactly
# ----------------------------------------------------------------------
SOURCE_LAW_ID        = os.environ["SOURCE_LAW_ID"]
DCE_ENDPOINT         = os.environ["DCE_ENDPOINT"]
DCR_IMMUTABLE_ID     = os.environ["DCR_IMMUTABLE_ID"]
STREAM_ALERT         = os.environ["STREAM_ALERT"]          # Custom-SecurityAlertMDE_CL
STREAM_INCIDENT      = os.environ["STREAM_INCIDENT"]       # Custom-SecurityIncidentMDE_CL
STORAGE_ACCOUNT      = os.environ["STORAGE_ACCOUNT"]       # stprdmderepwe01
CHECKPOINT_CONTAINER = os.environ["CHECKPOINT_CONTAINER"]  # checkpoint
CHECKPOINT_FILE      = os.environ["CHECKPOINT_FILE"]       # lastcheckpoint.json
MACHINE_GROUP        = os.environ["MACHINE_GROUP"]         # Servers_Island_ESB
LOOKBACK_DAYS        = int(os.environ.get("LOOKBACK_DAYS", "120"))

# Single credential reused everywhere (Managed Identity when running in Azure)
CRED = DefaultAzureCredential()

# ----------------------------------------------------------------------
# Checkpoint helpers  (blob JSON: {"LastExecutionTime": "ISO-8601"})
# The checkpoint tracks the max ingestion_time() already processed.
# ----------------------------------------------------------------------
def _blob_client() -> BlobClient:
    account_url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net"
    return BlobClient(account_url=account_url,
                      container_name=CHECKPOINT_CONTAINER,
                      blob_name=CHECKPOINT_FILE,
                      credential=CRED)

def read_checkpoint() -> str:
    try:
        data = _blob_client().download_blob().readall()
        ts = json.loads(data).get("LastExecutionTime")
        if ts:
            return ts
    except Exception as e:
        logging.warning(f"Checkpoint read failed, defaulting to 1h ago. {e}")
    return (dt.datetime.utcnow() - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

def write_checkpoint(ts_iso: str) -> None:
    body = json.dumps({"LastExecutionTime": ts_iso})
    _blob_client().upload_blob(body, overwrite=True)
    logging.info(f"Checkpoint updated -> {ts_iso}")

# ----------------------------------------------------------------------
# KQL queries
#   - host scope built dynamically from DeviceInfo / MachineGroup
#   - incremental filter on ingestion_time() (resilient to ingestion latency)
#   - projections match EXACTLY the DCR stream schemas (26 columns each)
#   - _IngestTime is a helper column used only to advance the checkpoint
# ----------------------------------------------------------------------
def kql_alerts(checkpoint: str) -> str:
    return f"""
let scope = DeviceInfo
    | where TimeGenerated > ago({LOOKBACK_DAYS}d)
    | where MachineGroup == "{MACHINE_GROUP}"
    | summarize by DeviceName;
SecurityAlert
| extend _IngestTime = ingestion_time()
| where _IngestTime > datetime('{checkpoint}')
| where ProviderName == "MDATP"
| mv-apply e = parse_json(Entities) on (
    where tostring(e.Type) == "host"
    | extend HostName = tostring(e.HostName)
  )
| where HostName in (scope) or CompromisedEntity in (scope)
| project _IngestTime, TimeGenerated, DisplayName, AlertName, AlertSeverity, Description,
          ProviderName, VendorName, VendorOriginalId, SystemAlertId, AlertType,
          IsIncident, StartTime, EndTime, ProcessingEndTime,
          RemediationSteps = tostring(RemediationSteps),
          ExtendedProperties = tostring(ExtendedProperties),
          Entities = tostring(Entities),
          ExtendedLinks = tostring(ExtendedLinks),
          ProductName, AlertLink, Status, CompromisedEntity,
          Tactics = tostring(Tactics),
          Techniques = tostring(Techniques),
          SubTechniques = tostring(SubTechniques)
"""

def kql_incidents(checkpoint: str) -> str:
    return f"""
let scope = DeviceInfo
    | where TimeGenerated > ago({LOOKBACK_DAYS}d)
    | where MachineGroup == "{MACHINE_GROUP}"
    | summarize by DeviceName;
let scopedAlertIds = SecurityAlert
    | where ProviderName == "MDATP"
    | mv-apply e = parse_json(Entities) on (
        where tostring(e.Type) == "host"
        | extend HostName = tostring(e.HostName)
      )
    | where HostName in (scope) or CompromisedEntity in (scope)
    | distinct SystemAlertId;
SecurityIncident
| extend _IngestTime = ingestion_time()
| where _IngestTime > datetime('{checkpoint}')
| mv-expand AlertIds to typeof(string)
| where AlertIds in (scopedAlertIds)
| summarize arg_max(_IngestTime, *) by IncidentNumber
| project _IngestTime, TimeGenerated, IncidentName, Title, Description, Severity,
          Status, Classification, ClassificationComment,
          Owner = tostring(Owner), ProviderName, ProviderIncidentId,
          FirstActivityTime, LastActivityTime, LastModifiedTime, CreatedTime, ClosedTime,
          IncidentNumber,
          RelatedAnalyticRuleIds = tostring(RelatedAnalyticRuleIds),
          AlertIds = tostring(AlertIds),
          BookmarkIds = tostring(BookmarkIds),
          Comments = tostring(Comments),
          Tasks = tostring(Tasks),
          Labels = tostring(Labels),
          IncidentUrl,
          AdditionalData = tostring(AdditionalData),
          ModifiedBy
"""

# ----------------------------------------------------------------------
# Query + Ingest
# ----------------------------------------------------------------------
def run_query(logs_client: LogsQueryClient, query: str) -> list:
    resp = logs_client.query_workspace(
        workspace_id=SOURCE_LAW_ID,
        query=query,
        timespan=None,   # time window is encoded in the query via the checkpoint
    )
    if resp.status != LogsQueryStatus.SUCCESS:
        logging.error(f"Query failed/partial: {getattr(resp, 'partial_error', resp.status)}")
        return []
    rows = []
    for table in resp.tables:
        cols = table.columns
        for r in table.rows:
            rec = {}
            for c, v in zip(cols, r):
                if isinstance(v, dt.datetime):
                    v = v.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                rec[c] = v
            rows.append(rec)
    return rows

def ingest(ingest_client: LogsIngestionClient, stream: str, records: list) -> None:
    if not records:
        return
    # Strip helper column before sending (not part of the DCR stream schema)
    payload = [{k: v for k, v in r.items() if k != "_IngestTime"} for r in records]
    CHUNK = 1000
    for i in range(0, len(payload), CHUNK):
        batch = payload[i:i + CHUNK]
        ingest_client.upload(rule_id=DCR_IMMUTABLE_ID, stream_name=stream, logs=batch)
        logging.info(f"Ingested {len(batch)} records into {stream}")

def max_ingesttime(records: list, current: str) -> str:
    mx = current
    for r in records:
        tg = r.get("_IngestTime")
        if tg and tg > mx:
            mx = tg
    return mx

# ----------------------------------------------------------------------
# Timer trigger  (every 15 minutes)
# ----------------------------------------------------------------------
@app.function_name(name="MDEReplicationJob")
@app.timer_trigger(schedule="0 */15 * * * *", arg_name="timer",
                   run_on_startup=False, use_monitor=True)
def MDEReplicationJob(timer: func.TimerRequest) -> None:
    logging.info("=== MDE/XDR replication run started ===")

    checkpoint = read_checkpoint()
    logging.info(f"Checkpoint (ingestion_time) = {checkpoint} | MachineGroup = {MACHINE_GROUP}")

    logs_client   = LogsQueryClient(CRED)
    ingest_client = LogsIngestionClient(endpoint=DCE_ENDPOINT, credential=CRED)

    new_checkpoint = checkpoint

    # ---- Alerts ----
    alerts = run_query(logs_client, kql_alerts(checkpoint))
    logging.info(f"Alerts fetched: {len(alerts)}")
    ingest(ingest_client, STREAM_ALERT, alerts)
    new_checkpoint = max_ingesttime(alerts, new_checkpoint)

    # ---- Incidents ----
    incidents = run_query(logs_client, kql_incidents(checkpoint))
    logging.info(f"Incidents fetched: {len(incidents)}")
    ingest(ingest_client, STREAM_INCIDENT, incidents)
    new_checkpoint = max_ingesttime(incidents, new_checkpoint)

    # ---- Advance checkpoint only if something was processed ----
    if new_checkpoint != checkpoint:
        write_checkpoint(new_checkpoint)
    else:
        logging.info("No new records; checkpoint unchanged.")

    logging.info("=== MDE/XDR replication run finished ===")
