import azure.functions as func
import logging
import json
import os
import urllib.request
import urllib.error
import ipaddress
import re
from typing import Any, Dict, List, Optional

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
VT_API_BASE_URL = "https://www.virustotal.com/api/v3/ip_addresses"

@app.function_name(name="my_test_function")
@app.route(route="")

def my_test_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")

    name = req.params.get("name")

    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            req_body = {}
        name = req_body.get("name")

    if name:
        return func.HttpResponse(
            f"Hello, {name}. This HTTP triggered function executed successfully.",
            status_code=200
        )

    return func.HttpResponse(
        "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
        status_code=200
    )




def is_valid_public_ip(ip_value: str) -> bool:
    """
    Checks if the value is a valid public IPv4 or IPv6 address.
    Private/internal IPs are skipped because VirusTotal usually won't help for them.
    """
    try:
        ip_obj = ipaddress.ip_address(ip_value)

        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            return False

        return True

    except ValueError:
        return False
    

def extract_ips_from_text(text: str) -> List:
    """
    Extracts possible IPv4 addresses from any text.
    This is useful when Sentinel sends a complete incident JSON body.
    """
    ipv4_regex = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
    possible_ips = re.findall(ipv4_regex, text)

    valid_ips = []
    for ip in possible_ips:
        if is_valid_public_ip(ip):
            valid_ips.append(ip)

    return list(set(valid_ips))


def extract_ips_from_sentinel_body(body: Dict[str, Any]) -> List:
    """
    Tries multiple common places where Sentinel / Logic App may send IP entities.
    Also falls back to scanning the full JSON body for IP addresses.
    """
    found_ips = []

    # Direct input examples:
    # { "ip": "8.8.8.8" }
    # { "ipAddress": "8.8.8.8" }
    for key in ["ip", "ipAddress", "IPAddress", "address"]:
        value = body.get(key)
        if isinstance(value, str) and is_valid_public_ip(value):
            found_ips.append(value)

    # Entity examples:
    # { "entities": [ { "type": "ip", "address": "8.8.8.8" } ] }
    entities = body.get("entities")
    if isinstance(entities, list):
        for entity in entities:
            if isinstance(entity, dict):
                for key in ["ip", "ipAddress", "IPAddress", "address"]:
                    value = entity.get(key)
                    if isinstance(value, str) and is_valid_public_ip(value):
                        found_ips.append(value)

    # Fallback: convert full JSON body to text and extract IPs
    body_as_text = json.dumps(body)
    found_ips.extend(extract_ips_from_text(body_as_text))

    return list(set(found_ips))


def query_virustotal_ip(ip_value: str, api_key: str) -> Dict[str, Any]:
    """
    Calls VirusTotal API v3 for an IP address.
    """
    url = f"{VT_API_BASE_URL}/{ip_value}"

    request = urllib.request.Request(
        url=url,
        method="GET",
        headers={
            "x-apikey": api_key,
            "accept": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
            return json.loads(response_body)

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="ignore")
        return {
            "error": True,
            "status_code": error.code,
            "message": error_body
        }

    except urllib.error.URLError as error:
        return {
            "error": True,
            "status_code": 500,
            "message": str(error)
        }

    except Exception as error:
        return {
            "error": True,
            "status_code": 500,
            "message": str(error)
        }


def calculate_confidence_score(stats: Dict[str, int]) -> Dict[str, Any]:
    """
    Calculates a simple confidence score from VirusTotal detection stats.

    Formula:
    confidence_score = ((malicious + suspicious) / total_engines) * 100
    """
    harmless = int(stats.get("harmless", 0))
    malicious = int(stats.get("malicious", 0))
    suspicious = int(stats.get("suspicious", 0))
    undetected = int(stats.get("undetected", 0))
    timeout = int(stats.get("timeout", 0))

    total_engines = harmless + malicious + suspicious + undetected + timeout
    risky_engines = malicious + suspicious

    if total_engines == 0:
        confidence_score = 0
    else:
        confidence_score = round((risky_engines / total_engines) * 100, 2)

    if malicious >= 5 or confidence_score >= 20:
        verdict = "malicious"
    elif malicious > 0 or suspicious > 0:
        verdict = "suspicious"
    else:
        verdict = "clean_or_unknown"

    return {
        "confidence_score": confidence_score,
        "verdict": verdict,
        "total_engines": total_engines,
        "risky_engines": risky_engines,
        "harmless": harmless,
        "malicious": malicious,
        "suspicious": suspicious,
        "undetected": undetected,
        "timeout": timeout
    }


@app.route(route="vt-ip-confidence", methods=["GET", "POST"])
def vt_ip_confidence(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP Trigger Azure Function.

    GET example:
    /api/vt-ip-confidence?ip=8.8.8.8

    POST example:
    {
        "ip": "8.8.8.8"
    }
    """

    vt_api_key = os.environ.get("VIRUSTOTAL_API_KEY")

    if not vt_api_key:
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": "Missing VIRUSTOTAL_API_KEY application setting."
            }),
            status_code=500,
            mimetype="application/json"
        )

    ips_to_check = []

    # Try IP from query string first
    ip_from_query = req.params.get("ip")
    if ip_from_query and is_valid_public_ip(ip_from_query):
        ips_to_check.append(ip_from_query)

    # Try IPs from JSON body
    try:
        body = req.get_json()
        if isinstance(body, dict):
            ips_to_check.extend(extract_ips_from_sentinel_body(body))
    except ValueError:
        # No valid JSON body provided
        pass

    ips_to_check = list(set(ips_to_check))

    if not ips_to_check:
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": "No valid public IP address found in request.",
                "example_get": "/api/vt-ip-confidence?ip=8.8.8.8",
                "example_post": {
                    "ip": "8.8.8.8"
                }
            }),
            status_code=400,
            mimetype="application/json"
        )

    results = []

    for ip_value in ips_to_check:
        vt_response = query_virustotal_ip(ip_value, vt_api_key)

        if vt_response.get("error"):
            results.append({
                "ip": ip_value,
                "success": False,
                "error": vt_response
            })
            continue

        attributes = (
            vt_response
            .get("data", {})
            .get("attributes", {})
        )

        stats = attributes.get("last_analysis_stats", {})
        reputation = attributes.get("reputation")
        country = attributes.get("country")
        as_owner = attributes.get("as_owner")
        last_analysis_date = attributes.get("last_analysis_date")

        score_result = calculate_confidence_score(stats)

        results.append({
            "ip": ip_value,
            "success": True,
            "confidence_score": score_result["confidence_score"],
            "verdict": score_result["verdict"],
            "reputation": reputation,
            "country": country,
            "as_owner": as_owner,
            "last_analysis_date": last_analysis_date,
            "vt_stats": {
                "harmless": score_result["harmless"],
                "malicious": score_result["malicious"],
                "suspicious": score_result["suspicious"],
                "undetected": score_result["undetected"],
                "timeout": score_result["timeout"],
                "total_engines": score_result["total_engines"]
            },
            "virustotal_gui_link": f"https://www.virustotal.com/gui/ip-address/{ip_value}"
        })

    response_body = {
        "success": True,
        "count": len(results),
        "results": results
    }

    return func.HttpResponse(
        json.dumps(response_body, indent=2),
        status_code=200,
        mimetype="application/json"
    )
