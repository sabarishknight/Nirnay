"""Nirnay: HTTP API and pages. Starlette + uvicorn; one container on Cloud Run."""
import asyncio, datetime as dt, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse, FileResponse, Response
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import agent, gcp, mocks, store
from policy_pack import CLAUSES, POLICY_EVENTS, PARAMS, emi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
DECISIONS = {}   # application_id -> latest officer decision (also written to BigQuery)
PAGES = {"": "index.html", "demo": "demo.html", "applicant": "applicant.html", "head": "head.html", "story": "story.html", "architecture": "architecture.html",
         "research": "research.html", "faq": "faq.html", "about": "about.html", "contact": "contact.html", "ai-log": "ai-log.html", "policy": "policy.html"}


def J(data, status=200):
    return Response(json.dumps(data, default=str), status_code=status, media_type="application/json")


async def page(request):
    name = request.path_params.get("name", "")
    f = PAGES.get(name)
    if not f:
        return Response("Not found", status_code=404)
    return FileResponse(os.path.join(WEB, f), headers={"Cache-Control": "no-cache"})


async def meta(request):
    return J(dict(data_engine="BigQuery" if store.MODE == "bigquery" else "SQLite stand-in", project=gcp.PROJECT or None, bq_location=gcp.BQ_LOCATION if store.MODE == "bigquery" else None,
                  ai="Gemini on Vertex AI" if agent.AI_ENABLED else "Offline (pre-extracted values, template note)", ai_model=gcp._working_model["name"] or (gcp.GEMINI_MODELS[0] if agent.AI_ENABLED else None),
                  repo_rate=PARAMS["repo_rate"]))


async def queue(request):
    rows, m = await run_in_threadpool(store.query, "queue")
    for r in rows:
        d = DECISIONS.get(r["application_id"])
        r["officer_decision"] = d["officer_decision"] if d else None
    return J(dict(rows=rows, meta=m))


def _case(app_id):
    app, m1 = store.one("application", app_id=app_id)
    if not app:
        return None
    prop, _ = store.one("property", app_id=app_id)
    feat, m2 = store.one("features", app_id=app_id)
    docs = agent.HERO_DOCS.get(app_id, [])
    idx, _ = store.query("documents_index", app_id=app_id)
    last = next((r.result for r in reversed(list(agent.RUNS.values())) if r.app_id == app_id and r.result), None)
    return dict(app=app, property=prop, features=feat, documents=[dict(doc_type=d["doc_type"], file=d["file"]) for d in docs], documents_index=idx,
                last_result=last, decision=DECISIONS.get(app_id), sql=dict(application=m1["sql"], features=m2["sql"]), engine=m1["engine"])


async def case(request):
    c = await run_in_threadpool(_case, request.path_params["app_id"])
    return J(c) if c else J({"error": "No such application"}, 404)


async def run_start(request):
    r = agent.start(request.path_params["app_id"])
    return J(dict(run_id=r.run_id))


async def run_events(request):
    run = agent.RUNS.get(request.path_params["run_id"])
    if not run:
        return J({"error": "Unknown run"}, 404)

    async def gen():
        i = 0
        while True:
            evs = run.events[i:]
            for e in evs:
                yield f"data: {json.dumps(e, default=str)}\n\n"
            i += len(evs)
            if run.done and i >= len(run.events):
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.25)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def kfs(app, decision):
    """Key Facts Statement numbers: APR as an IRR including fees (RBI KFS directions)."""
    amount, n, rate = decision["loan_amount"], decision["tenor_months"], decision["rate"]
    e = emi(amount, rate, n)
    proc = min(0.0035 * amount, 10000) * 1.18
    third = 5000 + 3500 + 100 * 1.18   # legal, valuation, CERSAI at actuals
    net = amount - proc - third
    lo, hi = 0.0, 0.05
    for _ in range(80):
        mid = (lo + hi) / 2
        pv = e * (1 - (1 + mid) ** -n) / mid
        lo, hi = (mid, hi) if pv > net else (lo, mid)
    apr = mid * 12 * 100
    return dict(loan_amount=amount, tenor_months=n, interest_type="Floating, linked to RBI repo rate", benchmark=f"Repo {PARAMS['repo_rate']:.2f}%", spread=round(rate - PARAMS["repo_rate"], 2),
                rate=rate, emi=round(e), instalments=n, processing_fee=round(proc), third_party_charges=round(third), net_disbursed=round(net), total_interest=round(e * n - amount),
                apr=round(apr, 2), prepayment="Nil on floating rate loans to individuals", cooling_off="3 working days to accept these terms", grievance="Nodal officer, Retail Lending (synthetic contact)")


async def decision(request):
    b = await request.json()
    app_id, dec, reason = b["application_id"], b["decision"], (b.get("reason") or "").strip()
    run = agent.RUNS.get(b.get("run_id") or "")
    rec = run.result["recommendation"] if run and run.result else None
    agent_dec = rec["decision"] if rec else "None"
    as_authority = bool(b.get("as_authority"))
    override = dec != agent_dec and not (as_authority and agent_dec == "Refer")
    if override and not reason:
        return J({"error": "A reason is required when your decision differs from the agent's recommendation."}, 400)
    if dec == "Decline" and not reason:
        return J({"error": "A decline needs reasons that will be sent to the applicant in writing."}, 400)
    row = dict(application_id=app_id, decided_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), agent_recommendation=agent_dec, officer_decision=dec,
               override=int(override), override_reason=reason, decided_by=(rec["authority"] + " (demo)") if as_authority and rec else (b.get("officer") or "Credit officer (demo)"), run_id=b.get("run_id") or "")
    await run_in_threadpool(store.insert, "lending_gold", "officer_decisions", [row])
    out = dict(row)
    prev = DECISIONS.get(app_id)
    if as_authority and prev:
        out["referred_by"] = prev
    if dec == "Sanction" and rec:
        out["kfs"] = kfs(None, rec)
        out["authority"] = rec["authority"]
    if b.get("note"):
        out["note"] = b["note"]
    DECISIONS[app_id] = out
    return J(out)


async def applicant(request):
    app_id = request.path_params["app_id"]
    c = await run_in_threadpool(_case, app_id)
    if not c:
        return J({"error": "No such application"}, 404)
    a = c["app"]
    stages = ["Application received", "Documents and KYC", "Credit check", "Property legal and valuation", "Sanction", "Agreement and mortgage", "Disbursement"]
    pos = {"Login & KYC": 1, "Credit appraisal": 2, "Legal & technical": 3, "Sanction": 4, "Documentation": 5, "Disbursed": 6}.get(a["stage"], 2)
    d = c["decision"]
    msg = None
    if d:
        if d["officer_decision"] == "Sanction":
            pos, msg = 5, "Your loan is sanctioned. Review the Key Facts Statement below; you have 3 working days to accept."
        elif d["officer_decision"] == "Hold":
            msg = "We need one more check before we can decide. Your relationship manager will contact you with what is needed."
        elif d["officer_decision"] == "Refer":
            msg = "Your file has gone to a senior credit officer for approval. No action is needed from you."
        elif d["officer_decision"] == "Decline":
            msg = "We are unable to offer this loan. A letter with the reasons will be sent to you."
    return J(dict(application_id=app_id, name=a["full_name"], loan_amount=a["loan_amount"], tenor_months=a["tenor_months"], property=c["property"]["address"],
                  stages=stages, current=pos, message=msg, kfs=(d or {}).get("kfs"), documents=[x["doc_type"] for x in c["documents_index"]],
                  consents=[dict(what="Credit bureau check (CIBIL)", given=a["received_date"]), dict(what="Account Aggregator: bank statements, 6-12 months", given=a["received_date"]),
                            dict(what="Aadhaar e-KYC", given=a["received_date"])]))


async def dashboard(request):
    def work():
        out = {}
        for k in ("dash_pipeline", "dash_screening", "dash_tat", "dash_overrides", "dash_override_patterns", "dash_channel", "dash_live_decisions"):
            rows, m = store.query(k)
            out[k] = dict(rows=rows, sql=m["sql"], ms=m["ms"], bytes=m.get("bytes_processed"))
        return out
    return J(await run_in_threadpool(work))


async def policy_events(request):
    return J(dict(events=[{k: v for k, v in e.items() if k not in ("before", "after")} for e in POLICY_EVENTS], params=PARAMS))


async def policy_watch(request):
    b = await request.json()
    ev = next(e for e in POLICY_EVENTS if e["event_id"] == b["event_id"])
    p = dict(repo_before=PARAMS["repo_rate"], repo_after=PARAMS["repo_rate"], cap_low_before=50.0, cap_low_after=50.0, floor_before=700, floor_after=700)
    if "repo_rate" in ev["before"]:
        p.update(repo_before=ev["before"]["repo_rate"], repo_after=ev["after"]["repo_rate"])
    if "foir_cap" in ev["before"]:
        p.update(cap_low_before=ev["before"]["foir_cap"][0][1], cap_low_after=ev["after"]["foir_cap"][0][1])
    if "score_floor" in ev["before"]:
        p.update(floor_before=ev["before"]["score_floor"], floor_after=ev["after"]["score_floor"])
    rows, m = await run_in_threadpool(store.query, "rescreen", **p)
    changed = [r for r in rows if r["status_before"] != r["status_after"]]
    exposure = sum(r["loan_amount"] for r in changed)
    summary = (f"{len(rows)} in-flight files re-screened in {m['ms']} ms. {len(changed)} move from within policy to outside it, worth Rs {exposure / 1e7:,.2f} crore. "
               "Each one is flagged to its credit officer with the new figures; none is changed automatically.")
    return J(dict(event={k: v for k, v in ev.items() if k not in ("before", "after")}, params=p, screened=len(rows), changed=changed[:40], changed_count=len(changed),
                  exposure=exposure, summary=summary, sql=m["sql"], engine=m["engine"], ms=m["ms"], bytes=m.get("bytes_processed")))


async def ask(request):
    b = await request.json()
    q = (b.get("question") or "").strip()[:500]
    if not q:
        return J({"error": "Type a question about the credit policy."}, 400)
    return J(await run_in_threadpool(agent.ask_policy, q))


async def clauses(request):
    return J(dict(clauses=CLAUSES))


async def mock_api(request):
    svc, key = request.path_params["service"], request.path_params["key"]
    if svc not in mocks.SERVICES:
        return J({"error": "Unknown service"}, 404)
    return J(await run_in_threadpool(mocks.call, svc, key, 0.3))


async def health(request):
    return J({"ok": True})


routes = [
    Route("/api/meta", meta), Route("/api/queue", queue), Route("/api/case/{app_id}", case), Route("/api/run/{app_id}", run_start, methods=["POST"]),
    Route("/api/run/{run_id}/events", run_events), Route("/api/decision", decision, methods=["POST"]), Route("/api/applicant/{app_id}", applicant),
    Route("/api/dashboard", dashboard), Route("/api/policy/events", policy_events), Route("/api/policy/watch", policy_watch, methods=["POST"]),
    Route("/api/ask", ask, methods=["POST"]), Route("/api/policy/clauses", clauses), Route("/mock/{service}/{key}", mock_api), Route("/healthz", health),
    Mount("/static", StaticFiles(directory=os.path.join(WEB, "static")), name="static"),
    Route("/", page), Route("/{name}", page),
]
app = Starlette(routes=routes)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
