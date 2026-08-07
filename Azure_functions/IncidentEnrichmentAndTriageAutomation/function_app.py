import hashlib
import ipaddress
import json
import logging
import re
import time
import uuid

from datetime import datetime, timezone
from typing import Any

import azure.functions as func
import logging

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.function_name(name="my_test_function",methods=["GET", "POST"])
@app.route(route="")

def my_test_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )



# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# MAX_ENTITIES = 100
# MAX_REQUEST_SIZE_BYTES = 1_000_000

# SUPPORTED_ENTITY_TYPES = {
#     "ip",
#     "domain",
#     "hash",
#     "url",
#     "user",
#     "host",
# }

# SEVERITY_SCORES = {
#     "informational": 0,
#     "low": 5,
#     "medium": 10,
#     "high": 15,
#     "critical": 25,
# }

# HASH_LENGTH_TO_TYPE = {
#     32: "MD5",
#     40: "SHA1",
#     64: "SHA256",
# }

# DOMAIN_PATTERN = re.compile(
#     r"^(?=.{1,253}$)"
#     r"(?:?:[a-z0-9-]{0,61}[a-z0-9]?\.)+"
#     r"[a-z]{2,63}$",
#     re.IGNORECASE,
# )

# HASH_PATTERN = re.compile(r"^[a-fA-F0-9]+$")

# HOST_PATTERN = re.compile(
#     r"^[a-zA-Z0-9]"
#     r"(?:[a-zA-Z0-9._-]{0,253}[a-zA-Z0-9])?$"
# )

# USER_PATTERN = re.compile(
#     r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
# )


# # --------------------------------------------------------------------------
# # Custom exceptions
# # --------------------------------------------------------------------------

# class ValidationError(Exception):
#     """Raised when the request payload is invalid."""


# # --------------------------------------------------------------------------
# # Utility functions
# # --------------------------------------------------------------------------

# def utc_now() -> str:
#     """Return the current UTC time in ISO 8601 format."""

#     return datetime.now(timezone.utc).isoformat()


# def json_response(
#     body: dict[str, Any],
#     status_code: int,
#     correlation_id: str,
# ) -> func.HttpResponse:
#     """Create a consistent JSON HTTP response."""

#     return func.HttpResponse(
#         body=json.dumps(body, indent=2, ensure_ascii=False),
#         status_code=status_code,
#         mimetype="application/json",
#         headers={
#             "X-Correlation-ID": correlation_id,
#             "Cache-Control": "no-store",
#         },
#     )


# def create_error_response(
#     status_code: int,
#     error_code: str,
#     message: str,
#     correlation_id: str,
#     details: list[str] | None = None,
# ) -> func.HttpResponse:
#     """Create a standardized error response."""

#     body = {
#         "status": "error",
#         "error": {
#             "code": error_code,
#             "message": message,
#             "details": details or [],
#         },
#         "correlation_id": correlation_id,
#         "timestamp_utc": utc_now(),
#     }

#     return json_response(
#         body=body,
#         status_code=status_code,
#         correlation_id=correlation_id,
#     )


# def clean_text(value: Any, maximum_length: int = 500) -> str:
#     """
#     Convert a value to a sanitized string.

#     Control characters are removed to reduce log injection and malformed
#     output risks.
#     """

#     if value is None:
#         return ""

#     cleaned = str(value).strip()
#     cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)

#     return cleaned[:maximum_length]


# def create_indicator_id(entity_type: str, normalized_value: str) -> str:
#     """Create a stable identifier without exposing the full indicator."""

#     source = f"{entity_type}:{normalized_value}".encode("utf-8")

#     return hashlib.sha256(source).hexdigest()[:16]


# # --------------------------------------------------------------------------
# # Request validation
# # --------------------------------------------------------------------------

# def validate_payload(payload: Any) -> dict[str, Any]:
#     """Validate the incoming security alert."""

#     if not isinstance(payload, dict):
#         raise ValidationError("The request body must be a JSON object.")

#     incident_id = clean_text(payload.get("incident_id"), 200)
#     title = clean_text(payload.get("title"), 500)
#     severity = clean_text(payload.get("severity"), 50).lower()
#     entities = payload.get("entities")

#     errors: list[str] = []

#     if not incident_id:
#         errors.append("'incident_id' is required.")

#     if not title:
#         errors.append("'title' is required.")

#     if not severity:
#         errors.append("'severity' is required.")
#     elif severity not in SEVERITY_SCORES:
#         allowed = ", ".join(SEVERITY_SCORES.keys())
#         errors.append(
#             f"'severity' must be one of: {allowed}."
#         )

#     if not isinstance(entities, list):
#         errors.append("'entities' must be a JSON array.")
#     elif not entities:
#         errors.append("'entities' must contain at least one entity.")
#     elif len(entities) > MAX_ENTITIES:
#         errors.append(
#             f"'entities' cannot contain more than {MAX_ENTITIES} items."
#         )

#     if errors:
#         raise ValidationError(" ".join(errors))

#     normalized_payload = {
#         "incident_id": incident_id,
#         "title": title,
#         "severity": severity,
#         "host": clean_text(payload.get("host"), 255),
#         "user": clean_text(payload.get("user"), 320),
#         "entities": entities,
#     }

#     return normalized_payload


# # --------------------------------------------------------------------------
# # Entity normalization
# # --------------------------------------------------------------------------

# def normalize_ip(value: str) -> dict[str, Any]:
#     """Validate and classify an IPv4 or IPv6 address."""

#     try:
#         ip = ipaddress.ip_address(value.strip())
#     except ValueError:
#         return {
#             "valid": False,
#             "normalized_value": value,
#             "classification": "invalid",
#             "ip_version": None,
#             "risk_points": 0,
#             "reasons": ["Invalid IP address"],
#         }

#     if ip.is_loopback:
#         classification = "loopback"
#         risk_points = -20
#     elif ip.is_private:
#         classification = "private"
#         risk_points = -10
#     elif ip.is_multicast:
#         classification = "multicast"
#         risk_points = -15
#     elif ip.is_unspecified:
#         classification = "unspecified"
#         risk_points = -20
#     elif ip.is_reserved:
#         classification = "reserved"
#         risk_points = -10
#     elif ip.is_link_local:
#         classification = "link-local"
#         risk_points = -15
#     elif ip.is_global:
#         classification = "public"
#         risk_points = 10
#     else:
#         classification = "special-purpose"
#         risk_points = 0

#     return {
#         "valid": True,
#         "normalized_value": ip.compressed,
#         "classification": classification,
#         "ip_version": ip.version,
#         "risk_points": risk_points,
#         "reasons": [
#             f"{classification.capitalize()} IPv{ip.version} address"
#         ],
#     }


# def normalize_domain(value: str) -> dict[str, Any]:
#     """Validate and normalize a domain name."""

#     normalized = value.strip().lower().rstrip(".")

#     if not normalized:
#         return {
#             "valid": False,
#             "normalized_value": normalized,
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["Domain is empty"],
#         }

#     try:
#         ipaddress.ip_address(normalized)

#         return {
#             "valid": False,
#             "normalized_value": normalized,
#             "classification": "ip-submitted-as-domain",
#             "risk_points": 0,
#             "reasons": ["An IP address was submitted as a domain"],
#         }
#     except ValueError:
#         pass

#     if not DOMAIN_PATTERN.fullmatch(normalized):
#         return {
#             "valid": False,
#             "normalized_value": normalized,
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["Invalid domain format"],
#         }

#     labels = normalized.split(".")
#     subdomain_depth = max(0, len(labels) - 2)

#     risk_points = 5
#     reasons = ["Valid external domain"]

#     if subdomain_depth >= 3:
#         risk_points += 5
#         reasons.append("Domain has multiple subdomain levels")

#     return {
#         "valid": True,
#         "normalized_value": normalized,
#         "classification": "domain",
#         "subdomain_depth": subdomain_depth,
#         "risk_points": risk_points,
#         "reasons": reasons,
#     }


# def normalize_hash(value: str) -> dict[str, Any]:
#     """Validate and classify MD5, SHA-1 or SHA-256 hashes."""

#     normalized = value.strip().lower()

#     if not HASH_PATTERN.fullmatch(normalized):
#         return {
#             "valid": False,
#             "normalized_value": normalized,
#             "classification": "invalid",
#             "hash_type": None,
#             "risk_points": 0,
#             "reasons": ["Hash contains non-hexadecimal characters"],
#         }

#     hash_type = HASH_LENGTH_TO_TYPE.get(len(normalized))

#     if not hash_type:
#         return {
#             "valid": False,
#             "normalized_value": normalized,
#             "classification": "unsupported",
#             "hash_type": None,
#             "risk_points": 0,
#             "reasons": [
#                 "Only MD5, SHA-1 and SHA-256 hashes are supported"
#             ],
#         }

#     return {
#         "valid": True,
#         "normalized_value": normalized,
#         "classification": "cryptographic-hash",
#         "hash_type": hash_type,
#         "risk_points": 10,
#         "reasons": [f"Valid {hash_type} file hash"],
#     }


# def normalize_url(value: str) -> dict[str, Any]:
#     """Perform basic URL validation and normalization."""

#     normalized = value.strip()

#     if not re.match(r"^https?://", normalized, re.IGNORECASE):
#         return {
#             "valid": False,
#             "normalized_value": normalized,
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["URL must start with http:// or https://"],
#         }

#     if len(normalized) > 2048:
#         return {
#             "valid": False,
#             "normalized_value": normalized[:2048],
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["URL exceeds the maximum supported length"],
#         }

#     return {
#         "valid": True,
#         "normalized_value": normalized,
#         "classification": "url",
#         "risk_points": 10,
#         "reasons": ["Valid external URL"],
#     }


# def normalize_user(value: str) -> dict[str, Any]:
#     """Normalize a user principal name or account name."""

#     normalized = value.strip().lower()

#     if not normalized:
#         return {
#             "valid": False,
#             "normalized_value": normalized,
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["User value is empty"],
#         }

#     is_upn = bool(USER_PATTERN.fullmatch(normalized))

#     return {
#         "valid": True,
#         "normalized_value": normalized,
#         "classification": "user-principal-name" if is_upn else "account-name",
#         "risk_points": 0,
#         "reasons": [
#             "Valid user principal name" if is_upn else "Account name received"
#         ],
#     }


# def normalize_host(value: str) -> dict[str, Any]:
#     """Normalize a hostname."""

#     normalized = value.strip().lower().rstrip(".")

#     if not normalized or not HOST_PATTERN.fullmatch(normalized):
#         return {
#             "valid": False,
#             "normalized_value": normalized,
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["Invalid hostname"],
#         }

#     return {
#         "valid": True,
#         "normalized_value": normalized,
#         "classification": "hostname",
#         "risk_points": 0,
#         "reasons": ["Valid hostname"],
#     }


# def normalize_entity(entity: Any) -> dict[str, Any]:
#     """Validate and normalize one security entity."""

#     if not isinstance(entity, dict):
#         return {
#             "valid": False,
#             "type": "unknown",
#             "original_value": "",
#             "normalized_value": "",
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["Entity must be a JSON object"],
#         }

#     entity_type = clean_text(entity.get("type"), 50).lower()
#     original_value = clean_text(entity.get("value"), 2048)

#     if not entity_type:
#         return {
#             "valid": False,
#             "type": "unknown",
#             "original_value": original_value,
#             "normalized_value": original_value,
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["Entity type is missing"],
#         }

#     if entity_type not in SUPPORTED_ENTITY_TYPES:
#         return {
#             "valid": False,
#             "type": entity_type,
#             "original_value": original_value,
#             "normalized_value": original_value,
#             "classification": "unsupported",
#             "risk_points": 0,
#             "reasons": [f"Unsupported entity type: {entity_type}"],
#         }

#     if not original_value:
#         return {
#             "valid": False,
#             "type": entity_type,
#             "original_value": "",
#             "normalized_value": "",
#             "classification": "invalid",
#             "risk_points": 0,
#             "reasons": ["Entity value is missing"],
#         }

#     normalizers = {
#         "ip": normalize_ip,
#         "domain": normalize_domain,
#         "hash": normalize_hash,
#         "url": normalize_url,
#         "user": normalize_user,
#         "host": normalize_host,
#     }

#     result = normalizers.get(entity_type, lambda x: {"valid": False})(original_value)

#     result["type"] = entity_type
#     result["original_value"] = original_value

#     result["indicator_id"] = create_indicator_id(
#         entity_type=entity_type,
#         normalized_value=result["normalized_value"],
#     )

#     return result


# def normalize_and_deduplicate_entities(
#     entities: list[Any],
# ) -> tuple[list[dict[str, Any]], int]:
#     """Normalize entities and remove duplicate values."""

#     unique_entities: list[dict[str, Any]] = []
#     seen: set[tuple[str, str]] = set()
#     duplicate_count = 0

#     for raw_entity in entities:
#         normalized_entity = normalize_entity(raw_entity)

#         deduplication_key = (
#             normalized_entity["type"],
#             normalized_entity["normalized_value"],
#         )

#         if deduplication_key in seen:
#             duplicate_count += 1
#             continue

#         seen.add(deduplication_key)
#         unique_entities.append(normalized_entity)

#     return unique_entities, duplicate_count


# # --------------------------------------------------------------------------
# # Risk scoring
# # --------------------------------------------------------------------------

# def calculate_risk_score(
#     alert: dict[str, Any],
#     entities: list[dict[str, Any]],
# ) -> tuple[int, str, list[str]]:
#     """Calculate an explainable incident risk score."""

#     score = 0
#     reasons: list[str] = []

#     severity = alert["severity"]
#     severity_points = SEVERITY_SCORES[severity]

#     score += severity_points
#     reasons.append(
#         f"Incident severity '{severity}' contributed "
#         f"{severity_points:+d} points"
#     )

#     valid_entities = 0
#     invalid_entities = 0

#     for entity in entities:
#         points = int(entity.get("risk_points", 0))
#         score += points

#         if entity.get("valid"):
#             valid_entities += 1
#         else:
#             invalid_entities += 1

#         if points != 0:
#             entity_description = (
#                 f"{entity['type']} indicator "
#                 f"{entity['classification']} contributed {points:+d} points"
#             )
#             reasons.append(entity_description)

#     if valid_entities >= 5:
#         score += 10
#         reasons.append(
#             "Five or more valid indicators contributed +10 points"
#         )

#     if invalid_entities == len(entities):
#         score -= 20
#         reasons.append(
#             "No valid indicators were found, which contributed -20 points"
#         )

#     final_score = max(0, min(score, 100))

#     if final_score != score:
#         reasons.append(
#             f"Raw score {score} was limited to the 0 to 100 range"
#         )

#     if final_score >= 80:
#         priority = "critical"
#     elif final_score >= 60:
#         priority = "high"
#     elif final_score >= 30:
#         priority = "medium"
#     else:
#         priority = "low"

#     return final_score, priority, reasons


# def build_recommendations(
#     entities: list[dict[str, Any]],
#     priority: str,
# ) -> list[str]:
#     """Create investigation recommendations from the entity types."""

#     valid_types = {
#         entity["type"]
#         for entity in entities
#         if entity.get("valid")
#     }

#     recommendations: list[str] = []

#     if "ip" in valid_types:
#         recommendations.extend(
#             [
#                 "Search the IP addresses across network, DNS and authentication logs.",
#                 "Determine whether the IP addresses are common in the environment.",
#             ]
#         )

#     if "domain" in valid_types or "url" in valid_types:
#         recommendations.extend(
#             [
#                 "Review DNS queries and proxy activity for the domains and URLs.",
#                 "Identify all users and hosts that communicated with the destinations.",
#             ]
#         )

#     if "hash" in valid_types:
#         recommendations.extend(
#             [
#                 "Search file hashes across endpoint telemetry.",
#                 "Review process creation and file activity on matching hosts.",
#             ]
#         )

#     if "user" in valid_types:
#         recommendations.extend(
#             [
#                 "Review recent authentication activity for the affected users.",
#                 "Check MFA results, device compliance and privilege changes.",
#             ]
#         )

#     if "host" in valid_types:
#         recommendations.append(
#             "Review process, network and authentication activity on affected hosts."
#         )

#     if priority in {"critical", "high"}:
#         recommendations.append(
#             "Escalate the incident for priority analyst review."
#         )
#     else:
#         recommendations.append(
#             "Continue standard analyst triage before taking containment action."
#         )

#     # Preserve order while removing duplicate recommendations.
#     return list(dict.fromkeys(recommendations))


# # --------------------------------------------------------------------------
# # HTTP-triggered Azure Function
# # --------------------------------------------------------------------------
# app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
# @app.function_name(name="My_actual_function",methods=["GET", "POST"])
# @app.route(route="")

# def My_actual_function(req: func.HttpRequest) -> func.HttpResponse:
#     """
#     Receive, validate, enrich and score a security alert.

#     Endpoint:
#         POST /api/enrich-alert
#     """

#     start_time = time.perf_counter()

#     correlation_id = clean_text(
#         req.headers.get("X-Correlation-ID"),
#         maximum_length=100,
#     )

#     if not correlation_id:
#         correlation_id = str(uuid.uuid4())

#     logging.info(
#         "Security alert processing started. correlation_id=%s",
#         correlation_id,
#     )

#     try:
#         content_length = req.headers.get("Content-Length")

#         if content_length:
#             try:
#                 if int(content_length) > MAX_REQUEST_SIZE_BYTES:
#                     return create_error_response(
#                         status_code=413,
#                         error_code="REQUEST_TOO_LARGE",
#                         message="The request body exceeds the allowed size.",
#                         correlation_id=correlation_id,
#                     )
#             except ValueError:
#                 logging.warning(
#                     "Invalid Content-Length header. correlation_id=%s",
#                     correlation_id,
#                 )

#         try:
#             payload = req.get_json()
#         except ValueError:
#             return create_error_response(
#                 status_code=400,
#                 error_code="INVALID_JSON",
#                 message="The request body is not valid JSON.",
#                 correlation_id=correlation_id,
#             )

#         alert = validate_payload(payload)

#         entities, duplicate_count = normalize_and_deduplicate_entities(
#             alert["entities"]
#         )

#         risk_score, priority, scoring_reasons = calculate_risk_score(
#             alert=alert,
#             entities=entities,
#         )

#         recommendations = build_recommendations(
#             entities=entities,
#             priority=priority,
#         )

#         valid_entity_count = sum(
#             1 for entity in entities if entity.get("valid")
#         )

#         invalid_entity_count = len(entities) - valid_entity_count

#         duration_ms = round(
#             (time.perf_counter() - start_time) * 1000,
#             2,
#         )

#         response_body = {
#             "status": "success",
#             "incident": {
#                 "incident_id": alert["incident_id"],
#                 "title": alert["title"],
#                 "severity": alert["severity"],
#                 "host": alert["host"] or None,
#                 "user": alert["user"] or None,
#             },
#             "triage": {
#                 "risk_score": risk_score,
#                 "priority": priority,
#                 "scoring_reasons": scoring_reasons,
#                 "recommended_actions": recommendations,
#             },
#             "entity_summary": {
#                 "submitted": len(alert["entities"]),
#                 "unique": len(entities),
#                 "duplicates_removed": duplicate_count,
#                 "valid": valid_entity_count,
#                 "invalid": invalid_entity_count,
#             },
#             "entities": entities,
#             "correlation_id": correlation_id,
#             "processed_at_utc": utc_now(),
#             "processing_duration_ms": duration_ms,
#         }

#         logging.info(
#             (
#                 "Security alert processing completed. "
#                 "correlation_id=%s incident_id=%s "
#                 "risk_score=%s priority=%s duration_ms=%s"
#             ),
#             correlation_id,
#             alert["incident_id"],
#             risk_score,
#             priority,
#             duration_ms,
#         )

#         return json_response(
#             body=response_body,
#             status_code=200,
#             correlation_id=correlation_id,
#         )

#     except ValidationError as error:
#         logging.warning(
#             "Request validation failed. correlation_id=%s error=%s",
#             correlation_id,
#             str(error),
#         )

#         return create_error_response(
#             status_code=400,
#             error_code="VALIDATION_ERROR",
#             message=str(error),
#             correlation_id=correlation_id,
#         )

#     except Exception:
#         logging.exception(
#             "Unexpected processing error. correlation_id=%s",
#             correlation_id,
#         )

#         return create_error_response(
#             status_code=500,
#             error_code="INTERNAL_SERVER_ERROR",
#             message="An unexpected error occurred while processing the alert.",
#             correlation_id=correlation_id,
#         )