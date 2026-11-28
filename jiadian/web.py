"""Web 入口:零依赖 http.server,单页 + JSON API。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import agent, llm
from . import db as dbmod

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>家电 · 修还是换</title>
<style>
  :root{--bg:#f4f6f8;--card:#fff;--ink:#1f2937;--muted:#6b7280;--accent:#1f6feb;--soft:#dbeafe;
        --line:#e5e7eb;--red:#b42318;--green:#067647;--amber:#b54708;--radius:16px}
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
  .wrap{max-width:940px;margin:0 auto;padding:32px 20px 80px}
  h1{font-size:26px;margin:0 0 4px} header p{color:var(--muted);margin:0 0 22px}
  .badge{display:inline-block;font-size:12px;padding:3px 10px;border-radius:999px;background:var(--soft);color:var(--accent);margin-left:8px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
  label{display:block;font-size:13px;color:var(--muted);margin:0 0 6px}
  textarea,input{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:12px;font-size:14px;font-family:inherit;background:#fff}
  textarea{line-height:1.7}
  textarea:focus,input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--soft)}
  .row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1;min-width:180px}
  button{background:var(--accent);color:#fff;border:none;padding:12px 22px;border-radius:12px;font-size:15px;cursor:pointer}
  button:hover{filter:brightness(1.1)}
  .hint{color:var(--muted);font-size:12px;margin-top:8px}
  .spin{display:inline-block;width:16px;height:16px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sp .7s linear infinite}
  @keyframes sp{to{transform:rotate(360deg)}}
  .result{display:none}.result.show{display:block}
  h3{font-size:15px;color:var(--muted);margin:20px 0 8px}
  .item{border-left:3px solid var(--accent);padding:4px 0 4px 12px;margin:8px 0;font-size:14px}
  .box{background:#f9fafb;border-radius:10px;padding:12px 14px;margin:8px 0;font-size:14px;white-space:pre-wrap;line-height:1.7}
  .ok{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}
  ul{margin:6px 0 0 18px;padding:0}li{margin:6px 0;font-size:14px}

.prod{display:block;font-size:11px;line-height:1.4;letter-spacing:.18em;font-weight:650;margin-bottom:8px;opacity:.72}
.lede{max-width:62ch;line-height:1.75}
.route{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin:0 0 20px;border:1px solid var(--line);background:var(--line)}
.route span{padding:11px 13px;background:var(--card);font-size:12px;line-height:1.5}
.route b{display:block;font-size:10px;letter-spacing:.1em;margin-bottom:3px;opacity:.66}
button{min-height:46px}
input,select{min-height:44px}
@media(max-width:680px){
  .wrap{padding:20px 16px 56px}
  .route{grid-template-columns:1fr}
  header h1{font-size:30px!important}
  .row>div{min-width:100%!important}
  button{width:100%}
}

body{background:#edf3f5;color:#16344f;font-family:"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:880px}
header{background:#16344f;color:#f7fbfd;padding:24px 24px 22px;margin-bottom:20px;border-bottom:4px solid #cf5a2e}
header h1{font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:38px;line-height:1.25;letter-spacing:-.02em}
header p{color:#c9dbe6;font-size:14px}
.card{background:#fbfdfe;border:1px solid #c7d8e0;border-radius:2px;box-shadow:0 1px 0 #dbe6eb}
button{background:#cf5a2e;border-radius:2px;letter-spacing:.06em}
button:hover{background:#b94b22}
textarea,input,select{background:#fff;border-color:#bdd1db;border-radius:2px}
textarea:focus,input:focus,select:focus{border-color:#16344f;box-shadow:0 0 0 2px #d5e3e9}
.item{border-left:4px solid #cf5a2e}
.cost .cell{border-color:#c7d8e0;border-radius:2px;background:#f2f7f9}
h3{color:#315a75;letter-spacing:.08em}


/* palette-normalized */
:root{--bg:#edf3f5;--card:#fbfdfe;--ink:#16344f;--text:#16344f;--dim:#5a7180;--line:#c7d8e0;--accent:#cf5a2e}

/* polish-batch1 */
button.ghost,button.secondary{background:transparent!important;color:#cf5a2e!important;border:1px solid #c7d8e0!important}

/* mobile-32 */

@media(max-width:760px){
  main{grid-template-columns:1fr!important}
  aside{border-right:0!important;border-bottom:1px solid #c7d8e0;width:auto!important}
  section{padding:16px!important}
  .row{flex-wrap:wrap!important}
  .row>div{min-width:100%!important}
  h1{font-size:30px!important}
  .route{grid-template-columns:1fr!important}
  button{min-height:48px}
  pre{overflow-x:auto}
}

/* mobile-height */
@media(max-width:760px){main{min-height:auto!important}aside{min-height:0!important}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><span class="prod">家电</span>这台家电，修还是换 <span class="badge" id="badge">…</span></h1>
    <p class="lede">给家电刚坏的住户：选型号、说故障、交代已经做过的安全操作，先判断能不能继续用，再对照维修报价和换新成本。</p>
  </header>
  <div class="route" aria-label="任务步骤"><span><b>01</b>说清故障</span><span><b>02</b>先过安全关</span><span><b>03</b>拿走报修单</span></div>

  <div class="card">
    <label>故障描述</label>
    <textarea id="text" rows="6" placeholder="冰箱不制冷,2021年买的,新机价 3800,门封看起来有点松"></textarea>
    <div class="row" style="margin-top:12px">
      <div><label>购机年份(可选)</label><input id="buy" placeholder="例:2021"></div>
      <div><label>提示</label><div class="hint" style="margin-top:8px">写上新机价才能判断修值不值</div></div>
    </div>
    <div style="margin-top:16px"><button id="btn">开始诊断</button></div>
    <div class="hint">故障树、保修、估价与修换结论全在本地;模型只写解释与追问,金额不会被改写。</div>
  </div>
  <div class="result" id="res"></div>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function load(btn,on){btn.disabled=on;if(on){btn.dataset.label=btn.dataset.label||btn.textContent.trim();btn.innerHTML='<span class="spin"></span>';}else{btn.innerHTML=btn.dataset.label||btn.textContent;}}
$('#btn').onclick=async()=>{
  const el=$('#res');el.classList.remove('show');load($('#btn'),true);
  try{
    const p=await fetch('/api/diagnose',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:$('#text').value,buy_year:$('#buy').value})});
    const r=await p.json(); if(r.error) throw new Error(r.error);
    let h='<div class="card"><div class="hint">'+(r.mode==='model'?'模型已连接':'离线模式')+(r.saved_id?' · 已入库 #'+r.saved_id:'')+'</div>';
    h+='<p style="line-height:1.75;font-size:16px">'+esc(r.verdict)+'</p>';
    h+='<h3>可能的故障</h3>';
    r.causes.forEach(c=>{h+='<div class="item"><b>'+esc(c.cause)+'</b> <span class="hint">['+esc(c.level)+'] '+esc(c.check)+'</span></div>';});
    h+='<h3>保修</h3>';
    if(r.warranty.age===null){h+='<div class="warn">'+esc(r.warranty.note)+'</div>';}
    else{h+='<div>购机 '+r.purchase_year+' 年,已用 '+r.warranty.age+' 年</div>';
      r.warranty.items.forEach(i=>{h+='<div class="'+(i.active?'ok':'bad')+'">'+(i.active?'✅ 在保':'❌ 过保')+' '+esc(i.name)+'('+i.years+' 年)</div>';});
      h+='<div class="hint">'+esc(r.warranty.note)+'</div>';}
    h+='<h3>维修估价</h3><div class="box">';
    r.estimate.items.forEach(i=>{h+=esc(i.cause)+':'+i.low+'–'+i.high+' 元\\n';});
    h+='合计参考:'+r.estimate.low+'–'+r.estimate.high+' 元';
    if(r.new_price){h+='\\n新机价 '+r.new_price+' 元,残值约 '+(r.residual==null?'算不出(缺购机年份)':r.residual)+' 元';}
    h+='</div>';
    h+='<h3>修还是换</h3><div class="item"><b>'+esc(r.decision.verdict)+'</b><div class="hint">'+esc(r.decision.why)+'</div></div>';
    h+='<h3>安全禁忌</h3><ul>';r.safety.forEach(s=>h+='<li class="bad">'+esc(s)+'</li>');h+='</ul>';
    h+='<h3>报修话术</h3><div class="box">'+esc(r.talk)+'</div>';
    if(r.summary){h+='<h3>判断</h3><p>'+esc(r.summary)+'</p>';}
    if(r.risks.length){h+='<h3>风险与坑</h3><ul>';r.risks.forEach(x=>h+='<li>'+esc(x)+'</li>');h+='</ul>';}
    if(r.questions.length){h+='<h3>还要问</h3><ul>';r.questions.forEach(x=>h+='<li>'+esc(x)+'</li>');h+='</ul>';}
    h+='<h3>报修前体检</h3>';
    r.checklist.forEach(c=>{h+='<div class="'+(c.ok?'ok':'warn')+'">'+(c.ok?'✅':'❌')+' '+esc(c.item)+' —— '+esc(c.how)+'</div>';});
    h+='</div>'; el.innerHTML=h;
  }catch(e){el.innerHTML='<div class="card" style="color:#b42318">请求失败:'+esc(e.message)+'</div>';}
  el.classList.add('show');load($('#btn'),false);
};
fetch('/api/status').then(r=>r.json()).then(s=>{const b=$('#badge');
  if(s.mock){b.textContent='离线模式';b.style.background='#fee2e2';b.style.color='#b42318';}
  else{b.textContent=s.model||'模型已连接';b.style.background='#dcfce7';b.style.color='#067647';}
}).catch(()=>{});
</script>
</body></html>
"""


def _handler(db, cfg, force_mock):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", status)

        def _read(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")
            return json.loads(text) if text else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/status":
                mock = force_mock or not cfg.get("api_key")
                self._json({"mock": mock, "model": None if mock else cfg.get("model")})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/diagnose":
                # 先把请求体吃掉再回 404:留着不读就关连接,Windows 上会发 RST,
                # 客户端可能在读到响应前就收到「连接被重置」。
                try:
                    left = int(self.headers.get("Content-Length", 0) or 0)
                    if left:
                        self.rfile.read(left)
                except (OSError, ValueError):
                    pass
                self._json({"error": "not found"}, 404)
                return
            try:
                body = self._read()
                buy = str(body.get("buy_year") or "").strip()
                year = int(buy) if buy.isdigit() else None
                r = agent.diagnose(body.get("text", ""), buy_year=year, config=cfg,
                                   db=db, force_mock=force_mock, save=True)
                self._json(r)
            except llm.LLMError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)

        def log_message(self, *args):
            pass

    return Handler


def serve(host="127.0.0.1", port=8000, db_path=None, force_mock=False):
    db = dbmod.Database(db_path)
    cfg = llm.default_config()
    httpd = ThreadingHTTPServer((host, port), _handler(db, cfg, force_mock))
    mode = "离线模式(未配置 key)" if (force_mock or not cfg.get("api_key")) else "模型:%s" % cfg.get("model")
    print("🔧 家电已启动:http://%s:%s  [%s]" % (host, port, mode))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
