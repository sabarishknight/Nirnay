"""Thin REST clients for BigQuery and Gemini on Vertex AI.

Plain HTTPS with an OAuth token from the Cloud Run metadata server (or GOOGLE_OAUTH_ACCESS_TOKEN /
`gcloud auth print-access-token` when run on a laptop). Keeping to REST means the container has
three dependencies and the calls are easy to show on the architecture page.
"""
import base64, json, os, subprocess, threading, time, urllib.request, urllib.error

PROJECT = os.environ.get("GCP_PROJECT", "")
BQ_LOCATION = os.environ.get("BQ_LOCATION", "asia-south1")
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")
GEMINI_MODELS = [m.strip() for m in os.environ.get("GEMINI_MODEL", "gemini-2.5-flash,gemini-3-flash,gemini-3.5-flash,gemini-flash-latest,gemini-3-flash-preview").split(",") if m.strip()]

_tok = {"value": None, "exp": 0}
_lock = threading.Lock()


def token():
    with _lock:
        if _tok["value"] and time.time() < _tok["exp"] - 60:
            return _tok["value"]
        if os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN"):
            _tok.update(value=os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"], exp=time.time() + 3000)
            return _tok["value"]
        try:
            req = urllib.request.Request("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token", headers={"Metadata-Flavor": "Google"})
            d = json.loads(urllib.request.urlopen(req, timeout=3).read())
            _tok.update(value=d["access_token"], exp=time.time() + d.get("expires_in", 3000))
        except Exception:
            out = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, timeout=20)
            _tok.update(value=out.stdout.strip(), exp=time.time() + 3000)
        return _tok["value"]


def _call(url, body=None, timeout=30, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} {e.read()[:400].decode(errors='ignore')}")


# ------------------------------------------------------------------ BigQuery
def _bq_type(v):
    if isinstance(v, bool):
        return "BOOL"
    if isinstance(v, int):
        return "INT64"
    if isinstance(v, float):
        return "FLOAT64"
    return "STRING"


def _conv(v, ty):
    if v is None:
        return None
    if ty in ("INTEGER", "INT64"):
        return int(v)
    if ty in ("FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
        return float(v)
    if ty in ("BOOLEAN", "BOOL"):
        return v == "true"
    return v


def bq_query(sql, params=None, timeout_ms=30000):
    body = {"query": sql, "useLegacySql": False, "location": BQ_LOCATION, "timeoutMs": timeout_ms,
            "defaultDataset": {"projectId": PROJECT, "datasetId": "lending_gold"}}
    if params:
        body["parameterMode"] = "NAMED"
        body["queryParameters"] = [{"name": k, "parameterType": {"type": _bq_type(v)}, "parameterValue": {"value": str(v).lower() if isinstance(v, bool) else str(v)}} for k, v in params.items()]
    t0 = time.time()
    r = _call(f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/queries", body, timeout=timeout_ms / 1000 + 10)
    job = r.get("jobReference", {})
    while not r.get("jobComplete", False):
        r = _call(f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/queries/{job['jobId']}?location={BQ_LOCATION}&timeoutMs=10000")
    fields = r.get("schema", {}).get("fields", [])
    rows = [{f["name"]: _conv(c.get("v"), f["type"]) for f, c in zip(fields, row["f"])} for row in r.get("rows", [])]
    meta = dict(engine="BigQuery", job_id=job.get("jobId"), ms=int((time.time() - t0) * 1000), bytes_processed=int(r.get("totalBytesProcessed", 0) or 0),
                cache_hit=r.get("cacheHit", False), location=BQ_LOCATION)
    return rows, meta


def bq_insert(dataset, table, rows):
    body = {"rows": [{"json": r} for r in rows], "skipInvalidRows": True}
    return _call(f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/datasets/{dataset}/tables/{table}/insertAll", body, timeout=15)


# ------------------------------------------------------------------ Gemini on Vertex AI
_working_model = {"name": None}


def gemini(parts, system=None, json_mode=False, temperature=0.2, timeout=45):
    """parts: list of str or (mime, bytes). Returns (text, model_used)."""
    contents = [{"role": "user", "parts": [{"text": p} if isinstance(p, str) else {"inlineData": {"mimeType": p[0], "data": base64.b64encode(p[1]).decode()}} for p in parts]}]
    body = {"contents": contents, "generationConfig": {"temperature": temperature, "maxOutputTokens": 8192}}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    host = "aiplatform.googleapis.com" if GEMINI_LOCATION == "global" else f"{GEMINI_LOCATION}-aiplatform.googleapis.com"
    models = [_working_model["name"]] if _working_model["name"] else GEMINI_MODELS
    last = None
    for m in models:
        try:
            r = _call(f"https://{host}/v1/projects/{PROJECT}/locations/{GEMINI_LOCATION}/publishers/google/models/{m}:generateContent", body, timeout=timeout)
            text = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"] if not p.get("thought"))
            _working_model["name"] = m
            return text, m
        except Exception as e:  # try the next model id
            last = e
    raise RuntimeError(f"Gemini unavailable: {last}")
