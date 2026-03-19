"""Run comprehensive scenario tests against the FastAPI server."""

import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
results = []


def req(method, path, body=None, label=""):
    url = BASE + path
    t0 = time.time()
    try:
        if body:
            data = json.dumps(body).encode()
            r = urllib.request.Request(url, data=data, method=method,
                                       headers={"Content-Type": "application/json"})
        else:
            r = urllib.request.Request(url, method=method)
        resp = urllib.request.urlopen(r, timeout=30)
        elapsed = (time.time() - t0) * 1000
        d = json.loads(resp.read())
        return {"label": label, "status": resp.status, "ms": round(elapsed), "data": d, "ok": True}
    except urllib.error.HTTPError as e:
        elapsed = (time.time() - t0) * 1000
        try:
            d = json.loads(e.read())
        except Exception:
            d = {"detail": str(e)}
        return {"label": label, "status": e.code, "ms": round(elapsed), "data": d, "ok": False}
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return {"label": label, "status": 0, "ms": round(elapsed), "data": {"error": str(e)}, "ok": False}


def get_rows(data):
    """Extract rows from response data regardless of format."""
    if isinstance(data, list):
        return data
    return data.get("results", data.get("data", []))


# ========================================
# SCENARIO TESTS
# ========================================

# S01: Health check
print("S01: Health check")
r = req("GET", "/health", label="Health check")
results.append(r)
h = r["data"]
print(f"  status={h['status']}  entity_links={h['tables']['entity_links']}  {r['ms']}ms")

# S02: Pipeline metrics
print("S02: Pipeline metrics (top 10)")
r = req("GET", "/metrics/pipeline?limit=10", label="Pipeline top 10")
results.append(r)
rows = get_rows(r["data"])
if rows:
    top = rows[0]
    print(f"  #1: {top.get('drug_name','?')}  score={top.get('pipeline_score','?')}  TA={top.get('therapeutic_area','-')}  mech={top.get('mechanism','-')}")
    print(f"  count={len(rows)}  {r['ms']}ms")

# S03: Trial success rates
print("S03: Trial success rates")
r = req("GET", "/metrics/success-rate?limit=10", label="Success rates")
results.append(r)
rows = get_rows(r["data"])
if rows:
    top = rows[0]
    print(f"  #1: {top.get('drug_name','?')}  rate={top.get('success_rate','?')}  {r['ms']}ms")

# S04: Evidence density
print("S04: Evidence density")
r = req("GET", "/metrics/evidence?limit=10", label="Evidence density")
results.append(r)
rows = get_rows(r["data"])
if rows:
    top = rows[0]
    print(f"  #1: {top.get('drug_name','?')}  articles={top.get('article_count','?')}  {r['ms']}ms")

# S05: Company portfolios
print("S05: Company portfolios")
r = req("GET", "/metrics/portfolio?limit=10", label="Company portfolios")
results.append(r)
rows = get_rows(r["data"])
if rows:
    for x in rows[:5]:
        print(f"  {x.get('company_name','?'):40s}  drugs={x.get('drug_count',0):>3}  trials={x.get('trial_count',0):>5}  TAs={x.get('ta_count',0)}")
    print(f"  {r['ms']}ms")

# S06: Competitive landscape
print("S06: Competitive landscape")
r = req("GET", "/metrics/competitive?limit=15", label="Competitive landscape")
results.append(r)
rows = get_rows(r["data"])
if rows:
    print(f"  {len(rows)} segments  {r['ms']}ms")
    for x in rows[:5]:
        print(f"  {str(x.get('mechanism_name','-')):40s}  TA={str(x.get('therapeutic_area','-')):25s}  drugs={x.get('drug_count',0):>3}  trials={x.get('trial_count',0):>5}")
else:
    print(f"  EMPTY  {r['ms']}ms")

# S07: GLP-1 obesity trial search
print("S07: GLP-1 obesity trial search")
r = req("POST", "/search", {"query": "GLP-1 receptor agonist obesity trials", "entity_types": ["trial"], "limit": 10}, label="GLP-1 obesity search")
results.append(r)
d = r["data"]
print(f"  results={d.get('total', len(d.get('results',[])))}/{len(d.get('results',[]))}  {r['ms']}ms")

# S08: Diabetes literature search
print("S08: Diabetes literature search")
r = req("POST", "/search", {"query": "type 2 diabetes treatment efficacy", "entity_types": ["literature"], "limit": 10}, label="Diabetes lit search")
results.append(r)
d = r["data"]
print(f"  results={d.get('total', len(d.get('results',[])))}/{len(d.get('results',[]))}  {r['ms']}ms")

# S09: Cross-type search
print("S09: Cross-type search (semaglutide)")
r = req("POST", "/search", {"query": "semaglutide", "limit": 15}, label="Cross-type semaglutide")
results.append(r)
d = r["data"]
type_dist = {}
for x in d.get("results", []):
    t = x.get("entity_type", "?")
    type_dist[t] = type_dist.get(t, 0) + 1
print(f"  total={d.get('total',0)}  types={type_dist}  {r['ms']}ms")

# S10: Filtered search
print("S10: Filtered search (Phase 3 + RECRUITING)")
r = req("POST", "/search", {"query": "diabetes", "entity_types": ["trial"], "filters": {"phase": "Phase 3", "status": "RECRUITING"}, "limit": 10}, label="Filtered Phase3 search")
results.append(r)
d = r["data"]
print(f"  results={d.get('total', len(d.get('results',[])))}/{len(d.get('results',[]))}  {r['ms']}ms")

# S11: Semaglutide graph neighborhood
print("S11: Semaglutide neighborhood")
r = req("GET", "/graph/neighborhood/drug/semaglutide", label="Semaglutide neighborhood")
results.append(r)
d = r["data"]
print(f"  nodes={d.get('node_count',0)}  edges={d.get('edge_count',0)}  {r['ms']}ms")

# S12: 2-hop traversal
print("S12: 2-hop traversal semaglutide")
r = req("GET", "/graph/traverse/drug/semaglutide?hops=2&max_nodes=50", label="2-hop traversal")
results.append(r)
d = r["data"]
print(f"  nodes={d.get('node_count',0)}  edges={d.get('edge_count',0)}  {r['ms']}ms")

# S13: Entity summary semaglutide
print("S13: Entity summary semaglutide")
r = req("GET", "/graph/summary/drug/semaglutide", label="Summary semaglutide")
results.append(r)
d = r["data"]
conn = d.get("connections_by_type", {})
print(f"  total_conn={d.get('total_connections',0)}  by_type={conn}  {r['ms']}ms")

# S14: Entity summary Novo Nordisk (use UUID to avoid slash in URL path)
print("S14: Entity summary Novo Nordisk")
# First resolve UUID
r0 = req("GET", "/entities/company?search=Novo%20Nordisk&limit=1", label="_resolve novo")
novo_id = "Novo Nordisk A/S"
if r0["ok"] and r0["data"].get("results"):
    novo_id = r0["data"]["results"][0].get("entity_id", novo_id)
r = req("GET", f"/graph/summary/company/{novo_id}", label="Summary Novo Nordisk")
results.append(r)
d = r["data"]
conn = d.get("connections_by_type", {})
print(f"  total_conn={d.get('total_connections',0)}  by_type={conn}  {r['ms']}ms")

# S15: Similar entities
print("S15: Similar entities to semaglutide")
r = req("GET", "/search/similar/drug/semaglutide?limit=5", label="Similar to semaglutide")
results.append(r)
d = r["data"]
for x in d.get("results", [])[:3]:
    print(f"  {x.get('label','?'):30s}  sim={x.get('similarity','?')}")
print(f"  {r['ms']}ms")

# S16: Entity listing - drugs
print("S16: Entity listing - drugs")
r = req("GET", "/entities/drug?limit=5", label="Drug listing")
results.append(r)
d = r["data"]
print(f"  count={d.get('count',0)}  type={d.get('entity_type','?')}  {r['ms']}ms")

# S17: Entity listing - companies
print("S17: Entity listing - companies")
r = req("GET", "/entities/company?limit=20", label="Company listing")
results.append(r)
d = r["data"]
print(f"  count={d.get('count',0)}  {r['ms']}ms")
for x in d.get("results", [])[:5]:
    print(f"    {x.get('label','?')}")

# S18: GraphRAG competitive landscape query
print("S18: GraphRAG competitive landscape query")
r = req("POST", "/query", {"question": "What is the competitive landscape for GLP-1 drugs in obesity?", "max_evidence": 15}, label="GraphRAG GLP-1 query")
results.append(r)
d = r["data"]
ev = d.get("evidence", [])
mc = d.get("metrics_context", {})
gc = d.get("graph_context", {})
print(f"  evidence={len(ev)}  metrics_keys={list(mc.keys()) if mc else []}  graph_entities={len(gc.get('neighbor_entities',[]))}  {r['ms']}ms")

# S19: Semaglutide dossier
print("S19: Semaglutide dossier")
r = req("POST", "/query/dossier", {"entity_id": "semaglutide", "entity_type": "drug"}, label="Semaglutide dossier")
results.append(r)
d = r["data"]
ev = d.get("evidence", [])
mc = d.get("metrics_context", {})
gc = d.get("graph_context", {})
print(f"  evidence={len(ev)}  metrics={list(mc.keys()) if mc else []}  graph_nodes={gc.get('total_nodes',0)}  {r['ms']}ms")

# S20: Tirzepatide dossier
print("S20: Tirzepatide dossier")
r = req("POST", "/query/dossier", {"entity_id": "Tirzepatide", "entity_type": "drug"}, label="Tirzepatide dossier")
results.append(r)
d = r["data"]
ev = d.get("evidence", [])
mc = d.get("metrics_context", {})
print(f"  evidence={len(ev)}  metrics={list(mc.keys()) if mc else []}  {r['ms']}ms")

# S21: Novo Nordisk company dossier
print("S21: Novo Nordisk company dossier")
r = req("POST", "/query/dossier", {"entity_id": "Novo Nordisk A/S", "entity_type": "company"}, label="Novo Nordisk dossier")
results.append(r)
d = r["data"]
ev = d.get("evidence", [])
mc = d.get("metrics_context", {})
gc = d.get("graph_context", {})
print(f"  evidence={len(ev)}  metrics={list(mc.keys()) if mc else []}  graph_nodes={gc.get('total_nodes',0)}  {r['ms']}ms")

# S22: Compare semaglutide vs tirzepatide
print("S22: Compare semaglutide vs tirzepatide")
r = req("POST", "/query/compare", {"entity_ids": ["semaglutide", "Tirzepatide"], "entity_type": "drug"}, label="Sema vs Tirz compare")
results.append(r)
d = r["data"]
ents = d.get("entities", [])
metrics_cmp = d.get("metrics_comparison", {})
shared = d.get("shared_connections", [])
print(f"  entities={len(ents)}  shared_connections={len(shared)}  metrics_keys={list(metrics_cmp.keys())}  {r['ms']}ms")
for e in ents:
    print(f"    {e.get('label','?')}: connections={e.get('total_connections',0)}  by_type={e.get('connections_by_type',{})}")

# S23: Graph path finding (use max_hops=2 to avoid CTE explosion)
print("S23: Graph path semaglutide -> Novo Nordisk")
r = req("GET", f"/graph/path?source_id=semaglutide&source_type=drug&target_id={novo_id}&target_type=company&max_hops=2", label="Path sema->novo")
results.append(r)
d = r["data"]
path = d.get("path", []) or []
print(f"  hops={d.get('hops','?')}  path_len={len(path)}  {r['ms']}ms")
for step in path[:3]:
    print(f"    {step.get('source','?')} --[{step.get('type','?')}]--> {step.get('target','?')}")

# S24: 404 - nonexistent entity
print("S24: 404 - nonexistent entity")
r = req("GET", "/graph/summary/drug/NONEXISTENT_DRUG_XYZ", label="404 test")
results.append(r)
print(f"  status={r['status']}  {r['ms']}ms")

# S25: Empty search results
print("S25: Empty search results")
r = req("POST", "/search", {"query": "xyznonexistent123", "limit": 5}, label="Empty search")
results.append(r)
d = r["data"]
print(f"  results={d.get('total',0)}  status={r['status']}  {r['ms']}ms")

# S26: Invalid entity type
print("S26: Invalid entity type")
r = req("GET", "/entities/invalid_type", label="Invalid entity type")
results.append(r)
print(f"  status={r['status']}  {r['ms']}ms")

# ========================================
# SUMMARY
# ========================================

print()
print("=" * 60)
print("SCENARIO TEST SUMMARY")
print("=" * 60)

edge_case_labels = {"404 test", "Invalid entity type", "Empty search"}
passed = 0
for r in results:
    if r["ok"]:
        passed += 1
    elif r["label"] in edge_case_labels and r["status"] in [404, 400, 422, 200]:
        passed += 1
    elif r["label"] == "Empty search" and r["ok"]:
        passed += 1

total = len(results)
latencies = [r["ms"] for r in results]
ok_latencies = [r["ms"] for r in results if r["ok"]]

print(f"  Total:   {total}")
print(f"  Passed:  {passed}")
print(f"  Failed:  {total - passed}")
if ok_latencies:
    print(f"  Avg latency (success): {sum(ok_latencies)//len(ok_latencies)}ms")
    print(f"  Max latency: {max(ok_latencies)}ms")
    print(f"  Min latency: {min(ok_latencies)}ms")
    p95 = sorted(ok_latencies)[int(len(ok_latencies)*0.95)]
    print(f"  p95 latency: {p95}ms")

print()
print(f"  {'#':>3}  {'Status':>6}  {'Result':>6}  {'Latency':>7}  Label")
print(f"  {'---':>3}  {'------':>6}  {'------':>6}  {'-------':>7}  -----")
for i, r in enumerate(results):
    is_edge = r["label"] in edge_case_labels
    if r["ok"]:
        icon = "PASS"
    elif is_edge and r["status"] in [404, 400, 422, 200]:
        icon = "PASS"
    else:
        icon = "FAIL"
    print(f"  {i+1:>3}  {r['status']:>6}  {icon:>6}  {r['ms']:>5}ms  {r['label']}")
