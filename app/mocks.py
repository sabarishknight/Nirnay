"""Mock external services. Each behaves like the real one in shape, latency and per-call cost.

Real counterparts: TransUnion CIBIL bureau, CERSAI central registry, NSDL/Protean PAN verification
with CKYCR lookup, an RBI-licensed Account Aggregator (via Sahamati network), EPFO UAN passbook,
GSTN return status. No real system is contacted; data comes from world/*.json.
"""
import json, os, random, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_W = {}


def world(name):
    if name not in _W:
        _W[name] = json.load(open(os.path.join(ROOT, "world", name + ".json")))
    return _W[name]


# service: (display name, what the bank would integrate with, latency range ms, cost per call INR - illustrative)
SERVICES = {
    "kyc": ("PAN + CKYC verification", "NSDL / Protean PAN API, CKYCR", (250, 500), 3.0),
    "bureau": ("Credit bureau report", "TransUnion CIBIL (consumer report)", (700, 1200), 25.0),
    "cersai": ("CERSAI search", "Central Registry (CERSAI) asset-based search", (500, 900), 10.0),
    "aa": ("Account Aggregator fetch", "RBI-licensed AA (Sahamati network), consent-based", (900, 1500), 12.0),
    "epfo": ("EPFO employment check", "EPFO UAN / establishment lookup", (300, 600), 2.0),
    "gst": ("GST return status", "GSTN via GST Suvidha Provider", (300, 600), 2.0),
}


def call(service, key, speed=1.0):
    name, provider, (lo, hi), cost = SERVICES[service]
    latency = random.randint(lo, hi)
    time.sleep(latency / 1000 * speed)
    data = world(service).get(key)
    if data is None:
        resp = {"status": "NO_RECORD", "key": key}
    elif service == "bureau":
        resp = {"status": "OK", "report": data}
    elif service == "cersai":
        resp = {"status": "OK", "search_ref": data["search_ref"], "property_id": key, "subsisting_charges": data["charges"]}
    else:
        resp = {"status": "OK", **{("registration_status" if k == "status" else k): v for k, v in data.items()}}
    return dict(service=service, name=name, provider=provider, key=key, latency_ms=latency, cost_inr=cost, response=resp)
