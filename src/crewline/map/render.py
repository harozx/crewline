"""Render change-map data into one self-contained HTML page (data inline; d3 from cdnjs). Vietnamese by default,
English toggle. Layout: summary cards, map on the left, work list + details on the right."""

from __future__ import annotations

import html
import json
from pathlib import Path

TEMPLATE = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · Crewline</title>
<style>
:root{--bg:#f5f5f2;--panel:#ffffff;--ink:#1c1c1e;--muted:#6e6e73;--line:#e2e2e6;--soft:#f0f0ee;--hit:#d23b2f;
--impact:#d9822b;--co:#3566cf;--ok:#2e8b57;--sel:#fff4e8;--shadow:0 1px 2px rgba(0,0,0,.06)}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--panel:#1b1b1e;--ink:#ececef;--muted:#9b9ba3;--line:#2e2e33;
--soft:#242428;--sel:#33261a;--shadow:none}}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;display:flex;flex-direction:column}
header{padding:12px 18px 10px;border-bottom:1px solid var(--line);background:var(--panel)}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.top h1{font-size:17px;margin:0;font-weight:650}
.top .sub{color:var(--muted);font-size:12.5px}.top .sp{flex:1}
.btn{padding:5px 10px;border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--ink);
cursor:pointer;font:inherit;font-size:12.5px}.btn:hover{background:var(--soft)}.btn.on{background:var(--ink);color:var(--panel)}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:10px}
.card{background:var(--soft);border-radius:10px;padding:9px 12px;cursor:pointer;border:1px solid transparent}
.card:hover{border-color:var(--line)}.card .n{font-size:22px;font-weight:650;line-height:1.1}.card .l{color:var(--muted);font-size:12px}
.card .t{font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
main{flex:1;display:grid;grid-template-columns:minmax(0,1fr) 440px;min-height:0}
#graph{position:relative;min-height:0}#graph>svg{width:100%;height:100%;display:block}
#logic{position:absolute;inset:0;overflow:auto;padding:58px 22px 60px;background:var(--bg)}#logic[hidden]{display:none}
.lwrap{position:relative;min-width:640px;max-width:1100px}.lcols{display:grid;gap:56px;position:relative;z-index:1}
.lcol h4{margin:0 0 8px;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
.lbox{background:var(--panel);border:1.5px solid var(--line);border-radius:10px;padding:7px 10px;margin-bottom:12px;font-size:12.5px;
box-shadow:var(--shadow);cursor:pointer}.lbox.hit{border-color:var(--hit)}.lbox.imp{border-color:var(--impact)}.lbox.main{border-color:var(--ink)}
.lbox .why{color:var(--muted);font-size:11.5px;margin-top:2px}.lbox b{font-weight:600}
svg.lines{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible;z-index:0}
.lempty{color:var(--muted);text-align:center;margin-top:20vh}
.gtools{position:absolute;left:12px;top:12px;display:flex;gap:6px;flex-wrap:wrap}
.legend{position:absolute;left:12px;bottom:10px;background:var(--panel);border:1px solid var(--line);border-radius:8px;
padding:6px 10px;font-size:11.5px;color:var(--muted);box-shadow:var(--shadow);display:flex;gap:12px;flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;vertical-align:0}
aside{border-left:1px solid var(--line);background:var(--panel);display:flex;flex-direction:column;min-height:0}
.side-top{padding:12px 14px 8px;border-bottom:1px solid var(--line)}
input{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit}
.tabs{display:flex;gap:4px;margin-top:8px}.tabs .btn{flex:1;padding:6px 4px}
.filters{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}.filters .btn{padding:3px 9px;font-size:12px}
.scroll{overflow:auto;flex:1;min-height:0}
.item{padding:9px 14px;border-bottom:1px solid var(--line);cursor:pointer;display:grid;grid-template-columns:40px 1fr;gap:10px}
.item:hover{background:var(--soft)}.item.on{background:var(--sel)}
.score{width:38px;height:38px;border-radius:9px;display:grid;place-items:center;font-weight:650;font-size:14px;
background:var(--soft)}.score.h{background:#d23b2f22;color:var(--hit)}.score.m{background:#d9822b22;color:var(--impact)}
.item .k{font-size:12px;color:var(--muted)}.item .ti{font-weight:550;line-height:1.35}
.tag{display:inline-block;font-size:11px;padding:0 6px;border-radius:5px;background:var(--soft);color:var(--muted);margin:2px 3px 0 0}
.tag.red{color:var(--hit);background:#d23b2f1a}.tag.orange{color:var(--impact);background:#d9822b1a}.tag.blue{color:var(--co);background:#3566cf1a}.tag.green{color:#2f8f4e;background:#2f8f4e1a}
#detail{border-top:1px solid var(--line);max-height:58%;overflow:auto;padding:12px 14px;background:var(--bg)}
#detail:empty{display:none}
.d-h{font-size:15.5px;font-weight:650;margin:0 0 4px}.d-h a{color:inherit}.meta{margin-bottom:8px}
.box{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 11px;margin:8px 0}
.box h3{margin:0 0 5px;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
.two{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.file{margin:3px 0}.file b{font-weight:600}.file .dir{color:var(--muted);font-size:11.5px;word-break:break-all}
ul{margin:0;padding-left:18px}li{margin:2px 0}a{color:var(--co)}
.node text{font-size:11.5px;fill:var(--ink);pointer-events:none;paint-order:stroke;stroke:var(--bg);stroke-width:3px}
.dim{opacity:.13}.empty{color:var(--muted);padding:14px}
@media (max-width:980px){main{grid-template-columns:1fr;grid-template-rows:50vh auto}aside{border-left:0;border-top:1px solid var(--line)}
.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body>
<header><div class="top"><h1>__TITLE__</h1><span class="sub" id="sub"></span><span class="sp"></span>
<button class="btn" id="lang">English</button></div><div class="cards" id="cards"></div></header>
<main><div id="graph"><svg></svg><div id="logic" hidden></div><div class="gtools"><button class="btn on" id="vGraph"></button><button class="btn" id="vLogic"></button><button class="btn" id="fit"></button><button class="btn" id="allLinks"></button></div>
<div class="legend" id="legend"></div></div>
<aside><div class="side-top"><input id="q"><div class="tabs" id="tabs"></div><div class="filters" id="filters"></div></div>
<div class="scroll" id="list"></div><div id="detail"></div></aside></main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>
const D = __DATA__;
const T = {
 vi:{search:"Tìm ticket, người, module…",work:"Việc cần làm",parents:"Epic / task cha",col:"Đâm nhau",mods:"Module",
  open:"việc đang mở",due:"quá hạn / sắp hạn",clash:"cặp sửa cùng file",first:"nên làm trước",bug:"Bug",dueF:"Có hạn",clashF:"Có va chạm",
  fit:"Căn giữa",vGraph:"Đồ thị",vLogic:"Sơ đồ logic",pick:"Chọn một ticket, epic hoặc module để xem sơ đồ logic.",lTicket:"Ticket",lLands:"Rơi vào module",lFiles:"File cần sửa",lSpread:"Lan ảnh hưởng tới",lUsedBy:"Được dùng bởi",lModule:"Module",lDeps:"Phụ thuộc vào",lTogether:"Hay sửa cùng",lChildren:"Task con",all:"Hiện liên kết chính",strong:"Ẩn liên kết",lands:"Ticket rơi vào",impactL:"Vùng ảnh hưởng",importL:"mũi tên = import",
  coL:"nét đứt = hay sửa cùng nhau",sizeL:"to = nhiều ticket, đỏ = nhiều bug",why:"Vì sao ưu tiên",where:"Nằm ở",spread:"Lan ảnh hưởng tới",
  files:"File có khả năng phải sửa",people:"Người nắm phần code này",parent:"Task cha",siblings:"Task anh em đang mở",
  clashWith:"Sửa cùng file với",similar:"Rất giống (trùng hay task anh em?)",links:"Liên kết Jira",past:"Ticket cũ tương tự",
  note:"Ghi chú cho Jira",copy:"Sao chép ghi chú",copied:"đã sao chép",imports:"file import nó",commits:"commit/năm",
  overdue:"quá hạn",left:"còn",days:"ngày",sameParent:"cùng task cha",noItems:"Không có mục nào.",children:"việc con đang mở",
  topChild:"Việc con gấp nhất",outside:"Đâm vào việc ngoài epic",experts:"Người nắm module",bus:"bus factor",
  hot:"Điểm nóng (sửa nhiều × lớn)",fixed:"File hay phải sửa",typical:"Ticket tiêu biểu",usedBy:"Được import bởi",dependsOn:"Phụ thuộc vào",
  together:"Hay sửa cùng",pastT:"ticket cũ",bugs:"bug",none:"không có",onePerson:"một người giữ một nửa số thay đổi",
  ppl:"Người làm",unF:"Chưa giao",newF:"Người làm chưa từng sửa vùng này",knowsT:"đã từng sửa hoặc review code này",nearT:"từng sửa module này hoặc module bên cạnh, nhưng ít",newT:"chưa từng sửa vùng code này",
  unT:"chưa giao ai",openN:"việc",late:"quá hạn",knowsN:"việc đúng vùng mình từng sửa",pts:"điểm",whoHint:"Gợi ý dựa trên git 1 năm qua, không phải đánh giá người.",
  subtitle:(m,h,o)=>`${m} module · ${h} ticket đã sửa · ${o} ticket đang mở`},
 en:{search:"Search tickets, people, modules…",work:"To do",parents:"Epics / parents",col:"Collisions",mods:"Modules",
  open:"open tickets",due:"overdue / due soon",clash:"same-file pairs",first:"do first",bug:"Bugs",dueF:"Has deadline",clashF:"Collides",
  fit:"Fit",vGraph:"Graph",vLogic:"Logic view",pick:"Pick a ticket, epic or module to see its logic view.",lTicket:"Ticket",lLands:"Lands in",lFiles:"Files to change",lSpread:"Spreads to",lUsedBy:"Used by",lModule:"Module",lDeps:"Depends on",lTogether:"Changed together with",lChildren:"Children",all:"Show main links",strong:"Hide links",lands:"Ticket lands here",impactL:"Impact area",importL:"arrow = import",
  coL:"dashed = changed together",sizeL:"size = tickets, red = bugs",why:"Why this priority",where:"Lands in",spread:"Spreads to",
  files:"Likely files",people:"People who know this code",parent:"Parent",siblings:"Open siblings",clashWith:"Same files as",
  similar:"Very similar (duplicate or sibling?)",links:"Jira links",past:"Similar past tickets",note:"Note for Jira",copy:"Copy note",
  copied:"copied",imports:"files import it",commits:"commits/yr",overdue:"overdue",left:"",days:"d left",sameParent:"same parent",
  noItems:"Nothing here.",children:"open children",topChild:"Most urgent child",outside:"Collides outside the epic",
  experts:"People who know it",bus:"bus factor",hot:"Hotspots (changes often × large)",fixed:"Most-fixed files",typical:"Typical tickets",
  ppl:"People",unF:"Unassigned",newF:"Assignee never changed this code",knowsT:"has changed or reviewed this code",nearT:"touched this module or a neighbour, a little",newT:"has not changed this code",
  unT:"unassigned",openN:"open",late:"overdue",knowsN:"in code they have changed",pts:"pts",whoHint:"Hint from the last year of git, not a judgement of people.",
  usedBy:"Imported by",dependsOn:"Depends on",together:"Changed together with",pastT:"past tickets",bugs:"bugs",none:"none",
  onePerson:"one person holds half of the changes",subtitle:(m,h,o)=>`${m} modules · ${h} fixed tickets · ${o} open tickets`}};
let L = (()=>{try{return localStorage.getItem("cl_lang")||"vi"}catch(e){return "vi"}})();
const t_ = k => T[L][k];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const byId = Object.fromEntries(D.modules.map(m => [m.id, m]));
const byKey = Object.fromEntries(D.open.map(o => [o.key, o]));
D.collisions = D.collisions || []; D.parents = D.parents || [];
const realClash = D.collisions.filter(c => c.level === "file" && !c.same_parent);
const dueTxt = o => o.days_left == null ? "" : o.days_left < 0 ? `${t_("overdue")} ${-o.days_left}d` : `${t_("left")} ${o.days_left} ${t_("days")}`.trim();
const fileHtml = f => { const i = f.lastIndexOf("/"); return `<b>${esc(f.slice(i+1))}</b> <span class="dir">${esc(f.slice(0, i))}</span>`; };

/* ---------- graph ---------- */
const svg = d3.select("svg"), g = svg.append("g");
const zoom = d3.zoom().scaleExtent([.2, 4]).on("zoom", e => g.attr("transform", e.transform)); svg.call(zoom);
svg.append("defs").append("marker").attr("id","arr").attr("viewBox","0 -4 8 8").attr("refX",8).attr("markerWidth",5)
  .attr("markerHeight",5).attr("orient","auto").append("path").attr("d","M0,-4L8,0L0,4").attr("fill","var(--muted)");
const nodes = D.modules.filter(m => m.tickets || m.files > 5).map(m => ({...m}));
const ok = new Set(nodes.map(n => n.id));
const allLinks = D.imports.filter(l => ok.has(l.source) && ok.has(l.target)).map(l => ({...l, kind:"imp"}))
  .concat(D.cochange.filter(c => ok.has(c.a) && ok.has(c.b)).map(c => ({source:c.a, target:c.b, n:c.n, kind:"co"})));
// Only the strongest links shape the layout and can be shown; everything else appears on selection only.
const ranked = [...allLinks].sort((a, b) => b.n - a.n);
const topImp = new Set(ranked.filter(l => l.kind === "imp").slice(0, 35)), topCo = new Set(ranked.filter(l => l.kind === "co").slice(0, 15));
const strong = l => topImp.has(l) || topCo.has(l);
let showAll = false;
const maxT = Math.max(1, ...nodes.map(n => n.tickets));
const r = d => 5 + 23 * Math.sqrt(d.tickets / maxT);
const color = d3.scaleLinear().domain([0, .5]).range(["#a3abb5", "#d23b2f"]).clamp(true);
const link = g.append("g").selectAll("line").data(allLinks).join("line")
  .attr("stroke", d => d.kind === "co" ? "var(--co)" : "var(--muted)").attr("stroke-dasharray", d => d.kind === "co" ? "4 3" : null)
  .attr("stroke-width", d => Math.min(3, .6 + Math.log1p(d.n) / 2)).attr("marker-end", d => d.kind === "imp" ? "url(#arr)" : null);
const node = g.append("g").selectAll("g").data(nodes).join("g").attr("class","node").style("cursor","pointer").on("click", (e, d) => showModule(d.id));
node.append("circle").attr("r", r).attr("fill", d => color(d.bug_share)).attr("stroke","var(--panel)").attr("stroke-width",2);
node.append("text").attr("dy", d => r(d) + 12).attr("text-anchor","middle").text(d => d.id.split("/").pop())
  .attr("display", d => r(d) >= 8 ? null : "none");
node.append("title").text(d => `${d.id} · ${d.tickets} tickets`);
const el = id => document.getElementById(id), W = () => el("graph").clientWidth, H = () => el("graph").clientHeight;
const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(allLinks.filter(strong)).id(d => d.id).distance(110).strength(.2))
  .force("charge", d3.forceManyBody().strength(-260)).force("center", d3.forceCenter(W()/2, H()/2))
  .force("x", d3.forceX(W()/2).strength(.04)).force("y", d3.forceY(H()/2).strength(.06))
  .force("collide", d3.forceCollide(d => r(d) + 22)).on("tick", draw);
function draw(){
  link.each(function(d){ const s = typeof d.source === "object" ? d.source : nodes.find(n => n.id === d.source),
    q = typeof d.target === "object" ? d.target : nodes.find(n => n.id === d.target); if (!s || !q) return;
    const dx = q.x - s.x, dy = q.y - s.y, L2 = Math.hypot(dx, dy) || 1, cut = d.kind === "imp" ? r(q) + 4 : 0;
    d3.select(this).attr("x1", s.x).attr("y1", s.y).attr("x2", q.x - dx/L2*cut).attr("y2", q.y - dy/L2*cut); });
  node.attr("transform", d => `translate(${d.x},${d.y})`);
}
const ends = d => [d.source.id ?? d.source, d.target.id ?? d.target];
// default: no lines (a hairball explains nothing); selection shows its own links; the button shows the top ones
function paintLinks(lit, hit){
  link.attr("display", d => { const [a, b] = ends(d);
      // on a selection, only the links that touch the landing modules: they explain why the area is lit
      if (lit && lit.size) return lit.has(a) && lit.has(b) && (!hit || hit.has(a) || hit.has(b)) ? null : "none";
      return showAll && strong(d) ? null : "none"; })
    .attr("stroke-opacity", d => lit && lit.size ? .85 : (d.kind === "co" ? .5 : .4)); }
paintLinks();
node.call(d3.drag().on("start",(e,d)=>{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y})
  .on("drag",(e,d)=>{d.fx=e.x;d.fy=e.y}).on("end",(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null}));
function fit(){ const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y); if (!xs.length) return;
  const x0 = Math.min(...xs)-40, x1 = Math.max(...xs)+40, y0 = Math.min(...ys)-40, y1 = Math.max(...ys)+50;
  const k = Math.min(W()/(x1-x0), H()/(y1-y0), 1.6);
  svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity.translate(W()/2 - k*(x0+x1)/2, H()/2 - k*(y0+y1)/2).scale(k)); }
setTimeout(fit, 1600);
function highlight(hit, area){
  const lit = new Set([...hit, ...area]);
  node.classed("dim", d => lit.size && !lit.has(d.id));
  node.select("circle").attr("stroke", d => hit.includes(d.id) ? "var(--hit)" : area.includes(d.id) ? "var(--impact)" : "var(--panel)")
    .attr("stroke-width", d => lit.has(d.id) ? 5 : 2);
  paintLinks(lit.size ? lit : null, hit.length ? new Set(hit) : null);
}

/* ---------- side panel ---------- */
let tab = "work", filt = new Set(), person = null;
function chips(o){ const c = [];
  if (o.days_left != null) c.push(`<span class="tag ${o.days_left < 0 ? "red" : o.days_left <= 7 ? "orange" : ""}">${esc(dueTxt(o))}</span>`);
  if ((o.type||"").toLowerCase() === "bug") c.push(`<span class="tag red">bug</span>`);
  if (o.status) c.push(`<span class="tag">${esc(o.status)}</span>`);
  if ((o.overlaps||[]).some(x => x.level === "file" && !x.same_parent)) c.push(`<span class="tag red">${esc(t_("clashF"))}</span>`);
  if (o.parent) c.push(`<span class="tag blue">↑ ${esc(o.parent)}</span>`);
  return c.join(""); }
function who(o){ if (!o.assignee) return `<span class="tag orange">${esc(t_("unT"))}</span>`;
  const f = {knows:["green","knowsT","✓"], near:["blue","nearT","~"], new:["orange","newT","?"]}[o.assignee_fit] || ["","",""];
  return `<span class="tag ${f[0]}" title="${esc(f[1] ? t_(f[1]) : "")}">${f[2]} ${esc(o.assignee)}</span>`; }
function scoreCls(s){ return s >= 55 ? "h" : s >= 35 ? "m" : ""; }
function renderList(){
  const q = el("q").value.toLowerCase(), box = el("list");
  if (tab === "work") {
    let rows = D.open.filter(o => [o.key, o.title, o.assignee, o.status, o.parent, o.modules.join(" ")].join(" ").toLowerCase().includes(q));
    if (filt.has("bug")) rows = rows.filter(o => (o.type||"").toLowerCase() === "bug");
    if (filt.has("due")) rows = rows.filter(o => o.days_left != null && o.days_left <= 14);
    if (filt.has("clash")) rows = rows.filter(o => (o.overlaps||[]).some(x => x.level === "file" && !x.same_parent));
    if (filt.has("un")) rows = rows.filter(o => !o.assignee);
    if (filt.has("new")) rows = rows.filter(o => o.assignee_fit === "new");
    if (person != null) rows = rows.filter(o => (o.assignee || "") === person);
    box.innerHTML = rows.map(o => `<div class="item" data-k="${esc(o.key)}"><div class="score ${scoreCls(o.priority_score)}">${o.priority_score}</div>
      <div><div class="k">${esc(o.key)}</div><div class="ti">${esc(o.title)}</div>
      <div>${who(o)}${chips(o)}<span class="tag">→ ${o.modules.map(esc).join(", ")}</span></div></div></div>`).join("") || `<div class="empty">${t_("noItems")}</div>`;
    box.querySelectorAll(".item").forEach(x => x.onclick = () => showTicket(x.dataset.k));
  } else if (tab === "ppl") {
    box.innerHTML = `<div class="empty">${esc(t_("whoHint"))}</div>` + (D.people||[]).filter(p => (p.name || t_("unF")).toLowerCase().includes(q)).map(p => `<div class="item" data-n="${esc(p.name)}">
      <div class="score ${p.late ? "h" : ""}">${p.open}</div><div><div class="k">${esc(p.name || t_("unF"))}</div>
      <div><span class="tag">${p.open} ${esc(t_("openN"))}</span>${p.points ? `<span class="tag">${p.points} ${esc(t_("pts"))}</span>` : ""}
      ${p.late ? `<span class="tag red">${p.late} ${esc(t_("late"))}</span>` : ""}${p.name ? `<span class="tag ${p.knows === p.open ? "green" : "orange"}">${p.knows}/${p.open} ${esc(t_("knowsN"))}</span>` : ""}</div></div></div>`).join("");
    box.querySelectorAll(".item").forEach(x => x.onclick = () => { person = x.dataset.n; setTab("work"); });
  } else if (tab === "parents") {
    box.innerHTML = D.parents.filter(p => (p.key + p.title).toLowerCase().includes(q)).map(p => `<div class="item" data-p="${esc(p.key)}">
      <div class="score ${scoreCls(p.max_score)}">${p.max_score}</div><div><div class="k">${esc(p.key)} · ${esc(p.kind)}${p.status ? " · " + esc(p.status) : ""}</div>
      <div class="ti">${esc(p.title || p.key)}</div><div><span class="tag blue">${p.children.length} ${t_("children")}</span>
      ${Object.entries(p.statuses).map(([s,n]) => `<span class="tag">${esc(s)} ${n}</span>`).join("")}
      ${p.collides_outside.length ? `<span class="tag red">${esc(t_("outside"))}: ${p.collides_outside.length}</span>` : ""}
      <span class="tag">→ ${p.modules.map(esc).join(", ")}</span></div></div></div>`).join("") || `<div class="empty">${t_("noItems")}</div>`;
    box.querySelectorAll(".item").forEach(x => x.onclick = () => showParent(x.dataset.p));
  } else if (tab === "col") {
    const rows = D.collisions.filter(c => c.level === "file").filter(c => (c.a + c.b + c.files.join(" ")).toLowerCase().includes(q))
      .sort((a, b) => a.same_parent - b.same_parent);
    box.innerHTML = rows.map(c => `<div class="item" data-k="${esc(c.a)}"><div class="score ${c.same_parent ? "" : "h"}">${c.files.length}</div>
      <div><div class="ti">${esc(c.a)} ↔ ${esc(c.b)}</div><div>${c.same_parent ? `<span class="tag blue">${esc(t_("sameParent"))}</span>` : `<span class="tag red">${esc(t_("clashF"))}</span>`}
      ${c.different_owners ? `<span class="tag orange">≠ assignee</span>` : ""}</div>
      ${c.files.map(f => `<div class="file">${fileHtml(f)}</div>`).join("")}</div></div>`).join("") || `<div class="empty">${t_("noItems")}</div>`;
    box.querySelectorAll(".item").forEach(x => x.onclick = () => showTicket(x.dataset.k));
  } else {
    box.innerHTML = [...D.modules].filter(m => m.tickets || m.files > 5).sort((a,b)=>b.tickets-a.tickets).filter(m => m.id.toLowerCase().includes(q)).map(m =>
      `<div class="item" data-m="${esc(m.id)}"><div class="score" style="background:${color(m.bug_share)}33">${m.tickets}</div><div><div class="ti">${esc(m.id)}</div>
      <div><span class="tag">${Math.round(m.bug_share*100)}% ${t_("bugs")}</span><span class="tag">${m.files} files</span>${m.bus_factor === 1 ? `<span class="tag orange">${t_("bus")} 1</span>` : ""}</div></div></div>`).join("");
    box.querySelectorAll(".item").forEach(x => x.onclick = () => showModule(x.dataset.m));
  }
}
function mark(attr, v){ document.querySelectorAll(".item").forEach(x => x.classList.toggle("on", !!attr && x.dataset[attr] === v)); }

/* ---------- selection: clicking the same thing again, or empty space, clears it ---------- */
let cur = null, view = "graph";
function toggleSel(id){ if (cur === id) { clearSel(); return false; } cur = id; return true; }
function clearSel(){ cur = null; mark(null); highlight([], []); el("detail").innerHTML = ""; drawLogic(); }
svg.on("click", e => { if (e.target === svg.node()) clearSel(); });

/* ---------- logic view: left-to-right boxes and arrows ---------- */
const modOf = f => f.includes("/src/") ? f.split("/src/")[0] : (f.includes("/") ? f.split("/")[0] : "(root)");
function drawLogic(){
  const box = el("logic"); if (view !== "logic") return;
  const [kind, id] = cur ? [cur.slice(0, 1), cur.slice(2)] : [null, null];
  let cols = [], edges = [];
  const B = (bid, cls, html, go) => ({bid, cls, html, go});
  if (kind === "t") {
    const o = byKey[id];
    const t = [B("tk", "main", `<b>${esc(o.key)}</b> · ${esc(o.title)}<div class="why">${o.priority_score}/100${o.assignee ? " · " + esc(o.assignee) : ""}</div>`)];
    if (o.parent) t.unshift(B("par", "", `↑ <b>${esc(o.parent)}</b> ${esc(o.parent_title || "")}`, `p:${o.parent}`));
    if ((o.suggested_people||[]).length) t.push(B("ppl", "", `<div class="why">${esc(t_("people"))}</div>${o.suggested_people.map(esc).join(", ")}`));
    // files sit inside their module's box: no line has to cross a column of files
    const filesOf = m => o.files.slice(0, 6).filter(f => modOf(f) === m);
    const fileLine = f => `<div class="why">• <b style="color:var(--ink)">${esc(f.split("/").pop())}</b>${(o.file_dependents||{})[f] ? ` · ${o.file_dependents[f]} ${esc(t_("imports"))}` : ""}</div>`;
    const loose = o.files.slice(0, 6).filter(f => !o.modules.includes(modOf(f)));
    const mods = o.modules.map((m, i) => B("m" + i, "hit", `<b>${esc(m)}</b>${filesOf(m).map(fileLine).join("")}`, `m:${m}`));
    if (loose.length) mods.push(B("mx", "", `<div class="why">${esc(t_("lFiles"))}</div>${loose.map(fileLine).join("")}`));
    const imp = o.impact.map((m, i) => B("i" + i, "imp", `<b>${esc(m)}</b><div class="why">${esc((o.impact_reasons[m]||[]).join("; "))}</div>`, `m:${m}`));
    cols = [[t_("lTicket"), t], [t_("lLands"), mods], [t_("lSpread"), imp]];
    if (o.parent) edges.push(["par", "tk"]);
    mods.forEach(m => edges.push(["tk", m.bid]));
    o.impact.forEach((m, i) => o.modules.forEach((lm, j) => { if ((o.impact_reasons[m]||[]).some(r => r.includes(lm))) edges.push(["m" + j, "i" + i]); }));
  } else if (kind === "m") {
    const inn = D.imports.filter(l => l.target === id).sort((a,b)=>b.n-a.n).slice(0, 8);
    const out = D.imports.filter(l => l.source === id).sort((a,b)=>b.n-a.n).slice(0, 8);
    const co = D.cochange.filter(c => c.a === id || c.b === id).sort((a,b)=>b.n-a.n).slice(0, 6);
    const m = byId[id];
    cols = [[t_("lUsedBy"), inn.map((l, i) => B("u" + i, "imp", `<b>${esc(l.source)}</b><div class="why">${l.n} imports</div>`, `m:${l.source}`))],
      [t_("lModule"), [B("me", "main", `<b>${esc(id)}</b><div class="why">${m.tickets} ${esc(t_("pastT"))} · ${Math.round(m.bug_share*100)}% ${esc(t_("bugs"))}</div>`)]],
      [t_("lDeps"), out.map((l, i) => B("d" + i, "", `<b>${esc(l.target)}</b><div class="why">${l.n} imports</div>`, `m:${l.target}`))],
      [t_("lTogether"), co.map((c, i) => { const x = c.a === id ? c.b : c.a; return B("c" + i, "", `<b>${esc(x)}</b><div class="why">${c.n} ${esc(t_("pastT"))}</div>`, `m:${x}`); })]];
    inn.forEach((l, i) => edges.push(["u" + i, "me"])); out.forEach((l, i) => edges.push(["me", "d" + i])); co.forEach((c, i) => edges.push(["me", "c" + i, "co"]));
  } else if (kind === "p") {
    const p = D.parents.find(x => x.key === id);
    const kids = p.children.map((k, i) => { const o = byKey[k]; return B("k" + i, "", `<b>${esc(k)}</b> · ${esc(o.title)}<div class="why">${o.priority_score}/100 · ${esc(o.status || "")}</div>`, `t:${k}`); });
    const mods = p.modules.map((m, i) => B("m" + i, "hit", `<b>${esc(m)}</b>`, `m:${m}`));
    const imp = p.impact.map((m, i) => B("i" + i, "imp", `<b>${esc(m)}</b>`, `m:${m}`));
    cols = [[t_("parent"), [B("pp", "main", `<b>${esc(p.key)}</b> · ${esc(p.title || "")}`)]], [t_("lChildren"), kids], [t_("lLands"), mods], [t_("lSpread"), imp]];
    kids.forEach(k => edges.push(["pp", k.bid]));
    p.children.forEach((k, i) => byKey[k].modules.forEach(m => { const j = p.modules.indexOf(m); if (j >= 0) edges.push(["k" + i, "m" + j]); }));
    imp.forEach(x => mods.forEach(m => edges.push([m.bid, x.bid, "co"])));
  } else { box.innerHTML = `<div class="lempty">${esc(t_("pick"))}</div>`; return; }
  box.innerHTML = `<div class="lwrap"><svg class="lines"></svg><div class="lcols" style="grid-template-columns:repeat(${cols.length},minmax(150px,1fr))">${cols.map(([h, items]) =>
    `<div class="lcol"><h4>${esc(h)}</h4>${items.map(b => `<div class="lbox ${b.cls}" id="lb-${b.bid}" ${b.go ? `data-go="${esc(b.go)}"` : ""}>${b.html}</div>`).join("") || `<div class="why">${esc(t_("none"))}</div>`}</div>`).join("")}</div></div>`;
  box.querySelectorAll(".lbox[data-go]").forEach(x => x.onclick = () => go(x.dataset.go));
  requestAnimationFrame(() => {
    const wrap = box.querySelector(".lwrap"), sv = box.querySelector("svg.lines"), wr = wrap.getBoundingClientRect();
    sv.innerHTML = `<defs><marker id="la" viewBox="0 -4 8 8" refX="8" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,-4L8,0L0,4" fill="var(--muted)"/></marker></defs>` +
      edges.map(([a, b, k]) => { const A = el("lb-" + a), Z = el("lb-" + b); if (!A || !Z) return "";
        const ra = A.getBoundingClientRect(), rz = Z.getBoundingClientRect();
        const x1 = ra.right - wr.left, y1 = ra.top + ra.height / 2 - wr.top, x2 = rz.left - wr.left - 2, y2 = rz.top + rz.height / 2 - wr.top, mx = (x1 + x2) / 2;
        return `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" fill="none" stroke="${k === "co" ? "var(--co)" : "var(--muted)"}" stroke-width="1.4" ${k === "co" ? 'stroke-dasharray="4 3"' : ""} marker-end="url(#la)"/>`; }).join(""); });
}
function go(target){ const [k, v] = [target.slice(0, 1), target.slice(2)]; cur = null;
  if (k === "t") showTicket(v); else if (k === "p") showParent(v); else showModule(v); }
function setView(v){ view = v; el("logic").hidden = v !== "logic"; el("vGraph").classList.toggle("on", v === "graph"); el("vLogic").classList.toggle("on", v === "logic");
  el("fit").style.display = el("allLinks").style.display = v === "graph" ? "" : "none"; drawLogic(); }

function showTicket(k){
  if (!toggleSel("t:" + k)) return;
  const o = byKey[k]; if (!o) return; mark("k", k); highlight(o.modules, o.impact); drawLogic();
  const sibs = o.parent ? D.open.filter(x => x.parent === o.parent && x.key !== o.key) : [];
  const clash = (o.overlaps||[]).filter(c => c.level === "file");
  el("detail").innerHTML = `<div class="d-h">${o.url ? `<a href="${esc(o.url)}" target="_blank">${esc(o.key)}</a>` : esc(o.key)} · ${esc(o.title)}</div>
   <div class="meta">${chips(o)}${who(o)}${[o.priority, o.sprint ? "sprint " + o.sprint : "", o.points != null ? o.points + " pts" : "", (o.fix_versions||[]).join(", ")].filter(Boolean).map(x => `<span class="tag">${esc(x)}</span>`).join("")}</div>
   <div class="box"><h3>${t_("why")} · ${o.priority_score}/100</h3><ul>${(o.priority_reasons||[]).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
   <div class="two"><div class="box"><h3>${t_("where")}</h3>${o.modules.map(m => `<span class="tag red">${esc(m)}</span>`).join("")}</div>
   <div class="box"><h3>${t_("spread")}</h3>${o.impact.map(m => `<span class="tag orange" title="${esc((o.impact_reasons[m]||[]).join("; "))}">${esc(m)}</span>`).join("") || `<span class="tag">${t_("none")}</span>`}</div></div>
   <div class="box"><h3>${t_("files")}</h3>${o.files.map(f => `<div class="file">${fileHtml(f)}<br>${(o.evidence[f]||[]).map(e => `<span class="tag">${esc(e)}</span>`).join("")}${(o.file_dependents||{})[f] ? `<span class="tag">${o.file_dependents[f]} ${t_("imports")}</span>` : ""}${(o.file_commits_1y||{})[f] ? `<span class="tag">${o.file_commits_1y[f]} ${t_("commits")}</span>` : ""}</div>`).join("")}</div>
   ${(o.suggested_people||[]).length ? `<div class="box"><h3>${t_("people")}</h3>${o.suggested_people.map(esc).join(", ")}</div>` : ""}
   ${o.parent ? `<div class="box"><h3>${t_("parent")}</h3><a href="#" class="go-p" data-p="${esc(o.parent)}">${esc(o.parent)}</a> ${esc(o.parent_title || "")}
     ${sibs.length ? `<div style="margin-top:5px">${t_("siblings")}: ${sibs.map(s => `<a href="#" class="go-k" data-k="${esc(s.key)}">${esc(s.key)}</a>`).join(", ")}</div>` : ""}</div>` : ""}
   ${clash.length ? `<div class="box"><h3>${t_("clashWith")}</h3>${clash.map(c => { const x = c.a === o.key ? c.b : c.a;
     return `<div><a href="#" class="go-k" data-k="${esc(x)}">${esc(x)}</a> ${c.same_parent ? `<span class="tag blue">${esc(t_("sameParent"))}</span>` : `<span class="tag red">!</span>`} ${c.files.map(f => `<span class="tag">${esc(f.split("/").pop())}</span>`).join("")}</div>`; }).join("")}</div>` : ""}
   ${(o.duplicates||[]).length ? `<div class="box"><h3>${t_("similar")}</h3>${o.duplicates.map(d => `<span class="tag orange">${esc(d.key)} · ${esc(d.kind)} · ${d.similarity}</span>`).join("")}</div>` : ""}
   ${(o.links||[]).length ? `<div class="box"><h3>${t_("links")}</h3>${o.links.map(l => `<span class="tag">${esc(l.rel)} ${esc(l.key)}</span>`).join("")}</div>` : ""}
   ${(o.similar||[]).length ? `<div class="box"><h3>${t_("past")}</h3>${o.similar.map(s => `<span class="tag">${esc(s)}</span>`).join("")}</div>` : ""}
   ${o.jira_note ? `<div class="box"><h3>${t_("note")}</h3><button class="btn" id="copyNote">${t_("copy")}</button> <span class="tag" id="copied" style="display:none">${t_("copied")}</span></div>` : ""}`;
  const cb = el("copyNote"); if (cb) cb.onclick = () => navigator.clipboard.writeText(o.jira_note).then(() => el("copied").style.display = "inline-block", () => {});
  wireLinks();
}
function showParent(pk){
  if (!toggleSel("p:" + pk)) return;
  const p = D.parents.find(x => x.key === pk); if (!p) return; mark("p", pk); highlight(p.modules, p.impact); drawLogic();
  el("detail").innerHTML = `<div class="d-h">${esc(p.key)} · ${esc(p.title || "")}</div>
   <div class="meta"><span class="tag blue">${esc(p.kind)}</span>${p.status ? `<span class="tag">${esc(p.status)}</span>` : ""}</div>
   <div class="two"><div class="box"><h3>${t_("where")}</h3>${p.modules.map(m => `<span class="tag red">${esc(m)}</span>`).join("")}</div>
   <div class="box"><h3>${t_("spread")}</h3>${p.impact.map(m => `<span class="tag orange">${esc(m)}</span>`).join("") || `<span class="tag">${t_("none")}</span>`}</div></div>
   <div class="box"><h3>${p.children.length} ${t_("children")}</h3>${p.children.map(k => { const o = byKey[k];
     return `<div class="file"><a href="#" class="go-k" data-k="${esc(k)}">${esc(k)}</a> <span class="tag">${o.priority_score}</span> ${esc(o.title)} ${chips(o)}</div>`; }).join("")}</div>
   ${p.collides_outside.length ? `<div class="box"><h3>${t_("outside")}</h3>${p.collides_outside.map(k => `<a href="#" class="go-k" data-k="${esc(k)}">${esc(k)}</a>`).join(", ")}</div>` : ""}`;
  wireLinks();
}
function wireLinks(){ document.querySelectorAll("a.go-k").forEach(a => a.onclick = e => { e.preventDefault(); showTicket(a.dataset.k); });
  document.querySelectorAll("a.go-p").forEach(a => a.onclick = e => { e.preventDefault(); setTab("parents"); showParent(a.dataset.p); }); }
function showModule(id){
  if (!toggleSel("m:" + id)) return;
  const m = byId[id]; if (!m) return; mark("m", id); setTimeout(drawLogic);
  const out = D.imports.filter(l => l.source === id).sort((a,b)=>b.n-a.n).slice(0,6), inn = D.imports.filter(l => l.target === id).sort((a,b)=>b.n-a.n).slice(0,6);
  const co = D.cochange.filter(c => c.a === id || c.b === id).sort((a,b)=>b.n-a.n).slice(0,6);
  highlight([id], [...inn.map(l=>l.source), ...co.map(c => c.a === id ? c.b : c.a)]);
  const chip = (x, n) => `<span class="tag">${esc(x)} · ${n}</span>`;
  el("detail").innerHTML = `<div class="d-h">${esc(id)}</div>
   <div class="meta"><span class="tag">${m.tickets} ${t_("pastT")}</span><span class="tag ${m.bug_share >= .3 ? "red" : ""}">${Math.round(m.bug_share*100)}% ${t_("bugs")}</span><span class="tag">${m.files} files</span>${m.commits_1y ? `<span class="tag">${m.commits_1y} ${t_("commits")}</span>` : ""}</div>
   ${(m.experts||[]).length ? `<div class="box"><h3>${t_("experts")}</h3>${m.experts.map(e => chip(e.name, e.commits)).join("")}<div class="tag ${m.bus_factor === 1 ? "orange" : ""}">${t_("bus")} ${m.bus_factor}${m.bus_factor === 1 ? " — " + t_("onePerson") : ""}</div></div>` : ""}
   ${(m.hotspots||[]).length ? `<div class="box"><h3>${t_("hot")}</h3>${m.hotspots.map(h => `<div class="file">${fileHtml(h.file)} <span class="tag">${h.commits} commits · ${h.lines} lines</span></div>`).join("")}</div>` : ""}
   <div class="box"><h3>${t_("fixed")}</h3>${m.hot_files.map(f => `<div class="file">${fileHtml(f)}</div>`).join("") || t_("none")}</div>
   <div class="box"><h3>${t_("typical")}</h3><ul>${m.examples.map(e => `<li>${e.url ? `<a href="${esc(e.url)}" target=_blank>${esc(e.key)}</a>` : esc(e.key)} ${esc(e.title)}</li>`).join("")}</ul></div>
   <div class="two"><div class="box"><h3>${t_("usedBy")}</h3>${inn.map(l => chip(l.source, l.n)).join("") || t_("none")}</div>
   <div class="box"><h3>${t_("dependsOn")}</h3>${out.map(l => chip(l.target, l.n)).join("") || t_("none")}</div></div>
   <div class="box"><h3>${t_("together")}</h3>${co.map(c => chip(c.a === id ? c.b : c.a, c.n)).join("") || t_("none")}</div>`;
}
function setTab(name){ tab = name; document.querySelectorAll("#tabs .btn").forEach(b => b.classList.toggle("on", b.dataset.t === name));
  if (name !== "work") person = null; paintFilters();
  el("filters").style.display = name === "work" ? "flex" : "none"; renderList(); }
function cards(){
  const due = D.open.filter(o => o.days_left != null && o.days_left <= 7).length, top = D.open[0];
  const c = [[D.open.length, t_("open"), () => setTab("work")], [due, t_("due"), () => { filt = new Set(["due"]); paintFilters(); setTab("work"); }],
    [realClash.length, t_("clash"), () => setTab("col")]];
  el("cards").innerHTML = c.map(([n, l], i) => `<div class="card" data-i="${i}"><div class="n">${n}</div><div class="l">${esc(l)}</div></div>`).join("") +
    (top ? `<div class="card" data-i="3"><div class="l">${t_("first")} · ${top.priority_score}</div><div class="t"><b>${esc(top.key)}</b> ${esc(top.title)}</div></div>` : "");
  el("cards").querySelectorAll(".card").forEach(x => x.onclick = () => x.dataset.i === "3" ? showTicket(top.key) : c[+x.dataset.i][2]());
}
function paintFilters(){ el("filters").innerHTML = (person != null ? `<button class="btn on" data-x="1">✕ ${esc(person || t_("unF"))}</button>` : "") +
  [["bug", t_("bug")], ["due", t_("dueF")], ["clash", t_("clashF")], ["un", t_("unF")], ["new", t_("newF")]].map(([k, l]) =>
  `<button class="btn ${filt.has(k) ? "on" : ""}" data-f="${k}">${esc(l)}</button>`).join("");
  const x = el("filters").querySelector("[data-x]"); if (x) x.onclick = e => { e.stopPropagation(); person = null; paintFilters(); renderList(); };
  el("filters").querySelectorAll(".btn[data-f]").forEach(b => b.onclick = () => { filt.has(b.dataset.f) ? filt.delete(b.dataset.f) : filt.add(b.dataset.f); paintFilters(); renderList(); }); }
function i18n(){
  document.documentElement.lang = L; el("lang").textContent = L === "vi" ? "English" : "Tiếng Việt";
  el("sub").textContent = T[L].subtitle(D.modules.length, D.history_tickets, D.open.length); el("q").placeholder = t_("search");
  el("tabs").innerHTML = [["work", t_("work")], ["parents", t_("parents")], ["ppl", t_("ppl")], ["col", t_("col")], ["mods", t_("mods")]].map(([k, l]) =>
    `<button class="btn ${tab === k ? "on" : ""}" data-t="${k}">${esc(l)}</button>`).join("");
  el("tabs").querySelectorAll(".btn").forEach(b => b.onclick = () => setTab(b.dataset.t));
  el("fit").textContent = t_("fit"); el("allLinks").textContent = showAll ? t_("strong") : t_("all");
  el("vGraph").textContent = t_("vGraph"); el("vLogic").textContent = t_("vLogic");
  el("legend").innerHTML = `<span><i style="background:var(--hit)"></i>${t_("lands")}</span><span><i style="background:var(--impact)"></i>${t_("impactL")}</span>
    <span>→ ${t_("importL")}</span><span style="color:var(--co)">- - ${t_("coL")}</span><span>${t_("sizeL")}</span>`;
  cards(); paintFilters(); setTab(tab); clearSel();
}
el("lang").onclick = () => { L = L === "vi" ? "en" : "vi"; try { localStorage.setItem("cl_lang", L) } catch(e){} i18n(); };
el("vGraph").onclick = () => setView("graph"); el("vLogic").onclick = () => setView("logic");
el("fit").onclick = fit; el("allLinks").onclick = () => { showAll = !showAll; el("allLinks").textContent = showAll ? t_("strong") : t_("all"); paintLinks(); };
el("q").oninput = renderList;
i18n();
// deep link: page.html#PROJ-123 opens that ticket (paste it in Jira), #module:core opens a module
function fromHash(){ let h = decodeURIComponent(location.hash.slice(1)); if (!h) return;
  if (h.endsWith("/logic")) { h = h.slice(0, -6); setView("logic"); }
  cur = null;
  if (h.startsWith("module:")) { setTab("mods"); showModule(h.slice(7)); }
  else if (byKey[h]) { setTab("work"); showTicket(h); }
  else if (D.parents.some(p => p.key === h)) { setTab("parents"); showParent(h); } }
window.addEventListener("hashchange", fromHash); setTimeout(fromHash, 1700);
</script></body></html>"""


def render(data: dict, out: Path) -> Path:
    page = TEMPLATE.replace("__TITLE__", html.escape(data["title"])).replace(
        "__DATA__", json.dumps(data).replace("</", "<\\/"))
    out.write_text(page, encoding="utf-8")
    return out
