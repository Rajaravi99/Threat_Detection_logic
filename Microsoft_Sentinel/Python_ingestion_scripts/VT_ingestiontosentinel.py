import os
import json
import time
import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

import requests
from azure.identity import DefaultAzureCredential
from azure.monitor.ingestion import LogsIngestionClient
from azure.core.exceptions import HttpResponseError


# -----------------------------
# Configuration from environment
# -----------------------------
VT_API_KEY = os.environ["VT_API_KEY"]

DATA_COLLECTION_ENDPOINT = os.environ["DATA_COLLECTION_ENDPOINT"]
LOGS_DCR_RULE_ID = os.environ["LOGS_DCR_RULE_ID"]
LOGS_DCR_STREAM_NAME = os.environ.get("LOGS_DCR_STREAM_NAME", "Custom-VirusTotal")

INDICATOR_FILE = os.environ.get("INDICATOR_FILE", "indicators.txt")

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "100"))
REQUEST_SLEEP_SECONDS = float(os.environ.get("REQUEST_SLEEP_SECONDS", "15"))

VT_BASE_URL = "https://www.virustotal.com/api/v3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def epoch_to_iso(epoch_value):
    if not epoch_value:
        return None
    try:
        return datetime.fromtimestamp(int(epoch_value), tz=timezone.utc).isoformat()
    except Exception:
        return None


def vt_url_id(url: str) -> str:
    """
    VirusTotal v3 URL object ID is URL-safe base64 without padding.
    """
    return base64.urlsafe_b64encode(url.encode()).decode().strip("=")


def detect_hash_type(value: str) -> str:
    value = value.strip()
    if len(value) == 32:
        return "md5"
    if len(value) == 40:
        return "sha1"
    if len(value) == 64:
        return "sha256"
    return "unknown"


def get_vt_endpoint(indicator_type: str, indicator: str) -> Tuple[str, str]:
    indicator_type = indicator_type.lower().strip()
    indicator = indicator.strip()

    if indicator_type == "ip":
        return f"{VT_BASE_URL}/ip_addresses/{indicator}", indicator

    if indicator_type == "domain":
        return f"{VT_BASE_URL}/domains/{indicator}", indicator

    if indicator_type == "hash":
        return f"{VT_BASE_URL}/files/{indicator}", indicator

    if indicator_type == "url":
        encoded_id = vt_url_id(indicator)
        return f"{VT_BASE_URL}/urls/{encoded_id}", encoded_id

    raise ValueError(f"Unsupported indicator type: {indicator_type}")


def query_virustotal(indicator_type: str, indicator: str) -> Dict[str, Any]:
    endpoint, vt_object_id = get_vt_endpoint(indicator_type, indicator)

    headers = {
        "x-apikey": VT_API_KEY,
        "accept": "application/json"
    }

    response = requests.get(endpoint, headers=headers, timeout=60)

    if response.status_code == 404:
        logging.warning("Indicator not found in VirusTotal: %s,%s", indicator_type, indicator)
        return {
            "found": False,
            "status_code": response.status_code,
            "vt_object_id": vt_object_id,
            "raw": response.text
        }

    if response.status_code == 429:
        raise RuntimeError("VirusTotal API quota exceeded or rate limited. Reduce polling frequency.")

    response.raise_for_status()

    return {
        "found": True,
        "status_code": response.status_code,
        "vt_object_id": vt_object_id,
        "raw": response.json()
    }


def normalize_vt_record(indicator_type: str, indicator: str, vt_response: Dict[str, Any]) -> Dict[str, Any]:
    now = utc_now_iso()

    if not vt_response.get("found"):
        return {
            "TimeGenerated": now,
            "Indicator": indicator,
            "IndicatorType": indicator_type,
            "VTObjectId": vt_response.get("vt_object_id"),
            "VTReputation": None,
            "VTHarmless": 0,
            "VTMalicious": 0,
            "VTSuspicious": 0,
            "VTUndetected": 0,
            "VTTimeout": 0,
            "VTLastAnalysisDate": None,
            "VTLink": build_vt_link(indicator_type, indicator),
            "Source": "VirusTotalAPI",
            "RawData": {
                "found": False,
                "status_code": vt_response.get("status_code"),
                "raw": vt_response.get("raw")
            }
        }

    raw = vt_response["raw"]
    data = raw.get("data", {})
    attributes = data.get("attributes", {})
    stats = attributes.get("last_analysis_stats", {})

    return {
        "TimeGenerated": now,
        "Indicator": indicator,
        "IndicatorType": indicator_type,
        "VTObjectId": data.get("id", vt_response.get("vt_object_id")),
        "VTReputation": attributes.get("reputation"),
        "VTHarmless": stats.get("harmless", 0),
        "VTMalicious": stats.get("malicious", 0),
        "VTSuspicious": stats.get("suspicious", 0),
        "VTUndetected": stats.get("undetected", 0),
        "VTTimeout": stats.get("timeout", 0),
        "VTLastAnalysisDate": epoch_to_iso(attributes.get("last_analysis_date")),
        "VTLink": build_vt_link(indicator_type, indicator),
        "Source": "VirusTotalAPI",
        "RawData": raw
    }


def build_vt_link(indicator_type: str, indicator: str) -> str:
    indicator_type = indicator_type.lower()

    if indicator_type == "ip":
        return f"https://www.virustotal.com/gui/ip-address/{indicator}"

    if indicator_type == "domain":
        return f"https://www.virustotal.com/gui/domain/{indicator}"

    if indicator_type == "url":
        return f"https://www.virustotal.com/gui/url/{vt_url_id(indicator)}"

    if indicator_type == "hash":
        return f"https://www.virustotal.com/gui/file/{indicator}"

    return "https://www.virustotal.com/gui/home/search"


def load_indicators(path: str) -> List[Tuple[str, str]]:
    indicators = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.strip()

            if not clean or clean.startswith("#"):
                continue

            parts = clean.split(",", 1)

            if len(parts) != 2:
                raise ValueError(f"Invalid indicator line: {clean}. Expected format: type,value")

            indicator_type = parts[0].strip().lower()
            indicator_value = parts[1].strip()

            indicators.append((indicator_type, indicator_value))

    return indicators


def upload_to_log_analytics(records: List[Dict[str, Any]]) -> None:
    if not records:
        logging.info("No records to upload.")
        return

    credential = DefaultAzureCredential()
    client = LogsIngestionClient(
        endpoint=DATA_COLLECTION_ENDPOINT,
        credential=credential,
        logging_enable=False
    )

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]

        try:
            client.upload(
                rule_id=LOGS_DCR_RULE_ID,
                stream_name=LOGS_DCR_STREAM_NAME,
                logs=batch
            )
            logging.info("Uploaded %s records to Log Analytics.", len(batch))

        except HttpResponseError as e:
            logging.error("Upload failed: %s", e)
            raise


def main():
    indicators = load_indicators(INDICATOR_FILE)
    logging.info("Loaded %s indicators.", len(indicators))

    normalized_records = []

    for indicator_type, indicator in indicators:
        try:
            logging.info("Querying VirusTotal: %s,%s", indicator_type, indicator)

            vt_response = query_virustotal(indicator_type, indicator)
            normalized = normalize_vt_record(indicator_type, indicator, vt_response)
            normalized_records.append(normalized)

            time.sleep(REQUEST_SLEEP_SECONDS)

        except Exception as e:
            logging.exception("Failed processing indicator %s,%s: %s", indicator_type, indicator, e)

    upload_to_log_analytics(normalized_records)


if __name__ == "__main__":
    main()