    const tg = window.Telegram?.WebApp;
    if (tg) { try { tg.ready(); tg.expand(); tg.setHeaderColor?.('#07070b'); } catch(e){} }

    const tools = [
        {icon:'🎨', name:'Image Gen',    desc:'Text → image, HD'},
        {icon:'✍️', name:'Text Writer',  desc:'Articles & posts'},
        {icon:'🎙️', name:'Voice Studio', desc:'TTS & cloning'},
        {icon:'🎬', name:'Video AI',     desc:'Short-form clips'},
        {icon:'🧠', name:'Chat GPT-Pro', desc:'Smart assistant'},
        {icon:'🔍', name:'Upscaler',     desc:'4K enhance'},
        {icon:'🎵', name:'Music AI',     desc:'Compose tracks'},
        {icon:'📝', name:'Translator',   desc:'80+ languages'},
    ];

    const history = [
        {icon:'🎨', title:'Cyberpunk samurai portrait', sub:'Image · 2 min ago',  status:'done',    label:'Done'},
        {icon:'✍️', title:'Blog post: AI in 2026',     sub:'Text · 12 min ago',  status:'done',    label:'Done'},
        {icon:'🎙️', title:'Voice clone — narrator',    sub:'Voice · 1 h ago',    status:'',        label:'Ready'},
        {icon:'🎬', title:'Product teaser clip',        sub:'Video · 3 h ago',    status:'pending', label:'Rendering'},
        {icon:'🔍', title:'Upscale: landscape_04.png',  sub:'Upscale · yesterday',status:'done',    label:'Done'},
        {icon:'🎵', title:'Lo-fi beat draft',           sub:'Music · 2 d ago',    status:'done',    label:'Done'},
    ];

    function toolCard(t){
        return `<div class="tool" onclick="toast('Opening ${t.name}…')">
        <div class="ico">${t.icon}</div>
        <h4>${t.name}</h4><p>${t.desc}</p>
        </div>`;
    }

    document.getElementById('homeTools').innerHTML = tools.slice(0,4).map(toolCard).join('');
    document.getElementById('allTools').innerHTML  = tools.map(toolCard).join('');

    function histCard(h){
        return `<div class="hist-item">
        <div class="thumb">${h.icon}</div>
        <div class="hist-body">
            <div class="hist-title">${h.title}</div>
            <div class="hist-sub">${h.sub}</div>
        </div>
        <span class="chip ${h.status}">${h.label}</span>
        </div>`;
    }

    document.getElementById('homeHist').innerHTML = history.slice(0,3).map(histCard).join('');
    document.getElementById('fullHist').innerHTML = history.map(histCard).join('');

    function switchView(name){
        document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active', v.dataset.view===name));
        document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active', b.dataset.view===name));
        document.querySelector('.scroll').scrollTo({top:0, behavior:'smooth'});
        if (tg?.HapticFeedback) tg.HapticFeedback.selectionChanged();
    }

    document.querySelectorAll('.nav-btn').forEach(btn=>{
        btn.addEventListener('click', ()=>switchView(btn.dataset.view));
    });

    function setTheme(mode){
        document.documentElement.dataset.theme = mode;
        localStorage.setItem('sylvex-theme', mode);
        document.getElementById('themeSwitch')?.classList.toggle('on', mode==='dark');
        if (tg) try { tg.setHeaderColor?.(mode==='dark' ? '#07070b' : '#eef0f7'); } catch(e){}
    }

    const saved = localStorage.getItem('sylvex-theme') || (tg?.colorScheme==='light' ? 'light':'dark');
    setTheme(saved);

    document.getElementById('themeBtn').addEventListener('click', ()=>{
        setTheme(document.documentElement.dataset.theme==='dark' ? 'light' : 'dark');
    });

    document.getElementById('themeSwitch').addEventListener('click', ()=>{
        setTheme(document.documentElement.dataset.theme==='dark' ? 'light' : 'dark');
    });

    document.getElementById('bgSwitch').addEventListener('click', function(){
        this.classList.toggle('on');
        document.body.style.setProperty('animation-play-state', this.classList.contains('on') ? 'running':'paused');
    });

    function toggleSwitch(el){ el.classList.toggle('on'); }

    let toastT;

    function toast(msg){
        const t = document.getElementById('toast');
        t.textContent = msg; t.classList.add('show');
        clearTimeout(toastT);
        toastT = setTimeout(()=>t.classList.remove('show'), 1800);
        if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
    }

    async function loadTelegramUserData() {
        const tgUser = tg?.initDataUnsafe?.user;

        if (!tgUser) {
        toast("Telegram user not found");
        return;
        }

        const telegramId = tgUser.id;

        document.getElementById("tgName").textContent = tgUser.first_name || "User";
        document.getElementById("tgUsername").textContent = tgUser.username ? "@" + tgUser.username : "@user";
        document.getElementById("tgId").textContent = "ID · " + telegramId;

        const response = await fetch(`/api/cabinet/${telegramId}`);
        const data = await response.json();

        if (!data.success) {
        return;
        }

        document.getElementById("tgBalance").textContent = data.user.balance + " ⭐";
        document.getElementById("tgStatus").textContent = data.user.subscription || "FREE";
        document.getElementById("tgGenerations").textContent = data.user.total_generations || 0;
    }

    loadTelegramUserData();
