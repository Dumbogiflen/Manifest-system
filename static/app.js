// =============== Quick beskeder ===============
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
    btn.style.margin = "4px";
    if (quickEditMode) {
      btn.disabled = true;
      const del = document.createElement("span");
      del.textContent = " 🗑";
      del.style.cursor = "pointer";
      del.onclick = () => {
        quickMessages.splice(i, 1);
        saveQuick();
        renderQuick();
      };
      btn.appendChild(del);
    } else {
      btn.onclick = () => sendMsg(msg);
    }
    quickDiv.appendChild(btn);
  });

  // Gear toggler edit-boks
  document.getElementById("quickConfig").style.display = quickEditMode ? "flex" : "none";
}

function addQuick() {
  const val = document.getElementById("quickText").value.trim();
  if (!val) return;
  quickMessages.push(val);
  saveQuick();
  document.getElementById("quickText").value = "";
  renderQuick();
}

// =============== Chat / beskeder ===============
async function loadState() {
  const res = await fetch("/api/state");
  return await res.json();
}

async function refreshState() {
  await drawChat();
}

async function drawChat() {
  const data = await loadState();
  const chat = document.getElementById("chat");
  chat.innerHTML = "";

  (data.messages || []).forEach((m) => {
    const div = document.createElement("div");
    // retning: "in" (fra pilot) eller "out" (fra manifest)
    const cls = m.direction === "in" ? "in" : "out";
    div.className = "msg " + cls;

    // vis tekst (bevar simple bobler – backend kan senere tilføje status/tid)
    div.textContent = m.text;
    chat.appendChild(div);
  });

  chat.scrollTop = chat.scrollHeight;
}

async function sendMsg(text) {
  const val = (text ?? document.getElementById("msgInput").value).trim();
  if (!val) return;
  await fetch("/api/messages", {
    method: "POST",
    body: new URLSearchParams({ text: val }),
  });
  const input = document.getElementById("msgInput");
  if (input) input.value = "";
  drawChat();
}

// =============== Lift-formular ===============
const heights = [1000, 1500, 2250, 4000];
let userEditedTotals = false;
let userEditedCanopies = false;

// gem/brug sidste lift-id lokalt
function getNextLiftId() {
  const last = parseInt(localStorage.getItem("lastLiftId") || "0", 10);
  return isNaN(last) ? 1 : last + 1;
}

function setLastLiftId(id) {
  localStorage.setItem("lastLiftId", String(id));
}

function renderLiftRows() {
  const tbody = document.getElementById("liftRows");
  tbody.innerHTML = "";
  heights.forEach((h) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${h}</td>
      <td><input id="jump_${h}" type="number" min="0" style="width:90px" /></td>
      <td><input id="over_${h}" type="number" min="0" style="width:90px" /></td>
    `;
    tbody.appendChild(tr);
  });
}

function sumJumpersFromRows() {
  return heights.reduce((sum, h) => {
    const j = parseInt(document.getElementById(`jump_${h}`).value) || 0;
    return sum + j;
  }, 0);
}

function calcTotals() {
  const autoJumpers = sumJumpersFromRows();

  // kun auto-opdater, hvis brugeren ikke selv har ændret
  if (!userEditedTotals) {
    document.getElementById("totalJumpers").value = autoJumpers;
  }

  if (!userEditedCanopies) {
    const currentTJ = parseInt(document.getElementById("totalJumpers").value) || autoJumpers;
    document.getElementById("totalCanopies").value = currentTJ;
  }
}

function setupLift() {
  renderLiftRows();

  const idEl = document.getElementById("liftId");
  if (!idEl.value || parseInt(idEl.value) < 1) {
    idEl.value = getNextLiftId();
  }

  // registrér ændringer i inputfelter
  document.getElementById("liftRows").addEventListener("input", (e) => {
    const field = e.target.id;
    // Når brugeren ændrer totalfelter, skal auto-beregning stoppes
    if (field.startsWith("jump_") || field.startsWith("over_")) {
      calcTotals();
    }
  });

  document.getElementById("totalJumpers").addEventListener("input", () => {
    userEditedTotals = true;
  });

  document.getElementById("totalCanopies").addEventListener("input", () => {
    userEditedCanopies = true;
  });

  calcTotals();
}


async function sendLift() {
  // byg rows (springere > 0; overflyvninger default 1 hvis tom)
  const rows = [];
  heights.forEach((h) => {
    const j = parseInt(document.getElementById(`jump_${h}`).value) || 0;
    if (j > 0) {
      const o = parseInt(document.getElementById(`over_${h}`).value) || 1;
      rows.push({ alt: h, jumpers: j, overflights: o });
    }
  });

  // ID – respekter manuelt felt; ellers next
  const idInput = document.getElementById("liftId");
  const typedId = parseInt(idInput.value);
  const id = !isNaN(typedId) && typedId > 0 ? typedId : getNextLiftId();

  // totals – respekter manuelle hvis udfyldt; ellers auto
  const autoJumpers = rows.reduce((a, b) => a + b.jumpers, 0);
  const tj = parseInt(document.getElementById("totalJumpers").value);
  const tc = parseInt(document.getElementById("totalCanopies").value);
  const totalJumpers = !isNaN(tj) ? tj : autoJumpers;
  const totalCanopies = !isNaN(tc) ? tc : totalJumpers;

  const lift = {
    id,
    name: `Lift ${id}`,
    status: "active",
    rows,
    totals: { jumpers: totalJumpers, canopies: totalCanopies },
  };

  // send til backend (videre til pilot via MQTT)
  await fetch("/api/lift", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(lift),
  });

  // vis i “sendte lifts”
  prependLiftListItem(lift);

  // bump next id først efter succes
  setLastLiftId(id);
  idInput.value = id + 1;

  // nulstil “manuelt redigeret” flag
  userEditedTotals = false;
  userEditedCanopies = false;
}

function prependLiftListItem(lift) {
  const list = document.getElementById("liftList");
  const item = document.createElement("div");
  item.textContent = `${lift.name}: ${lift.totals.jumpers} springere / ${lift.totals.canopies} skærme`;
  list.prepend(item);
}

function setupLift() {
  renderLiftRows();

  // init id-felt (kun første gang eller hvis tomt)
  const idEl = document.getElementById("liftId");
  if (!idEl.value || parseInt(idEl.value) < 1) {
    idEl.value = getNextLiftId();
  }

  // reagér på ændringer i rækkerne => auto totals (med respekt for manuel)
  document.getElementById("liftRows").addEventListener("input", calcTotals);

  // markér totals som manuelt redigeret hvis bruger skriver i felterne
  document.getElementById("totalJumpers").addEventListener("input", () => (userEditedTotals = true));
  document.getElementById("totalCanopies").addEventListener("input", () => (userEditedCanopies = true));

  // første beregning
  calcTotals();
}

// =============== Init & events ===============
document.getElementById("sendBtn").addEventListener("click", () => sendMsg());
document.getElementById("addQuickBtn").addEventListener("click", addQuick);
document.getElementById("gearBtn").addEventListener("click", () => {
  quickEditMode = !quickEditMode;
  renderQuick();
});

renderQuick();
setupLift();
drawChat();
setInterval(drawChat, 3000);
