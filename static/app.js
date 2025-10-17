const ALT_PRESETS = [1000, 1500, 2250, 4000];

async function jsonGet(url){ const r = await fetch(url); return r.json(); }
async function formPost(url, data){
  const fd = new FormData();
  for (const [k,v] of Object.entries(data)) fd.append(k, v);
  const r = await fetch(url, { method: "POST", body: fd });
  return r.json();
}
async function jsonPost(url, obj){
  const r = await fetch(url, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(obj)
  });
  return r.json();
}

function el(tag, attrs={}, children=[]){
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k,v]) => {
    if (k === "text") e.textContent = v;
    else e.setAttribute(k, v);
  });
  (Array.isArray(children) ? children : [children]).forEach(c => {
    if (c == null) return;
    if (typeof c === "string") e.appendChild(document.createTextNode(c));
    else e.appendChild(c);
  });
  return e;
}

async function load(){
  const state = await jsonGet("/api/state");
  document.getElementById("club").textContent = state.club || "";

  // chat
  const chat = document.getElementById("chat");
  chat.innerHTML = "";
  state.messages.forEach(m => {
    const bubble = el("div", {class: "msg " + (m.direction==="in" ? "in":"out")}, [
      el("div", {text: m.text}),
      el("div", {class:"status", text: (m.status||"") + (m.ts ? (" • " + new Date(m.ts).toLocaleTimeString()) : "") })
    ]);
    chat.appendChild(bubble);
  });
  chat.scrollTop = chat.scrollHeight;

  // lifts
  const ll = document.getElementById("liftList");
  ll.innerHTML = "";
  state.lifts.forEach(l => {
    const tag = el("div", {class:"row"}, [
      el("div", {text: `${l.name || ("Lift " + l.id)} – ${l.status || "active"}`}),
      el("div", {class:"badge", text: `Σ ${l.totals?.jumpers ?? 0}/${l.totals?.canopies ?? 0}`})
    ]);
    ll.appendChild(tag);
  });

  // quicks
  const qs = await jsonGet("/api/quick");
  const quick = document.getElementById("quick");
  quick.innerHTML = "";
  qs.forEach(q => {
    const b = el("button", {text:q});
    b.onclick = () => sendMsg(q);
    quick.appendChild(b);
  });

  suggestNextLiftId(state.lifts);
}

function suggestNextLiftId(list){
  const i = document.getElementById("liftId");
  if (!list || !list.length) { i.value = 1; return; }
  const maxId = Math.max(...list.map(x => Number(x.id)||0));
  i.value = maxId + 1;
}

function buildLiftRowsUI(){
  const tbody = document.getElementById("liftRows");
  tbody.innerHTML = "";
  ALT_PRESETS.forEach(alt => {
    const tr = el("tr");
    tr.appendChild(el("td", {text: alt}));
    const j = el("input", {type:"number", min:"0", value:"", placeholder:"0", style:"width:90px"});
    const o = el("input", {type:"number", min:"0", value:"", placeholder:"1", style:"width:90px"});
    j.addEventListener("change", () => {
      if (j.value && (!o.value || Number(o.value) === 0)) o.value = "1";
    });
    tr.appendChild(el("td", {}, j));
    tr.appendChild(el("td", {}, o));
    tr.dataset.alt = String(alt);
    tr.dataset.jRef = j;
    tr.dataset.oRef = o;
    // vi kan ikke gemme refs i dataset direkte, så:
    tr._j = j; tr._o = o;
    tbody.appendChild(tr);
  });
}

async function sendLift(){
  const id = Number(document.getElementById("liftId").value || "0");
  const status = document.getElementById("liftStatus").value || "active";
  const tj = document.getElementById("totalJumpers").value;
  const tc = document.getElementById("totalCanopies").value;

  const rows = [];
  document.querySelectorAll("#liftRows tr").forEach(tr => {
    const alt = Number(tr.childNodes[0].textContent);
    const j = Number(tr._j.value || "0");
    const o = Number(tr._o.value || (j>0 ? "1":"0"));
    if (j > 0) rows.push({alt, jumpers:j, overflights:o});
  });

  if (!id || rows.length === 0){
    alert("Angiv lift nr. og mindst én række med springere.");
    return;
  }

  const payload = {
    id,
    status,
    rows,
    totals_jumpers: tj ? Number(tj) : null,
    totals_canopies: tc ? Number(tc) : null
  };

  await jsonPost("/api/lift", payload);
  await load();
}

async function sendMsg(textOverride){
  const text = textOverride ?? document.getElementById("msgInput").value.trim();
  if (!text) return;
  await formPost("/api/messages", {text});
  document.getElementById("msgInput").value = "";
  await load();
}

async function addQuick(){
  const t = document.getElementById("quickText").value.trim();
  if (!t) return;
  await formPost("/api/quick/add", {text:t});
  document.getElementById("quickText").value="";
  await load();
}

async function refreshState(){ await load(); }

buildLiftRowsUI();
load();
setInterval(load, 4000);

