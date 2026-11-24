"""Render change-map data into one self-contained HTML page (data inline; d3 from cdnjs)."""

from __future__ import annotations

import html
import json
from pathlib import Path

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · change map</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#d8d8dc;--hit:#d23b2f;--impact:#e8902a;
--co:#3a6fd8;--chip:#efefef;--sel:#fff3e8}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--panel:#1d1d20;--ink:#ececee;--muted:#9a9aa2;--line:#34343a;
--chip:#2a2a2e;--sel:#3a2a1c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,
"Segoe UI",sans-serif;height:100vh;display:grid;grid-template-columns:1fr 400px;grid-template-rows:auto 1fr}
header{grid-column:1/3;padding:10px 16px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;
flex-wrap:wrap}header h1{font-size:16px;margin:0}header .s{color:var(--muted);font-size:12px}
.legend{display:flex;gap:12px;font-size:12px;color:var(--muted);margin-left:auto;flex-wrap:wrap}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:-1px}
#graph{position:relative;overflow:hidden}svg{width:100%;height:100%}
aside{border-left:1px solid var(--line);background:var(--panel);overflow:auto;padding:12px 14px}
input{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
.tabs{display:flex;gap:6px;margin:10px 0}.tabs button{flex:1;padding:6px;border:1px solid var(--line);
background:var(--bg);color:var(--ink);border-radius:6px;cursor:pointer}.tabs button.on{background:var(--ink);
color:var(--bg)}.t{padding:7px 8px;border-radius:6px;cursor:pointer;border:1px solid transparent}
.t:hover{border-color:var(--line)}.t.on{background:var(--sel)}.t .k{font-weight:600;font-size:12px}
.t .m{color:var(--muted);font-size:12px}h2{font-size:15px;margin:4px 0 6px}h3{font-size:12px;margin:12px 0 4px;
color:var(--muted);text-transform:uppercase;letter-spacing:.04em}code{font-size:12px;word-break:break-all}
.chip{display:inline-block;background:var(--chip);border-radius:4px;padding:0 5px;margin:1px 2px;font-size:11px;
color:var(--muted)}ul{margin:0;padding-left:18px}li{margin:2px 0}a{color:var(--co)}
.node text{font-size:11px;fill:var(--ink);pointer-events:none}.dim{opacity:.18}
@media (max-width:900px){body{grid-template-columns:1fr;grid-template-rows:auto 55vh auto}aside{border-left:0;
border-top:1px solid var(--line)}}
</style></head><body>
<header><h1>__TITLE__</h1><span class="s" id="stats"></span>
<div class="legend"><span><i style="background:var(--hit)"></i>ticket lands here</span>
<span><i style="background:var(--impact)"></i>impact area</span><span>── imports</span>
<span style="color:var(--co)">- - changed together</span><span>size = past tickets, red = bug share</span></div></header>
<div id="graph"><svg></svg></div>
<aside><input id="q" placeholder="Search tickets or modules">
<div class="tabs"><button id="tOpen" class="on">Open tickets</button><button id="tCol">Overlaps</button><button id="tMod">Modules</button></div>
<div id="list"></div><div id="detail"></div></aside>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>
const D = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const byId = Object.fromEntries(D.modules.map(m => [m.id, m]));
D.collisions = D.collisions || [];
const nFile = D.collisions.filter(c => c.level === "file").length;
document.getElementById("stats").textContent =
  `${D.modules.length} modules · ${D.history_tickets} past tickets · ${D.open.length} open tickets · ${nFile} file collisions`;
const svg = d3.select("svg"), g = svg.append("g");
svg.call(d3.zoom().scaleExtent([.2, 4]).on("zoom", e => g.attr("transform", e.transform)));
svg.append("defs").append("marker").attr("id","arr").attr("viewBox","0 -4 8 8").attr("refX",8).attr("markerWidth",6)
  .attr("markerHeight",6).attr("orient","auto").append("path").attr("d","M0,-4L8,0L0,4").attr("fill","var(--muted)");
const nodes = D.modules.filter(m => m.tickets || m.files > 3).map(m => ({...m}));
const ok = new Set(nodes.map(n => n.id));
const links = D.imports.filter(l => ok.has(l.source) && ok.has(l.target)).map(l => ({...l, kind:"imp"}))
  .concat(D.cochange.filter(c => ok.has(c.a) && ok.has(c.b)).map(c => ({source:c.a, target:c.b, n:c.n, kind:"co"})));
const r = d => 5 + Math.sqrt(d.tickets) * 2.2;
const color = d3.scaleLinear().domain([0, .6]).range(["#9aa3ad", "#d23b2f"]).clamp(true);
const link = g.append("g").selectAll("line").data(links).join("line")
  .attr("stroke", d => d.kind === "co" ? "var(--co)" : "var(--muted)")
  .attr("stroke-dasharray", d => d.kind === "co" ? "4 3" : null)
  .attr("stroke-opacity", d => d.kind === "co" ? .55 : Math.min(.6, .12 + Math.log1p(d.n) / 10))
  .attr("marker-end", d => d.kind === "imp" ? "url(#arr)" : null);
const node = g.append("g").selectAll("g").data(nodes).join("g").attr("class","node").style("cursor","pointer")
  .on("click", (e, d) => showModule(d.id));
node.append("circle").attr("r", r).attr("fill", d => color(d.bug_share)).attr("stroke","var(--panel)").attr("stroke-width",1.5);
node.append("text").attr("dy", d => r(d) + 11).attr("text-anchor","middle").text(d => d.id.split("/").pop());
const W = () => document.getElementById("graph").clientWidth, H = () => document.getElementById("graph").clientHeight;
const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d => d.id).distance(d => d.kind === "co" ? 90 : 120).strength(.25))
  .force("charge", d3.forceManyBody().strength(-260)).force("center", d3.forceCenter(W()/2, H()/2))
  .force("collide", d3.forceCollide(d => r(d) + 14))
  .on("tick", () => {
    link.each(function(d){ const dx=d.target.x-d.source.x, dy=d.target.y-d.source.y, L=Math.hypot(dx,dy)||1,
      rt=r(d.target)+3; d3.select(this).attr("x1",d.source.x).attr("y1",d.source.y)
      .attr("x2",d.target.x-dx/L*(d.kind==="imp"?rt:0)).attr("y2",d.target.y-dy/L*(d.kind==="imp"?rt:0)); });
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });
node.call(d3.drag().on("start",(e,d)=>{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y})
  .on("drag",(e,d)=>{d.fx=e.x;d.fy=e.y}).on("end",(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null}));

function highlight(hit, impact){
  const lit = new Set([...hit, ...impact]);
  node.classed("dim", d => lit.size && !lit.has(d.id));
  node.select("circle").attr("stroke", d => hit.includes(d.id) ? "var(--hit)" : impact.includes(d.id) ? "var(--impact)" : "var(--panel)")
    .attr("stroke-width", d => lit.has(d.id) ? 4 : 1.5);
  link.classed("dim", d => lit.size && !(lit.has(d.source.id) && lit.has(d.target.id)));
}
let tab = "open";
function renderList(){
  const q = document.getElementById("q").value.toLowerCase(), el = document.getElementById("list");
  if (tab === "open") {
    el.innerHTML = D.open.filter(t => [t.key, t.title, t.assignee, t.status, t.epic].join(" ").toLowerCase().includes(q)).map(t =>
      `<div class="t" data-k="${esc(t.key)}"><div class="k"><span class="chip" title="priority score" style="color:var(--ink);font-weight:600">${t.priority_score ?? "-"}</span>${esc(t.key)} <span class="chip">${esc(t.type)}</span>${t.status ? `<span class="chip">${esc(t.status)}</span>` : ""}${(t.overlaps||[]).some(c => c.level === "file") ? `<span class="chip" style="color:var(--hit)">collides</span>` : ""}${t.days_left != null ? `<span class="chip" style="color:${t.days_left < 0 ? "var(--hit)" : t.days_left <= 7 ? "var(--impact)" : "var(--muted)"}">${t.days_left < 0 ? "overdue " + (-t.days_left) + "d" : t.days_left + "d left"}</span>` : ""}</div>
       <div>${esc(t.title)}</div><div class="m">→ ${t.modules.map(esc).join(", ")}${t.assignee ? " · " + esc(t.assignee) : ""}</div></div>`).join("") || "<p class=m>No open tickets loaded.</p>";
    el.querySelectorAll(".t").forEach(x => x.onclick = () => showTicket(x.dataset.k));
  } else if (tab === "col") {
    // same-module overlaps are common and noisy; only same-file collisions are listed unless searched for
    const rows = D.collisions.filter(c => (q ? true : c.level === "file") &&
      (c.a + c.b + c.files.join(" ") + c.modules.join(" ")).toLowerCase().includes(q));
    el.innerHTML = rows.map(c => `<div class="t" data-k="${esc(c.a)}"><div class="k">${esc(c.a)} ↔ ${esc(c.b)}
       <span class="chip" style="color:${c.level === "file" ? "var(--hit)" : "var(--impact)"}">${c.level === "file" ? "same file" : "same module"}</span>
       ${c.different_owners ? `<span class="chip">different assignees</span>` : ""}</div>
       <div class="m">${(c.files.length ? c.files : c.modules).map(esc).join(", ")}</div></div>`).join("") || "<p class=m>No overlapping open tickets.</p>";
    el.querySelectorAll(".t").forEach(x => x.onclick = () => showTicket(x.dataset.k));
  } else {
    el.innerHTML = [...D.modules].sort((a,b)=>b.tickets-a.tickets).filter(m => m.id.toLowerCase().includes(q)).map(m =>
      `<div class="t" data-m="${esc(m.id)}"><div class="k">${esc(m.id)}</div><div class="m">${m.tickets} tickets · ${Math.round(m.bug_share*100)}% bugs · ${m.files} files</div></div>`).join("");
    el.querySelectorAll(".t").forEach(x => x.onclick = () => showModule(x.dataset.m));
  }
}
function showTicket(k){
  const t = D.open.find(x => x.key === k); if (!t) return;
  document.querySelectorAll(".t").forEach(x => x.classList.toggle("on", x.dataset.k === k));
  highlight(t.modules, t.impact);
  document.getElementById("detail").innerHTML = `<hr><h2>${t.url ? `<a href="${esc(t.url)}" target="_blank">${esc(t.key)}</a>` : esc(t.key)} ${esc(t.title)}</h2>
   <div class="m">${[t.type, t.status, t.priority, t.assignee, t.epic ? "epic " + t.epic : "", (t.fix_versions||[]).join(", ")].filter(Boolean).map(esc).join(" · ")}</div>
   <div class="m">${[t.due ? "due " + t.due : "", !t.due && t.release_date ? "release " + t.release_date : "", t.sprint ? "sprint " + t.sprint : "", t.points != null ? t.points + " pts" : "", t.created ? "created " + t.created : "", t.updated ? "updated " + t.updated : ""].filter(Boolean).map(esc).join(" · ")}</div>
   ${t.priority_score != null ? `<h3>Priority ${t.priority_score}/100</h3><ul>${(t.priority_reasons||[]).map(r => `<li>${esc(r)}</li>`).join("") || "<li class=m>no strong signal</li>"}</ul>` : ""}
   ${(t.overlaps||[]).length ? `<h3>Overlaps with open tickets</h3><ul>${t.overlaps.map(c => { const o = c.a === t.key ? c.b : c.a;
     return `<li><a href="#" data-k="${esc(o)}" class="ov">${esc(o)}</a> · ${c.level === "file" ? "same file: " + c.files.map(esc).join(", ") : "same module: " + c.modules.map(esc).join(", ")}${c.different_owners ? " · different assignees" : ""}</li>`; }).join("")}</ul>` : ""}
   ${(t.links||[]).length ? `<h3>Jira links</h3>${t.links.map(l => `<span class=chip>${esc(l.rel)} ${esc(l.key)}</span>`).join("")}` : ""}
   <h3>Lands in</h3>${t.modules.map(m => `<span class="chip" style="color:var(--hit)">${esc(m)}</span>`).join("")}
   ${(t.duplicates||[]).length ? `<h3>Very similar tickets (duplicate or sibling task?)</h3>${t.duplicates.map(d => `<span class="chip" style="color:var(--impact)">${esc(d.key)} · ${d.kind === "fixed" ? "already fixed?" : "open"} · ${d.similarity}</span>`).join("")}` : ""}
   <h3>Likely files</h3><ul>${t.files.map(f => `<li><code>${esc(f)}</code> ${(t.evidence[f]||[]).map(e=>`<span class=chip>${esc(e)}</span>`).join("")}${(t.file_dependents||{})[f] ? `<span class=chip>${t.file_dependents[f]} files import it</span>` : ""}${(t.file_commits_1y||{})[f] ? `<span class=chip>${t.file_commits_1y[f]} commits/yr</span>` : ""}</li>`).join("")}</ul>
   ${(t.suggested_people||[]).length ? `<h3>People who know this code</h3>${t.suggested_people.map(esc).join(", ")}` : ""}
   <h3>Impact area</h3>${t.impact.length ? t.impact.map(m => `<span class="chip" style="color:var(--impact)">${esc(m)}</span>`).join("") : "<span class=m>none found</span>"}
   <div class="m" style="margin-top:4px">Modules that import the landing modules, and modules historically fixed together with them.</div>
   <h3>Similar past tickets</h3>${t.similar.length ? t.similar.map(s => `<span class=chip>${esc(s)}</span>`).join("") : "<span class=m>none</span>"}
   ${owners(t.modules)}
   ${t.jira_note ? `<h3>Jira note</h3><button id="copyNote" style="padding:5px 9px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);cursor:pointer">Copy impact note for Jira</button> <span class=m id="copied"></span>` : ""}`;
  const cb = document.getElementById("copyNote");
  if (cb) cb.onclick = () => navigator.clipboard.writeText(t.jira_note).then(() => document.getElementById("copied").textContent = "copied", () => document.getElementById("copied").textContent = "copy blocked by the browser");
  document.querySelectorAll("a.ov").forEach(a => a.onclick = e => { e.preventDefault(); showTicket(a.dataset.k); });
}
function owners(mods){ const o = mods.map(m => byId[m]?.owners).filter(Boolean);
  return o.length ? `<h3>Owners</h3>${[...new Set(o)].map(esc).join(", ")}` : ""; }
function showModule(id){
  const m = byId[id]; if (!m) return;
  const out = D.imports.filter(l => l.source === id).sort((a,b)=>b.n-a.n).slice(0,6);
  const inn = D.imports.filter(l => l.target === id).sort((a,b)=>b.n-a.n).slice(0,6);
  const co = D.cochange.filter(c => c.a === id || c.b === id).sort((a,b)=>b.n-a.n).slice(0,6);
  highlight([id], [...inn.map(l=>l.source), ...co.map(c => c.a === id ? c.b : c.a)]);
  document.getElementById("detail").innerHTML = `<hr><h2>${esc(id)}</h2>
   <div class="m">${m.tickets} past tickets · ${Math.round(m.bug_share*100)}% bugs · ${m.recent} recent · ${m.files} code files</div>
   ${owners([id])}
   ${(m.experts||[]).length ? `<h3>People who know it</h3>${m.experts.map(e => `<span class=chip>${esc(e.name)} · ${e.commits}</span>`).join("")}<div class=m>bus factor ${m.bus_factor}${m.bus_factor === 1 ? " — one person holds half of the changes" : ""} · ${m.commits_1y} commits in the last year</div>` : ""}
   ${(m.hotspots||[]).length ? `<h3>Hotspots (changes often × large)</h3><ul>${m.hotspots.map(h => `<li><code>${esc(h.file)}</code> <span class=chip>${h.commits} commits · ${h.lines} lines</span></li>`).join("")}</ul>` : ""}
   <h3>Most-fixed files</h3><ul>${m.hot_files.map(f => `<li><code>${esc(f)}</code></li>`).join("") || "<li class=m>none</li>"}</ul>
   <h3>Typical tickets</h3><ul>${m.examples.map(e => `<li>${e.url ? `<a href="${esc(e.url)}" target=_blank>${esc(e.key)}</a>` : esc(e.key)} ${esc(e.title)}</li>`).join("")}</ul>
   <h3>Used by (imports it)</h3>${inn.map(l => `<span class=chip>${esc(l.source)} · ${l.n}</span>`).join("") || "<span class=m>none</span>"}
   <h3>Depends on</h3>${out.map(l => `<span class=chip>${esc(l.target)} · ${l.n}</span>`).join("") || "<span class=m>none</span>"}
   <h3>Changed together with</h3>${co.map(c => `<span class=chip style="color:var(--co)">${esc(c.a === id ? c.b : c.a)} · ${c.n}</span>`).join("") || "<span class=m>none</span>"}`;
}
document.getElementById("q").oninput = renderList;
const tabs = {tOpen: "open", tCol: "col", tMod: "mod"};
Object.entries(tabs).forEach(([id, name]) => document.getElementById(id).onclick = () => {
  tab = name; Object.keys(tabs).forEach(b => document.getElementById(b).classList.toggle("on", b === id)); renderList(); });
renderList();
</script></body></html>"""


def render(data: dict, out: Path) -> Path:
    page = TEMPLATE.replace("__TITLE__", html.escape(data["title"])).replace(
        "__DATA__", json.dumps(data).replace("</", "<\\/"))
    out.write_text(page, encoding="utf-8")
    return out
