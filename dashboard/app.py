"""
CATERYA Enterprise Dashboard v2
Author : Ary HH <cateryatech@proton.me>
Modes  : Analyse | Build SaaS (real code generation)
Export : PDF · HTML · Markdown · JSON
"""
import sys, os, traceback, json as _json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st

st.set_page_config(page_title="CATERYA Enterprise", page_icon="⬡",
                   layout="wide", initial_sidebar_state="expanded")

# ── Provider detection ────────────────────────────────────────────────────────
def _detect_providers():
    ollama_ok = False
    try:
        import urllib.request
        urllib.request.urlopen(
            os.getenv("OLLAMA_BASE_URL","http://localhost:11434")+"/api/tags", timeout=2)
        ollama_ok = True
    except Exception:
        pass
    return {
        "groq":       (bool(os.getenv("GROQ_API_KEY")),       "llama-3.1-8b-instant",                           "GROQ_API_KEY"),
        "openrouter": (bool(os.getenv("OPENROUTER_API_KEY")), "meta-llama/llama-3.1-8b-instruct:free",          "OPENROUTER_API_KEY"),
        "together":   (bool(os.getenv("TOGETHER_API_KEY")),   "meta-llama/Llama-3-8b-chat-hf",                  "TOGETHER_API_KEY"),
        "fireworks":  (bool(os.getenv("FIREWORKS_API_KEY")),  "accounts/fireworks/models/llama-v3-8b-instruct", "FIREWORKS_API_KEY"),
        "gemini":     (bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")), "gemini-2.0-flash", "GEMINI_API_KEY"),
        "ollama":     (ollama_ok, os.getenv("OLLAMA_MODEL","qwen3.5"), "OLLAMA_BASE_URL"),
    }

PROVIDERS = _detect_providers()

def _default_provider():
    for p in ["ollama","groq","openrouter","together","fireworks","gemini"]:
        if PROVIDERS[p][0]: return p, PROVIDERS[p][1]
    return "groq", "llama-3.1-8b-instant"

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap');
html,body,[class*="css"]{font-family:'Syne',sans-serif;}
code,pre{font-family:'Space Mono',monospace!important;}
[data-testid="stSidebar"]{background:#0d0d1a;border-right:1px solid #1a1a30;}
[data-testid="stSidebar"] *{color:#c8c8e8!important;}
.main{background:#07070f;color:#e8e8f8;}
.ac{background:linear-gradient(135deg,#0f0f22,#141428);border:1px solid #252545;
    border-radius:10px;padding:12px 14px;margin:4px 0;transition:all .25s;}
.ac.running{border-color:#6c63ff;box-shadow:0 0 18px rgba(108,99,255,.4);animation:glow 1.8s ease-in-out infinite;}
.ac.done{border-color:#00c99a;background:linear-gradient(135deg,#001a12,#001f18);}
.ac.error{border-color:#ff5555;}
.ac.skip{opacity:.3;}
@keyframes glow{0%,100%{box-shadow:0 0 8px rgba(108,99,255,.2)}50%{box-shadow:0 0 22px rgba(108,99,255,.6)}}
.ar{font-size:9px;text-transform:uppercase;letter-spacing:2.5px;color:#6c63ff;font-family:'Space Mono',monospace;}
.an{font-size:13px;font-weight:700;color:#e8e8f8;margin:2px 0;}
.ad{font-size:10px;color:#50507a;line-height:1.4;}
.ab{display:inline-block;padding:2px 9px;border-radius:8px;font-size:9px;
    font-family:'Space Mono',monospace;margin-top:5px;}
.b-idle{background:#101028;color:#40406a;border:1px solid #252545;}
.b-running{background:#1a1030;color:#6c63ff;border:1px solid #6c63ff60;}
.b-done{background:#001810;color:#00c99a;border:1px solid #00c99a60;}
.b-error{background:#200010;color:#ff5555;border:1px solid #ff555560;}
.b-skip{background:#101028;color:#303060;border:1px solid #202040;}
.mt{background:#0e0e20;border:1px solid #252545;border-radius:10px;padding:14px 12px;text-align:center;}
.mv{font-size:24px;font-weight:800;font-family:'Space Mono',monospace;}
.ml{font-size:9px;color:#50507a;text-transform:uppercase;letter-spacing:1.5px;margin-top:3px;}
.ob{background:#0b0b1e;border:1px solid #252545;border-radius:8px;padding:14px;
    font-family:'Space Mono',monospace;font-size:11.5px;color:#9898c8;
    max-height:500px;overflow-y:auto;white-space:pre-wrap;line-height:1.75;}
.cn{font-size:44px;font-weight:800;font-family:'Space Mono',monospace;
    background:linear-gradient(135deg,#6c63ff,#00d4ff);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.pr{display:flex;align-items:center;gap:8px;margin:4px 0;}
.pn{width:150px;color:#6868a0;font-family:'Space Mono',monospace;font-size:10px;}
.pb{flex:1;height:5px;background:#141428;border-radius:3px;overflow:hidden;}
.pf{height:100%;border-radius:3px;}
.pv{width:44px;text-align:right;font-family:'Space Mono',monospace;font-size:10px;}
.fw{display:flex;flex-wrap:wrap;align-items:center;gap:0;margin:12px 0 20px;}
.fn{padding:6px 11px;border-radius:6px;font-size:11px;font-family:'Space Mono',monospace;
    background:#0e0e20;border:1px solid #252545;color:#505080;white-space:nowrap;}
.fn.running{background:#1a1030;border-color:#6c63ff;color:#6c63ff;}
.fn.done{background:#001810;border-color:#00c99a;color:#00c99a;}
.fn.skip{opacity:.3;}
.fa{color:#303060;padding:0 3px;font-size:13px;}
.dl{font-size:9px;text-transform:uppercase;letter-spacing:3px;color:#2a2a50;
    font-family:'Space Mono',monospace;padding:10px 0 4px;
    border-top:1px solid #141428;margin-top:8px;}
.mode-a{display:inline-block;padding:4px 14px;border-radius:12px;font-size:11px;
         font-weight:700;font-family:'Space Mono',monospace;
         background:#1a1030;color:#6c63ff;border:1px solid #6c63ff55;}
.mode-b{display:inline-block;padding:4px 14px;border-radius:12px;font-size:11px;
         font-weight:700;font-family:'Space Mono',monospace;
         background:#001810;color:#00c99a;border:1px solid #00c99a55;}
.stButton>button{background:linear-gradient(135deg,#6c63ff,#00d4ff)!important;
    color:#fff!important;border:none!important;border-radius:8px!important;
    font-weight:700!important;padding:9px 22px!important;}
.stButton>button:hover{opacity:.82!important;}
.stDownloadButton>button{background:#0f0f22!important;color:#c8c8e8!important;
    border:1px solid #3a3a6a!important;border-radius:8px!important;
    font-family:'Space Mono',monospace!important;font-size:12px!important;}
.stDownloadButton>button:hover{border-color:#6c63ff!important;color:#fff!important;}
</style>""", unsafe_allow_html=True)

# ── Agent definitions ─────────────────────────────────────────────────────────
AGENTS_ANALYSE = {
    "Core": [
        {"id":"research",  "name":"Research Agent",   "emoji":"🔍", "desc":"Facts, context, references"},
        {"id":"analysis",  "name":"Analysis Agent",   "emoji":"🧠", "desc":"Critical thinking, patterns"},
        {"id":"writer",    "name":"Writer Agent",     "emoji":"✍️",  "desc":"Synthesises final output"},
    ],
    "Business": [
        {"id":"marketing", "name":"Marketing Agent",  "emoji":"📣", "desc":"Audiences, messaging, GTM"},
        {"id":"sales",     "name":"Sales Agent",      "emoji":"💼", "desc":"ICP, funnel, pricing, KPIs"},
        {"id":"finance",   "name":"Finance Agent",    "emoji":"💰", "desc":"P&L, CAC/LTV, projections"},
    ],
    "Compliance": [
        {"id":"evaluate",  "name":"Ethics Evaluator", "emoji":"⚖️",  "desc":"COS: Bias, Safety, Privacy"},
    ],
}
AGENTS_BUILD = {
    "Core": [
        {"id":"research",      "name":"Research Agent",    "emoji":"🔍", "desc":"Tech research & benchmarks"},
        {"id":"analysis",      "name":"Analysis Agent",    "emoji":"🧠", "desc":"Requirements analysis"},
        {"id":"writer",        "name":"Writer Agent",      "emoji":"✍️",  "desc":"Spec & documentation"},
    ],
    "Engineering": [
        {"id":"architect",     "name":"Architect Agent",   "emoji":"🏗️", "desc":"System design, DB schema, API"},
        {"id":"backend_coder", "name":"Backend Engineer",  "emoji":"⚙️",  "desc":"FastAPI, SQLAlchemy, Docker"},
        {"id":"frontend_coder","name":"Frontend Engineer", "emoji":"🎨", "desc":"Next.js 14, TypeScript, Tailwind"},
    ],
    "Compliance": [
        {"id":"evaluate",      "name":"Ethics Evaluator",  "emoji":"⚖️",  "desc":"COS ethical evaluation"},
    ],
}
PIPELINE_ANALYSE = ["research","analysis","writer","marketing","sales","finance","evaluate"]
PIPELINE_BUILD   = ["research","analysis","writer","architect","backend_coder","frontend_coder","evaluate"]
NODE_OUTPUT = {
    "research":"research_output", "analysis":"analysis_output", "writer":"final_output",
    "marketing":"marketing_output", "sales":"sales_output", "finance":"finance_output",
    "architect":"architect_output", "backend_coder":"backend_code",
    "frontend_coder":"frontend_code", "evaluate":"final_output",
}
ALL_IDS = set(PIPELINE_ANALYSE + PIPELINE_BUILD)

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "statuses":{a:"idle" for a in ALL_IDS}, "outputs":{},
    "last_result":None, "run_history":[], "tenant_id":"demo",
    "wf_mode":"analyse", "_run_pending":False, "_run_query":"",
    "_run_provider":"groq", "_run_model":"llama-3.1-8b-instant",
    "_run_tenant":"demo", "_run_thresh":0.7, "_run_mode":"analyse", "_last_query":"",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⬡ CATERYA")
    st.markdown(
        "<div style='font-size:9px;color:#2a2a50;letter-spacing:2.5px;"
        "text-transform:uppercase;margin-bottom:14px'>Enterprise · Ethical AI</div>",
        unsafe_allow_html=True)
    _mode = st.session_state.get("wf_mode","analyse")
    _amap = AGENTS_BUILD if _mode=="build" else AGENTS_ANALYSE
    _pipe = PIPELINE_BUILD if _mode=="build" else PIPELINE_ANALYSE
    for dept, agents in _amap.items():
        st.markdown(f"<div class='dl'>{dept}</div>", unsafe_allow_html=True)
        for ag in agents:
            s    = st.session_state.statuses.get(ag["id"],"idle")
            skip = ag["id"] not in _pipe
            css  = "skip" if skip else s
            clr_map = {"idle":"#303060","running":"#6c63ff","done":"#00c99a","error":"#ff5555","skip":"#202040"}
            icon_map = {"idle":"○","running":"◉","done":"✓","error":"✗","skip":"—"}
            clr  = clr_map.get(css,"#303060")
            icon = icon_map.get(css,"○")
            lbl  = s if not skip else "skip"
            st.markdown(
                f"<div class='ac {css}' style='padding:9px 12px;margin:3px 0'>"
                f"{ag['emoji']} "
                f"<span style='font-size:12px;font-weight:700;color:#d8d8f0'>{ag['name']}</span>"
                f"<div class='ab b-{css}' style='color:{clr}'>{icon} {lbl}</div>"
                f"</div>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(
        "<div style='font-size:9px;text-transform:uppercase;letter-spacing:2px;"
        "color:#2a2a50;font-family:Space Mono,mono;padding-bottom:6px'>LLM Providers</div>",
        unsafe_allow_html=True)
    for pname,(pok,pm,pe) in PROVIDERS.items():
        dot = "🟢" if pok else "🔴"
        clr = "#40407a" if pok else "#303050"
        st.markdown(
            f"<div style='font-size:10px;font-family:Space Mono,mono;padding:2px 0;color:{clr}'>"
            f"{dot} {pname}</div>", unsafe_allow_html=True)
    if st.session_state.run_history:
        st.markdown("---")
        for h in reversed(st.session_state.run_history[-4:]):
            cos=h.get("cos",0); c="#00c99a" if cos>=0.7 else "#ffaa00"
            m=h.get("mode","?")[0].upper()
            st.markdown(
                f"<div style='font-size:10px;font-family:Space Mono,mono;padding:3px 0;color:#38386a'>"
                f"[{m}] <span style='color:{c}'>COS {cos:.3f}</span>"
                f" · {h.get('query','')[:22]}…</div>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
t_run,t_out,t_cos,t_export,t_eval = st.tabs([
    "⬡ Run Pipeline","📄 Outputs","📊 COS Report","⬇ Export","🔬 Evaluator"])

# ══ TAB 1 — Run ══════════════════════════════════════════════════════════════
with t_run:
    st.markdown("# ⬡ CATERYA Enterprise")

    # Mode selector
    st.markdown("### Mode")
    mc1,mc2 = st.columns(2)
    with mc1:
        if st.button("🔍 **Analyse Mode**  \nResearch · Marketing · Sales · Finance",
                     use_container_width=True):
            st.session_state.wf_mode = "analyse"
            for a in ALL_IDS: st.session_state.statuses[a]="idle"
            st.rerun()
    with mc2:
        if st.button("🏗️ **Build SaaS Mode**  \nArchitect · Backend code · Frontend code",
                     use_container_width=True):
            st.session_state.wf_mode = "build"
            for a in ALL_IDS: st.session_state.statuses[a]="idle"
            st.rerun()

    mode = st.session_state.wf_mode
    badge_cls = "mode-a" if mode=="analyse" else "mode-b"
    badge_txt = "🔍 ANALYSE MODE" if mode=="analyse" else "🏗️ BUILD SAAS MODE"
    st.markdown(
        f"<span class='{badge_cls}'>{badge_txt}</span>",
        unsafe_allow_html=True)
    st.markdown("")

    # Metrics
    if st.session_state.last_result:
        r=st.session_state.last_result; cr=r.get("cos_result",{})
        if not isinstance(cr,dict): cr={}
        cos=cr.get("cos",0.0)
        done=sum(1 for s in st.session_state.statuses.values() if s=="done")
        mc=st.columns(4)
        data=[
            (f"{cos:.4f}","COS Score","#6c63ff" if cos>=0.7 else "#ff5555"),
            ("PASS" if cos>=0.7 else "FAIL","Status","#00c99a" if cos>=0.7 else "#ff5555"),
            (f"{done}/{len(ALL_IDS)}","Agents Done","#6c63ff"),
            (r.get("workflow_mode","?").upper(),"Last Mode","#6c63ff"),
        ]
        for col,(val,lbl,clr) in zip(mc,data):
            with col:
                st.markdown(
                    f"<div class='mt'><div class='mv' style='color:{clr}'>{val}</div>"
                    f"<div class='ml'>{lbl}</div></div>", unsafe_allow_html=True)
        st.markdown("")

    # Pipeline flow diagram
    pipe      = PIPELINE_BUILD if mode=="build" else PIPELINE_ANALYSE
    amap      = AGENTS_BUILD   if mode=="build" else AGENTS_ANALYSE
    aflatlist = [a for d in amap.values() for a in d]
    flow = "<div class='fw'>"
    for i,nid in enumerate(pipe):
        s   = st.session_state.statuses.get(nid,"idle")
        css = "done" if s=="done" else ("running" if s=="running" else "")
        ag  = next((a for a in aflatlist if a["id"]==nid),{"emoji":"⬡","name":nid})
        flow += f"<span class='fn {css}'>{ag['emoji']} {ag['name']}</span>"
        if i < len(pipe)-1: flow += "<span class='fa'>→</span>"
    flow += "</div>"
    st.markdown(flow, unsafe_allow_html=True)

    # Agent cards by department
    for dept_name, agents in amap.items():
        st.markdown(f"**{dept_name}**")
        cols = st.columns(len(agents))
        for col, agent in zip(cols, agents):
            s = st.session_state.statuses.get(agent["id"],"idle")
            with col:
                st.markdown(
                    f"<div class='ac {s}'>"
                    f"<div style='font-size:22px'>{agent['emoji']}</div>"
                    f"<div class='ar'>{dept_name}</div>"
                    f"<div class='an'>{agent['name']}</div>"
                    f"<div class='ad'>{agent['desc']}</div>"
                    f"<div class='ab b-{s}'>{s.upper()}</div></div>",
                    unsafe_allow_html=True)
        st.markdown("")

    st.markdown("---")
    st.markdown("## 🚀 Launch Agents")

    if mode == "build":
        st.info(
            "**Build mode** menghasilkan kode lengkap: arsitektur sistem, "
            "FastAPI backend (models, schemas, routers, auth, docker), "
            "Next.js 14 frontend (pages, API client, auth, components). "
            "Gunakan model lebih besar untuk kode terbaik: "
            "`llama-3.3-70b-versatile` (Groq) atau `openai/gpt-4o-mini` (OpenRouter).")

    with st.form("run_form", clear_on_submit=False):
        if mode == "build":
            ph = (
                "e.g. Build a multi-tenant project management SaaS with Kanban boards, "
                "real-time collaboration, AI sprint planning, time tracking, and Stripe billing.\n"
                "e.g. Build a B2B invoicing SaaS with multi-currency, automated reminders, "
                "PDF generation, and QuickBooks integration.")
        else:
            ph = (
                "e.g. What are the ethical implications of AI in hiring decisions?\n"
                "e.g. Analyse the SaaS market opportunity for project management in Southeast Asia.")
        query = st.text_area("Query / Product Brief",
                             value=st.session_state.get("_last_query",""),
                             placeholder=ph, height=100)
        c1,c2,c3,c4 = st.columns(4)
        all_p = ["groq","openrouter","together","fireworks","gemini","ollama"]
        dp,dm = _default_provider()
        def_i = all_p.index(dp) if dp in all_p else 0
        with c1:
            provider = st.selectbox("LLM Provider", all_p, index=def_i,
                format_func=lambda p: ("✅ " if PROVIDERS[p][0] else "❌ ")+p)
        with c2:
            _default_model = PROVIDERS[provider][1]
            model = st.text_input(
                "Model",
                value=_default_model,
                help=(
                    "Ollama: qwen3.5 (text) | qwen3-vl (vision)\n"
                    "Groq: llama-3.3-70b-versatile | llama-3.1-8b-instant\n"
                    "Gemini: gemini-2.0-flash | gemini-1.5-pro"
                ),
            )
        with c3:
            tenant_id = st.text_input("Tenant ID", value=st.session_state.tenant_id)
        with c4:
            threshold = st.slider("COS min", 0.5, 0.99, 0.7, 0.01)
        prov_ok,_,prov_env = PROVIDERS.get(provider,(False,"","API_KEY"))
        if not prov_ok:
            st.warning(f"⚠️ {provider} key belum diset — tambahkan `{prov_env}` ke Streamlit Secrets")
        submitted = st.form_submit_button("⬡ Launch All Agents", use_container_width=True)

    if submitted:
        if not query.strip():
            st.warning("Masukkan query terlebih dahulu.")
        else:
            updates = {
                "_run_pending":True, "_run_query":query.strip(),
                "_run_provider":provider, "_run_model":model,
                "_run_tenant":tenant_id, "_run_thresh":threshold,
                "_run_mode":mode, "tenant_id":tenant_id, "_last_query":query.strip(),
            }
            for k,v in updates.items(): st.session_state[k]=v
            for a in ALL_IDS: st.session_state.statuses[a]="idle"
            st.session_state.outputs = {}
            st.rerun()

    # ── Pipeline execution ────────────────────────────────────
    if st.session_state._run_pending:
        st.session_state._run_pending = False
        q         = st.session_state._run_query
        provider  = st.session_state._run_provider
        model     = st.session_state._run_model
        tenant_id = st.session_state._run_tenant
        threshold = st.session_state._run_thresh
        wf_mode   = st.session_state._run_mode

        st.markdown(f"**Running [{wf_mode.upper()}]:** _{q[:80]}_")
        prog = st.progress(0, text="Initialising agents…")
        try:
            from workflows.langgraph_workflow import CateryaWorkflow
            wf = CateryaWorkflow(
                tenant_id=tenant_id, cos_threshold=threshold,
                llm_provider=provider, llm_model=model)
            pipe_nodes = PIPELINE_BUILD if wf_mode=="build" else PIPELINE_ANALYSE
            result = {}
            amap_run = AGENTS_BUILD if wf_mode=="build" else AGENTS_ANALYSE
            aflatrun = [a for d in amap_run.values() for a in d]

            with st.status("⬡ Pipeline running…", expanded=True) as sw:
                done_count = 0
                for node_name, node_state in wf.stream(q, workflow_mode=wf_mode):
                    if not isinstance(node_state,dict): continue
                    result.update(node_state)
                    done_count += 1
                    pct = min(int(done_count/len(pipe_nodes)*95), 95)
                    prog.progress(pct, text=f"✓ {node_name.replace('_',' ').title()}")
                    if node_name in st.session_state.statuses:
                        st.session_state.statuses[node_name] = "done"
                    fld = NODE_OUTPUT.get(node_name)
                    if fld and node_state.get(fld):
                        st.session_state.outputs[node_name] = str(node_state[fld])
                    em = next((a["emoji"] for a in aflatrun if a["id"]==node_name),"⬡")
                    snippet = str(node_state.get(fld,"") if fld else "")[:300]
                    st.write(f"**{em} {node_name.replace('_',' ').title()}** — complete")
                    if snippet:
                        st.caption(snippet+("…" if len(snippet)==300 else ""))
                sw.update(label="✓ Pipeline complete", state="complete", expanded=False)

            prog.progress(100, text="Done ✓")
            if not isinstance(result,dict): result={}
            cr = result.get("cos_result")
            if hasattr(cr,"to_dict"): result["cos_result"]=cr.to_dict()
            elif not isinstance(cr,dict): result["cos_result"]={"cos":0.0}
            result["workflow_mode"] = wf_mode
            for node,fld in NODE_OUTPUT.items():
                if result.get(fld) and node not in st.session_state.outputs:
                    st.session_state.outputs[node] = str(result[fld])
            cos = result.get("cos_result",{}).get("cos",0.0)
            st.session_state.last_result = result
            st.session_state.wf_mode     = wf_mode
            st.session_state.run_history.append({"query":q[:60],"cos":cos,"mode":wf_mode})
            if cos >= threshold:
                st.success(f"✅ COS: **{cos:.4f}** — PASS  ·  Lihat tab **📄 Outputs** dan **⬇ Export**")
            else:
                st.warning(f"⚠️ COS: **{cos:.4f}** — di bawah threshold {threshold}")

        except Exception as exc:
            prog.empty()
            exc_s = str(exc)
            if "Connection refused" in exc_s or "11434" in exc_s:
                st.error("Ollama tidak tersedia di Streamlit Cloud.")
                st.info("Gunakan Groq (gratis): console.groq.com → buat key → Streamlit Secrets → GROQ_API_KEY")
            elif "decommissioned" in exc_s or "deprecated" in exc_s:
                st.error(f"Model `{model}` sudah dihentikan.")
                st.info("Untuk Groq gunakan: `llama-3.1-8b-instant` atau `llama-3.3-70b-versatile`")
            elif "401" in exc_s or "invalid_api_key" in exc_s.lower() or "authentication" in exc_s.lower():
                env = PROVIDERS.get(provider,(False,"","API_KEY"))[2]
                st.error(f"API key `{provider}` tidak valid. Periksa `{env}` di Streamlit → Settings → Secrets")
            else:
                st.error(f"Pipeline error: {exc_s[:400]}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())

# ══ TAB 2 — Outputs ══════════════════════════════════════════════════════════
with t_out:
    st.markdown("# 📄 Agent Outputs")
    r = st.session_state.last_result
    if not r:
        st.info("Jalankan pipeline dari tab **⬡ Run Pipeline** terlebih dahulu.")
    else:
        _outmode = r.get("workflow_mode","analyse")
        st.markdown(f"Mode: **{_outmode.upper()}**")
        if _outmode == "build":
            _secs = [
                ("🔍 Research",           "research",      "research_output"),
                ("🧠 Analysis",           "analysis",      "analysis_output"),
                ("✍️ Specification",      "writer",        "final_output"),
                ("🏗️ Architecture Design","architect",     "architect_output"),
                ("⚙️ Backend Code",       "backend_coder", "backend_code"),
                ("🎨 Frontend Code",      "frontend_coder","frontend_code"),
            ]
        else:
            _secs = [
                ("🔍 Research",            "research",  "research_output"),
                ("🧠 Analysis",            "analysis",  "analysis_output"),
                ("✍️ Final Synthesis",     "writer",    "final_output"),
                ("📣 Marketing Strategy",  "marketing", "marketing_output"),
                ("💼 Sales Strategy",      "sales",     "sales_output"),
                ("💰 Financial Projection","finance",   "finance_output"),
            ]
        for label, node, fld in _secs:
            val = r.get(fld) or st.session_state.outputs.get(node,"")
            if val:
                _exp = node in ("backend_coder","frontend_coder","architect")
                with st.expander(label, expanded=_exp):
                    st.markdown(f"<div class='ob'>{val}</div>", unsafe_allow_html=True)
                    st.download_button(
                        f"⬇ Download {node}.txt", data=val,
                        file_name=f"{node}_output.txt", mime="text/plain",
                        key=f"dl_txt_{node}")
        _chain = r.get("provenance_chain",[])
        if _chain:
            with st.expander(f"📜 ProvenanceChain ({len(_chain)} records)"):
                st.json(_chain[-3:] if len(_chain)>3 else _chain)
        with st.expander("🔧 Raw state (debug)"):
            st.json({k:v for k,v in r.items() if k!="provenance_chain"})

# ══ TAB 3 — COS Report ═══════════════════════════════════════════════════════
with t_cos:
    st.markdown("# ⚖️ Ethical Evaluation")
    r = st.session_state.last_result
    if not r:
        st.info("Jalankan pipeline terlebih dahulu.")
    else:
        cr = r.get("cos_result",{})
        if not isinstance(cr,dict): cr={}
        cos = cr.get("cos",0.0)
        pass_clr = "#00c99a" if cos>=0.7 else "#ff5555"
        pass_txt = "✅ PASS" if cos>=0.7 else "❌ FAIL"
        st.markdown(
            f"<div style='margin:16px 0'>"
            f"<div class='cn'>{cos:.4f}</div>"
            f"<div style='font-size:13px;margin-top:6px;font-family:Space Mono,mono;"
            f"color:{pass_clr}'>{pass_txt}</div></div>",
            unsafe_allow_html=True)
        for p in cr.get("pillars",[]):
            score=p.get("score",0)
            name=p.get("name","").replace("_"," ").title()
            pct=int(score*100)
            pclr="#00c99a" if score>=0.7 else ("#ffaa00" if score>=0.5 else "#ff5555")
            st.markdown(
                f"<div class='pr'>"
                f"<div class='pn'>{name}</div>"
                f"<div class='pb'><div class='pf' style='width:{pct}%;background:{pclr}'></div></div>"
                f"<div class='pv' style='color:{pclr}'>{score:.3f}</div></div>",
                unsafe_allow_html=True)
        if cr.get("pillars"):
            with st.expander("Full JSON"): st.json(cr)

# ══ TAB 4 — Export ═══════════════════════════════════════════════════════════
with t_export:
    st.markdown("# ⬇ Export Results")
    r = st.session_state.last_result
    if not r:
        st.info("Jalankan pipeline terlebih dahulu, lalu export hasilnya di sini.")
    else:
        _emode  = r.get("workflow_mode","analyse")
        _equery = st.session_state.get("_last_query","CATERYA Report")
        st.markdown(f"**Mode:** {_emode.upper()}  ·  **Query:** _{_equery[:80]}_")
        st.markdown("")
        try:
            import base64 as _b64
            from src.caterya.utils.export import to_markdown, to_html, to_pdf
            ec1,ec2,ec3,ec4 = st.columns(4)

            with ec1:
                st.markdown("### 📝 Markdown")
                st.caption("Notion, Obsidian, GitHub")
                try:
                    md_out = to_markdown(r, mode=_emode, query=_equery)
                    st.download_button("⬇ Download .md", data=md_out.encode("utf-8"),
                        file_name="caterya_report.md", mime="text/markdown",
                        use_container_width=True, key="dl_md")
                    with st.expander("Preview"):
                        st.markdown(md_out[:2500]+("\n…" if len(md_out)>2500 else ""))
                except Exception as ex: st.error(str(ex))

            with ec2:
                st.markdown("### 🌐 HTML")
                st.caption("Dark-theme, buka di browser")
                try:
                    html_out = to_html(r, mode=_emode, query=_equery)
                    st.download_button("⬇ Download .html", data=html_out.encode("utf-8"),
                        file_name="caterya_report.html", mime="text/html",
                        use_container_width=True, key="dl_html")
                    with st.expander("Source preview"):
                        st.code(html_out[:1500]+"…", language="html")
                except Exception as ex: st.error(str(ex))

            with ec3:
                st.markdown("### 📄 PDF")
                st.caption("ReportLab — via base64 link (Streamlit binary-safe)")
                try:
                    pdf_out = to_pdf(r, mode=_emode, query=_equery)
                    if not isinstance(pdf_out, bytes) or pdf_out[:4] != b'%PDF':
                        st.error("PDF generation failed — file bukan PDF valid.")
                        st.code(pdf_out[:300].decode("utf-8","ignore"))
                    else:
                        # Use base64 HTML link — bypasses Streamlit binary serialization
                        # that can corrupt PDF bytes in some deployments
                        b64_pdf = _b64.b64encode(pdf_out).decode("ascii")
                        _pdf_href = (
                            f'<a href="data:application/pdf;base64,{b64_pdf}" '
                            f'download="caterya_report.pdf" '
                            f'style="display:inline-block;padding:10px 22px;'
                            f'background:linear-gradient(135deg,#6c63ff,#00d4ff);'
                            f'color:#fff;border-radius:8px;font-weight:700;'
                            f'font-family:Space Mono,monospace;font-size:13px;'
                            f'text-decoration:none;width:100%;text-align:center;'
                            f'box-sizing:border-box">'
                            f'⬇ Download .pdf ({len(pdf_out)//1024} KB)</a>'
                        )
                        st.markdown(_pdf_href, unsafe_allow_html=True)
                        st.caption(
                            f"Valid PDF · {len(pdf_out):,} bytes · "
                            f"{'✅ opens in all viewers' if pdf_out[:4]==b'%PDF' else '❌ invalid'}"
                        )
                except Exception as ex:
                    st.error(f"PDF error: {ex}")
                    import traceback as _tb; st.code(_tb.format_exc())

            with ec4:
                st.markdown("### {} JSON")
                st.caption("Machine-readable full result")
                _jsafe = _json.dumps(
                    {k:v for k,v in r.items() if k!="provenance_chain"},
                    indent=2, default=str)
                st.download_button("⬇ Download .json", data=_jsafe.encode("utf-8"),
                    file_name="caterya_result.json", mime="application/json",
                    use_container_width=True, key="dl_json")

        except ImportError as ex:
            st.error(f"Export engine tidak ditemukan: {ex}")
            st.info("Pastikan `src/caterya/utils/export.py` sudah di-push ke GitHub.")

# ══ TAB 5 — Standalone Evaluator ════════════════════════════════════════════
with t_eval:
    st.markdown("# 🔬 Standalone COS Evaluator")
    st.markdown(
        "<div style='color:#40407a;font-size:12px;margin-bottom:16px'>"
        "Evaluasi teks apapun terhadap 5 pilar etika — tanpa LLM.</div>",
        unsafe_allow_html=True)
    _ev_txt  = st.text_area("Teks untuk dievaluasi", height=180,
                            placeholder="Tempel output, dokumen, atau kode di sini…")
    _ev_expl = st.text_area("Penjelasan/reasoning (opsional)", height=70)
    _ev1,_ev2 = st.columns([1,2])
    with _ev1: _ev_thr = st.slider("Threshold",0.0,1.0,0.7,0.01,key="ev_thr")
    with _ev2: _ev_ten = st.text_input("Tenant ID",st.session_state.tenant_id,key="ev_ten")
    if st.button("⬡ Evaluate Now") and _ev_txt.strip():
        try:
            from src.caterya.core.evaluator import CATERYAEvaluator
            ev  = CATERYAEvaluator(threshold=_ev_thr, tenant_id=_ev_ten)
            res = ev.evaluate(
                output=_ev_txt,
                context={"tenant_id":_ev_ten,"agent_id":"manual","trace_id":"ui","timestamp":"now"},
                explanation=_ev_expl or None)
            _ev_cos = res.cos
            _ev_clr = "#00c99a" if res.passed else "#ff5555"
            st.markdown(
                f"<div class='mt' style='max-width:240px;margin:14px 0'>"
                f"<div class='mv' style='color:{_ev_clr}'>{_ev_cos:.4f}</div>"
                f"<div class='ml' style='color:{_ev_clr}'>{'PASS' if res.passed else 'FAIL'}</div>"
                f"</div>", unsafe_allow_html=True)
            for p in res.pillar_scores:
                _ps=p.score; _pn=p.name.replace("_"," ").title()
                _pp=int(_ps*100)
                _pc="#00c99a" if _ps>=0.7 else ("#ffaa00" if _ps>=0.5 else "#ff5555")
                st.markdown(
                    f"<div class='pr'>"
                    f"<div class='pn'>{_pn}</div>"
                    f"<div class='pb'><div class='pf' style='width:{_pp}%;background:{_pc}'></div></div>"
                    f"<div class='pv' style='color:{_pc}'>{_ps:.3f}</div></div>",
                    unsafe_allow_html=True)
            with st.expander("Full JSON"): st.json(res.to_dict())
        except Exception as exc:
            st.error(f"Evaluation error: {exc}")
            with st.expander("Traceback"): st.code(traceback.format_exc())
