let quickEditMode = false;
const liftRows = [1000,1500,2250,4000];

function toggleQuickEdit(){
  quickEditMode = !quickEditMode;
  document.getElementById('quickEdit').style.display = quickEditMode ? 'block' : 'none';
  renderQuick();
}

async function refreshState(){
  const res = await fetch('/api/state');
  const data = await res.json();
  renderMessages(data.messages);
  renderQuick(data.quick);
  renderLiftList(data.lifts);
}

function renderMessages(msgs){
  const chat = document.getElementById('chat');
  chat.innerHTML = '';
  msgs.forEach(m=>{
    const div = document.createElement('div');
    div.className = `bubble ${m.direction==='out'?'right':'left'}`;
    div.textContent = m.text;
    chat.appendChild(div);
  });
  chat.scrollTop = chat.scrollHeight;
}

function renderQuick(list){
  const c = document.getElementById('quick');
  c.innerHTML = '';
  list.forEach(q=>{
    const btn = document.createElement('button');
    btn.className = quickEditMode ? 'secondary removeable' : 'secondary';
    btn.textContent = q;
    if(quickEditMode){
      btn.onclick = ()=>removeQuick(q);
    } else {
      btn.onclick = ()=>sendMsg(q);
    }
    c.appendChild(btn);
  });
}

function renderLiftList(list){
  const c = document.getElementById('liftList');
  c.innerHTML = '';
  list.sort((a,b)=>b.id-a.id).forEach(l=>{
    const div = document.createElement('div');
    div.textContent = `${l.name || 'Lift '+l.id} – ${l.status}`;
    c.appendChild(div);
  });
}

async function sendMsg(txt){
  const text = txt || document.getElementById('msgInput').value.trim();
  if(!text) return;
  const fd = new FormData();
  fd.append('text', text);
  await fetch('/api/messages',{method:'POST',body:fd});
  document.getElementById('msgInput').value='';
  refreshState();
}

async function addQuick(){
  const text = document.getElementById('quickText').value.trim();
  if(!text) return;
  const fd = new FormData();
  fd.append('text', text);
  await fetch('/api/quick/add',{method:'POST',body:fd});
  document.getElementById('quickText').value='';
  refreshState();
}

async function removeQuick(text){
  const fd = new FormData();
  fd.append('text', text);
  await fetch('/api/quick/remove',{method:'POST',body:fd});
  refreshState();
}

function buildLiftRows(){
  const tbody = document.getElementById('liftRows');
  tbody.innerHTML='';
  liftRows.forEach(alt=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`
      <td>${alt}</td>
      <td><input type="number" min="0" id="jumpers_${alt}" value="0"></td>
      <td><input type="number" min="0" id="over_${alt}" value="0"></td>`;
    tbody.appendChild(tr);
  });
}

async function sendLift(){
  const liftId=parseInt(document.getElementById('liftId').value)||1;
  const totalJumpers=parseInt(document.getElementById('totalJumpers').value)||0;
  const totalCanopies=parseInt(document.getElementById('totalCanopies').value)||totalJumpers;

  const rows=[];
  liftRows.forEach(a=>{
    const j=parseInt(document.getElementById('jumpers_'+a).value)||0;
    const o=parseInt(document.getElementById('over_'+a).value)||0;
    if(j>0){
      rows.push({alt:a,jumpers:j,overflights:o>0?o:1});
    }
  });

  const lift={
    id: liftId,
    name:`Lift ${liftId}`,
    status:"active",
    rows:rows,
    totals:{jumpers:totalJumpers||rows.reduce((s,r)=>s+r.jumpers,0),
            canopies:totalCanopies||rows.reduce((s,r)=>s+r.jumpers,0)}
  };

  await fetch('/api/lift/send',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(lift)
  });
  refreshState();
  document.getElementById('liftId').value=liftId+1;
}

buildLiftRows();
refreshState();
setInterval(refreshState,5000);
