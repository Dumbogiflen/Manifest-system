// --- Hurtigbeskeder ---
let quickMessages = JSON.parse(localStorage.getItem("quickMessages") || '["Klar til lift","5 min forsinket","Skal tanke"]');
let quickEditMode = false;

function saveQuick() {
  localStorage.setItem("quickMessages", JSON.stringify(quickMessages));
}

function renderQuick() {
  const quickDiv = document.getElementById("quick");
  quickDiv.innerHTML = "";

  quickMessages.forEach((msg, i) => {
    const btn = document.createElement("button");
    btn.textContent = msg;
    btn.style.color = "black"; // sort tekst
    if (quickEditMode) {
      const del = document.createElement("span");
      del.textContent = " 🗑";
      del.style.cursor = "pointer";
      del.onclick = () => { quickMessages.splice(i, 1); saveQuick(); renderQuick(); };
      btn.appendChild(del);
      btn.disabled = true;
    } else {
      btn.onclick = () => sendMsg(msg);
    }
    quickDiv.appendChild(btn);
  });

  const gear = document.createElement("button");
  gear.textContent = "⚙️";
  gear.className = "secondary";
  gear.onclick = () => { quickEditMode = !quickEditMode; renderQuick(); };
  quickDiv.appendChild(gear);
}

function addQuick() {
  const val = document.getElementById("quickText").value.trim();
  if (!val) return;
  quickMessages.push(val);
  saveQuick();
  document.getElementById("quickText").value = "";
  renderQuick();
}

// --- Chat ---
async function loadMessages() {
  const res = await fetch("/api/state");
  const data = await res.json();
  const chat = document.getElementById("chat");
  chat.innerHTML = "";

  (data.messages || []).forEach(m => {
    const div = document.createElement("div");
    div.className = "msg " + (m.direction === "out" ? "out" : "in");
    div.textContent = m.text;
    chat.appendChild(div);
  });

  chat.scrollTop = chat.scrollHeight;
}

async function sendMsg(text) {
  if (!text) return;
  await fetch("/api/messages", {
    method: "POST",
    body: new URLSearchParams({ text })
  });
  document.getElementById("msgInput").value = "";
  loadMessages();
}

// --- Lift ---
const heights = [1000, 1500, 2250, 4000];
let userEditedTotals = false;
let userEditedCanopies = false;
let nextLiftId = 1;

function renderLiftRows() {
  const tbody = document.getElementById("liftRows");
  tbody.innerHTML = "";
  heights.forEach(h => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${h}</td>
      <td><input id="jump_${h}" type="number" min="0" style="width:80px"></td>
      <td><input id="over_${h}" type="number" min="0" style="width:80px"></td>
    `;
    tbody.appendChild(tr);
  });
}

function calcTotals() {
  let totalJumpers = 0;
  heights.forEach(h => {
    const j = parseInt(document.getElementById(`jump_${h}`).value) || 0;
    totalJumpers += j;
  });
  if (!userEditedTotals) document.getElementById("totalJumpers").value = totalJumpers;
  if (!userEditedCanopies) document.getElementById("totalCanopies").value = document.getElementById("totalJumpers").value || totalJumpers;
}

async function sendLift() {
  const rows = [];
  heights.forEach(h => {
    const j = parseInt(document.getElementById(`jump_${h}`).value) || 0;
    if (j > 0) {
      const o = parseInt(document.getElementById(`over_${h}`).value) || 1;
      rows.push({ alt: h, jumpers: j, overflights: o });
    }
  });

  const id = parseInt(document.getElementById("liftId").value) || nextLiftId;
  const totalJumpers = parseInt(document.getElementById("totalJumpers").value) || rows.reduce((a, b) => a + b.jumpers, 0);
  const totalCanopies = parseInt(document.getElementById("totalCanopies").value) || totalJumpers;

  const lift = {
    id,
    name: `Lift ${id}`,
    status: "active",
    rows,
    totals: { jumpers: totalJumpers, canopies: totalCanopies }
  };

  await fetch("/api/lift", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(lift)
  });

  const list = document.getElementById("liftList");
  const item = document.createElement("div");
  item.textContent = `${lift.name}: ${totalJumpers} springere / ${totalCanopies} skærme`;
  list.prepend(item);

  nextLiftId = id + 1;
  document.getElementById("liftId").value = nextLiftId;

  userEditedTotals = false;
  userEditedCanopies = false;
}

function setupLift() {
  renderLiftRows();
  document.getElementById("liftRows").addEventListener("input", calcTotals);
  document.getElementById("totalJumpers").addEventListener("input", () => userEditedTotals = true);
  document.getElementById("totalCanopies").addEventListener("input", () => userEditedCanopies = true);
  calcTotals();
}

// --- Init ---
renderQuick();
setupLift();
loadMessages();
setInterval(loadMessages, 3000);
