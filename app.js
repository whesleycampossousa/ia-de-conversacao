document.addEventListener('DOMContentLoaded', () => {
    // 1. Auth Check with JWT
    const isLoginPage = document.body.classList.contains('login-page') || window.location.href.includes('login.html') || window.location.href.includes('index.html') || window.location.pathname === '/' || window.location.pathname === '';

    // If on login page but already authenticated, redirect based on role
    if (isLoginPage && apiClient.isAuthenticated()) {
        const user = apiClient.getUser();
        if (user && user.is_admin) {
            window.location.href = 'admin.html';
        } else {
            window.location.href = 'dashboard.html';
        }
        return;
    }

    if (isLoginPage) {
        handleLogin();
        return; // Stop other logic on login page
    }

    // 2. Main App Logic
    // Check for audio-only mode URL param
    const urlParams = new URLSearchParams(window.location.search);
    const mode = urlParams.get('mode');
    // Resolve the current scenario context with a defensive chain:
    //   1. URL param (authoritative when arriving from scenario catalog)
    //   2. localStorage 'current_context' (survives soft reloads / back nav)
    //   3. localStorage 'last_context' (last thing the student practiced)
    //   4. 'free_conversation' as a SAFE fallback — picking coffee_shop as default
    //      silently contaminated chat/suggestions/reports when the URL was lost.
    function resolveScenarioContext() {
        const fromUrl = urlParams.get('context');
        if (fromUrl && fromUrl.trim()) return fromUrl.trim();
        try {
            const fromStorage = localStorage.getItem('current_context');
            if (fromStorage && fromStorage.trim()) return fromStorage.trim();
            const fromLast = localStorage.getItem('last_context');
            if (fromLast && fromLast.trim()) return fromLast.trim();
        } catch (_) {}
        return 'free_conversation';
    }
    const context = resolveScenarioContext();
    try { localStorage.setItem('current_context', context); } catch (_) {}
    const contextName = urlParams.get('title') || 'Practice';
    const lessonLang = urlParams.get('lessonLang') || 'en'; // 'en' or 'pt' for bilingual
    const isGrammarMode = urlParams.get('type') === 'grammar';
    const isFreeConversation = context === 'free_conversation';
    const structuredModeParam = (urlParams.get('structured') || '').toLowerCase();
    const user = apiClient.isAuthenticated() ? apiClient.getUser() : { name: 'Visitante', is_admin: false };

    // studentLevel is derived from the difficulty selector when practice starts
    let studentLevel = '';


    const MODE_LABELS_PT = {
        learning: 'Aprender',
        simulator: 'Simulador'
    };
    const MODE_LABELS_EN = {
        learning: 'Learning',
        simulator: 'Simulator'
    };
    const MODE_LABELS = {
        learning: 'Learning',
        simulator: 'Simulator'
    };

    // Objetivo mostrado ao aluno (PT, simples, evita jargão como
    // "reservation/amenities/check-in details" que confunde A1-A2).
    const COMMUNICATIVE_OBJECTIVES = {
        coffee_shop: 'Objetivo: pedir uma bebida e escolher opções (tamanho, açúcar).',
        restaurant: 'Objetivo: pedir comida e bebida de forma educada.',
        airport: 'Objetivo: apresentar passaporte e passagem, falar da bagagem.',
        hotel: 'Objetivo: dizer seu nome e fazer check-in.',
        supermarket: 'Objetivo: perguntar onde ficam os itens e pagar.',
        doctor: 'Objetivo: dizer onde dói e há quanto tempo.',
        bank: 'Objetivo: fazer uma operação simples (depósito, saque).',
        pharmacy: 'Objetivo: pedir um remédio para um sintoma.',
        gym: 'Objetivo: falar do seu objetivo e escolher um treino.',
        job_interview: 'Objetivo: falar de você e sua experiência.',
        tech_support: 'Objetivo: descrever um problema e seguir instruções.',
        hair_salon: 'Objetivo: pedir o corte que você quer.',
        clothing_store: 'Objetivo: perguntar tamanho, cor e experimentar.',
        train_station: 'Objetivo: comprar uma passagem e confirmar horário.',
        bus_stop: 'Objetivo: perguntar qual ônibus pegar.',
        renting_car: 'Objetivo: alugar um carro por alguns dias.',
        pizza_delivery: 'Objetivo: fazer um pedido e confirmar o endereço.',
        bakery: 'Objetivo: pedir pães e doces.',
        library: 'Objetivo: pegar um livro emprestado.',
        cinema: 'Objetivo: comprar ingresso e escolher a poltrona.',
        lost_found: 'Objetivo: descrever o que você perdeu.'
    };

    let recentCorrections = [];

    // =============================================
    // STRUCTURED LESSON STATE (Learning Mode)
    // =============================================
    let lessonState = {
        active: false,           // Is a structured lesson in progress?
        layer: 0,                // Current layer index
        totalLayers: 0,          // Total number of layers
        selectedOption: null,    // Currently selected option index
        selectedPhrase: null,    // The phrase object that was selected
        nextAction: 'start',     // What action to take next
        lessonTitle: '',         // Title of the lesson
        skipToLayer: null,       // For branching: skip to this layer after practice
        compositeTemplate: null, // Template for building cumulative phrase (e.g. "{verb} {size} {drink}{end}")
        compositeLayers: null,   // Which layers participate in composite (e.g. [1,2,3,4,5])
        phraseSlots: {},         // Accumulated slots from selections (e.g. {verb: "I'd like a", drink: "coffee"})
        compositePhrase: null,   // The built composite phrase for current practice
        currentOptions: []       // Available options for voice matching
    };

    // Default: Audio-First (Subtitles OFF)
    // We do NOT add 'subtitles-on' class by default.
    // User must click CC to see text.

    if (mode === 'audio-only') {
        document.body.classList.add('audio-only-mode');
        // In strict audio-only, we might want to also hide the CC button? 
        // Or just let it be strictly off initially.
        // Let's keep it consistent: user can always toggle CC if they get stuck.
    }

    // Initialize UI
    const recordBtn = document.getElementById('record-btn');
    const recordText = document.getElementById('record-text');
    const setRecordText = (text) => {
        if (recordText) {
            recordText.innerText = text;
        }
    };
    function syncMicTurnCue(statusText = '') {
        if (!recordBtn) return;
        const normalized = String(statusText || '').toLowerCase();
        const shouldShowCue = normalized.includes('listening');
        if (shouldShowCue && !recordBtn.classList.contains('recording')) {
            recordBtn.classList.add('mic-turn-highlight');
        } else {
            recordBtn.classList.remove('mic-turn-highlight');
        }
    }

    const setStatusText = (text) => {
        const friendlyStatus = {
            'Listening...': '🎤 Escutando... fale agora.',
            'Thinking...': '⏳ Pensando... preparando resposta.',
            'Speaking...': '🔊 Falando... escute e responda.',
            'Choose a question': 'Escolha uma pergunta para continuar.'
        };
        if (statusIndicator) {
            statusIndicator.textContent = friendlyStatus[text] || text;
            const normalized = String(text || '').toLowerCase();
            const isListening = normalized.includes('listening');
            statusIndicator.classList.toggle('listening', isListening);
        }
        if (recordBtn) {
            const normalized = String(text || '').toLowerCase();
            const isListening = normalized.includes('listening') && !recordBtn.classList.contains('recording');
            recordBtn.classList.toggle('listening', isListening);
        }
        syncMicTurnCue(text);
    };
    const reportBtn = document.getElementById('report-btn');
    const reportBarBtn = document.getElementById('report-bar-btn');
    const micHint = document.getElementById('mic-hint');

    // Update the mic hint text + color based on the mic button's current state.
    // Uses a MutationObserver so every existing call site (setMicReadyState,
    // recordBtn.classList.add('recording'), etc.) updates the hint for free.
    function syncMicHint() {
        if (!micHint || !recordBtn) return;
        const cls = recordBtn.classList;
        micHint.classList.remove('recording', 'processing');
        if (cls.contains('recording')) {
            micHint.textContent = '🔴 Gravando... fale agora';
            micHint.classList.add('recording');
        } else if (cls.contains('listening')) {
            micHint.textContent = '⏳ Processando sua fala...';
            micHint.classList.add('processing');
        } else if (recordBtn.disabled) {
            micHint.textContent = '⏳ Aguarde...';
            micHint.classList.add('processing');
        } else {
            micHint.textContent = 'Clique no microfone para responder';
        }
    }
    if (recordBtn && typeof MutationObserver !== 'undefined') {
        const micObserver = new MutationObserver(syncMicHint);
        micObserver.observe(recordBtn, { attributes: true, attributeFilter: ['class', 'disabled'] });
        // Initial sync
        setTimeout(syncMicHint, 0);
    }
    const chatWindow = document.getElementById('chat-window');
    const subtitleToggleBtn = document.getElementById('subtitle-toggle-btn');
    const statusIndicator = document.getElementById('status-indicator');
    const freeQuestionPanel = document.getElementById('free-question-panel');
    const freeQuestionText = document.getElementById('free-question-text');
    const freeQuestionRefresh = document.getElementById('free-question-refresh');
    const freeQuestionOk = document.getElementById('free-question-ok');
    const freeSessionModeWrap = document.getElementById('free-session-mode');
    const freeMissionPreview = document.getElementById('free-mission-preview');
    const freeTopicInput = document.getElementById('free-topic-input');
    const freeTopicChipsWrap = document.getElementById('topic-chips');
    // Barra de relatório agora é gerenciada por updateReportButton()
    const suggestionsToggleBtn = document.getElementById('suggestions-toggle-btn');
    const suggestionsPanel = document.getElementById('suggestions-panel');
    const suggestionsList = document.getElementById('suggestions-list');

    // Keep more visible turns to preserve context and reduce repetition.
    const MAX_VISIBLE_GROUPS = 12;
    const CLEAN_VIEW_VISIBLE_GROUPS = 2;
    const CLEAN_VIEW_STORAGE_KEY = 'clean_practice_view_enabled';
    const cleanPracticeViewEnabled = localStorage.getItem(CLEAN_VIEW_STORAGE_KEY) !== 'false';
    let historyExpanded = false;
    let historyToggleBtn = null;
    let historyControls = null;

    function shuffleArray(items) {
        const arr = [...items];
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function pickNonRepeatingVariant(memoryKey, variants) {
        if (!Array.isArray(variants) || variants.length === 0) return null;
        const storageKey = `variant_memory_${memoryKey}`;
        let lastIndex = -1;
        try {
            const raw = localStorage.getItem(storageKey);
            const parsed = Number.parseInt(raw, 10);
            if (Number.isInteger(parsed) && parsed >= 0 && parsed < variants.length) {
                lastIndex = parsed;
            }
        } catch (err) {
            lastIndex = -1;
        }

        let candidateIndexes = variants.map((_, idx) => idx);
        if (candidateIndexes.length > 1 && lastIndex >= 0) {
            candidateIndexes = candidateIndexes.filter(idx => idx !== lastIndex);
            if (!candidateIndexes.length) {
                candidateIndexes = variants.map((_, idx) => idx);
            }
        }

        const pickedIndex = candidateIndexes[Math.floor(Math.random() * candidateIndexes.length)];
        try {
            localStorage.setItem(storageKey, String(pickedIndex));
        } catch (err) {
            // ignore localStorage write issues (private mode, quota, etc.)
        }
        return variants[pickedIndex];
    }

    function getSubtitleGroups() {
        if (!chatWindow) return [];
        return Array.from(chatWindow.querySelectorAll('.subtitle-group'));
    }

    function updateHistoryToggleUI() {
        if (!cleanPracticeViewEnabled || !historyToggleBtn) return;
        const totalGroups = getSubtitleGroups().length;
        const hiddenCount = Math.max(0, totalGroups - Math.min(CLEAN_VIEW_VISIBLE_GROUPS, totalGroups));
        const hasHistory = hiddenCount > 0 || historyExpanded;

        historyToggleBtn.classList.toggle('has-history', hasHistory);
        historyToggleBtn.setAttribute('aria-expanded', historyExpanded ? 'true' : 'false');
        historyToggleBtn.disabled = !hasHistory && !historyExpanded;

        if (historyExpanded) {
            historyToggleBtn.textContent = '▴ Ocultar histórico';
            historyToggleBtn.title = 'Fechar histórico e voltar ao modo limpo';
            return;
        }

        if (hiddenCount > 0) {
            historyToggleBtn.textContent = `▾ Ver histórico (${hiddenCount})`;
            historyToggleBtn.title = 'Abrir histórico de interações anteriores';
        } else {
            historyToggleBtn.textContent = '▾ Ver histórico';
            historyToggleBtn.title = 'Sem histórico ainda';
        }
    }

    function refreshConversationFocusView() {
        if (!chatWindow || !cleanPracticeViewEnabled) return;
        const groups = getSubtitleGroups();
        const keepFromIndex = Math.max(0, groups.length - CLEAN_VIEW_VISIBLE_GROUPS);

        groups.forEach((group, idx) => {
            const hideGroup = !historyExpanded && idx < keepFromIndex;
            group.classList.toggle('history-hidden', hideGroup);
            // Also hide/show turn dividers adjacent to hidden groups
            const prevSibling = group.previousElementSibling;
            if (prevSibling && prevSibling.classList.contains('turn-divider')) {
                prevSibling.style.display = hideGroup ? 'none' : '';
            }
        });

        chatWindow.classList.toggle('history-expanded', historyExpanded);
        updateHistoryToggleUI();

        if (!historyExpanded) {
            chatWindow.scrollTop = chatWindow.scrollHeight;
        }
    }

    function toggleConversationHistory(forceExpanded = null) {
        if (!cleanPracticeViewEnabled) return;
        if (typeof forceExpanded === 'boolean') {
            historyExpanded = forceExpanded;
        } else {
            historyExpanded = !historyExpanded;
        }
        refreshConversationFocusView();
    }

    function ensureHistoryControls() {
        if (!chatWindow || !cleanPracticeViewEnabled) return;
        if (historyControls && historyToggleBtn) {
            updateHistoryToggleUI();
            return;
        }

        historyControls = document.createElement('div');
        historyControls.className = 'conversation-history-controls';

        historyToggleBtn = document.createElement('button');
        historyToggleBtn.type = 'button';
        historyToggleBtn.className = 'history-toggle-btn';
        historyToggleBtn.addEventListener('click', () => toggleConversationHistory());

        historyControls.appendChild(historyToggleBtn);

        const parent = chatWindow.parentElement;
        if (parent) {
            parent.insertBefore(historyControls, chatWindow);
        }

        updateHistoryToggleUI();
    }

    window.toggleConversationHistory = toggleConversationHistory;
    ensureHistoryControls();

    // --- VOICE: Single voice (Chirp3-HD-Achernar) for all interactions ---
    // In structured lessons, pre-generated audio is served from cache.
    // In free conversation, TTS API generates with Achernar voice.
    const lessonVoice = isFreeConversation ? null : 'lesson';
    function getActiveVoice() {
        return lessonVoice || 'achernar';
    }

    // Hide voice selector (single voice, no selection needed)
    const voiceSelectionStep = document.getElementById('voice-selection-step');
    if (voiceSelectionStep) {
        voiceSelectionStep.style.display = 'none';
    }



    // Função global para ofuscar texto com pontos (legendas ocultas por padrão)
    window.obfuscateText = function () {
        return '(... ...)';
    };

    // TTS Speed Logic
    // Priority: URL param > user's manual setting > difficulty preset > grammar mode > 1.0
    let ttsSpeed = 1.0;
    const urlSpeed = parseFloat(urlParams.get('speed'));
    const ttsSpeedUserOverride = localStorage.getItem('tts_speed_user_set') === 'true';
    const savedTtsSpeed = parseFloat(localStorage.getItem('tts_speed'));
    const currentDifficultyForTts = localStorage.getItem('practice_difficulty') || 'intermediate';

    if (urlSpeed && !isNaN(urlSpeed)) {
        ttsSpeed = urlSpeed;
    } else if (ttsSpeedUserOverride && !isNaN(savedTtsSpeed) && savedTtsSpeed > 0) {
        ttsSpeed = savedTtsSpeed; // Respect user's manual override
    } else if (currentDifficultyForTts === 'beginner') {
        ttsSpeed = 0.85; // Preset: slow down for beginners so they can follow
    } else if (urlParams.get('type') === 'grammar') {
        ttsSpeed = 0.7;
    }
    window.ttsSpeed = ttsSpeed;

    // Dual TTS (speak PT translation after EN) — helps beginners feel comfortable
    // while still hearing the real English audio first. Opt-in.
    // RULES:
    //  - Default ON  for beginner in LEARNING mode (confidence scaffolding)
    //  - Default OFF in SIMULATOR mode regardless of level (simulator = real
    //    conversation, dual playback breaks immersion AND doubles the delay
    //    between turns — main complaint from product owner)
    //  - User's manual override always wins
    const dualTtsUserOverride = localStorage.getItem('tts_speak_pt_user_set') === 'true';
    const savedDualTts = localStorage.getItem('tts_speak_pt');
    const currentPracticeMode = localStorage.getItem('practice_mode') || 'learning';
    let speakPtTranslation;
    if (dualTtsUserOverride) {
        speakPtTranslation = savedDualTts === 'true';
    } else if (currentPracticeMode === 'simulator') {
        speakPtTranslation = false; // simulator stays fast by default
    } else {
        speakPtTranslation = currentDifficultyForTts === 'beginner';
    }
    window.speakPtTranslation = speakPtTranslation;

    // PT-first mode — play the Portuguese translation BEFORE the English audio.
    // Useful for true super-beginners (A1 just starting out) who need to know the
    // meaning before their ear engages with the English. Opt-in.
    // localStorage 'tts_pt_first' = 'true' | 'false'
    window.ptFirst = localStorage.getItem('tts_pt_first') === 'true';

    // Volume boost multiplier for TTS playback (via Web Audio API GainNode).
    // The cloned PT voice came back quiet — 1.6 = +60% compensates for that without
    // distortion on typical voice samples. User can override via localStorage.
    const savedVolumeBoost = parseFloat(localStorage.getItem('tts_volume_boost'));
    window.ttsVolumeBoost = (Number.isFinite(savedVolumeBoost) && savedVolumeBoost > 0)
        ? savedVolumeBoost
        : 1.6;

    // Suggestions for Learning Mode (Grammar)
    const suggestionSets = {
        'verb_to_be': [
            { en: 'I am happy today.', pt: 'Eu estou feliz hoje.' },
            { en: 'I am a student.', pt: 'Eu sou estudante.' },
            { en: 'She is my friend.', pt: 'Ela e minha amiga.' },
            { en: 'We are ready.', pt: 'Nos estamos prontos.' }
        ],
        'greetings': [
            { en: 'Hi, my name is Ana.', pt: 'Oi, meu nome e Ana.' },
            { en: 'Nice to meet you.', pt: 'Prazer em conhecer voce.' },
            { en: 'How are you today?', pt: 'Como voce esta hoje?' },
            { en: 'I am from Brazil.', pt: 'Eu sou do Brasil.' }
        ],
        'greetings_intros': [
            { en: 'Hi, my name is Ana.', pt: 'Oi, meu nome e Ana.' },
            { en: 'Nice to meet you.', pt: 'Prazer em conhecer voce.' },
            { en: 'How are you today?', pt: 'Como voce esta hoje?' },
            { en: 'I am from Brazil.', pt: 'Eu sou do Brasil.' }
        ],
        'articles': [
            { en: 'I have an apple.', pt: 'Eu tenho uma maca.' },
            { en: 'She bought a book.', pt: 'Ela comprou um livro.' },
            { en: 'The car is new.', pt: 'O carro e novo.' },
            { en: 'I want a coffee.', pt: 'Eu quero um cafe.' }
        ],
        'plurals': [
            { en: 'I have two cats.', pt: 'Eu tenho dois gatos.' },
            { en: 'There are three books.', pt: 'Ha tres livros.' },
            { en: 'We have many friends.', pt: 'Nos temos muitos amigos.' },
            { en: 'These are my shoes.', pt: 'Estes sao meus sapatos.' }
        ],
        'plural_nouns': [
            { en: 'I have two cats.', pt: 'Eu tenho dois gatos.' },
            { en: 'There are three books.', pt: 'Ha tres livros.' },
            { en: 'We have many friends.', pt: 'Nos temos muitos amigos.' },
            { en: 'These are my shoes.', pt: 'Estes sao meus sapatos.' }
        ],
        'demonstratives': [
            { en: 'This is my phone.', pt: 'Este e meu telefone.' },
            { en: 'That is your bag.', pt: 'Aquele e sua bolsa.' },
            { en: 'These are my keys.', pt: 'Estas sao minhas chaves.' },
            { en: 'Those are your shoes.', pt: 'Aqueles sao seus sapatos.' }
        ],
        'this_that_these_those': [
            { en: 'This is my phone.', pt: 'Este e meu telefone.' },
            { en: 'That is your bag.', pt: 'Aquele e sua bolsa.' },
            { en: 'These are my keys.', pt: 'Estas sao minhas chaves.' },
            { en: 'Those are your shoes.', pt: 'Aqueles sao seus sapatos.' }
        ],
        'subject_pronouns': [
            { en: 'I live in Sao Paulo.', pt: 'Eu moro em Sao Paulo.' },
            { en: 'She likes music.', pt: 'Ela gosta de musica.' },
            { en: 'They are at home.', pt: 'Eles estao em casa.' },
            { en: 'We study English.', pt: 'Nos estudamos ingles.' }
        ],
        'possessives': [
            { en: 'My phone is new.', pt: 'Meu celular e novo.' },
            { en: 'Your bag is here.', pt: 'Sua bolsa esta aqui.' },
            { en: 'His car is red.', pt: 'O carro dele e vermelho.' },
            { en: 'Her name is Julia.', pt: 'O nome dela e Julia.' }
        ],
        'possessive_adjectives': [
            { en: 'My phone is new.', pt: 'Meu celular e novo.' },
            { en: 'Your bag is here.', pt: 'Sua bolsa esta aqui.' },
            { en: 'His car is red.', pt: 'O carro dele e vermelho.' },
            { en: 'Her name is Julia.', pt: 'O nome dela e Julia.' }
        ],
        'object_pronouns': [
            { en: 'He called me.', pt: 'Ele me ligou.' },
            { en: 'I saw her yesterday.', pt: 'Eu a vi ontem.' },
            { en: 'We need him.', pt: 'Nos precisamos dele.' },
            { en: 'They invited us.', pt: 'Eles nos convidaram.' }
        ],
        'possessive_pronouns': [
            { en: 'This book is mine.', pt: 'Este livro e meu.' },
            { en: 'That pen is yours.', pt: 'Aquela caneta e sua.' },
            { en: 'The choice is his.', pt: 'A escolha e dele.' },
            { en: 'The house is theirs.', pt: 'A casa e deles.' }
        ],
        'reflexive_pronouns': [
            { en: 'I did it myself.', pt: 'Eu fiz isso sozinho.' },
            { en: 'She hurt herself.', pt: 'Ela se machucou.' },
            { en: 'We enjoyed ourselves.', pt: 'Nos nos divertimos.' },
            { en: 'He taught himself.', pt: 'Ele aprendeu sozinho.' }
        ],
        'present_simple': [
            { en: 'I work every day.', pt: 'Eu trabalho todo dia.' },
            { en: 'She likes coffee.', pt: 'Ela gosta de cafe.' },
            { en: 'They study at night.', pt: 'Eles estudam a noite.' },
            { en: 'We go to school.', pt: 'Nos vamos para a escola.' }
        ],
        'present_continuous': [
            { en: 'I am studying now.', pt: 'Eu estou estudando agora.' },
            { en: 'She is cooking.', pt: 'Ela esta cozinhando.' },
            { en: 'They are working.', pt: 'Eles estao trabalhando.' },
            { en: 'We are learning English.', pt: 'Nos estamos aprendendo ingles.' }
        ],
        'there_is_there_are': [
            { en: 'There is a cafe nearby.', pt: 'Ha um cafe perto.' },
            { en: 'There are two parks.', pt: 'Ha dois parques.' },
            { en: 'There is a problem.', pt: 'Ha um problema.' },
            { en: 'There are many people.', pt: 'Ha muitas pessoas.' }
        ],
        'basic_questions': [
            { en: 'What is your name?', pt: 'Qual e o seu nome?' },
            { en: 'Where do you live?', pt: 'Onde voce mora?' },
            { en: 'When do you study?', pt: 'Quando voce estuda?' },
            { en: 'Why are you here?', pt: 'Por que voce esta aqui?' }
        ],
        'countable_uncountable': [
            { en: 'I have some water.', pt: 'Eu tenho um pouco de agua.' },
            { en: 'I need two apples.', pt: 'Eu preciso de duas macas.' },
            { en: 'I bought some bread.', pt: 'Eu comprei um pouco de pao.' },
            { en: 'I have three books.', pt: 'Eu tenho tres livros.' }
        ],
        'some_any_no': [
            { en: 'Do you have any questions?', pt: 'Voce tem alguma pergunta?' },
            { en: 'I have some time.', pt: 'Eu tenho algum tempo.' },
            { en: 'I have no money.', pt: 'Eu nao tenho dinheiro.' },
            { en: 'There are no seats.', pt: 'Nao ha lugares.' }
        ],
        'quantifiers': [
            { en: 'I have a few friends.', pt: 'Eu tenho alguns amigos.' },
            { en: 'I drink a lot of coffee.', pt: 'Eu tomo muito cafe.' },
            { en: 'She has little time.', pt: 'Ela tem pouco tempo.' },
            { en: 'We read many books.', pt: 'Nos lemos muitos livros.' }
        ],
        'quantifiers_much_many_few_little': [
            { en: 'I have a few friends.', pt: 'Eu tenho alguns amigos.' },
            { en: 'I drink a lot of coffee.', pt: 'Eu tomo muito cafe.' },
            { en: 'She has little time.', pt: 'Ela tem pouco tempo.' },
            { en: 'We read many books.', pt: 'Nos lemos muitos livros.' }
        ],
        'adverbs_frequency_manner': [
            { en: 'I usually wake up early.', pt: 'Eu geralmente acordo cedo.' },
            { en: 'She always studies.', pt: 'Ela sempre estuda.' },
            { en: 'He runs quickly.', pt: 'Ele corre rapidamente.' },
            { en: 'They never smoke.', pt: 'Eles nunca fumam.' }
        ],
        'prepositions_time_place': [
            { en: 'I work at 9 am.', pt: 'Eu trabalho as 9.' },
            { en: 'The keys are on the table.', pt: 'As chaves estao na mesa.' },
            { en: 'I live in Brazil.', pt: 'Eu moro no Brasil.' },
            { en: 'I go to school.', pt: 'Eu vou para a escola.' }
        ],
        'prepositions_core': [
            { en: 'I work at 9 am.', pt: 'Eu trabalho as 9.' },
            { en: 'The keys are on the table.', pt: 'As chaves estao na mesa.' },
            { en: 'I live in Brazil.', pt: 'Eu moro no Brasil.' },
            { en: 'I go to school.', pt: 'Eu vou para a escola.' }
        ],
        'dependent_prepositions': [
            { en: 'I am good at math.', pt: 'Eu sou bom em matematica.' },
            { en: 'She is interested in music.', pt: 'Ela esta interessada em musica.' },
            { en: 'He is afraid of dogs.', pt: 'Ele tem medo de cachorros.' },
            { en: 'We are excited about the trip.', pt: 'Nos estamos animados com a viagem.' }
        ],
        'comparatives_superlatives': [
            { en: 'This is better than that.', pt: 'Isto e melhor que aquilo.' },
            { en: 'She is taller than me.', pt: 'Ela e mais alta do que eu.' },
            { en: 'This is the best day.', pt: 'Este e o melhor dia.' },
            { en: 'He is the fastest.', pt: 'Ele e o mais rapido.' }
        ],
        'order_of_adjectives': [
            { en: 'A small red car.', pt: 'Um carro pequeno e vermelho.' },
            { en: 'A beautiful old house.', pt: 'Uma casa bonita e velha.' },
            { en: 'A big black dog.', pt: 'Um cachorro grande e preto.' },
            { en: 'A nice new phone.', pt: 'Um celular novo e legal.' }
        ],
        'adjectives_order': [
            { en: 'A small red car.', pt: 'Um carro pequeno e vermelho.' },
            { en: 'A beautiful old house.', pt: 'Uma casa bonita e velha.' },
            { en: 'A big black dog.', pt: 'Um cachorro grande e preto.' },
            { en: 'A nice new phone.', pt: 'Um celular novo e legal.' }
        ],
        'adjectives_vs_adverbs': [
            { en: 'She is quick.', pt: 'Ela e rapida.' },
            { en: 'She runs quickly.', pt: 'Ela corre rapidamente.' },
            { en: 'That was loud.', pt: 'Isso foi alto.' },
            { en: 'He speaks softly.', pt: 'Ele fala suavemente.' }
        ],
        'comparative_adverbs': [
            { en: 'He drives more carefully.', pt: 'Ele dirige com mais cuidado.' },
            { en: 'She speaks faster than me.', pt: 'Ela fala mais rapido que eu.' },
            { en: 'I work better at night.', pt: 'Eu trabalho melhor a noite.' },
            { en: 'They move more slowly.', pt: 'Eles se movem mais devagar.' }
        ],
        'linking_words': [
            { en: 'I stayed home because it rained.', pt: 'Eu fiquei em casa porque choveu.' },
            { en: 'I was tired, but I went.', pt: 'Eu estava cansado, mas fui.' },
            { en: 'I was hungry, so I ate.', pt: 'Eu estava com fome, entao eu comi.' },
            { en: 'Although it was late, I worked.', pt: 'Embora estivesse tarde, eu trabalhei.' }
        ],
        'modal_deduction': [
            { en: 'It must be late.', pt: 'Deve estar tarde.' },
            { en: 'She might be at work.', pt: 'Ela talvez esteja no trabalho.' },
            { en: 'He cannot be 10.', pt: 'Ele nao pode ter 10 anos.' },
            { en: 'They could be lost.', pt: 'Eles podem estar perdidos.' }
        ],
        'future_forms': [
            { en: 'I will call you later.', pt: 'Eu vou te ligar mais tarde.' },
            { en: 'I am going to study tonight.', pt: 'Eu vou estudar hoje a noite.' },
            { en: 'It is going to rain.', pt: 'Vai chover.' },
            { en: 'I am meeting Ana at 7.', pt: 'Vou encontrar a Ana as 7.' }
        ],
        'present_perfect_basics': [
            { en: 'I have visited Mexico.', pt: 'Eu ja visitei o Mexico.' },
            { en: 'She has lived here for five years.', pt: 'Ela mora aqui ha cinco anos.' },
            { en: 'Have you ever eaten sushi?', pt: 'Voce ja comeu sushi?' },
            { en: 'I have just finished work.', pt: 'Eu acabei de terminar o trabalho.' }
        ],
        'present_perfect_continuous': [
            { en: 'I have been working all day.', pt: 'Eu tenho trabalhado o dia todo.' },
            { en: 'She has been studying a lot.', pt: 'Ela tem estudado muito.' },
            { en: 'We have been waiting here.', pt: 'Nos temos esperado aqui.' },
            { en: 'Have you been sleeping well?', pt: 'Voce tem dormido bem?' }
        ],
        'past_simple': [
            { en: 'I watched a movie yesterday.', pt: 'Eu assisti a um filme ontem.' },
            { en: 'She went to the store.', pt: 'Ela foi a loja.' },
            { en: 'We played soccer.', pt: 'Nos jogamos futebol.' },
            { en: 'Did you call me?', pt: 'Voce me ligou?' }
        ],
        'past_continuous': [
            { en: 'I was cooking when you called.', pt: 'Eu estava cozinhando quando voce ligou.' },
            { en: 'She was sleeping at 10.', pt: 'Ela estava dormindo as 10.' },
            { en: 'We were watching TV.', pt: 'Nos estavamos vendo TV.' },
            { en: 'They were working at 8.', pt: 'Eles estavam trabalhando as 8.' }
        ],
        'past_perfect': [
            { en: 'I had finished before 8.', pt: 'Eu tinha terminado antes das 8.' },
            { en: 'She had left when I arrived.', pt: 'Ela tinha saído quando eu cheguei.' },
            { en: 'We had already eaten.', pt: 'Nos ja tinhamos comido.' },
            { en: 'They had never seen it.', pt: 'Eles nunca tinham visto isso.' }
        ],
        'used_to_past_habits': [
            { en: 'I used to live in Rio.', pt: 'Eu morava no Rio.' },
            { en: 'She used to play piano.', pt: 'Ela tocava piano.' },
            { en: 'We would go to the beach.', pt: 'Nos iamos a praia.' },
            { en: 'Did you use to study English?', pt: 'Voce estudava ingles antes?' }
        ],
        'conditionals_zero_first': [
            { en: 'If I eat too much, I feel sick.', pt: 'Se eu como muito, eu passo mal.' },
            { en: 'If it rains, I will stay home.', pt: 'Se chover, eu fico em casa.' },
            { en: 'If you study, you will pass.', pt: 'Se voce estudar, voce passa.' },
            { en: 'When I finish, I will call you.', pt: 'Quando eu terminar, eu te ligo.' }
        ],
        'conditionals_second': [
            { en: 'If I had more time, I would travel.', pt: 'Se eu tivesse mais tempo, eu viajaria.' },
            { en: 'If I were rich, I would buy a house.', pt: 'Se eu fosse rico, eu compraria uma casa.' },
            { en: 'She would help if she could.', pt: 'Ela ajudaria se pudesse.' },
            { en: 'What would you do?', pt: 'O que voce faria?' }
        ],
        'conditionals_third': [
            { en: 'If I had studied, I would have passed.', pt: 'Se eu tivesse estudado, eu teria passado.' },
            { en: 'If we had left early, we would have arrived.', pt: 'Se tivessemos saído cedo, teriamos chegado.' },
            { en: 'She would have called if she had known.', pt: 'Ela teria ligado se soubesse.' },
            { en: 'Would you have gone?', pt: 'Voce teria ido?' }
        ],
        'gerunds_infinitives': [
            { en: 'I enjoy reading.', pt: 'Eu gosto de ler.' },
            { en: 'I want to learn English.', pt: 'Eu quero aprender ingles.' },
            { en: 'She decided to stay.', pt: 'Ela decidiu ficar.' },
            { en: 'We finished cleaning.', pt: 'Nos terminamos de limpar.' }
        ],
        'phrasal_verbs_basics': [
            { en: 'I wake up at 7.', pt: 'Eu acordo as 7.' },
            { en: 'She turned on the TV.', pt: 'Ela ligou a TV.' },
            { en: 'We are looking for a cafe.', pt: 'Nos estamos procurando um cafe.' },
            { en: 'He gave up smoking.', pt: 'Ele parou de fumar.' }
        ],
        'passive_voice_basics': [
            { en: 'The car was fixed.', pt: 'O carro foi consertado.' },
            { en: 'The cake was made by my mom.', pt: 'O bolo foi feito pela minha mae.' },
            { en: 'English is spoken here.', pt: 'Ingles e falado aqui.' },
            { en: 'The report was finished.', pt: 'O relatorio foi concluido.' }
        ],
        'reported_speech_basics': [
            { en: 'He said he was tired.', pt: 'Ele disse que estava cansado.' },
            { en: 'She told me to wait.', pt: 'Ela me disse para esperar.' },
            { en: 'They said they were coming.', pt: 'Eles disseram que viriam.' },
            { en: 'I asked if he was ok.', pt: 'Eu perguntei se ele estava bem.' }
        ],
        'question_tags': [
            { en: 'You are tired, aren\'t you?', pt: 'Voce esta cansado, nao esta?' },
            { en: 'He likes coffee, doesn\'t he?', pt: 'Ele gosta de cafe, nao gosta?' },
            { en: 'She is here, isn\'t she?', pt: 'Ela esta aqui, nao esta?' },
            { en: 'We can start, can\'t we?', pt: 'Podemos comecar, nao podemos?' }
        ],
        'relative_clauses': [
            { en: 'The man who lives next door is nice.', pt: 'O homem que mora ao lado e legal.' },
            { en: 'This is the book that I bought.', pt: 'Este e o livro que eu comprei.' },
            { en: 'She is the teacher who helped me.', pt: 'Ela e a professora que me ajudou.' },
            { en: 'I have a friend who speaks French.', pt: 'Eu tenho um amigo que fala frances.' }
        ],
        'future_continuous': [
            { en: 'I will be working at 8 pm.', pt: 'Eu estarei trabalhando as 8.' },
            { en: 'She will be studying tonight.', pt: 'Ela estara estudando hoje a noite.' },
            { en: 'We will be traveling tomorrow.', pt: 'Nos estaremos viajando amanha.' },
            { en: 'They will be waiting here.', pt: 'Eles estarao esperando aqui.' }
        ],
        'future_perfect': [
            { en: 'I will have finished by 6.', pt: 'Eu terei terminado ate as 6.' },
            { en: 'She will have arrived by noon.', pt: 'Ela tera chegado ate o meio-dia.' },
            { en: 'We will have completed the task.', pt: 'Nos teremos completado a tarefa.' },
            { en: 'They will have left by then.', pt: 'Eles terao saido ate la.' }
        ],
        'present_perfect_vs_past_simple': [
            { en: 'I have been to Rio.', pt: 'Eu ja fui ao Rio.' },
            { en: 'I went to Rio last year.', pt: 'Eu fui ao Rio no ano passado.' },
            { en: 'She has tried sushi.', pt: 'Ela ja provou sushi.' },
            { en: 'She tried sushi last week.', pt: 'Ela provou sushi semana passada.' }
        ],
        'wish_if_only': [
            { en: 'I wish I had more time.', pt: 'Eu queria ter mais tempo.' },
            { en: 'If only I could travel.', pt: 'Se ao menos eu pudesse viajar.' },
            { en: 'I wish I were there.', pt: 'Eu queria estar la.' },
            { en: 'If only it were easier.', pt: 'Se ao menos fosse mais facil.' }
        ],
        'zero_article': [
            { en: 'I love coffee.', pt: 'Eu amo cafe.' },
            { en: 'Dogs are friendly.', pt: 'Cachorros sao amigaveis.' },
            { en: 'I like music.', pt: 'Eu gosto de musica.' },
            { en: 'I love the coffee here.', pt: 'Eu adoro o cafe daqui.' }
        ],
        'modals_ability_permission': [
            { en: 'I can swim.', pt: 'Eu sei nadar.' },
            { en: 'Can I sit here?', pt: 'Posso sentar aqui?' },
            { en: 'She can help you.', pt: 'Ela pode ajudar voce.' },
            { en: 'We could try later.', pt: 'Nos poderiamos tentar depois.' }
        ],
        'modals_obligation': [
            { en: 'I have to work today.', pt: 'Eu tenho que trabalhar hoje.' },
            { en: 'You must wear a seatbelt.', pt: 'Voce deve usar cinto.' },
            { en: 'She needs to study.', pt: 'Ela precisa estudar.' },
            { en: 'We have to leave now.', pt: 'Nos temos que sair agora.' }
        ],
        'modals_advice': [
            { en: 'You should rest.', pt: 'Voce deveria descansar.' },
            { en: 'You should drink water.', pt: 'Voce deveria beber agua.' },
            { en: 'You ought to try it.', pt: 'Voce deveria tentar.' },
            { en: 'You should go early.', pt: 'Voce deveria ir cedo.' }
        ],
        'default': [
            { en: 'I am learning English.', pt: 'Eu estou aprendendo ingles.' },
            { en: 'I like music.', pt: 'Eu gosto de musica.' },
            { en: 'My name is Carlos.', pt: 'Meu nome e Carlos.' },
            { en: 'I live in Brazil.', pt: 'Eu moro no Brasil.' }
        ]
    };

    function normalizeIntentSource(text) {
        return String(text || '')
            .toLowerCase()
            .replace(/[^\p{L}\p{N}\s?']/gu, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function detectQuestionIntent(text) {
        const source = normalizeIntentSource(text);
        if (!source) return 'general';

        if (/(what would you like|what can i get|what can i get started|what do you want|o que voce gostaria|o que voce quer|o que posso preparar|como posso te ajudar|como posso ajudar|como posso ajudar voce)/i.test(source)) return 'order_request';
        if (/(what kind of coffee|which coffee|kind of coffee|tipo de caf[eé]|que tipo de caf[eé])/i.test(source)) return 'coffee_kind';
        if (/(what size|which size|size would you like|qual tamanho|tamanho)/i.test(source)) return 'size';
        if (/(to go|for here|take away|takeaway|para levar|consumir aqui|consumir no local)/i.test(source)) return 'to_go_here';
        if (/(hot or iced|iced or hot|quente ou gelado|gelado ou quente)/i.test(source)) return 'hot_iced';
        if (/(with sugar|with milk|sugar or milk|acucar|a[cç]ucar|leite)/i.test(source)) return 'milk_sugar';
        if (/(anything else|something else|mais alguma coisa|mais algo)/i.test(source)) return 'anything_else';
        return 'general';
    }

    const questionReplyPools = {
        order_request: [
            { en: 'I would like a hot coffee, please.', pt: 'Eu gostaria de um cafe quente, por favor.' },
            { en: 'Can I have a medium latte, please?', pt: 'Pode ser um latte medio, por favor?' },
            { en: 'Just a small black coffee, please.', pt: 'So um cafe preto pequeno, por favor.' }
        ],
        coffee_kind: [
            { en: 'A latte, please.', pt: 'Um latte, por favor.' },
            { en: 'A cappuccino, please.', pt: 'Um cappuccino, por favor.' },
            { en: 'A small black coffee, please.', pt: 'Um café preto pequeno, por favor.' }
        ],
        size: [
            { en: 'A small size, please.', pt: 'Um tamanho pequeno, por favor.' },
            { en: 'Medium is fine, thank you.', pt: 'Médio está ótimo, obrigado.' },
            { en: 'Large, please.', pt: 'Grande, por favor.' }
        ],
        to_go_here: [
            { en: 'For here, please.', pt: 'Para consumir aqui, por favor.' },
            { en: 'To go, please.', pt: 'Para viagem, por favor.' },
            { en: 'For here is fine, thanks.', pt: 'Aqui está ótimo, obrigado.' }
        ],
        hot_iced: [
            { en: 'Hot, please.', pt: 'Quente, por favor.' },
            { en: 'Iced, please.', pt: 'Gelado, por favor.' },
            { en: 'Hot is better for me.', pt: 'Quente é melhor para mim.' }
        ],
        milk_sugar: [
            { en: 'No sugar, please.', pt: 'Sem açúcar, por favor.' },
            { en: 'With milk, please.', pt: 'Com leite, por favor.' },
            { en: 'A little sugar, please.', pt: 'Um pouco de açúcar, por favor.' }
        ],
        anything_else: [
            { en: 'That is all, thank you.', pt: 'Isso é tudo, obrigado.' },
            { en: 'Yes, a cookie too, please.', pt: 'Sim, um cookie também, por favor.' },
            { en: 'No, thanks. That is all.', pt: 'Não, obrigado. Isso é tudo.' }
        ],
        general: [
            { en: 'Sure, thank you.', pt: 'Claro, obrigado.' },
            { en: 'Yes, please.', pt: 'Sim, por favor.' },
            { en: 'No, thank you.', pt: 'Não, obrigado.' }
        ]
    };

    function replyMatchesIntent(reply, intent) {
        const text = normalizeIntentSource(reply && reply.en ? reply.en : reply);
        if (!text) return false;
        if (intent === 'general') return true;
        if (intent === 'order_request') return /(i would like|i'?d like|can i have|just|coffee|latte|cappuccino|tea|espresso)/i.test(text);
        if (intent === 'coffee_kind') return /(latte|cappuccino|espresso|americano|mocha|black coffee|coffee)/i.test(text);
        if (intent === 'size') return /\b(small|medium|large)\b/i.test(text);
        if (intent === 'to_go_here') return /(to go|for here|take ?away|for here)/i.test(text);
        if (intent === 'hot_iced') return /\b(hot|iced)\b/i.test(text);
        if (intent === 'milk_sugar') return /(milk|sugar|no sugar)/i.test(text);
        if (intent === 'anything_else') return /\b(no|yes)\b|that is all|no thanks|nothing else|and also|another|one more/i.test(text);
        return true;
    }

    function dedupeSuggestionItems(items = []) {
        const seen = new Set();
        const result = [];
        items.forEach(item => {
            const candidate = item && typeof item === 'object'
                ? { en: String(item.en || '').trim(), pt: String(item.pt || '').trim() }
                : { en: String(item || '').trim(), pt: '' };
            if (!candidate.en) return;
            const key = candidate.en.toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            result.push(candidate);
        });
        return result;
    }

    function prioritizeRepliesByIntent(items = [], intentSource = '') {
        const intent = detectQuestionIntent(intentSource);
        const normalized = normalizeSuggestionItems(items);
        if (!normalized.length) return [];
        if (intent === 'general') return dedupeSuggestionItems(normalized);

        const matches = normalized.filter(item => replyMatchesIntent(item, intent));
        const rest = normalized.filter(item => !replyMatchesIntent(item, intent));
        return dedupeSuggestionItems([...matches, ...rest]);
    }

    function getIntentMatchedReplies(items = [], intentSource = '') {
        const intent = detectQuestionIntent(intentSource);
        const normalized = normalizeSuggestionItems(items);
        if (!normalized.length) return [];
        if (intent === 'general') return dedupeSuggestionItems(normalized);
        return dedupeSuggestionItems(normalized.filter(item => replyMatchesIntent(item, intent)));
    }

    function getQuestionSpecificFallbackReplies(intentSource = '') {
        const intent = detectQuestionIntent(intentSource);
        return questionReplyPools[intent] || questionReplyPools.general;
    }

    function getSuggestionsForContext(contextId, intentSource = '') {
        const intent = detectQuestionIntent(intentSource);
        const base = suggestionSets[contextId] || suggestionSets['default'];
        const prioritized = prioritizeRepliesByIntent(base, intentSource);
        const questionPool = getQuestionSpecificFallbackReplies(intentSource);
        if (intent === 'general') {
            return dedupeSuggestionItems([...prioritized, ...questionPool]);
        }
        return dedupeSuggestionItems([...questionPool, ...prioritized]);
    }

    function extractLatestQuestionFromText(text) {
        const source = sanitizeCoachDisplayText(text || '');
        if (!source) return '';
        const sentences = splitMessageIntoSentences(source).map(cleanScenarioSentence).filter(Boolean);
        return [...sentences].reverse().find(sentence => isLikelyQuestionSentence(sentence)) || '';
    }

    function rememberAIQuestionPrompt(text) {
        const question = extractLatestQuestionFromText(text);
        if (question) {
            lastAIQuestionPrompt = question;
        }
        return question;
    }

    function getLatestAIQuestionPrompt() {
        if (lastAIQuestionPrompt) return lastAIQuestionPrompt;
        if (!Array.isArray(conversationLog) || !conversationLog.length) return '';

        let fallbackSource = '';
        for (let i = conversationLog.length - 1; i >= 0; i--) {
            const item = conversationLog[i];
            if (!item || String(item.sender || '').toLowerCase() !== 'ai') continue;
            const source = sanitizeCoachDisplayText(item.text || '');
            if (!source) continue;

            const question = rememberAIQuestionPrompt(source);
            if (question) return question;
            if (!fallbackSource) fallbackSource = source;
        }
        return fallbackSource;
    }

    function getLearningPopupReplyOptions(contextId, questionPrompt = '', limit = 3) {
        const intentSource = sanitizeCoachDisplayText(questionPrompt) || String(questionPrompt || '');
        const questionPool = getQuestionSpecificFallbackReplies(intentSource);
        const contextPool = getSuggestionsForContext(contextId, intentSource);
        const matchedContext = getIntentMatchedReplies(contextPool, intentSource);
        return dedupeSuggestionItems([
            ...questionPool,
            ...matchedContext,
            ...contextPool
        ]).slice(0, Math.max(1, limit));
    }

    function normalizeSuggestionItems(rawItems = []) {
        if (!Array.isArray(rawItems)) return [];
        return rawItems.map(item => {
            if (item && typeof item === 'object') {
                const en = String(item.en || item.text || '').trim();
                const pt = String(item.pt || '').trim();
                if (!en) return null;
                return { en, pt };
            }
            const en = String(item || '').trim();
            if (!en) return null;
            return { en, pt: '' };
        }).filter(Boolean);
    }

    // Fetch dynamic suggestions from API based on AI's last message
    let lastAIMessage = ''; // Store last AI message for suggestions

    async function fetchDynamicSuggestions(aiMessage, forceOpen = false) {
        if (!aiMessage) return [];

        // Store for later use
        lastAIMessage = aiMessage;
        const intentSource = sanitizeCoachDisplayText(aiMessage) || aiMessage;

        try {
            // Show loading state
            if (suggestionsList) {
                suggestionsList.innerHTML = '<div class="suggestions-loading">Gerando sugestoes...</div>';
            }

            const baseURL = apiClient.baseURL || '';
            const response = await apiClient.fetchWithTimeout(`${baseURL}/api/suggestions`, {
                method: 'POST',
                headers: apiClient.getHeaders(),
                body: JSON.stringify({
                    aiMessage: aiMessage,
                    context: context,
                    lessonLang: lessonLang
                })
            }, 12000);

            if (!response.ok) throw new Error('Failed to fetch suggestions');

            const data = await response.json();
            const rawSuggestions = normalizeSuggestionItems(data.suggestions || data.data || data || []);

            // Priority: Gemini results FIRST, fallbacks ONLY if Gemini returned nothing
            let suggestions;
            if (rawSuggestions.length >= 3) {
                // Gemini returned enough good suggestions — use them directly
                suggestions = dedupeSuggestionItems(rawSuggestions).slice(0, 4);
            } else if (rawSuggestions.length > 0) {
                // Gemini returned some — supplement with intent-specific fallbacks only
                const intent = detectQuestionIntent(intentSource);
                const intentPool = questionReplyPools[intent] || [];
                suggestions = dedupeSuggestionItems([
                    ...rawSuggestions,
                    ...intentPool
                ]).slice(0, 4);
            } else {
                // Gemini returned nothing — use intent-specific fallback, then context
                const intentFallback = getQuestionSpecificFallbackReplies(intentSource);
                const isGrammarContext = suggestionSets.hasOwnProperty(context);
                const contextFallback = isGrammarContext ? getSuggestionsForContext(context, intentSource) : [];
                suggestions = dedupeSuggestionItems([
                    ...intentFallback,
                    ...contextFallback
                ]).slice(0, 4);
            }

            // Render suggestions
            if (suggestionsList) {
                suggestionsList.innerHTML = '';
                suggestions.forEach(item => {
                    const card = document.createElement('div');
                    card.className = 'suggestion-card';
                    const enDiv = document.createElement('div');
                    enDiv.className = 'suggestion-en';
                    enDiv.textContent = item.en;
                    card.appendChild(enDiv);

                    const ptDiv = document.createElement('div');
                    ptDiv.className = 'suggestion-pt';
                    ptDiv.textContent = item.pt || '';
                    card.appendChild(ptDiv);
                    // Add click handler to use suggestion
                    card.addEventListener('click', () => {
                        // Find text input and submit with this suggestion
                        const textInput = document.getElementById('text-input');
                        const sendBtn = document.getElementById('send-btn');
                        if (textInput && sendBtn) {
                            textInput.value = item.en;
                            sendBtn.click();
                        }
                        // Close suggestions panel
                        if (suggestionsPanel) {
                            suggestionsPanel.classList.remove('active');
                        }
                        if (suggestionsToggleBtn) {
                            suggestionsToggleBtn.textContent = 'Ver sugestoes';
                        }
                    });
                    suggestionsList.appendChild(card);
                });
            }

            if (forceOpen && suggestions.length) {
                const isHidden = suggestionsToggleBtn && suggestionsToggleBtn.style.display === 'none';
                if (!isHidden && suggestionsPanel && suggestionsToggleBtn) {
                    suggestionsPanel.classList.add('active');
                    suggestionsToggleBtn.textContent = 'Ocultar sugestoes';
                }
            }

            return suggestions;

        } catch (error) {
            console.error('[SUGGESTIONS] Error:', error);
            if (suggestionsList) {
                suggestionsList.innerHTML = '<div class="suggestions-error">Erro ao carregar sugestoes</div>';
            }
            // On API failure, use intent-specific fallback only (no generic defaults for conversation contexts)
            const intent = detectQuestionIntent(intentSource);
            const intentPool = questionReplyPools[intent] || questionReplyPools.general || [];
            const isGrammarContext = suggestionSets.hasOwnProperty(context);
            if (isGrammarContext) {
                return dedupeSuggestionItems([...intentPool, ...getSuggestionsForContext(context, intentSource)]).slice(0, 4);
            }
            return intentPool.slice(0, 4);
        }
    }

    // Fetch suggestions for popup only (no DOM rendering), based on the question being answered
    // excludeSuggestions: array of {en, pt} already shown inline — popup must show DIFFERENT ones
    async function fetchPopupSuggestions(questionText, excludeSuggestions = []) {
        if (!questionText) return [];
        try {
            const excludeList = excludeSuggestions.map(s => String(s.en || '').trim()).filter(Boolean);
            const baseURL = apiClient.baseURL || '';
            const response = await apiClient.fetchWithTimeout(`${baseURL}/api/suggestions`, {
                method: 'POST',
                headers: apiClient.getHeaders(),
                body: JSON.stringify({
                    aiMessage: questionText,
                    context: context,
                    lessonLang: lessonLang,
                    exclude: excludeList
                })
            }, 10000);
            if (!response.ok) return [];
            const data = await response.json();
            const results = normalizeSuggestionItems(data.suggestions || data.data || data || []);
            // Extra frontend dedup: remove any that still match inline suggestions
            if (excludeList.length) {
                const excludeSet = new Set(excludeList.map(t => t.toLowerCase()));
                return results.filter(r => !excludeSet.has(String(r.en || '').trim().toLowerCase()));
            }
            return results;
        } catch (e) {
            return [];
        }
    }

    function setupSuggestionsUI() {
        if (!suggestionsToggleBtn || !suggestionsPanel) return;
        updateSuggestionsVisibility();

        suggestionsToggleBtn.addEventListener('click', () => {
            const isActive = suggestionsPanel.classList.toggle('active');
            suggestionsToggleBtn.textContent = isActive ? 'Ocultar sugestoes' : 'Ver sugestoes';
        });
    }

    setupSuggestionsUI();

    function updateSuggestionsVisibility() {
        if (!suggestionsToggleBtn || !suggestionsPanel) return;
        const selectedMode = window.getSelectedMode ? window.getSelectedMode() : 'learning';
        const shouldHide = isFreeConversation || lessonState.active || selectedMode === 'simulator';
        suggestionsToggleBtn.style.display = shouldHide ? 'none' : '';
        suggestionsPanel.style.display = shouldHide ? 'none' : '';
    }

    window.updateSuggestionsVisibility = updateSuggestionsVisibility;

    function getObjectiveText() {
        const goalNote = (typeof sessionGoalTurns !== 'undefined') ? ` Meta da sessão: ${sessionGoalTurns} turnos.` : '';
        if (isGrammarMode) {
            const topic = contextName || context;
            return `Objetivo: praticar ${topic.toLowerCase()}.${goalNote}`;
        }
        const objective = COMMUNICATIVE_OBJECTIVES[context] || 'Objetivo: praticar conversa real no contexto.';
        return `${objective}${goalNote}`;
    }

    // Friendly emoji + label per scenario context. Falls back to a generic one.
    // Used to replace "BASIC STRUCTURES TRAINING" etc with "📗 Estruturas básicas" etc.
    const FRIENDLY_TITLES = {
        'coffee_shop': '☕ Cafeteria',
        'restaurant': '🍽 Restaurante',
        'airport': '✈ Aeroporto',
        'hotel': '🏨 Hotel',
        'supermarket': '🛒 Supermercado',
        'pharmacy': '💊 Farmácia',
        'doctor': '🩺 Médico',
        'bank': '🏦 Banco',
        'gym': '💪 Academia',
        'cinema': '🎬 Cinema',
        'library': '📚 Biblioteca',
        'bakery': '🥖 Padaria',
        'post_office': '📮 Correio',
        'train_station': '🚉 Estação de trem',
        'bus_stop': '🚏 Ponto de ônibus',
        'gas_station': '⛽ Posto',
        'hair_salon': '💇 Salão',
        'clothing_store': '👕 Loja de roupas',
        'pet_shop': '🐾 Pet Shop',
        'flower_shop': '💐 Floricultura',
        'dental_clinic': '🦷 Dentista',
        'tech_support': '💻 Suporte técnico',
        'pizza_delivery': '🍕 Entrega de pizza',
        'renting_car': '🚗 Alugar carro',
        'lost_found': '🧳 Achados e perdidos',
        'neighbor': '🏘 Vizinhança',
        'first_date': '💞 Primeiro encontro',
        'wedding': '💍 Casamento',
        'graduation': '🎓 Formatura',
        'school': '🏫 Escola',
        'street': '🚶 Na rua',
        'parents_house': '👨‍👩‍👧 Casa dos pais',
        'museum': '🖼 Museu',
        'park': '🌳 Parque',
        'free_conversation': '💬 Conversa livre',
        'basic_structures': '📗 Estruturas básicas'
    };
    function friendlyScenarioTitle(ctxKey, fallback) {
        const friendly = FRIENDLY_TITLES[String(ctxKey || '').toLowerCase()];
        if (friendly) return friendly;
        // Fallback: title-case the raw string, remove "Training" suffix
        const raw = String(fallback || '').replace(/\bTraining\b/i, '').trim();
        if (!raw) return '💬 Prática';
        const niced = raw.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
        return `📝 ${niced}`;
    }

    function updateHeaderInfo() {
        const modeBadge = document.getElementById('player-mode-badge');
        const levelBadge = document.getElementById('player-level-badge');
        const objectiveEl = document.getElementById('player-objective');
        const scenarioTitle = document.getElementById('player-scenario-title');
        const selectedMode = window.getSelectedMode ? window.getSelectedMode() : 'learning';
        if (scenarioTitle && contextName) scenarioTitle.textContent = friendlyScenarioTitle(context, contextName);
        if (modeBadge) {
            const lang = (window.getInterfaceLang && window.getInterfaceLang()) || 'pt';
            const labelMap = (lang === 'en') ? MODE_LABELS_EN : MODE_LABELS_PT;
            const modeLabel = labelMap[selectedMode] || selectedMode;
            modeBadge.textContent = (lang === 'en' ? `Mode: ${modeLabel}` : `Modo: ${modeLabel}`);
        }
        if (levelBadge) levelBadge.textContent = `Nivel: ${studentLevel || '--'}`;
        if (objectiveEl) objectiveEl.textContent = getObjectiveText();
        if (typeof sessionGoalTurns !== 'undefined') {
            sessionGoalTurns = resolveSessionGoalByLevel();
            updateSessionProgress({ quiet: true });
        }
    }

    function resolveSessionGoalByLevel() {
        if (isFreeConversation) return 14;
        if (studentLevel === 'A1') return 8;
        if (studentLevel === 'A2') return 10;
        if (studentLevel === 'B1') return 12;
        return 10;
    }

    window.updateHeaderInfo = updateHeaderInfo;

    function extractCorrection(text) {
        if (!text) return null;
        const enMatch = text.match(/say:\s*([^.?!]*)/i);
        if (enMatch && enMatch[1]) return enMatch[1].trim();
        const ptMatch = text.match(/diga:\s*([^.?!]*)/i);
        if (ptMatch && ptMatch[1]) return ptMatch[1].trim();
        return null;
    }

    function updateRecentCorrections(text) {
        const correction = extractCorrection(text);
        if (!correction) return;
        if (!recentCorrections.includes(correction)) {
            recentCorrections.push(correction);
        }
        recentCorrections = recentCorrections.slice(-5);
    }

    if (isFreeConversation && chatWindow) {
        chatWindow.style.display = '';
    }

    if (isFreeConversation) {
        if (freeQuestionRefresh) {
            freeQuestionRefresh.addEventListener('click', () => {
                if (!questionBank) return;
                const nextQuestion = questionBank.refreshPreview();
                showQuestionPicker(nextQuestion);
            });
        }
        if (freeQuestionOk) {
            freeQuestionOk.addEventListener('click', async () => {
                if (freeQuestionOk) freeQuestionOk.disabled = true;
                try {
                    await launchSelectedFreeMode();
                } catch (err) {
                    console.error('Free mode launch error:', err);
                    if (freeQuestionOk) freeQuestionOk.disabled = false;
                    setStatusText('Error');
                }
            });
        }
    }

    if (reportBarBtn) {
        reportBarBtn.disabled = false;
        reportBarBtn.addEventListener('click', () => sendReport());
    }

    // Auto-clear conversation when switching scenarios
    const lastContext = localStorage.getItem('last_context');
    if (lastContext && lastContext !== context) {
        // Changed scenario - clear previous conversation
        localStorage.removeItem('conversation_backup');
    }
    localStorage.setItem('last_context', context);


    if (user) {
        const headerTitle = document.querySelector('header h1');
        if (headerTitle) {
            headerTitle.innerText = `${contextName}`;
        }

        // Add subtitle/greeting
        const existingP = document.querySelector('header p');
        if (existingP) existingP.innerText = `Welcome, ${user.name}`;
    }

    const startBtn = document.getElementById('start-btn');
    const messageCounter = document.getElementById('message-counter');
    const sessionProgressBadge = document.getElementById('player-session-progress');
    const autoTranslateToggle = document.getElementById('auto-translate-toggle');

    let isRecording = false;
    let isProcessing = false;
    const conversationLog = [];
    let lastAIQuestionPrompt = '';
    let currentAudio = null; // Track current audio for skip functionality
    let ttsCancelled = false;
    let userMessageCount = 0; // Track user messages for report button
    let hasPracticeStarted = false;
    let learningFeedbackPending = false;
    let sessionGoalTurns = resolveSessionGoalByLevel();
    const seenMilestones = new Set();
    const milestoneTips = {
        2: "Bom ritmo. Tente respostas com pelo menos 6 palavras para acelerar sua fluência.",
        5: "Excelente consistência. Agora varie conectores: because, but, so, then.",
        8: "Ótimo avanço. Foque em uma resposta mais detalhada com exemplo pessoal.",
        12: "Você está sustentando conversa real. Continue por mais alguns turnos para consolidar."
    };

    function updateSessionProgress(options = {}) {
        if (!sessionProgressBadge) return;
        const turns = Math.max(0, userMessageCount);
        const clamped = Math.min(turns, sessionGoalTurns);
        sessionProgressBadge.textContent = `Progress: ${clamped}/${sessionGoalTurns}`;

        if (options.quiet || !hasPracticeStarted) return;
        if (!Object.prototype.hasOwnProperty.call(milestoneTips, turns)) return;
        if (seenMilestones.has(turns)) return;
        seenMilestones.add(turns);
        addMessage('System', milestoneTips[turns], true);
    }

    updateHeaderInfo();
    updateSessionProgress({ quiet: true });

    function setMicReadyState() {
        if (!recordBtn) return;
        recordBtn.disabled = Boolean(isUsageLimitReached || isProcessing || learningFeedbackPending);
    }

    // --- Free Conversation (Guided Cycles) ---
    const FREE_STATES = {
        INTRO_AI_ASK_HOW_ARE_YOU: 'INTRO_AI_ASK_HOW_ARE_YOU',
        INTRO_STUDENT_ANSWER: 'INTRO_STUDENT_ANSWER',
        SHOW_QUESTION_PICKER: 'SHOW_QUESTION_PICKER',
        AI_READS_MAIN_QUESTION: 'AI_READS_MAIN_QUESTION',
        STUDENT_ANSWERS_MAIN: 'STUDENT_ANSWERS_MAIN',
        AI_ASKS_FOLLOWUP: 'AI_ASKS_FOLLOWUP',
        STUDENT_ANSWERS_FOLLOWUP: 'STUDENT_ANSWERS_FOLLOWUP',
        AI_OPINION_RESPONSE: 'AI_OPINION_RESPONSE',
        AI_ASK_ADDITIONAL_QUESTIONS: 'AI_ASK_ADDITIONAL_QUESTIONS',
        STUDENT_ADDITIONAL_INTENT: 'STUDENT_ADDITIONAL_INTENT',
        STUDENT_ASKS_QUESTION: 'STUDENT_ASKS_QUESTION',
        AI_ANSWERS_STUDENT_QUESTION: 'AI_ANSWERS_STUDENT_QUESTION',
        MISSION_WAIT_ANSWER: 'MISSION_WAIT_ANSWER'
    };

    const FREE_SESSION_MODES = {
        MISSION: 'mission',
        CHAT: 'chat'
    };
    let selectedFreeSessionMode = localStorage.getItem('free_session_mode') || FREE_SESSION_MODES.MISSION;
    if (![FREE_SESSION_MODES.MISSION, FREE_SESSION_MODES.CHAT].includes(selectedFreeSessionMode)) {
        selectedFreeSessionMode = FREE_SESSION_MODES.MISSION;
    }

    const EASY_MISSIONS = [
        {
            id: 'daily_routine',
            title: 'Daily Routine',
            objective: 'Talk about your day with easy words.',
            steps: [
                'What time do you wake up?',
                'What do you do first in the morning?',
                'What do you do before sleep?'
            ]
        },
        {
            id: 'food_choices',
            title: 'Food Choices',
            objective: 'Talk about food and simple preferences.',
            steps: [
                'What do you usually eat for lunch?',
                'What food do you like most?',
                'What new food do you want to try?'
            ]
        },
        {
            id: 'week_plan',
            title: 'Week Plan',
            objective: 'Talk about simple plans for this week.',
            steps: [
                'What is one plan for this week?',
                'When will you do it?',
                'Who can help you with this plan?'
            ]
        },
        {
            id: 'city_life',
            title: 'My City',
            objective: 'Describe your city in simple sentences.',
            steps: [
                'What is your favorite place in your city?',
                'Why do you like this place?',
                'Who do you go there with?'
            ]
        },
        {
            id: 'work_or_study',
            title: 'Work or Study',
            objective: 'Talk about work or school in a natural way.',
            steps: [
                'What do you do now: work or study?',
                'What part is easy for you?',
                'What part is hard for you?'
            ]
        },
        {
            id: 'free_time',
            title: 'Free Time',
            objective: 'Talk about your free time activities.',
            steps: [
                'What do you do on weekends?',
                'What activity helps you relax?',
                'What activity do you want to do more?'
            ]
        },
        {
            id: 'family_friends',
            title: 'Family and Friends',
            objective: 'Talk about people close to you.',
            steps: [
                'Who is important in your life?',
                'What do you like to do together?',
                'What did you do together recently?'
            ]
        },
        {
            id: 'small_goals',
            title: 'Small Goals',
            objective: 'Practice clear goals and next actions.',
            steps: [
                'What is one small goal for this month?',
                'What is your first step?',
                'How will you know you finished it?'
            ]
        }
    ];

    const missionState = {
        active: false,
        mission: null,
        stepIndex: 0,
        answers: []
    };
    const LAST_EASY_MISSION_ID_KEY = 'last_easy_mission_id';
    let queuedMission = null;

    let freeState = null;
    let questionBank = null;
    let currentMainQuestion = '';
    let currentFollowupQuestion = '';
    let lastMainAnswer = '';
    let lastFollowupAnswer = '';
    let lastTransitionText = '';
    let recentTransitionHistory = [];
    const TRANSITION_HISTORY_LIMIT = 12;
    const TRANSITION_FALLBACKS = [
        'What do you want to share next?',
        'Want to continue with one more idea?',
        'What is one more point for this?',
        'Do you want a new simple question?',
        'What can we explore now?'
    ];
    let lastPickerQuestion = '';

    class QuestionBank {
        constructor(questions = [], storageKey = 'free_conversation_questions_state') {
            this.storageKey = storageKey;
            this.questions = Array.from(new Set(questions.map(q => q.trim()).filter(Boolean)));
            this.remaining = [];
            this.used = [];
            this.preview = null;
            this.loadState();
        }

        loadState() {
            const raw = localStorage.getItem(this.storageKey);
            if (raw) {
                try {
                    const parsed = JSON.parse(raw);
                    const remaining = Array.isArray(parsed.remaining) ? parsed.remaining : [];
                    const used = Array.isArray(parsed.used) ? parsed.used : [];
                    const all = new Set(this.questions);
                    this.remaining = remaining.filter(q => all.has(q));
                    this.used = used.filter(q => all.has(q));
                } catch (err) {
                    this.remaining = [];
                    this.used = [];
                }
            }
            if (!this.remaining.length) {
                this.resetPool();
            }
        }

        saveState() {
            localStorage.setItem(this.storageKey, JSON.stringify({
                remaining: this.remaining,
                used: this.used
            }));
        }

        resetPool() {
            const pool = [...this.questions];
            for (let i = pool.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [pool[i], pool[j]] = [pool[j], pool[i]];
            }
            this.remaining = pool;
            this.used = [];
            this.preview = null;
            this.saveState();
        }

        getPreview() {
            if (!this.preview) {
                if (!this.remaining.length) {
                    this.resetPool();
                }
                this.preview = this.remaining[0];
            }
            return this.preview;
        }

        refreshPreview() {
            if (this.remaining.length <= 1) {
                return this.getPreview();
            }
            let next = this.preview;
            while (next === this.preview) {
                const idx = Math.floor(Math.random() * this.remaining.length);
                next = this.remaining[idx];
            }
            this.preview = next;
            return this.preview;
        }

        confirmPreview() {
            if (!this.preview) {
                this.getPreview();
            }
            const confirmed = this.preview;
            this.markUsed(confirmed);
            this.preview = null;
            if (!this.remaining.length) {
                this.resetPool();
            } else {
                this.saveState();
            }
            return confirmed;
        }

        markUsed(question) {
            const normalized = (question || '').trim();
            if (!normalized) return;
            this.remaining = this.remaining.filter(q => q !== normalized);
            if (!this.used.includes(normalized)) {
                this.used.push(normalized);
            }
            if (this.preview === normalized) {
                this.preview = null;
            }
        }
    }

    async function loadFreeConversationQuestions() {
        const candidates = [
            'free_conversation/questions.json',
            'free_conversation/questions.txt',
            'free_conversation_questions.json',
            'free_conversation_questions.txt'
        ];

        for (const url of candidates) {
            try {
                const response = await fetch(url);
                if (!response.ok) continue;
                const contentType = response.headers.get('content-type') || '';
                if (contentType.includes('application/json') || url.endsWith('.json')) {
                    const data = await response.json();
                    if (Array.isArray(data)) return data;
                } else {
                    const text = await response.text();
                    const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
                    if (lines.length) return lines;
                }
            } catch (err) {
                continue;
            }
        }

        return [
            'What did you learn this week?',
            'What do you like to do after work or school?',
            'Where do you want to travel next?'
        ];
    }

    function pickFreeConversationIntro() {
        const intros = [
            "How are you today?",
            "How's your day going so far?",
            "How are you feeling right now?",
            "How has your week been?"
        ];
        return pickNonRepeatingVariant('free_conversation_intro', intros) || intros[0];
    }

    function queueEasyMission(forceNew = false) {
        if (!Array.isArray(EASY_MISSIONS) || !EASY_MISSIONS.length) return null;
        if (!forceNew && queuedMission) return queuedMission;

        const lastMissionId = localStorage.getItem(LAST_EASY_MISSION_ID_KEY) || '';
        let pool = EASY_MISSIONS;
        if (EASY_MISSIONS.length > 1 && lastMissionId) {
            pool = EASY_MISSIONS.filter(mission => mission.id !== lastMissionId);
        }
        if (!pool.length) {
            pool = EASY_MISSIONS;
        }

        queuedMission = pool[Math.floor(Math.random() * pool.length)];
        return queuedMission;
    }

    function consumeQueuedEasyMission() {
        const mission = queueEasyMission(false);
        if (mission && mission.id) {
            localStorage.setItem(LAST_EASY_MISSION_ID_KEY, mission.id);
        }
        queuedMission = null;
        return mission;
    }

    function getMissionStepText(stepIndex, questionText) {
        const phaseLabels = ['Warm-up', 'Practice', 'Close'];
        const phase = phaseLabels[stepIndex] || 'Step';
        const labelVariants = [
            `Mission ${stepIndex + 1}/3 (${phase}):`,
            `Step ${stepIndex + 1}/3 (${phase}):`,
            `Round ${stepIndex + 1}/3 (${phase}):`
        ];
        const label = pickNonRepeatingVariant(`mission_step_label_${stepIndex}`, labelVariants) || labelVariants[0];
        return `${label} ${questionText}`;
    }

    function updateFreeSessionModeUI() {
        if (!freeSessionModeWrap) return;
        const modeButtons = freeSessionModeWrap.querySelectorAll('.free-session-chip');
        modeButtons.forEach(btn => {
            const isSelected = btn.dataset.freeMode === selectedFreeSessionMode;
            btn.classList.toggle('selected', isSelected);
        });

        const isMissionMode = selectedFreeSessionMode === FREE_SESSION_MODES.MISSION;
        if (freeQuestionText) {
            if (isMissionMode) {
                freeQuestionText.textContent = 'Escolha como quer praticar agora.';
            } else {
                freeQuestionText.textContent = lastPickerQuestion || (questionBank ? questionBank.getPreview() : '');
            }
        }
        if (freeTopicInput) {
            freeTopicInput.style.display = isMissionMode ? 'none' : '';
        }
        if (freeTopicChipsWrap) {
            freeTopicChipsWrap.style.display = isMissionMode ? 'none' : '';
        }

        if (freeMissionPreview) {
            if (isMissionMode) {
                const mission = queueEasyMission(false);
                if (mission) {
                    freeMissionPreview.textContent = `Missao Easy: ${mission.title}. Objetivo: ${mission.objective}`;
                } else {
                    freeMissionPreview.textContent = 'Missao Easy com 3 perguntas curtas.';
                }
                freeMissionPreview.style.display = '';
            } else {
                freeMissionPreview.textContent = 'Conversa livre com tema escolhido por voce.';
                freeMissionPreview.style.display = '';
            }
        }
    }

    function bindFreeSessionModeButtons() {
        if (!freeSessionModeWrap || freeSessionModeWrap.dataset.bound === '1') return;
        freeSessionModeWrap.dataset.bound = '1';
        const modeButtons = freeSessionModeWrap.querySelectorAll('.free-session-chip');
        modeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const nextMode = btn.dataset.freeMode || FREE_SESSION_MODES.MISSION;
                selectedFreeSessionMode = nextMode;
                localStorage.setItem('free_session_mode', selectedFreeSessionMode);
                updateFreeSessionModeUI();
            });
        });
    }

    function resolveFreeTopicFromPicker() {
        const topicInput = document.getElementById('free-topic-input');
        const typedTopic = (topicInput && topicInput.value.trim()) || '';
        const previewTopic = questionBank ? questionBank.getPreview() : '';
        const chosenTopic = typedTopic || previewTopic || 'anything you want';

        if (questionBank && previewTopic && chosenTopic === previewTopic) {
            questionBank.confirmPreview();
        } else if (questionBank && chosenTopic) {
            questionBank.markUsed(chosenTopic);
            questionBank.saveState();
        }

        return chosenTopic;
    }

    function showQuestionPicker(question) {
        if (!freeQuestionPanel) return;
        lastPickerQuestion = question || '';
        freeQuestionPanel.classList.remove('hidden');
        bindFreeSessionModeButtons();
        updateFreeSessionModeUI();
        if (freeQuestionOk) {
            freeQuestionOk.disabled = false;
        }

        // Setup topic chips
        const topicChips = freeQuestionPanel.querySelectorAll('.topic-chip');
        const topicInput = document.getElementById('free-topic-input');
        if (topicInput) {
            if (question) {
                topicInput.value = question;
            } else {
                topicInput.value = '';
            }
        }

        topicChips.forEach(chip => {
            if (chip.dataset.bound === '1') return;
            chip.dataset.bound = '1';
            chip.addEventListener('click', () => {
                topicChips.forEach(c => c.classList.remove('selected'));
                chip.classList.add('selected');
                if (topicInput) topicInput.value = chip.dataset.topic;
            });
        });

        // Focus input
        if (topicInput) {
            if (topicInput.dataset.bound !== '1') {
                topicInput.dataset.bound = '1';
                topicInput.addEventListener('focus', () => {
                    topicChips.forEach(c => c.classList.remove('selected'));
                });
                topicInput.addEventListener('input', () => {
                    topicChips.forEach(c => c.classList.remove('selected'));
                });
            }
        }
    }

    function hideQuestionPicker() {
        if (!freeQuestionPanel) return;
        freeQuestionPanel.classList.add('hidden');
    }

    async function startEasyMissionFlow() {
        const mission = consumeQueuedEasyMission();
        missionState.active = true;
        missionState.mission = mission;
        missionState.stepIndex = 0;
        missionState.answers = [];

        if (!mission || !Array.isArray(mission.steps) || mission.steps.length < 3) {
            missionState.active = false;
            freeState = FREE_STATES.SHOW_QUESTION_PICKER;
            if (questionBank) {
                showQuestionPicker(questionBank.getPreview());
            } else {
                showQuestionPicker('');
            }
            setStatusText('Choose a question');
            return;
        }

        const missionIntros = [
            `Today's Easy Mission: ${mission.title}. Three short questions.`,
            `New Easy Mission: ${mission.title}. Three quick answers.`,
            `Mission mode on: ${mission.title}. Let's do 3 short questions.`,
            `Easy Mission: ${mission.title}. Ready for three questions?`
        ];
        const intro = pickNonRepeatingVariant(`mission_intro_${mission.id}`, missionIntros) || missionIntros[0];
        logConversationEntry('AI', intro);
        await playTtsOnly(intro);

        const stepText = getMissionStepText(0, mission.steps[0]);
        logConversationEntry('AI', stepText);
        await playTtsOnly(stepText);

        freeState = FREE_STATES.MISSION_WAIT_ANSWER;
        setStatusText('Listening...');
    }

    async function launchSelectedFreeMode() {
        if (selectedFreeSessionMode === FREE_SESSION_MODES.MISSION) {
            hideQuestionPicker();
            freeState = FREE_STATES.AI_READS_MAIN_QUESTION;
            setStatusText('Thinking...');
            await startEasyMissionFlow();
            return;
        }

        const chosenTopic = resolveFreeTopicFromPicker();
        currentMainQuestion = chosenTopic;
        if (freeQuestionOk) freeQuestionOk.disabled = true;
        hideQuestionPicker();
        freeState = FREE_STATES.AI_READS_MAIN_QUESTION;
        setStatusText('Thinking...');
        const introData = await apiClient.freeConversationAction('introduce_topic', {
            main_question: chosenTopic
        });
        const introText = introData.text || `Let's talk about ${chosenTopic}. What comes to mind?`;
        logConversationEntry('AI', introText);
        await playTtsOnly(introText);
        freeState = FREE_STATES.STUDENT_ANSWERS_MAIN;
        setStatusText('Listening...');
    }

    async function handleMissionInput(text) {
        if (!missionState.active || freeState !== FREE_STATES.MISSION_WAIT_ANSWER) return false;

        const mission = missionState.mission;
        if (!mission || !Array.isArray(mission.steps)) return false;

        missionState.answers.push(text);
        const currentQuestion = mission.steps[missionState.stepIndex] || mission.steps[0];

        setStatusText('Thinking...');
        if (recordBtn) {
            recordBtn.disabled = true;
            setRecordText("⏳ Pensando...");
        }

        try {
            const reactionData = await apiClient.freeConversationAction('opinion', {
                main_question: currentQuestion,
                student_answer: text
            });
            const reactionText = reactionData.text || 'Good answer. Nice and clear.';
            logConversationEntry('AI', reactionText);
            await playTtsOnly(reactionText);
        } catch (error) {
            logConversationEntry('AI', 'Good answer. Nice and clear.');
            await playTtsOnly('Good answer. Nice and clear.');
        }

        missionState.stepIndex += 1;
        if (missionState.stepIndex < 3) {
            const nextStep = getMissionStepText(
                missionState.stepIndex,
                mission.steps[missionState.stepIndex]
            );
            logConversationEntry('AI', nextStep);
            await playTtsOnly(nextStep);
            freeState = FREE_STATES.MISSION_WAIT_ANSWER;
            setStatusText('Listening...');
            return true;
        }

        let finalFeedback = '';
        try {
            const feedbackData = await apiClient.freeConversationAction('mission_feedback', {
                mission_title: mission.title,
                mission_objective: mission.objective,
                mission_steps: mission.steps,
                mission_answers: missionState.answers
            });
            finalFeedback = feedbackData.text || '';
        } catch (error) {
            finalFeedback = '';
        }

        if (!finalFeedback) {
            finalFeedback = 'Strong point: your answers were clear. Next step: add one extra detail in each answer.';
        }

        logConversationEntry('AI', finalFeedback);
        await playTtsOnly(finalFeedback);

        const completionPrompt = 'Mission complete. Do you want a new mission or free chat?';
        logConversationEntry('AI', completionPrompt);
        await playTtsOnly(completionPrompt);

        missionState.active = false;
        missionState.mission = null;
        missionState.stepIndex = 0;
        missionState.answers = [];

        freeState = FREE_STATES.SHOW_QUESTION_PICKER;
        if (questionBank) {
            const preview = questionBank.getPreview();
            showQuestionPicker(preview);
        } else {
            showQuestionPicker('');
        }
        setStatusText('Choose a question');
        return true;
    }

    function logConversationEntry(sender, text) {
        if (!text) return;
        conversationLog.push({ sender, text });
        // Also render in DOM so subtitles/captions work in free conversation
        const isAI = sender === 'AI' || sender === 'System';
        addMessage(sender, text, isAI, false); // false = don't double-log
        updateMessageCounter();
        updateReportButton();
        saveConversation();
    }

    function isNegativeResponse(text) {
        const normalized = (text || '').toLowerCase().trim();
        return [
            'no', 'nope', 'not really', 'no thanks', 'nothing else', 'nothing', 'nah',
            'nao', 'não', 'nao obrigado', 'não obrigado', 'nada', 'nada mais'
        ].some(phrase => normalized === phrase || normalized.startsWith(phrase));
    }

    function normalizeTransitionText(text) {
        return String(text || '')
            .toLowerCase()
            .replace(/[^a-z0-9\s]/g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function rememberTransitionText(text) {
        if (!text) return;
        recentTransitionHistory.push(text);
        if (recentTransitionHistory.length > TRANSITION_HISTORY_LIMIT) {
            recentTransitionHistory = recentTransitionHistory.slice(-TRANSITION_HISTORY_LIMIT);
        }
    }

    function getTransitionFallbackQuestion() {
        const used = new Set(recentTransitionHistory.map(normalizeTransitionText));
        const available = TRANSITION_FALLBACKS.filter(option => !used.has(normalizeTransitionText(option)));
        const pool = available.length ? available : TRANSITION_FALLBACKS;
        return pool[Math.floor(Math.random() * pool.length)];
    }

    function sanitizeTransitionQuestion(candidateText) {
        const bannedSnippets = [
            'what else is on your mind',
            'what would you like to talk about next',
            'do you want to talk about something else',
            'what do you want to talk about now',
            'do you have any additional questions',
            'that was interesting'
        ];

        let text = String(candidateText || '').replace(/\s+/g, ' ').trim();
        if (!text) return getTransitionFallbackQuestion();
        if (!text.endsWith('?')) {
            text = text.replace(/[.!]+$/g, '') + '?';
        }

        const normalized = normalizeTransitionText(text);
        const looksGeneric = bannedSnippets.some(snippet => normalized.includes(normalizeTransitionText(snippet)));
        const looksRepeated = recentTransitionHistory.some(previous => {
            const prevNorm = normalizeTransitionText(previous);
            if (!prevNorm || !normalized) return false;
            return prevNorm === normalized || prevNorm.includes(normalized) || normalized.includes(prevNorm);
        });

        if (looksGeneric || looksRepeated) {
            return getTransitionFallbackQuestion();
        }
        return text;
    }

    function buildTransitionPayload() {
        return {
            main_question: currentMainQuestion,
            previous_transition: lastTransitionText,
            previous_transitions: recentTransitionHistory.slice(-TRANSITION_HISTORY_LIMIT)
        };
    }

    async function playTtsOnly(text) {
        if (!text) return;
        isProcessing = true;
        if (recordBtn) {
            recordBtn.disabled = true;
            setRecordText("🔊 Falando...");
        }
        setStatusText('Speaking...');

        try {
            ttsCancelled = false;
            const ttsText = cleanTextForTts(text);
            const chunks = splitTtsText(ttsText, 480);
            if (chunks.length === 0) { finalizePlayback(); return; }
            const skipBtn = showSkipAudioButton();

            // Prefetch pipeline: fetch next chunk while current plays
            let nextBlobPromise = fetchTTSSafe(chunks[0]);

            for (let i = 0; i < chunks.length; i++) {
                if (ttsCancelled) break;
                const blob = await nextBlobPromise;

                if (i + 1 < chunks.length) {
                    nextBlobPromise = fetchTTSSafe(chunks[i + 1]);
                }

                if (ttsCancelled) break;
                if (blob && blob.size > 0) {
                    await playAudioBlob(blob);
                }
            }

            finalizePlayback(skipBtn);
        } catch (err) {
            console.error("TTS Error:", err);
            finalizePlayback();
        }
    }

    async function startFreeConversationFlow() {
        if (!questionBank) {
            const questions = await loadFreeConversationQuestions();
            questionBank = new QuestionBank(questions);
        }
        missionState.active = false;
        missionState.mission = null;
        missionState.stepIndex = 0;
        missionState.answers = [];
        currentMainQuestion = '';
        currentFollowupQuestion = '';
        lastMainAnswer = '';
        lastFollowupAnswer = '';
        lastTransitionText = '';
        recentTransitionHistory = [];
        hideQuestionPicker();
        freeState = FREE_STATES.INTRO_AI_ASK_HOW_ARE_YOU;
        const introQuestion = pickFreeConversationIntro();
        logConversationEntry('AI', introQuestion);
        await playTtsOnly(introQuestion);
        freeState = FREE_STATES.INTRO_STUDENT_ANSWER;
        setStatusText('Listening...');
    }

    async function handleFreeConversationInput(text) {
        if (!checkUsageLimit()) return;

        try {
            logConversationEntry(user ? user.name : "User", text);
            userMessageCount += 1;
            updateSessionProgress();

            if (missionState.active && freeState === FREE_STATES.MISSION_WAIT_ANSWER) {
                await handleMissionInput(text);
                return;
            }

            if (freeState === FREE_STATES.INTRO_STUDENT_ANSWER) {
                freeState = FREE_STATES.SHOW_QUESTION_PICKER;
                setStatusText('Thinking...');
                const reactData = await apiClient.freeConversationAction('react_intro', {
                    student_answer: text
                });
                const reactText = reactData.text || "That's great to hear!";
                logConversationEntry('AI', reactText);
                await playTtsOnly(reactText);
                const preview = questionBank.getPreview();
                showQuestionPicker(preview);
                setStatusText('Choose a question');
                return;
            }

            if (freeState === FREE_STATES.SHOW_QUESTION_PICKER) {
                await launchSelectedFreeMode();
                return;
            }

            if (freeState === FREE_STATES.STUDENT_ANSWERS_MAIN) {
                lastMainAnswer = text;
                freeState = FREE_STATES.AI_ASKS_FOLLOWUP;
                setStatusText('Thinking...');
                if (recordBtn) {
                    recordBtn.disabled = true;
                    setRecordText("⏳ Pensando...");
                }

                const followupData = await apiClient.freeConversationAction('followup', {
                    main_question: currentMainQuestion,
                    student_answer: lastMainAnswer
                });
                currentFollowupQuestion = followupData.text || followupData.question || followupData.response || '';
                logConversationEntry('AI', currentFollowupQuestion);
                await playTtsOnly(currentFollowupQuestion);
                freeState = FREE_STATES.STUDENT_ANSWERS_FOLLOWUP;
                setStatusText('Listening...');
                return;
            }

            if (freeState === FREE_STATES.STUDENT_ANSWERS_FOLLOWUP) {
                lastFollowupAnswer = text;
                freeState = FREE_STATES.AI_OPINION_RESPONSE;
                setStatusText('Thinking...');
                if (recordBtn) {
                    recordBtn.disabled = true;
                    setRecordText("⏳ Pensando...");
                }

                const opinionData = await apiClient.freeConversationAction('opinion', {
                    main_question: currentMainQuestion,
                    student_answer: lastMainAnswer,
                    followup_question: currentFollowupQuestion,
                    followup_answer: lastFollowupAnswer
                });
                const opinionText = opinionData.text || opinionData.response || '';
                logConversationEntry('AI', opinionText);
                await playTtsOnly(opinionText);

                const transData = await apiClient.freeConversationAction('transition', buildTransitionPayload());
                const transText = sanitizeTransitionQuestion(transData.text);
                lastTransitionText = transText;
                rememberTransitionText(transText);
                logConversationEntry('AI', transText);
                await playTtsOnly(transText);
                freeState = FREE_STATES.STUDENT_ADDITIONAL_INTENT;
                setStatusText('Listening...');
                return;
            }

            if (freeState === FREE_STATES.STUDENT_ADDITIONAL_INTENT) {
                if (isNegativeResponse(text)) {
                    freeState = FREE_STATES.SHOW_QUESTION_PICKER;
                    const preview = questionBank.refreshPreview();
                    showQuestionPicker(preview);
                    setStatusText('Choose a question');
                    return;
                }

                // If the text already contains a question, answer it directly
                if (text.includes('?')) {
                    freeState = FREE_STATES.AI_ANSWERS_STUDENT_QUESTION;
                    setStatusText('Thinking...');
                    if (recordBtn) {
                        recordBtn.disabled = true;
                        setRecordText("⏳ Pensando...");
                    }
                    const answerData = await apiClient.freeConversationAction('answer', {
                        main_question: currentMainQuestion,
                        student_answer: lastMainAnswer,
                        followup_question: currentFollowupQuestion,
                        followup_answer: lastFollowupAnswer,
                        student_question: text
                    });
                    const answerText = answerData.text || answerData.response || '';
                    logConversationEntry('AI', answerText);
                    await playTtsOnly(answerText);

                    const transData = await apiClient.freeConversationAction('transition', buildTransitionPayload());
                    const transText = sanitizeTransitionQuestion(transData.text);
                    lastTransitionText = transText;
                    rememberTransitionText(transText);
                    logConversationEntry('AI', transText);
                    await playTtsOnly(transText);
                    freeState = FREE_STATES.STUDENT_ADDITIONAL_INTENT;
                    setStatusText('Listening...');
                    return;
                }

                // Continue naturally when student adds more information (instead of forcing "ask me a question")
                setStatusText('Thinking...');
                if (recordBtn) {
                    recordBtn.disabled = true;
                    setRecordText("⏳ Pensando...");
                }
                lastMainAnswer = text;
                const moreData = await apiClient.freeConversationAction('followup', {
                    main_question: currentMainQuestion,
                    student_answer: text
                });
                currentFollowupQuestion = moreData.text || "Could you tell me a little more about that?";
                logConversationEntry('AI', currentFollowupQuestion);
                await playTtsOnly(currentFollowupQuestion);
                freeState = FREE_STATES.STUDENT_ANSWERS_FOLLOWUP;
                setStatusText('Listening...');
                return;
            }

            if (freeState === FREE_STATES.STUDENT_ASKS_QUESTION) {
                freeState = FREE_STATES.AI_ANSWERS_STUDENT_QUESTION;
                setStatusText('Thinking...');
                if (recordBtn) {
                    recordBtn.disabled = true;
                    setRecordText("⏳ Pensando...");
                }
                const answerData = await apiClient.freeConversationAction('answer', {
                    main_question: currentMainQuestion,
                    student_answer: lastMainAnswer,
                    followup_question: currentFollowupQuestion,
                    followup_answer: lastFollowupAnswer,
                    student_question: text
                });
                const answerText = answerData.text || answerData.response || '';
                logConversationEntry('AI', answerText);
                await playTtsOnly(answerText);

                const transData2 = await apiClient.freeConversationAction('transition', buildTransitionPayload());
                const transText2 = sanitizeTransitionQuestion(transData2.text);
                lastTransitionText = transText2;
                rememberTransitionText(transText2);
                logConversationEntry('AI', transText2);
                await playTtsOnly(transText2);
                freeState = FREE_STATES.STUDENT_ADDITIONAL_INTENT;
                setStatusText('Listening...');
                return;
            }
        } catch (err) {
            console.error(err);
            const backendError = extractBackendErrorPayload(err);
            if (err?.status === 429 && isWeekendLimitError(backendError || {})) {
                const usageMessage = applyUsageLimitFromServer(backendError || {});
                addMessage('System', usageMessage, true);
                showUsageExceededModal(backendError || {});
            }
            setStatusText('Error');
            if (recordBtn) {
                setMicReadyState();
                setRecordText("🎤 Clique para Falar");
            }
        }
    }

    // Usage tracking variables
    let sessionStartTime = null;
    let currentSessionSeconds = 0;
    let totalUsedToday = 0;
    let weekendLimitSeconds = 10800; // Fallback if backend value is unavailable
    let usageUpdateInterval = null;
    let remainingSeconds = weekendLimitSeconds;
    let isUsageLimitReached = false;
    let usageIsWeekend = true;

    function persistUsageData() {
        try {
            const payload = {
                seconds_used: totalUsedToday,
                remaining_seconds: remainingSeconds,
                weekend_limit_seconds: weekendLimitSeconds,
                is_blocked: isUsageLimitReached
            };
            localStorage.setItem('usage_data', JSON.stringify(payload));
        } catch (e) {
            console.log('Failed to update usage_data cache:', e);
        }
    }

    function applyUsageData(usageData = {}) {
        if (!usageData || typeof usageData !== 'object') return;

        if (typeof usageData.seconds_used === 'number' && usageData.seconds_used >= 0) {
            totalUsedToday = usageData.seconds_used;
        }
        if (typeof usageData.weekend_limit_seconds === 'number' && usageData.weekend_limit_seconds > 0) {
            weekendLimitSeconds = usageData.weekend_limit_seconds;
        }
        if (typeof usageData.remaining_seconds === 'number') {
            remainingSeconds = Math.max(0, usageData.remaining_seconds);
        } else if (usageData.is_blocked === true) {
            remainingSeconds = 0;
        }
        if (typeof usageData.is_weekend === 'boolean') {
            usageIsWeekend = usageData.is_weekend;
        }

        if (typeof usageData.is_blocked === 'boolean') {
            isUsageLimitReached = usageData.is_blocked;
        } else {
            isUsageLimitReached = remainingSeconds <= 0;
        }

        updateTimerDisplay(remainingSeconds);
        persistUsageData();
    }

    function extractBackendErrorPayload(err) {
        if (err && err.originalError && typeof err.originalError === 'object') {
            return err.originalError;
        }
        const rawMessage = typeof err?.message === 'string' ? err.message.trim() : '';
        if (!rawMessage || !rawMessage.startsWith('{')) return null;
        try {
            const parsed = JSON.parse(rawMessage);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (parseErr) {
            return null;
        }
    }

    function isWeekendLimitError(payload = {}) {
        const baseError = String(payload?.error || payload?.message || '');
        return /weekend practice limit reached/i.test(baseError);
    }

    function getUsageBlockedMessage(payload = {}) {
        if (typeof payload?.message === 'string' && payload.message.trim()) {
            return payload.message.trim();
        }
        const blockedDuringWeekend = typeof payload?.is_weekend === 'boolean' ? payload.is_weekend : usageIsWeekend;
        if (blockedDuringWeekend === false) {
            return 'A prática está disponível apenas aos finais de semana (sábado e domingo).';
        }
        return 'Você atingiu seu limite de prática deste fim de semana.';
    }

    function applyUsageLimitFromServer(payload = {}) {
        const normalized = {
            is_blocked: true,
            remaining_seconds: typeof payload.remaining_seconds === 'number' ? payload.remaining_seconds : 0
        };

        if (typeof payload.weekend_limit_seconds === 'number' && payload.weekend_limit_seconds > 0) {
            normalized.weekend_limit_seconds = payload.weekend_limit_seconds;
        }
        if (typeof payload.seconds_used === 'number' && payload.seconds_used >= 0) {
            normalized.seconds_used = payload.seconds_used;
        }
        if (typeof payload.is_weekend === 'boolean') {
            normalized.is_weekend = payload.is_weekend;
        }

        applyUsageData(normalized);
        isUsageLimitReached = true;
        return getUsageBlockedMessage(payload);
    }

    async function refreshUsageStatusFromServer() {
        try {
            const usageData = await apiClient.getUsageStatus();
            applyUsageData(usageData || {});
        } catch (err) {
            console.warn('[Usage] Could not refresh usage status:', err);
        }
    }

    // Initialize usage tracking from login response
    const storedUsage = localStorage.getItem('usage_data');
    if (storedUsage && user) {
        try {
            applyUsageData(JSON.parse(storedUsage));
        } catch (e) {
            console.log('Failed to parse usage data:', e);
        }
    }

    // Timer display update function
    function updateTimerDisplay(seconds) {
        const timerDisplay = document.getElementById('timer-display');
        const usageTimer = document.getElementById('usage-timer');

        if (!timerDisplay) return;

        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        timerDisplay.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;

        if (!usageTimer) return;

        // Update color based on remaining time
        usageTimer.classList.remove('timer-normal', 'timer-warning', 'timer-critical');

        if (seconds <= 0) {
            usageTimer.classList.add('timer-critical');
            timerDisplay.textContent = '0:00';
        } else if (seconds < 60) {
            usageTimer.classList.add('timer-critical');
        } else if (seconds < 120) {
            usageTimer.classList.add('timer-warning');
        } else {
            usageTimer.classList.add('timer-normal');
        }
    }

    // Start usage timer
    function startUsageTimer() {
        if (sessionStartTime || usageUpdateInterval) return; // Already running

        sessionStartTime = Date.now();
        currentSessionSeconds = 0;

        updateTimerDisplay(remainingSeconds);

        // Update display every second
        usageUpdateInterval = setInterval(() => {
            currentSessionSeconds = Math.floor((Date.now() - sessionStartTime) / 1000);
            const newRemaining = Math.max(0, remainingSeconds - currentSessionSeconds);

            updateTimerDisplay(newRemaining);

            // Check if limit reached
            if (newRemaining <= 0 && !isUsageLimitReached) {
                isUsageLimitReached = true;
                showUsageExceededModal();
            }
        }, 1000);

        // Sync with backend every 30 seconds
        setInterval(async () => {
            if (currentSessionSeconds > 0) {
                try {
                    const usageRes = await apiClient.trackUsage(currentSessionSeconds);
                    // Reset session counter after successful sync
                    sessionStartTime = Date.now();
                    if (usageRes) {
                        applyUsageData(usageRes);
                    } else {
                        remainingSeconds = Math.max(0, remainingSeconds - currentSessionSeconds);
                        isUsageLimitReached = remainingSeconds <= 0;
                        updateTimerDisplay(remainingSeconds);
                        persistUsageData();
                    }
                    currentSessionSeconds = 0;
                } catch (err) {
                    console.error('Failed to sync usage:', err);
                }
            }
        }, 30000);
    }

    // Check if user can send message
    function checkUsageLimit(limitPayload = null) {
        if (isUsageLimitReached || remainingSeconds <= 0) {
            showUsageExceededModal(limitPayload || {});
            return false;
        }
        return true;
    }

    // Show usage exceeded modal
    function showUsageExceededModal(limitPayload = {}) {
        // Check if already showing
        if (document.getElementById('usage-exceeded-overlay')) return;

        const blockedMessage = getUsageBlockedMessage(limitPayload);
        const blockedDuringWeekend = typeof limitPayload?.is_weekend === 'boolean' ? limitPayload.is_weekend : usageIsWeekend;
        const title = blockedDuringWeekend ? 'Tempo Esgotado' : 'Prática Fora do Horário';
        const nextAccess = blockedDuringWeekend ? 'Sábado que vem' : 'Neste sábado';
        const footerText = blockedDuringWeekend
            ? 'Continue praticando no próximo fim de semana!'
            : 'A prática por voz fica disponível aos fins de semana.';

        const overlay = document.createElement('div');
        overlay.id = 'usage-exceeded-overlay';
        overlay.className = 'usage-exceeded-overlay';
        const limitMinutes = Math.round(weekendLimitSeconds / 60);
        const limitLabel = limitMinutes >= 60
            ? `${(limitMinutes / 60).toFixed(limitMinutes % 60 === 0 ? 0 : 1)} hora(s)`
            : `${limitMinutes} minutos`;

        overlay.innerHTML = `
            <div class="usage-exceeded-modal">
                <div class="modal-icon">⏰</div>
                <h2>${title}</h2>
                <p>${escapeHtml(blockedMessage)}</p>
                <div class="time-info">
                    <p><strong>Tempo usado:</strong> ${Math.floor(totalUsedToday / 60)} minutos</p>
                    <p><strong>Limite:</strong> ${limitLabel}</p>
                    <p><strong>Próximo acesso:</strong> ${nextAccess}</p>
                </div>
                <p style="font-size: 0.9rem; color: #94a3b8;">${footerText}</p>
                <button class="close-btn" onclick="this.closest('.usage-exceeded-overlay').remove()">Entendi</button>
            </div>
        `;

        document.body.appendChild(overlay);

        // Disable  chat controls
        if (recordBtn) recordBtn.disabled = true;
        const sendBtn = document.getElementById('send-btn');
        if (sendBtn) sendBtn.disabled = true;
    }

    // Initialize timer display
    updateTimerDisplay(remainingSeconds);
    refreshUsageStatusFromServer();

    // Subtitles default to ON unless user explicitly disables them.
    if (typeof window.subtitlesEnabled === 'undefined') {
        const savedPref = localStorage.getItem('auto_translate');
        window.subtitlesEnabled = savedPref === null ? true : savedPref === 'true';
    }

    if (autoTranslateToggle) {
        autoTranslateToggle.checked = !!window.subtitlesEnabled;
    }

    // Save auto-translate preference when changed
    if (autoTranslateToggle) {
        autoTranslateToggle.addEventListener('change', () => {
            localStorage.setItem('auto_translate', autoTranslateToggle.checked);
        });
    }

    // Load conversation from localStorage backup
    const savedConversation = localStorage.getItem('conversation_backup');
    if (savedConversation) {
        try {
            const parsed = JSON.parse(savedConversation);
            conversationLog.push(...parsed);
            // Restore messages in UI
            if (!isFreeConversation) {
                parsed.forEach(msg => {
                    if (msg.sender && msg.text) {
                        addMessage(msg.sender, msg.text, msg.sender === 'AI', false);
                    }
                });
            }
            refreshConversationFocusView();
            updateMessageCounter();
            updateReportButton();
        } catch (e) {
            console.error('Failed to restore conversation:', e);
        }
    }

    // Save conversation periodically
    function saveConversation() {
        localStorage.setItem('conversation_backup', JSON.stringify(conversationLog));
    }

    let tipsModalPromise = null;
    async function showPracticeTipsModalIfNeeded() {
        if (window.__tipsModalShownThisSession) return;
        if (tipsModalPromise) return tipsModalPromise;

        // Only show on first practice session ever (per browser).
        // The tips were appearing on every session and adding to UI clutter.
        try {
            if (localStorage.getItem('practice_tips_seen') === '1') {
                window.__tipsModalShownThisSession = true;
                return;
            }
        } catch (_) {}

        const tipsModal = document.getElementById('tips-modal');
        if (!tipsModal) {
            window.__tipsModalShownThisSession = true;
            return;
        }

        tipsModalPromise = new Promise(resolve => {
            tipsModal.style.display = 'flex';
            const okBtn = document.getElementById('tips-modal-ok');
            if (!okBtn) {
                tipsModal.style.display = 'none';
                window.__tipsModalShownThisSession = true;
                try { localStorage.setItem('practice_tips_seen', '1'); } catch (_) {}
                resolve();
                return;
            }

            okBtn.addEventListener('click', () => {
                tipsModal.style.display = 'none';
                window.__tipsModalShownThisSession = true;
                try { localStorage.setItem('practice_tips_seen', '1'); } catch (_) {}
                resolve();
            }, { once: true });
        });

        try {
            await tipsModalPromise;
        } finally {
            tipsModalPromise = null;
        }
    }
    window.showPracticeTipsModalIfNeeded = showPracticeTipsModalIfNeeded;

    if (startBtn) {
        // Add pulse animation to start button
        startBtn.classList.add('pulse-animation');

        startBtn.addEventListener('click', async () => {
            await showPracticeTipsModalIfNeeded();

            const startOverlay = document.getElementById('start-overlay');
            if (startOverlay) startOverlay.style.display = 'none';
            const startMessage = document.getElementById('start-message');
            if (startMessage) startMessage.style.display = 'none';
            // Show footer bar now that overlay is hidden
            const footerBar = document.getElementById('footer-bar');
            if (footerBar) footerBar.style.display = '';

            // Remove hint and enable buttons
            if (micHint) micHint.style.display = 'none';
            if (recordBtn) setMicReadyState();

            // Start usage timer
            startUsageTimer();

            // Clear conversation and UI when starting fresh
            conversationLog.length = 0;
            lastAIQuestionPrompt = '';
            userMessageCount = 0;
            seenMilestones.clear();
            hasPracticeStarted = true;
            sessionGoalTurns = resolveSessionGoalByLevel();
            updateSessionProgress({ quiet: true });
            localStorage.removeItem('conversation_backup');
            try {
                await apiClient.clearConversations();
            } catch (err) {
                console.warn('[SESSION] Could not clear server-side history:', err);
            }

            // Remove all messages except the start message
            const messages = chatWindow.querySelectorAll(
                '.message:not(#start-message), .subtitle-group, .lesson-start-container, .lesson-options-container, .suggested-words-card'
            );
            messages.forEach(msg => msg.remove());
            toggleConversationHistory(false);
            refreshConversationFocusView();

            // Free Conversation guided cycles
            if (isFreeConversation) {
                if (freeQuestionPanel) hideQuestionPicker();
                await startFreeConversationFlow();
                return;
            }

            // Derive studentLevel from the difficulty selector
            const diffToLevel = { beginner: 'A1', intermediate: 'A2', advanced: 'B1' };
            const selDiff = window.getSelectedDifficulty ? window.getSelectedDifficulty() : 'intermediate';
            studentLevel = diffToLevel[selDiff] || 'A2';
            sessionGoalTurns = resolveSessionGoalByLevel();

            updateHeaderInfo();
            await startConversationFlow();
        });
    }

    async function startConversationFlow() {
        // Check if we should use structured lesson mode (Learning mode with predefined layers)
        const practiceMode = window.getSelectedMode ? window.getSelectedMode() : 'learning';
        if (practiceMode === 'learning' && !isGrammarMode && shouldUseStructuredLesson()) {
            await startStructuredLesson();
            return;
        }

        // Initial AI Greeting - context-specific, no generic "how can I help you"
        let greeting = "";
        let translation = "";

        // Natural greetings for Learning/Grammar topics
        const grammarGreetings = {
            'verb_to_be': {
                en: "Hey! I'm happy to chat. How are you right now?",
                pt: "Oi! Estou feliz em conversar. E voce, como esta agora?"
            },
            'greetings': {
                en: "Hey! I'm Alex. Nice to meet you. What's your name?",
                pt: "Oi! Eu sou a Alex. Prazer em conhecer. Qual e o seu nome?"
            },
            'articles': {
                en: "I grabbed an apple and a sandwich earlier. What's a snack you like?",
                pt: "Hoje eu comi uma maca e um sanduiche. Qual lanche voce gosta?"
            },
            'plurals': {
                en: "I have two cats and three plants at home. Do you have any pets or plants?",
                pt: "Eu tenho dois gatos e tres plantas em casa. Voce tem pets ou plantas?"
            },
            'demonstratives': {
                en: "This chair is comfy, but that one looks better. Which do you prefer?",
                pt: "Esta cadeira e confortavel, mas aquela parece melhor. Qual voce prefere?"
            },
            'subject_pronouns': {
                en: "I met my friend Maria today. She was in a great mood. Who do you usually talk to?",
                pt: "Hoje encontrei minha amiga Maria. Ela estava animada. Com quem voce costuma falar?"
            },
            'possessives': {
                en: "My phone is almost dead. Do you have your charger with you?",
                pt: "Meu celular esta quase sem bateria. Voce tem seu carregador?"
            },
            'present_simple': {
                en: "I wake up early and drink coffee every day. What do you usually do in the morning?",
                pt: "Eu acordo cedo e tomo cafe todos os dias. O que voce costuma fazer de manha?"
            },
            'present_continuous': {
                en: "I'm chatting with you right now. What are you doing at the moment?",
                pt: "Estou conversando com voce agora. O que voce esta fazendo neste momento?"
            },
            'basic_questions': {
                en: "By the way, where are you from? And what do you do?",
                pt: "Alias, de onde voce e? E o que voce faz?"
            },
            // Special training scenario
            'basic_structures': {
                en: "Excuse me, could you help me for a second? How would you ask for help in English?",
                pt: "Com licenca, voce poderia me ajudar por um segundo? Como voce pediria ajuda em ingles?"
            }
        };

        const bilingualGreetings = {
            'verb_to_be': "Oi! Vamos conversar um pouco. Por exemplo: [EN]I am happy[/EN]. E voce, como esta hoje?",
            'greetings': "Oi! [EN]Nice to meet you[/EN]. Qual e o seu nome?",
            'articles': "Hoje eu comi [EN]an apple[/EN] e [EN]a sandwich[/EN]. Qual lanche voce gosta?",
            'plurals': "Eu tenho [EN]two cats[/EN] e [EN]three plants[/EN] em casa. Voce tem pets ou plantas?",
            'demonstratives': "Olha: [EN]this chair[/EN] e confortavel, mas [EN]that one[/EN] parece melhor. Qual voce prefere?",
            'subject_pronouns': "Hoje encontrei a Maria. [EN]She[/EN] estava animada. Com quem voce costuma falar?",
            'possessives': "Meu celular esta quase sem bateria. [EN]Is this your charger?[/EN]",
            'present_simple': "Eu [EN]wake up[/EN] cedo e [EN]drink coffee[/EN] todo dia. O que voce costuma fazer de manha?",
            'present_continuous': "Agora eu [EN]am chatting[/EN] com voce. [EN]What are you doing right now?[/EN]",
            'basic_questions': "Pergunta rapida: [EN]Where are you from?[/EN] E [EN]what do you do?[/EN]",
            'basic_structures': "Quando peco ajuda, digo: [EN]Excuse me, can you help me?[/EN] Como voce pediria ajuda?"
        };

        // Aliases for legacy or UI ids
        grammarGreetings['greetings_intros'] = grammarGreetings['greetings'];
        grammarGreetings['plural_nouns'] = grammarGreetings['plurals'];
        grammarGreetings['this_that_these_those'] = grammarGreetings['demonstratives'];
        grammarGreetings['possessive_adjectives'] = grammarGreetings['possessives'];
        bilingualGreetings['greetings_intros'] = bilingualGreetings['greetings'];
        bilingualGreetings['plural_nouns'] = bilingualGreetings['plurals'];
        bilingualGreetings['this_that_these_those'] = bilingualGreetings['demonstratives'];
        bilingualGreetings['possessive_adjectives'] = bilingualGreetings['possessives'];

        const defaultGrammarGreeting = {
            en: "Hey! Let's chat for a minute. Tell me something about your day.",
            pt: "Oi! Vamos conversar um pouco. Me conte algo do seu dia."
        };
        const defaultBilingualGreeting = "Oi! Vamos conversar um pouco. Por exemplo: [EN]My day is busy[/EN]. E o seu?";

        if (isGrammarMode) {
            if (lessonLang === 'pt') {
                // PT MODE: Bilingual greeting with [EN] tags for English phrases
                greeting = bilingualGreetings[context] || defaultBilingualGreeting;
                translation = '';  // No separate translation in PT mode
            } else {
                // EN MODE: English greeting with PT translation
                const greetingBlock = grammarGreetings[context] || defaultGrammarGreeting;
                greeting = greetingBlock.en;
                translation = greetingBlock.pt;
            }
        } else {
            // For conversation scenarios, start with context-appropriate greeting
            const contextGreetings = {
                'coffee_shop': {
                    en: "Good morning! Welcome to The Daily Grind. What can I get started for you today?",
                    pt: "Bom dia! Bem-vindo ao The Daily Grind. O que posso preparar para você hoje?"
                },
                'restaurant': {
                    en: "Good evening! Welcome to our restaurant. Do you have a reservation?",
                    pt: "Boa noite! Bem-vindo ao nosso restaurante. Você tem reserva?"
                },
                'airport': {
                    en: "Good afternoon! May I see your passport and ticket, please?",
                    pt: "Boa tarde! Posso ver seu passaporte e passagem, por favor?"
                },
                'supermarket': {
                    en: "Hello! Did you find everything you were looking for today?",
                    pt: "Olá! Você encontrou tudo o que procurava hoje?"
                },
                'doctor': {
                    en: "Good morning! Please have a seat. What brings you in today?",
                    pt: "Bom dia! Por favor, sente-se. O que te traz aqui hoje?"
                },
                'hotel': {
                    en: "Welcome! Checking in? May I have your name, please?",
                    pt: "Bem-vindo! Fazendo check-in? Qual é o seu nome, por favor?"
                },
                'free_conversation': {
                    en: "Hi there! What would you like to talk about today? It can be anything - your day, hobbies, travel, work, or any topic you're interested in!",
                    pt: "Olá! Sobre o que você gostaria de conversar hoje? Pode ser qualquer coisa - seu dia, hobbies, viagens, trabalho, ou qualquer assunto!"
                }
            };

            // BEGINNER overrides: shorter greetings, A1-A2 vocabulary,
            // simple present, max ~8 words. Keeps the scenario role but
            // removes complex structures ("May I see...", "What can I get started...").
            const beginnerContextGreetings = {
                'coffee_shop': {
                    en: "Hi! Welcome. What would you like to drink?",
                    pt: "Oi! Bem-vindo. O que você gostaria de beber?"
                },
                'restaurant': {
                    en: "Hello! Welcome. How many people?",
                    pt: "Olá! Bem-vindo. Quantas pessoas?"
                },
                'airport': {
                    en: "Hello! Your passport, please?",
                    pt: "Olá! Seu passaporte, por favor?"
                },
                'supermarket': {
                    en: "Hi! Did you find everything?",
                    pt: "Oi! Você encontrou tudo?"
                },
                'doctor': {
                    en: "Hi! Please sit down. How can I help you?",
                    pt: "Oi! Por favor, sente-se. Como posso ajudar?"
                },
                'hotel': {
                    en: "Hi! Are you checking in? What's your name?",
                    pt: "Oi! Você está fazendo check-in? Qual é o seu nome?"
                },
                'free_conversation': {
                    en: "Hi! Let's talk. What did you do today?",
                    pt: "Oi! Vamos conversar. O que você fez hoje?"
                }
            };

            const selectedDifficulty = window.getSelectedDifficulty ? window.getSelectedDifficulty() : 'intermediate';
            const isBeginner = selectedDifficulty === 'beginner';

            const contextGreeting = (isBeginner && beginnerContextGreetings[context])
                ? beginnerContextGreetings[context]
                : contextGreetings[context];

            if (contextGreeting) {
                greeting = contextGreeting.en;
                translation = contextGreeting.pt;
            } else if (isBeginner) {
                // Generic fallback for beginner on scenarios without a specific override
                greeting = "Hi! How are you today?";
                translation = "Oi! Como você está hoje?";
            } else {
                // Generic fallback for other scenarios
                greeting = "Hello! How are you doing today?";
                translation = "Olá! Como você está hoje?";
            }

        }

        playResponse(greeting, translation);
    }


    // --- Speech Recognition with Groq Whisper ---
    let groqRecorder = null;

    // Initialize Groq Recorder
    if (typeof DeepgramRecorder !== 'undefined') {
        groqRecorder = new DeepgramRecorder();
        if (recordBtn) {
            setMicReadyState();
        }
        console.log('[Groq] Recorder initialized');
    } else {
        console.error('[Groq] DeepgramRecorder not available');
        if (recordBtn) {
            recordBtn.disabled = true;
        }
    }

    function showTranscriptionConfirm(transcript) {
        const existing = document.getElementById('stt-confirm-overlay');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'stt-confirm-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.65);display:flex;align-items:center;justify-content:center;z-index:9999;';

        const modal = document.createElement('div');
        modal.style.cssText = 'background:#0f1115;border:1px solid rgba(255,255,255,0.12);border-radius:14px;padding:20px;max-width:520px;width:90%;color:#f8fafc;';

        const title = document.createElement('div');
        title.style.cssText = 'font-size:1.05rem;font-weight:700;margin-bottom:10px;';
        title.textContent = 'Confirmar transcrição';

        const helper = document.createElement('div');
        helper.style.cssText = 'font-size:0.85rem;color:#9aa4b2;margin-bottom:10px;';
        helper.textContent = 'Ajuste o texto se necessário antes de enviar.';

        const textarea = document.createElement('textarea');
        textarea.value = transcript || '';
        textarea.style.cssText = 'width:100%;min-height:90px;background:#111827;color:#f8fafc;border:1px solid rgba(255,255,255,0.12);border-radius:10px;padding:10px;font-size:0.95rem;resize:vertical;';

        const actions = document.createElement('div');
        actions.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;margin-top:12px;';

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'action-btn';
        cancelBtn.textContent = 'Cancelar';
        cancelBtn.onclick = () => overlay.remove();

        const sendBtn = document.createElement('button');
        sendBtn.type = 'button';
        sendBtn.className = 'primary-btn';
        sendBtn.textContent = 'Enviar';
        sendBtn.onclick = () => {
            const text = (textarea.value || '').trim();
            if (!isMeaningfulSpeechText(text)) {
                helper.style.color = '#fca5a5';
                helper.textContent = 'Não entendi bem esse trecho. Fale uma frase curta e completa.';
                return;
            }
            overlay.remove();
            processUserResponse(text);
        };

        actions.appendChild(cancelBtn);
        actions.appendChild(sendBtn);
        modal.appendChild(title);
        modal.appendChild(helper);
        modal.appendChild(textarea);
        modal.appendChild(actions);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        textarea.focus();
        textarea.select();
    }

    function isMeaningfulSpeechText(text) {
        const normalized = String(text || '')
            .toLowerCase()
            .replace(/[^\p{L}\p{N}\s']/gu, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        if (!normalized) return false;

        const allowShort = new Set([
            'ok', 'okay', 'yes', 'no', 'hi', 'hello',
            'oi', 'ola', 'olá', 'sim', 'nao', 'não'
        ]);
        if (allowShort.has(normalized)) return true;

        const tokens = normalized.split(' ').filter(Boolean);
        if (!tokens.length) return false;
        if (tokens.length === 1) {
            const token = tokens[0];
            if (/^[a-z]$/i.test(token)) return false;
            if (['uh', 'um', 'hmm', 'mm'].includes(token)) return false;
        }
        return true;
    }

    const toggleRecording = async () => {
        if (!recordBtn || recordBtn.disabled || !groqRecorder || learningFeedbackPending) return;

        const micIcon = document.getElementById('mic-icon-inner');

        if (!isRecording) {
            if (!checkUsageLimit()) return;

            // Start recording
            try {
                const result = await groqRecorder.start();
                if (result.success) {
                    isRecording = true;
                    recordBtn.classList.add('recording');
                    recordBtn.classList.remove('mic-turn-highlight');
                    recordBtn.classList.add('listening');
                    if (micIcon) micIcon.innerText = "⏹️";
                    setRecordText("🔴 Escutando...");
                    setStatusText('Listening...');
                } else {
                    addMessage("System", result.error || "Microphone Error", true);
                }
            } catch (e) { console.error(e); }
        } else {
            // Stop recording and transcribe
            try {
                if (micIcon) micIcon.innerText = "⏳";
                recordBtn.disabled = true;
                setRecordText("⏳ Transcrevendo...");
                setStatusText('Thinking...');

                const audioBlob = await groqRecorder.stop();
                isRecording = false;
                recordBtn.classList.remove('recording');
                recordBtn.classList.remove('listening');

                // Transcribe — force English STT when practicing English phrases
                const sttLang = (lessonState.active && lessonState.nextAction === 'evaluate_practice') ? 'en' : lessonLang;
                const recorderMime = groqRecorder.getMimeType ? groqRecorder.getMimeType() : 'audio/webm';
                const transcribeResult = await transcribeWithDeepgram(audioBlob, apiClient.token, sttLang, recorderMime);

                if (transcribeResult.success) {
                    // Show pronunciation confidence feedback
                    if (typeof transcribeResult.confidence === 'number' && window.showPronunciationFeedback) {
                        window.showPronunciationFeedback(transcribeResult.confidence);
                    }
                    const transcript = (transcribeResult.transcript || '').trim();
                    if (!isMeaningfulSpeechText(transcript)) {
                        addMessage('System', 'Não entendi bem. Pode repetir em uma frase curta?', true);
                        setStatusText('Listening...');
                        return;
                    }
                    const shouldConfirm = window.getConfirmTranscription ? window.getConfirmTranscription() : true;
                    if (shouldConfirm) {
                        showTranscriptionConfirm(transcript);
                    } else {
                        processUserResponse(transcript);
                    }
                } else if (transcribeResult.retry) {
                    if (micIcon) micIcon.innerText = "🤔";
                    setTimeout(() => { if (micIcon) micIcon.innerText = "🎤"; setMicReadyState(); }, 2000);
                } else if (transcribeResult.usageBlocked) {
                    const usageMessage = applyUsageLimitFromServer(transcribeResult);
                    addMessage('System', usageMessage, true);
                    showUsageExceededModal(transcribeResult);
                    if (micIcon) micIcon.innerText = "⛔";
                } else {
                    throw new Error(transcribeResult.error);
                }

            } catch (err) {
                console.error('[Groq] Transcription error:', err);
                if (micIcon) micIcon.innerText = "❌";
                setTimeout(() => { if (micIcon) micIcon.innerText = "🎤"; }, 2000);
            } finally {
                setMicReadyState();
                if (!isRecording && micIcon && micIcon.innerText !== "❌" && micIcon.innerText !== "🤔" && micIcon.innerText !== "⛔") {
                    micIcon.innerText = "🎤";
                }
                if (!isRecording) {
                    setRecordText("🎤 Clique para Falar");
                }
                syncMicTurnCue(statusIndicator ? statusIndicator.textContent : '');
            }
        }
    };

    if (recordBtn) recordBtn.addEventListener('click', toggleRecording);
    if (reportBtn) reportBtn.addEventListener('click', sendReport);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Space key to toggle microphone (only when not typing in input)
        if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            if (recordBtn && !recordBtn.disabled && !isProcessing) {
                toggleRecording();
            }
        }
    });

    // --- Dynamic AI Logic ---
    async function processUserResponse(text) {
        if (!isMeaningfulSpeechText(text)) {
            addMessage('System', 'Não entendi bem. Pode repetir em uma frase curta?', true);
            setStatusText('Listening...');
            return;
        }

        // Check if usage limit has been reached
        if (!checkUsageLimit()) {
            return; // Exit early if limit reached
        }

        if (isFreeConversation) {
            await handleFreeConversationInput(text);
            return;
        }

        const previousAIPrompt = getLatestAIQuestionPrompt();

        // Check if we're in structured lesson mode
        if (lessonState.active) {
            // If in practice mode, evaluate the practice
            if (lessonState.nextAction === 'evaluate_practice') {
                // Show user's practice attempt
                addMessage(user ? user.name : "User", text);
                userMessageCount++;
                updateMessageCounter();

                // Evaluate the practice with Gemini
                await evaluateLessonPractice(text);
                return;
            }

            // If waiting for option selection, match voice input to an option
            if (lessonState.nextAction === 'show_options' || lessonState.nextAction === 'select_option') {
                if (lessonState.currentOptions && lessonState.currentOptions.length > 0) {
                    const matchResult = matchSpokenToOption(text, lessonState.currentOptions);
                    if (matchResult) {
                        addMessage(user ? user.name : "User", text);
                        userMessageCount++;
                        updateMessageCounter();
                        await selectLessonOption(matchResult.index, matchResult.option, text);
                    } else {
                        addMessage('System', 'Could not match your speech to any option. Please try again reading one of the phrases above.', true);
                    }
                }
                return;
            }
        }

        // 1. Show User Text
        addMessage(user ? user.name : "User", text);
        userMessageCount++;
        updateMessageCounter();
        updateSessionProgress();
        updateReportButton();

        // UI State
        isProcessing = true;
        if (recordBtn) {
            recordBtn.disabled = true;
            setRecordText("⏳ Pensando...");
            recordBtn.classList.remove('recording');
        }

        // Show loading indicator with animated messages
        showLoadingIndicator();

        try {
            // 2. Call AI Backend with new API client (pass lessonLang and practiceMode)
            const practiceMode = window.getSelectedMode ? window.getSelectedMode() : 'learning';
            const difficulty = window.getSelectedDifficulty ? window.getSelectedDifficulty() : 'intermediate';
            const data = await apiClient.chat(text, context, lessonLang, practiceMode, {
                studentLevel,
                turnCount: userMessageCount,
                recentCorrections,
                difficulty
            });

            // Hide loading indicator
            hideLoadingIndicator();

            // 3. Prepare Learning flow (popup guidance first, then AI response)
            updateRecentCorrections(data.text);
            const forceTranslation = Boolean(data.must_retry || (data.suggested_words && data.suggested_words.length));
            const backendSupportsKinds = data && data.learning_correction_kind_enabled !== false;
            const hasTurnFeedback = data && data.turn_feedback && typeof data.turn_feedback === 'object';
            let turnFeedbackPayload = hasTurnFeedback
                ? data.turn_feedback
                : {
                    kind: 'none',
                    user_text: text,
                    suggested_text: text,
                    reason: 'Sua frase esta correta para este contexto.'
                };
            const localFeedback = practiceMode === 'learning'
                ? inferLearningFeedbackFromText(text, previousAIPrompt)
                : null;
            if (localFeedback) {
                const currentKind = String(turnFeedbackPayload && turnFeedbackPayload.kind || 'none').trim();
                if (currentKind !== 'error_correction') {
                    turnFeedbackPayload = localFeedback;
                }
            }

            let responseText = data.text || '';
            let responseTranslation = data.translation || '';
            if (practiceMode === 'learning') {
                const simplified = simplifyLearningScenarioResponse(responseText, responseTranslation);
                responseText = simplified.text || responseText;
                responseTranslation = simplified.translation || responseTranslation;
            }

            // Show micro-feedback for simulator mode
            if (practiceMode === 'simulator' && data.feedback) {
                setTimeout(() => showSimulatorFeedback(data.feedback), 300);
            }

            let popupHints = [];
            let responseHints = [];
            if (!lessonState.active) {
                const suggestionBaseText = sanitizeCoachDisplayText(responseText) || responseText;
                // Run both suggestion fetches in PARALLEL (was sequential, ~2x slower)
                // popup no longer waits for dynamic; we dedupe in JS after both return
                const dynamicPromise = fetchDynamicSuggestions(suggestionBaseText, false);
                const popupPromise = (practiceMode === 'learning' && previousAIPrompt)
                    ? fetchPopupSuggestions(sanitizeCoachDisplayText(previousAIPrompt) || previousAIPrompt, [])
                    : Promise.resolve([]);

                const [dynamicResult, popupResultRaw] = await Promise.all([dynamicPromise, popupPromise]);
                responseHints = dynamicResult || [];

                if (practiceMode === 'learning' && previousAIPrompt) {
                    // Dedupe popup against inline (was previously done server-side via exclude)
                    const inlineSet = new Set(responseHints.map(s => String(s.en || '').trim().toLowerCase()).filter(Boolean));
                    const popupResult = (popupResultRaw || []).filter(r => !inlineSet.has(String(r.en || '').trim().toLowerCase()));
                    popupHints = popupResult.length
                        ? popupResult.slice(0, 3)
                        : getLearningPopupReplyOptions(context, previousAIPrompt, 3);
                } else if (practiceMode === 'learning') {
                    popupHints = responseHints.length
                        ? responseHints.slice(0, 3)
                        : getLearningPopupReplyOptions(context, previousAIPrompt, 3);
                }
            }

            if (practiceMode === 'learning') {
                const popupFeedback = buildLearningFeedbackPayload(turnFeedbackPayload, text, data);
                const aiQuestionForPopup = extractLatestQuestionFromText(previousAIPrompt) || previousAIPrompt;
                await showLearningFeedbackPopup(popupFeedback, popupHints, aiQuestionForPopup);
            }

            const inlineLearningFeedback = (() => {
                if (practiceMode !== 'learning') return null;
                const candidate = buildLearningFeedbackPayload(turnFeedbackPayload, text, data);
                if (!candidate) return null;
                const kind = String(candidate.kind || '').trim();
                if (kind === 'error_correction' || kind === 'style_upgrade') {
                    return candidate;
                }
                return null;
            })();

            playResponse(responseText, responseTranslation, {
                forceTranslation,
                turnFeedback: inlineLearningFeedback || (hasTurnFeedback ? data.turn_feedback : null),
                turnCorrection: !hasTurnFeedback && backendSupportsKinds ? (data.turn_correction || null) : null,
                enableLegacyCorrectionFallback: !hasTurnFeedback,
                // Learning mode: popup already shows feedback, skip inline cards to reduce mobile clutter
                showInlineFeedback: practiceMode !== 'learning'
            });

            const showSuggestedWords = practiceMode !== 'simulator';
            renderSuggestedWords(
                showSuggestedWords ? (data.suggested_words || []) : [],
                data.retry_prompt || '',
                responseHints,
                responseText
            );

            // Save conversation
            saveConversation();

            // 4. Check if Basic Structures training is complete (6 interactions)
            if (context === 'basic_structures' && userMessageCount >= 6) {
                // Auto-generate report after 6 interactions
                setTimeout(() => {
                    sendReport();
                }, 3000); // Wait 3 seconds after last response
            }

        } catch (err) {
            console.error(err);
            hideLoadingIndicator();

            // Mensagens friendly em PT — aluno A1 nao deve ler jargao tecnico
            // ("Connection error", "UNAVAILABLE", "AbortError") e achar que ele errou.
            let errorMessage = "Desculpe, não consegui ouvir direito. Pode tentar de novo?";
            const errMessage = String(err?.message || '');
            const backendError = extractBackendErrorPayload(err);
            if (err?.status === 429 && isWeekendLimitError(backendError || {})) {
                errorMessage = applyUsageLimitFromServer(backendError || {});
                showUsageExceededModal(backendError || {});
            }
            if (err?.status === 503 || errMessage.includes('UNAVAILABLE') || errMessage.includes('high demand')) {
                errorMessage = "A IA está um pouco ocupada agora. Tenta de novo em alguns segundos?";
            } else if (err.name === 'AbortError') {
                errorMessage = "Demorou muito pra responder. Vamos tentar de novo?";
            } else if (errMessage.includes('Session expired')) {
                errorMessage = "Your session has expired. Redirecting to login...";
            } else if (errMessage.includes('Text too long')) {
                errorMessage = "Your message is too long. Please keep it under 500 characters.";
            }

            addMessage("System", errorMessage, true);
            isProcessing = false;
            if (recordBtn) {
                setMicReadyState();
                setRecordText("🎤 Clique para Falar");
            }
        }
    }

    function splitPlainTextToSentences(text) {
        const parts = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [];
        return parts.map(part => part.trim()).filter(Boolean);
    }

    function splitByWords(text, maxLen) {
        const words = text.split(/\s+/).filter(Boolean);
        const chunks = [];
        let current = '';
        for (const word of words) {
            if (word.length > maxLen) {
                if (current) {
                    chunks.push(current);
                    current = '';
                }
                for (let i = 0; i < word.length; i += maxLen) {
                    chunks.push(word.slice(i, i + maxLen));
                }
                continue;
            }
            if (!current) {
                current = word;
                continue;
            }
            if ((current + ' ' + word).length <= maxLen) {
                current += ' ' + word;
            } else {
                chunks.push(current);
                current = word;
            }
        }
        if (current) chunks.push(current);
        return chunks;
    }

    function tokenizeTtsText(text) {
        const tokens = [];
        const tagRegex = /\[EN\][\s\S]*?\[\/EN\]/g;
        let last = 0;
        let match;
        while ((match = tagRegex.exec(text)) !== null) {
            if (match.index > last) {
                tokens.push({ text: text.slice(last, match.index), tag: false });
            }
            tokens.push({ text: match[0], tag: true });
            last = match.index + match[0].length;
        }
        if (last < text.length) {
            tokens.push({ text: text.slice(last), tag: false });
        }
        return tokens;
    }

    /**
     * Clean text for TTS (remove content in parentheses, brackets, or asterisks)
     * Example: "Hello (Ola)" -> "Hello"
     */
    function cleanTextForTts(text) {
        if (!text) return "";
        // Remove content in parentheses (...)
        let cleaned = text.replace(/\([^)]*\)/g, "");
        // Remove content in brackets [...]
        cleaned = cleaned.replace(/\[[^\]]*\]/g, "");
        // Remove content in braces {...}
        cleaned = cleaned.replace(/\{[^}]*\}/g, "");
        // Remove content between asterisks *...*
        cleaned = cleaned.replace(/\*[^*]*\*/g, "");
        // Remove standalone asterisks and excessive whitespace
        cleaned = cleaned.replace(/\*/g, "").replace(/\s+/g, " ").trim();
        return cleaned;
    }

    function splitTtsText(text, maxLen = 480) {
        if (!text) return [];
        if (text.length <= maxLen) return [text];

        const tokens = tokenizeTtsText(text);
        const pieces = [];

        for (const token of tokens) {
            if (token.tag) {
                const t = token.text.trim();
                if (!t) continue;
                if (t.length <= maxLen) {
                    pieces.push(t);
                } else {
                    const inner = t.replace(/^\[EN\]/, '').replace(/\[\/EN\]$/, '').trim();
                    const innerChunks = splitByWords(inner, Math.max(10, maxLen - 10));
                    innerChunks.forEach(chunk => pieces.push(`[EN]${chunk}[/EN]`));
                }
            } else {
                const sentences = splitPlainTextToSentences(token.text);
                for (const s of sentences) {
                    if (!s) continue;
                    if (s.length <= maxLen) {
                        pieces.push(s);
                    } else {
                        pieces.push(...splitByWords(s, maxLen));
                    }
                }
            }
        }

        const chunks = [];
        let current = '';
        const pushCurrent = () => {
            if (current.trim()) {
                chunks.push(current.trim());
                current = '';
            }
        };

        for (const piece of pieces) {
            if (!piece) continue;
            if (!current) {
                current = piece;
            } else if ((current + ' ' + piece).length <= maxLen) {
                current += ' ' + piece;
            } else {
                pushCurrent();
                current = piece;
            }
        }
        pushCurrent();
        return chunks;
    }

    // Lazy-init AudioContext for volume boost (Web Audio API).
    // Required because HTML5 <audio> volume is capped at 1.0 — we need gain > 1
    // to make the cloned voice (recorded quietly) comfortable to hear.
    let _ttsAudioContext = null;
    function getTtsAudioContext() {
        if (!_ttsAudioContext) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            _ttsAudioContext = new AC();
        }
        if (_ttsAudioContext.state === 'suspended') {
            _ttsAudioContext.resume().catch(() => {});
        }
        return _ttsAudioContext;
    }

    function playAudioBlob(blob, opts = {}) {
        return new Promise((resolve) => {
            // Stop any previous audio to prevent overlap
            if (currentAudio) {
                currentAudio.pause();
                currentAudio.currentTime = 0;
                if (window.stopAvatarTalking) window.stopAvatarTalking();
            }

            // Disable microphone during playback to prevent interruption
            if (recordBtn) recordBtn.disabled = true;

            const audioUrl = URL.createObjectURL(blob);
            const audio = new Audio(audioUrl);
            currentAudio = audio;

            // Playback rate override (used to speed up PT audio since Qwen ignores
            // the server-side `speed` param). preservesPitch keeps the voice tone
            // natural at faster rates — no chipmunk effect.
            const rate = Number(opts.playbackRate || 1.0);
            if (rate > 0 && rate !== 1.0) {
                try {
                    audio.playbackRate = rate;
                    if ('preservesPitch' in audio) audio.preservesPitch = true;
                    else if ('webkitPreservesPitch' in audio) audio.webkitPreservesPitch = true;
                    else if ('mozPreservesPitch' in audio) audio.mozPreservesPitch = true;
                } catch (e) {
                    console.warn('[TTS] playbackRate override failed:', e && e.message);
                }
            }

            // Volume boost via Web Audio API when the cloned voice is too quiet.
            // window.ttsVolumeBoost can be set by app code/localStorage (default 1.6 = +60%).
            const boost = Number(window.ttsVolumeBoost || 1.0);
            if (boost > 1.01) {
                try {
                    const ctx = getTtsAudioContext();
                    if (ctx) {
                        const source = ctx.createMediaElementSource(audio);
                        const gainNode = ctx.createGain();
                        gainNode.gain.value = boost;
                        source.connect(gainNode);
                        gainNode.connect(ctx.destination);
                    }
                } catch (e) {
                    // If gain setup fails (e.g. CORS, already-used element), fall back silently to normal playback
                    console.warn('[TTS] Volume boost unavailable, playing at default volume:', e && e.message);
                }
            }
            let cleaned = false;
            const cleanup = () => {
                if (cleaned) return;
                cleaned = true;
                URL.revokeObjectURL(audioUrl);
                currentAudio = null;
                if (window.stopAvatarTalking) window.stopAvatarTalking();
                // Re-enable microphone after playback ends
                if (recordBtn && !isProcessing) {
                    setMicReadyState();
                    setRecordText("🎤 Clique para Falar");
                }
                resolve();
            };

            setRecordText("Falando...");
            audio.onended = cleanup;
            audio.onerror = () => {
                console.error("Audio playback failed");
                cleanup();
            };

            audio.play()
                .then(() => {
                    if (window.startAvatarTalking) window.startAvatarTalking();
                })
                .catch(() => cleanup());
        });
    }

    function finalizePlayback(skipBtn) {
        isProcessing = false;
        if (recordBtn) {
            setMicReadyState();
            setRecordText("🎤 Clique para Falar");
        }
        if (window.stopAvatarTalking) window.stopAvatarTalking();
        currentAudio = null;
        if (skipBtn) skipBtn.remove();
    }

    async function fetchTTSSafe(chunk) {
        try {
            return await apiClient.getTTS(chunk, ttsSpeed, lessonLang, getActiveVoice());
        } catch (err) {
            console.error("TTS prefetch error:", err);
            return null;
        }
    }

    async function playResponse(text, translation = "", options = {}) {
        // Clean text for TTS (remove translations/metadata)
        const ttsText = cleanTextForTts(text);

        // Split text and start fetching first chunk BEFORE DOM work
        const chunks = splitTtsText(ttsText, 480);
        let firstBlobPromise = chunks.length > 0 ? fetchTTSSafe(chunks[0]) : null;

        // If dual-TTS is enabled (beginner default), prefetch the PT translation
        // audio in parallel so there's no extra delay after the EN finishes.
        const shouldSpeakPt = !!(window.speakPtTranslation && translation && translation.trim());
        let ptBlobPromise = null;
        if (shouldSpeakPt) {
            const ptText = cleanTextForTts(translation);
            if (ptText && ptText.trim()) {
                ptBlobPromise = apiClient.getTTS(ptText, 1.0, 'pt', getActiveVoice())
                    .catch(err => {
                        console.warn('[Dual TTS] PT translation fetch failed:', err);
                        return null;
                    });
            }
        }

        // Keep the last asked question cached for learning hints/popups.
        rememberAIQuestionPrompt(text);

        // Show text and save (runs while first TTS chunk is being fetched)
        addMessage("AI", text, true, true, translation, options);
        saveConversation();

        // Play audio with prefetch pipeline
        try {
            ttsCancelled = false;
            if (chunks.length === 0) return;
            const skipBtn = showSkipAudioButton();

            // Helper: play PT translation if dual-TTS enabled.
            // Portuguese always plays at 1.25x — native speakers don't need slow audio.
            // Qwen ignores server-side speed param, so rate is applied here via <audio>.playbackRate.
            const playPtIfNeeded = async () => {
                if (!shouldSpeakPt || !ptBlobPromise || ttsCancelled) return;
                try {
                    const ptBlob = await ptBlobPromise;
                    if (ptBlob && ptBlob.size > 0 && !ttsCancelled) {
                        await playAudioBlob(ptBlob, { playbackRate: 1.25 });
                    }
                } catch (err) {
                    console.warn('[Dual TTS] PT playback failed:', err);
                }
            };

            // Order controlled by window.ptFirst (localStorage 'tts_pt_first'):
            //  - false (default): EN first, then PT (intermediate anchoring)
            //  - true:            PT first, then EN (super-beginner needs meaning first)
            const ptFirst = !!window.ptFirst;
            if (ptFirst) {
                // Play PT first so student understands meaning, then the target EN
                await playPtIfNeeded();
            }

            // If the main TTS text is Portuguese (grammar PT modes, etc.),
            // speed it up too — native speakers want a natural-to-fast pace.
            const mainPlaybackRate = (lessonLang === 'pt') ? 1.25 : 1.0;

            let nextBlobPromise = firstBlobPromise;

            for (let i = 0; i < chunks.length; i++) {
                if (ttsCancelled) break;

                // Await the blob that was already being fetched
                const blob = await nextBlobPromise;

                // Start prefetching the NEXT chunk while this one plays
                if (i + 1 < chunks.length) {
                    nextBlobPromise = fetchTTSSafe(chunks[i + 1]);
                }

                if (ttsCancelled) break;
                if (blob && blob.size > 0) {
                    await playAudioBlob(blob, { playbackRate: mainPlaybackRate });
                }
            }

            if (!ptFirst) {
                // Default: PT comes after the EN
                await playPtIfNeeded();
            }

            finalizePlayback(skipBtn);
        } catch (e) {
            console.error("TTS Error:", e);
            finalizePlayback();
        }
    }

    /**
     * Play audio for a lesson option (without adding to chat)
     * Used by the audio button on each option card
     */
    async function playOptionAudio(text) {
        if (!text) return;

        try {
            const blob = await apiClient.getTTS(text, ttsSpeed, lessonLang, getActiveVoice());
            if (blob && blob.size > 0) {
                await playAudioBlob(blob);
            }
        } catch (e) {
            console.error("Option audio TTS error:", e);
        }
    }

    async function sendReport() {
        const activeBtn = reportBarBtn || reportBtn;
        if (!activeBtn) return;
        if (!conversationLog.length) {
            addMessage("System", "Nenhuma conversa para analisar ainda.", true);
            return;
        }

        // Open report window immediately to avoid popup blockers
        let reportWin = null;
        try {
            reportWin = window.open('', '_blank');
            if (reportWin) {
                const loadingHtml = `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gerando relatorio...</title>
<style>
  body { margin: 0; font-family: Inter, Arial, sans-serif; background: #0f1115; color: #fff; display: grid; place-items: center; min-height: 100vh; }
  .card { background: #171a21; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 32px 36px; text-align: center; }
  .spinner { width: 38px; height: 38px; border-radius: 50%; border: 4px solid rgba(255,255,255,0.15); border-top-color: #e50914; margin: 0 auto 16px; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .muted { color: #9aa4b2; margin: 8px 0 0; }
</style>
</head>
<body>
  <div class="card">
    <div class="spinner"></div>
    <h2>Gerando relatorio...</h2>
    <p class="muted">Aguarde alguns segundos. Estamos montando o resumo completo.</p>
  </div>
</body>
</html>`;
                reportWin.document.open();
                reportWin.document.write(loadingHtml);
                reportWin.document.close();
            }
        } catch (err) {
            reportWin = null;
        }

        activeBtn.disabled = true;
        const originalLabel = activeBtn.innerText;
        activeBtn.innerText = "Gerando...";
        showLoadingIndicator();

        try {
            const currentMode = window.getSelectedMode ? window.getSelectedMode() : 'learning';
            const currentDifficultyForReport = (window.getSelectedDifficulty ? window.getSelectedDifficulty() : (localStorage.getItem('practice_difficulty') || 'intermediate'));
            const data = await apiClient.generateReport(conversationLog, context, currentMode, currentDifficultyForReport);
            hideLoadingIndicator();

            // Save report data for export
            window.lastReport = data.report || data;

            // Save progress to localStorage
            saveSessionProgress(data);

            const opened = openReportWindow(data, reportWin);
            if (!opened) {
                renderReportCard(data);
            }
        } catch (err) {
            console.error(err);
            hideLoadingIndicator();
            addMessage("System", `Erro ao gerar relatorio: ${err.message}`, true);
            if (reportWin && !reportWin.closed) {
                reportWin.document.open();
                reportWin.document.write(`<html><body style="font-family: Arial; background:#0f1115; color:#fff; padding:24px;">
                <h2>Falha ao gerar relatorio</h2>
                <p>Tente novamente. Se o erro persistir, verifique a conexao.</p>
                </body></html>`);
                reportWin.document.close();
            }
        } finally {
            activeBtn.disabled = false;
            activeBtn.innerText = originalLabel || "Gerar relatorio da conversa";
        }
    }

    function saveSessionProgress(apiPayload) {
        try {
            const info = normalizeReportData(apiPayload);
            const stats = getConversationStats();
            const notaGeral = info.nota_geral !== null ? info.nota_geral : computeAvgNaturalidade(info.analise_frases);
            const practiceMode = window.getSelectedMode ? window.getSelectedMode() : 'learning';
            const difficulty = window.getSelectedDifficulty ? window.getSelectedDifficulty() : 'intermediate';

            const entry = {
                scenario_id: context,
                scenario_title: contextName,
                mode: practiceMode,
                difficulty: difficulty,
                score: notaGeral,
                date: new Date().toISOString().split('T')[0],
                interactions: stats.total,
                timestamp: Date.now()
            };

            let progress = [];
            try {
                const stored = localStorage.getItem('practice_progress');
                if (stored) progress = JSON.parse(stored);
                if (!Array.isArray(progress)) progress = [];
            } catch (e) { progress = []; }

            progress.push(entry);
            // Keep max 100 sessions
            if (progress.length > 100) progress = progress.slice(-100);

            localStorage.setItem('practice_progress', JSON.stringify(progress));
            console.log('[Progress] Saved session:', entry);

            // Notify dashboard progress system (Melhoria: Progresso + Conquistas)
            try {
                const reportPayload = {
                    report: info,
                    context: context,
                    minutes: Math.round((stats.total || 0) * 0.5) // estimate ~30s per interaction
                };
                localStorage.setItem('last_report_data', JSON.stringify(reportPayload));
            } catch (e2) { /* ignore */ }
        } catch (e) {
            console.error('[Progress] Failed to save:', e);
        }
    }

    function renderReportCard(apiPayload) {
        if (!chatWindow) return;
        const info = normalizeReportData(apiPayload);
        const stats = getConversationStats();

        const wrapper = document.createElement('div');
        wrapper.className = 'report-card';

        // Overall score section
        const notaGeral = info.nota_geral !== null ? info.nota_geral : computeAvgNaturalidade(info.analise_frases);
        const scoreColor = notaGeral >= 80 ? '#22c55e' : notaGeral >= 50 ? '#f59e0b' : '#ef4444';
        const notaLabel = notaGeral >= 90 ? 'Excelente!' : notaGeral >= 75 ? 'Muito Bom!' : notaGeral >= 60 ? 'Bom progresso!' : notaGeral >= 40 ? 'Continue praticando!' : 'Vamos melhorar juntos!';

        const scoreSection = document.createElement('div');
        scoreSection.style.cssText = 'text-align:center;padding:20px 16px;margin-bottom:16px;';
        scoreSection.innerHTML = `
            <div style="font-size:3rem;font-weight:800;color:${scoreColor};">${notaGeral}</div>
            <div style="font-size:0.8rem;color:#94a3b8;margin-bottom:4px;">Nota Geral</div>
            <div style="padding:4px 14px;border-radius:20px;display:inline-block;background:${scoreColor}22;color:${scoreColor};font-weight:700;font-size:0.85rem;margin-bottom:12px;">${notaLabel}</div>
            <div style="height:8px;background:rgba(255,255,255,0.1);border-radius:4px;overflow:hidden;">
                <div style="width:${notaGeral}%;height:100%;background:${scoreColor};border-radius:4px;"></div>
            </div>
        `;
        wrapper.appendChild(scoreSection);

        // Title
        const titleRow = document.createElement('div');
        titleRow.className = 'report-title-row';
        const title = document.createElement('div');
        title.className = 'report-title';
        title.textContent = `${info.emoji} ${info.titulo}`;
        titleRow.appendChild(title);
        wrapper.appendChild(titleRow);

        // Meta
        const meta = document.createElement('div');
        meta.className = 'report-meta';
        meta.appendChild(createChip('Contexto', contextName, '📍'));
        meta.appendChild(createChip('Trocas', `${stats.total} falas`, '🗣️'));
        meta.appendChild(createChip('Voce', `${stats.user} msg`, '👤'));
        meta.appendChild(createChip('AI', `${stats.ai} msg`, '🤖'));
        wrapper.appendChild(meta);

        // Elogios section
        if (info.elogios && info.elogios.length) {
            const elogiosBlock = document.createElement('div');
            elogiosBlock.style.cssText = 'margin-top:16px;padding:14px;background:rgba(34,197,94,0.08);border-left:3px solid #22c55e;border-radius:8px;';
            elogiosBlock.innerHTML = `<div style="font-weight:700;margin-bottom:8px;font-size:0.95rem;">🌟 O que você fez bem</div>` +
                info.elogios.map(e => `<div style="margin-bottom:4px;font-size:0.9rem;color:#d1d5db;">• ${escapeHtml(e)}</div>`).join('');
            wrapper.appendChild(elogiosBlock);
        }

        // Dicas section
        if (info.dicas && info.dicas.length) {
            const dicasBlock = document.createElement('div');
            dicasBlock.style.cssText = 'margin-top:12px;padding:14px;background:rgba(245,158,11,0.08);border-left:3px solid #f59e0b;border-radius:8px;';
            dicasBlock.innerHTML = `<div style="font-weight:700;margin-bottom:8px;font-size:0.95rem;">📈 O que melhorar</div>` +
                info.dicas.map(d => `<div style="margin-bottom:4px;font-size:0.9rem;color:#d1d5db;">• ${escapeHtml(d)}</div>`).join('');
            wrapper.appendChild(dicasBlock);
        }

        // Practice phrase
        if (info.frase_pratica) {
            const practiceBlock = document.createElement('div');
            practiceBlock.style.cssText = 'text-align:center;padding:18px;margin:16px 0;background:rgba(99,102,241,0.1);border:2px solid rgba(99,102,241,0.3);border-radius:12px;';
            practiceBlock.innerHTML = `<div style="font-size:0.8rem;color:#94a3b8;">🎯 Sua próxima missão</div>
                <div style="font-size:1.05rem;font-weight:700;margin-top:8px;color:#fff;">"${escapeHtml(info.frase_pratica)}"</div>`;
            wrapper.appendChild(practiceBlock);
        }

        // Phrase-by-phrase analysis block
        if (info.analise_frases && info.analise_frases.length) {
            wrapper.appendChild(buildAnaliseBlock(info.analise_frases));
        }

        if (info.erros_recorrentes && info.erros_recorrentes.length) {
            wrapper.appendChild(buildSimpleBlock('Erros recorrentes', '⚠️', info.erros_recorrentes, 'Sem padrões recorrentes.'));
        }

        if (info.plano_estudo && info.plano_estudo.length) {
            wrapper.appendChild(buildSimpleBlock('Plano de estudo', '🧭', info.plano_estudo, 'Sem plano disponível.'));
        }

        // Export buttons removed — report shown in modal only

        if (info.raw && !info.wasStructured) {
            const rawNote = document.createElement('div');
            rawNote.className = 'raw-report';
            rawNote.textContent = info.raw;
            wrapper.appendChild(rawNote);
        }

        // Show report in fullscreen modal instead of chat window
        const modalBody = document.getElementById('report-modal-body');
        const reportModal = document.getElementById('report-modal');
        if (modalBody && reportModal) {
            modalBody.innerHTML = '';
            modalBody.appendChild(wrapper);
            reportModal.style.display = 'flex';
        }
    }

    function openReportWindow(apiPayload, existingWindow = null) {
        const info = normalizeReportData(apiPayload);
        const stats = getConversationStats();
        const userName = user && user.name ? user.name : 'Aluno';
        const createdAt = new Date().toLocaleString('pt-BR');

        const escapeHtml = (value) => (value || '')
            .toString()
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');

        // Compute overall score (from Gemini or fallback)
        const notaGeral = info.nota_geral !== null ? info.nota_geral : computeAvgNaturalidade(info.analise_frases);
        const scoreColor = notaGeral >= 80 ? '#22c55e' : notaGeral >= 50 ? '#f59e0b' : '#ef4444';
        const dashLength = (notaGeral / 100) * 326.7;
        const notaLabel = notaGeral >= 90 ? 'Excelente!' : notaGeral >= 75 ? 'Muito Bom!' : notaGeral >= 60 ? 'Bom progresso!' : notaGeral >= 40 ? 'Continue praticando!' : 'Vamos melhorar juntos!';

        const elogiosHtml = (info.elogios && info.elogios.length)
            ? info.elogios.map(item => `<li style="margin-bottom:8px;">${escapeHtml(item)}</li>`).join('')
            : `<li>Sem elogios registrados.</li>`;

        const dicasHtml = (info.dicas && info.dicas.length)
            ? info.dicas.map(item => `<li style="margin-bottom:8px;">${escapeHtml(item)}</li>`).join('')
            : `<li>Sem dicas registradas.</li>`;

        const recorrentesHtml = (info.erros_recorrentes && info.erros_recorrentes.length)
            ? info.erros_recorrentes.map(item => `<li style="margin-bottom:8px;">${escapeHtml(item)}</li>`).join('')
            : `<li>Sem padrões recorrentes identificados.</li>`;

        const planoHtml = (info.plano_estudo && info.plano_estudo.length)
            ? info.plano_estudo.map(item => `<li style="margin-bottom:8px;">${escapeHtml(item)}</li>`).join('')
            : `<li>Sem plano específico nesta sessão.</li>`;

        const transcriptHtml = conversationLog.length
            ? conversationLog.map(entry => {
                const sender = escapeHtml(entry.sender || '');
                const text = escapeHtml(entry.text || '');
                const isAI = entry.sender === 'AI';
                return `<div class="transcript-line" style="padding:8px 12px;border-radius:8px;margin-bottom:4px;${isAI ? 'background:rgba(99,102,241,0.08);' : 'background:rgba(255,255,255,0.03);'}"><strong style="color:${isAI ? '#a5b4fc' : '#fbbf24'};">${sender}:</strong> ${text}</div>`;
            }).join('')
            : `<div class="empty">Sem falas registradas.</div>`;

        // Phrase-by-phrase analysis HTML
        const analiseHtml = (info.analise_frases && info.analise_frases.length)
            ? info.analise_frases.map((item, idx) => {
                const nat = typeof item.naturalidade === 'number' ? item.naturalidade : 50;
                let barColor = '#ef4444';
                if (nat >= 80) barColor = '#22c55e';
                else if (nat >= 50) barColor = '#f59e0b';
                const nivelText = escapeHtml(item.nivel || '');
                const explicacao = item.explicacao ? `<div style="font-size:0.85rem;color:var(--muted);padding:8px 10px;background:rgba(255,204,0,0.08);border-radius:6px;border-left:3px solid #f59e0b;margin-top:6px;">💡 ${escapeHtml(item.explicacao)}</div>` : '';
                const naturalLine = item.frase_natural ? `<div style="margin-bottom:6px;font-size:0.95rem;"><span style="color:#22c55e;">✅ Mais natural:</span> <strong>"${escapeHtml(item.frase_natural)}"</strong></div>` : '';
                return `
                    <div class="analise-card" style="page-break-inside:avoid;">
                        <div style="font-size:0.7rem;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:1px;">Frase ${idx + 1}</div>
                        <div style="margin-bottom:8px;font-size:0.95rem;"><span style="color:var(--muted);">🗣️ Você disse:</span> <strong>"${escapeHtml(item.frase_aluno || '')}"</strong></div>
                        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                            <div style="flex:1;height:8px;background:rgba(255,255,255,0.1);border-radius:4px;overflow:hidden;">
                                <div style="width:${nat}%;height:100%;background:${barColor};border-radius:4px;"></div>
                            </div>
                            <span style="font-weight:700;font-size:0.9rem;color:${barColor};min-width:40px;text-align:right;">${nat}%</span>
                        </div>
                        ${nivelText ? `<div style="font-size:0.8rem;color:${barColor};margin-bottom:8px;font-weight:600;">${nivelText}</div>` : ''}
                        ${naturalLine}
                        ${explicacao}
                    </div>
                `;
            }).join('')
            : `<div class="empty">Sem análise de frases disponível.</div>`;

        // Grammar/vocabulary summary tags
        const grammarTagsHtml = (info.resumo_gramatical && info.resumo_gramatical.length)
            ? info.resumo_gramatical.map(p => `<span style="padding:6px 14px;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.3);border-radius:20px;font-size:0.85rem;color:#a5b4fc;">${escapeHtml(p)}</span>`).join('')
            : '';

        // Practice phrase section
        const practicePhraseHtml = info.frase_pratica ? `
  <section class="mission-card" style="page-break-inside:avoid;background:linear-gradient(135deg,rgba(99,102,241,0.15),rgba(139,92,246,0.1));border:2px solid rgba(99,102,241,0.3);border-radius:16px;padding:24px;text-align:center;">
    <div style="font-size:0.85rem;color:var(--muted);margin-bottom:4px;">🎯 Sua próxima missão</div>
    <p style="font-size:1.3rem;font-weight:700;margin:12px 0 4px;color:#fff;">"${escapeHtml(info.frase_pratica)}"</p>
    <p style="color:var(--muted);font-size:0.85rem;margin:0;">Tente falar esta frase na sua próxima prática!</p>
  </section>` : '';

        // Final grade banner
        const gradeEmoji = notaGeral >= 80 ? '🏆' : notaGeral >= 60 ? '💪' : '📖';
        const gradeMsg = notaGeral >= 80 ? 'Você está dominando o idioma! Continue com essa dedicação.' :
            notaGeral >= 60 ? 'Ótimo progresso! Cada conversa te deixa mais fluente.' :
                'Cada erro é uma oportunidade de aprender. Você já está no caminho certo!';
        const gradeBg = notaGeral >= 70 ? 'rgba(34,197,94,0.1),rgba(16,185,129,0.05)' : 'rgba(245,158,11,0.1),rgba(234,88,12,0.05)';
        const gradeBorder = notaGeral >= 70 ? 'rgba(34,197,94,0.2)' : 'rgba(245,158,11,0.2)';

        const summaryText = [
            ...(info.elogios || []).slice(0, 4),
            ...(info.dicas || []).slice(0, 2)
        ].filter(Boolean).join(' • ');

        let win = existingWindow;
        if (win && win.closed) {
            win = null;
        }
        if (!win) {
            win = window.open('', '_blank');
        }
        if (!win) return false;

        const html = `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatório da Conversa</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"><\/script>
<style>
:root {
  --bg: #0f1115;
  --panel: #171a21;
  --panel-2: #1f2430;
  --accent: #ffcc00;
  --accent-2: #e50914;
  --text: #f8fafc;
  --muted: #9aa4b2;
  --success: #22c55e;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: 'Inter', sans-serif;
  background: radial-gradient(circle at top, #1a1f2b, #0c0f14 60%);
  color: var(--text);
}
header {
  padding: 40px 8vw 24px;
  background: linear-gradient(135deg, rgba(229,9,20,0.25), transparent 60%);
}
header h1 {
  font-family: 'Playfair Display', serif;
  font-size: 2.2rem;
  margin: 0 0 8px;
}
header p {
  margin: 0;
  color: var(--muted);
}
main {
  padding: 24px 8vw 60px;
  display: grid;
  gap: 24px;
}
.summary {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}
.summary .card {
  background: var(--panel);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  padding: 16px;
}
.summary .card strong { display:block; margin-bottom: 6px; font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.summary .card .val { font-size: 1.4rem; font-weight: 700; }
.highlight {
  background: var(--panel-2);
  border-radius: 16px;
  padding: 20px;
  border: 1px solid rgba(255,255,255,0.08);
}
.highlight h2 {
  margin-top: 0;
  font-size: 1.2rem;
}
.highlight ul { margin: 0; padding-left: 18px; line-height: 1.7; }
.corrections {
  display: grid;
  gap: 12px;
}
.correction-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 14px;
  padding: 16px;
  page-break-inside: avoid;
}
.badge-row { display: flex; gap: 8px; align-items: center; }
.badge {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
}
.tag {
  border: 1px solid rgba(255,255,255,0.2);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.7rem;
  color: var(--accent);
}
.line { margin-top: 8px; }
.line span { color: #fff; }
.line.bad { color: #fca5a5; }
.line.good { color: #86efac; }
.note {
  margin-top: 10px;
  padding: 8px 12px;
  background: rgba(255,255,255,0.05);
  border-left: 3px solid #60a5fa;
  border-radius: 8px;
  color: var(--muted);
}
.explain {
  margin-top: 10px;
  padding: 10px 12px;
  background: rgba(255,204,0,0.08);
  border-radius: 8px;
  color: var(--muted);
}
.transcript {
  background: var(--panel);
  border-radius: 16px;
  padding: 16px;
  border: 1px solid rgba(255,255,255,0.08);
  max-height: 400px;
  overflow-y: auto;
}
.transcript-line { margin-bottom: 4px; color: var(--muted); }
.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
}
.button {
  background: var(--accent-2);
  border: none;
  color: #fff;
  padding: 12px 20px;
  border-radius: 10px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
}
.button:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(229,9,20,0.4); }
.button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.button.secondary {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.2);
}
.button.secondary:hover { background: rgba(255,255,255,0.05); }
.footer-note { color: var(--muted); font-size: 0.9rem; }
.empty { color: var(--muted); }
.analise-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 12px;
}
@media print {
  body { background: #0f1115 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .action-bar, .no-print { display: none !important; }
}
@media (max-width: 600px) {
  header { padding: 24px 5vw 16px; }
  header h1 { font-size: 1.6rem; }
  main { padding: 16px 5vw 40px; }
  .summary { grid-template-columns: repeat(2, 1fr); }
}
</style>
</head>
<body>
<header>
  <div style="display:flex;align-items:center;gap:28px;flex-wrap:wrap;">
    <div style="position:relative;width:110px;height:110px;flex-shrink:0;">
      <svg viewBox="0 0 120 120" style="transform:rotate(-90deg);width:110px;height:110px;">
        <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="10"/>
        <circle cx="60" cy="60" r="52" fill="none" stroke="${scoreColor}" stroke-width="10"
          stroke-dasharray="${dashLength} ${326.7 - dashLength}" stroke-linecap="round"/>
      </svg>
      <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
        <span style="font-size:2rem;font-weight:800;color:${scoreColor};">${notaGeral}</span>
        <span style="font-size:0.65rem;color:var(--muted);">de 100</span>
      </div>
    </div>
    <div>
      <h1>${escapeHtml(info.emoji)} ${escapeHtml(info.titulo)}</h1>
      <p>${escapeHtml(contextName)} &bull; ${escapeHtml(userName)} &bull; ${escapeHtml(createdAt)}</p>
      <div style="margin-top:8px;padding:6px 16px;border-radius:20px;display:inline-block;background:${scoreColor}22;color:${scoreColor};font-weight:700;font-size:0.9rem;">
        ${notaLabel}
      </div>
    </div>
  </div>
</header>
<main>
  <section class="summary">
    <div class="card"><strong>Tom</strong><div class="val">${escapeHtml(info.tom)}</div></div>
    <div class="card"><strong>Total de falas</strong><div class="val">${stats.total}</div></div>
    <div class="card"><strong>Suas mensagens</strong><div class="val">${stats.user}</div></div>
    <div class="card"><strong>Respostas da IA</strong><div class="val">${stats.ai}</div></div>
  </section>

  <section class="highlight" style="border-left:4px solid #22c55e;">
    <h2>🌟 O que você fez bem</h2>
    <ul>${elogiosHtml}</ul>
  </section>

  <section class="highlight" style="border-left:4px solid #f59e0b;">
    <h2>📈 O que melhorar</h2>
    <ul>${dicasHtml}</ul>
  </section>

  <section class="highlight" style="border-left:4px solid #ef4444;">
    <h2>⚠️ Erros recorrentes</h2>
    <ul>${recorrentesHtml}</ul>
  </section>

  <section class="highlight" style="border-left:4px solid #38bdf8;">
    <h2>🧭 Plano de estudo</h2>
    <ul>${planoHtml}</ul>
  </section>

  ${practicePhraseHtml}

  ${grammarTagsHtml ? `
  <section class="highlight">
    <h2>📚 Pontos de Gramática e Vocabulário</h2>
    <div style="display:flex;flex-wrap:wrap;gap:8px;">
      ${grammarTagsHtml}
    </div>
  </section>` : ''}

  <section class="highlight">
    <h2>🎯 Análise Frase a Frase</h2>
    <div class="corrections">${analiseHtml}</div>
  </section>

  <section style="text-align:center;padding:32px 20px;background:linear-gradient(135deg,${gradeBg});border-radius:16px;border:1px solid ${gradeBorder};page-break-inside:avoid;">
    <div style="font-size:3rem;">${gradeEmoji}</div>
    <h2 style="margin:8px 0;">Nota Final: ${notaGeral}/100</h2>
    <p style="color:var(--muted);max-width:400px;margin:0 auto;">${escapeHtml(gradeMsg)}</p>
  </section>

  <section class="highlight">
    <h2>💬 Transcrição da conversa</h2>
    <div class="transcript">${transcriptHtml}</div>
  </section>

  <section class="highlight no-print">
    <h2>Exportar relatório</h2>
    <div class="action-bar">
      <button class="button" id="download-pdf">📄 Baixar PDF</button>
      <button class="button secondary" id="copy-summary">📋 Copiar resumo</button>
    </div>
    <p class="footer-note">O PDF inclui todo o conteúdo desta página, colorido e completo.</p>
  </section>
</main>
<script>
document.getElementById('download-pdf').addEventListener('click', async () => {
  const btn = document.getElementById('download-pdf');
  btn.disabled = true;
  btn.textContent = 'Gerando PDF...';

  try {
    const element = document.querySelector('main');
    const opt = {
      margin: [8, 8, 8, 8],
      filename: 'relatorio_' + new Date().toISOString().slice(0,10) + '.pdf',
      image: { type: 'jpeg', quality: 0.95 },
      html2canvas: { scale: 2, useCORS: true, backgroundColor: '#0f1115' },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
      pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
    };
    await html2pdf().set(opt).from(element).save();
  } catch (err) {
    console.error('PDF error:', err);
    alert('Erro ao gerar PDF. Tente novamente.');
  } finally {
    btn.disabled = false;
    btn.textContent = '📄 Baixar PDF';
  }
});

document.getElementById('copy-summary').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(${JSON.stringify(summaryText).replace(/</g, '\u003c')} || '');
    const btn = document.getElementById('copy-summary');
    btn.textContent = '✅ Copiado!';
    setTimeout(() => { btn.textContent = '📋 Copiar resumo'; }, 2000);
  } catch (err) {
    alert('Não foi possível copiar o resumo.');
  }
});
<\/script>
</body>
</html>`;

        win.document.open();
        win.document.write(html);
        win.document.close();
        return true;
    }


    // Function to close report modal
    function closeReportModal() {
        const reportModal = document.getElementById('report-modal');
        if (reportModal) {
            reportModal.style.display = 'none';
        }
    }

    // Make closeReportModal available globally
    window.closeReportModal = closeReportModal;

    function computeAvgNaturalidade(frases) {
        if (!frases || !frases.length) return 50;
        const sum = frases.reduce((a, f) => a + (typeof f.naturalidade === 'number' ? f.naturalidade : 50), 0);
        return Math.round(sum / frases.length);
    }

    function normalizeReportData(payload) {
        const base = {
            titulo: "Resumo da sessao",
            emoji: "✨",
            tom: "positivo",
            correcoes: [],
            analise_frases: [],
            elogios: [],
            dicas: [],
            frase_pratica: "",
            erros_recorrentes: [],
            plano_estudo: [],
            nota_geral: null,
            resumo_gramatical: [],
            raw: "",
            wasStructured: false
        };

        if (!payload) return base;

        const source = payload.report || payload;
        base.raw = payload.feedback || payload.raw || (typeof source === 'string' ? source : "");

        if (typeof source === 'string') {
            return base;
        }

        base.wasStructured = true;
        base.titulo = source.titulo || base.titulo;
        base.emoji = source.emoji || base.emoji;
        base.tom = source.tom || base.tom;
        base.frase_pratica = source.frase_pratica || "";

        const corrections = Array.isArray(source.correcoes) ? source.correcoes : [];
        base.correcoes = corrections.map(normalizeCorrection).filter(Boolean);

        base.analise_frases = Array.isArray(source.analise_frases) ? source.analise_frases.filter(Boolean) : [];
        base.elogios = Array.isArray(source.elogios) ? source.elogios.filter(Boolean) : [];
        base.dicas = Array.isArray(source.dicas) ? source.dicas.filter(Boolean) : [];
        base.erros_recorrentes = Array.isArray(source.erros_recorrentes) ? source.erros_recorrentes.filter(Boolean) : [];
        base.plano_estudo = Array.isArray(source.plano_estudo) ? source.plano_estudo.filter(Boolean) : [];
        base.nota_geral = typeof source.nota_geral === 'number' ? source.nota_geral : null;
        base.resumo_gramatical = Array.isArray(source.resumo_gramatical) ? source.resumo_gramatical.filter(Boolean) : [];

        return base;
    }

    function normalizeCorrection(item) {
        if (!item) return null;
        if (typeof item === 'string') {
            const parts = item.split('->').map(part => part.trim()).filter(Boolean);
            if (!parts.length) return null;
            return { ruim: parts[0] || "", boa: parts[1] || "", explicacao: "" };
        }

        const ruim = item.ruim || item.errada || item.incorreta || item.before || item.frase_errada || "";
        const boa = item.boa || item.correta || item.after || item.sugerida || item.frase_correta || "";
        const explicacao = item.explicacao || item.explanation || item.razao || "";

        if (!ruim && !boa) return null;
        return { ruim, boa, explicacao };
    }

    function buildAnaliseBlock(frases) {
        const block = document.createElement('div');
        block.className = 'report-block analise-block';

        const title = document.createElement('div');
        title.className = 'block-title';
        const icon = document.createElement('span');
        icon.className = 'block-icon';
        icon.textContent = '🎯';
        title.appendChild(icon);
        title.appendChild(document.createTextNode('Análise Frase a Frase'));
        block.appendChild(title);

        const container = document.createElement('div');
        container.style.cssText = 'display: flex; flex-direction: column; gap: 12px;';

        if (!frases || !frases.length) {
            const empty = document.createElement('div');
            empty.className = 'muted';
            empty.textContent = 'Sem análise de frases disponível.';
            container.appendChild(empty);
        } else {
            frases.forEach((item) => {
                const card = document.createElement('div');
                card.style.cssText = `
                    background: rgba(0,0,0,0.3);
                    border: 1px solid rgba(255,255,255,0.1);
                    border-radius: 12px;
                    padding: 16px;
                `;

                const nat = typeof item.naturalidade === 'number' ? item.naturalidade : 50;
                let barColor = '#ef4444';
                if (nat >= 80) barColor = '#22c55e';
                else if (nat >= 50) barColor = '#f59e0b';

                // Student phrase
                const studentLine = document.createElement('div');
                studentLine.style.cssText = 'margin-bottom: 8px; font-size: 0.95rem;';
                studentLine.innerHTML = `<span style="color:#94a3b8;">🗣️ Você disse:</span> <strong>"${escapeHtml(item.frase_aluno || '')}"</strong>`;
                card.appendChild(studentLine);

                // Progress bar
                const barWrap = document.createElement('div');
                barWrap.style.cssText = 'display: flex; align-items: center; gap: 10px; margin-bottom: 8px;';

                const barBg = document.createElement('div');
                barBg.style.cssText = 'flex: 1; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;';

                const barFill = document.createElement('div');
                barFill.style.cssText = `width: ${nat}%; height: 100%; background: ${barColor}; border-radius: 4px; transition: width 0.5s ease;`;
                barBg.appendChild(barFill);
                barWrap.appendChild(barBg);

                const pctLabel = document.createElement('span');
                pctLabel.style.cssText = `font-weight: 700; font-size: 0.9rem; color: ${barColor}; min-width: 40px; text-align: right;`;
                pctLabel.textContent = `${nat}%`;
                barWrap.appendChild(pctLabel);

                card.appendChild(barWrap);

                // Level label
                if (item.nivel) {
                    const nivel = document.createElement('div');
                    nivel.style.cssText = `font-size: 0.8rem; color: ${barColor}; margin-bottom: 8px; font-weight: 600;`;
                    nivel.textContent = item.nivel;
                    card.appendChild(nivel);
                }

                // Natural version
                if (item.frase_natural) {
                    const naturalLine = document.createElement('div');
                    naturalLine.style.cssText = 'margin-bottom: 6px; font-size: 0.95rem;';
                    naturalLine.innerHTML = `<span style="color:#22c55e;">✅ Mais natural:</span> <strong>"${escapeHtml(item.frase_natural || '')}"</strong>`;
                    card.appendChild(naturalLine);
                }

                // Explanation
                if (item.explicacao) {
                    const explLine = document.createElement('div');
                    explLine.style.cssText = 'font-size: 0.85rem; color: #94a3b8; padding: 8px 10px; background: rgba(255,204,0,0.08); border-radius: 6px; border-left: 3px solid #f59e0b;';
                    explLine.textContent = '💡 ' + item.explicacao;
                    card.appendChild(explLine);
                }

                container.appendChild(card);
            });
        }

        block.appendChild(container);
        return block;
    }

    function buildCorrectionsBlock(list, fallbackText) {
        const block = document.createElement('div');
        block.className = 'report-block corrections-block';

        const title = document.createElement('div');
        title.className = 'block-title';
        const icon = document.createElement('span');
        icon.className = 'block-icon';
        icon.textContent = '✏️';
        title.appendChild(icon);
        title.appendChild(document.createTextNode('Análise das Frases'));
        block.appendChild(title);

        const ul = document.createElement('ul');
        ul.className = 'report-list corrections-list';

        if (!list || !list.length) {
            const li = document.createElement('li');
            li.className = 'muted';
            li.textContent = fallbackText || 'Sem correções por enquanto.';
            ul.appendChild(li);
        } else {
            list.forEach((correction) => {
                const li = document.createElement('li');
                li.className = 'correction-item';

                // 1. Avaliação Geral (badge colorido)
                const avaliacaoBadge = document.createElement('div');
                avaliacaoBadge.className = 'avaliacao-badge';

                let badgeColor = '#10b981'; // verde (Correta)
                let badgeText = correction.avaliacaoGeral || 'Analisando';

                if (badgeText === 'Incorreta') {
                    badgeColor = '#ef4444'; // vermelho
                } else if (badgeText === 'Aceitável') {
                    badgeColor = '#f59e0b'; // amarelo/laranja
                }

                avaliacaoBadge.style.cssText = `
                    display: inline-block;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 0.75rem;
                    font-weight: 700;
                    color: white;
                    background: ${badgeColor};
                    margin-bottom: 8px;
                `;
                avaliacaoBadge.textContent = badgeText;
                li.appendChild(avaliacaoBadge);

                // 2. Tag de Tipo de Erro (se houver)
                if (correction.tag) {
                    const tagBadge = document.createElement('span');
                    tagBadge.className = 'error-tag';

                    let tagColor = '#3b82f6'; // azul (Pouco Natural)
                    if (correction.tag.includes('Estrutura Incorreta')) {
                        tagColor = '#ef4444'; // vermelho
                    } else if (correction.tag.includes('Compreensível')) {
                        tagColor = '#f59e0b'; // laranja
                    }

                    tagBadge.style.cssText = `
                        display: inline-block;
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 0.7rem;
                        font-weight: 600;
                        background: ${tagColor}40;
                        border: 1px solid ${tagColor};
                        color: ${tagColor};
                        margin-left: 8px;
                    `;
                    tagBadge.textContent = correction.tag;
                    li.appendChild(tagBadge);
                }

                // 3. Comentário Breve
                if (correction.comentarioBreve) {
                    const comentario = document.createElement('div');
                    comentario.className = 'comentario-breve';
                    comentario.style.cssText = `
                        margin: 8px 0;
                        padding: 8px 12px;
                        background: rgba(255,255,255,0.05);
                        border-left: 3px solid #60a5fa;
                        font-size: 0.9rem;
                        color: #94a3b8;
                    `;
                    comentario.textContent = correction.comentarioBreve;
                    li.appendChild(comentario);
                }

                // 4. Frase Original (com erro destacado)
                const badLine = document.createElement('div');
                badLine.className = 'correction-line bad';
                badLine.innerHTML = `<span style="color:#ef4444;">❌ Você disse:</span> "${escapeHtml(correction.fraseOriginal || correction.ruim || '')}"`;
                li.appendChild(badLine);

                // 5. Frase Corrigida
                const goodLine = document.createElement('div');
                goodLine.className = 'correction-line good';
                goodLine.innerHTML = `<span style="color:#10b981;">✓ Melhor forma:</span> "${escapeHtml(correction.fraseCorrigida || correction.boa || '')}"`;
                li.appendChild(goodLine);

                // 6. Explicação Detalhada
                if (correction.explicacaoDetalhada || correction.explicacao) {
                    const explanationLine = document.createElement('div');
                    explanationLine.className = 'correction-line explanation';
                    explanationLine.style.cssText = `
                        color: #94a3b8;
                        font-size: 0.85rem;
                        margin-top: 8px;
                        padding: 10px;
                        background: rgba(139, 92, 246, 0.1);
                        border-radius: 6px;
                        border-left: 3px solid #8b5cf6;
                    `;
                    explanationLine.innerHTML = `💡 <strong>Por que mudar:</strong> ${escapeHtml(correction.explicacaoDetalhada || correction.explicacao)}`;
                    li.appendChild(explanationLine);
                }

                ul.appendChild(li);
            });
        }

        block.appendChild(ul);
        return block;
    }

    function buildSimpleBlock(titleText, iconText, items, emptyText) {
        const block = document.createElement('div');
        block.className = 'report-block';

        const title = document.createElement('div');
        title.className = 'block-title';
        const icon = document.createElement('span');
        icon.className = 'block-icon';
        icon.textContent = iconText;
        title.appendChild(icon);
        title.appendChild(document.createTextNode(titleText));
        block.appendChild(title);

        const ul = document.createElement('ul');
        ul.className = 'report-list';

        if (!items.length) {
            const li = document.createElement('li');
            li.className = 'muted';
            li.textContent = emptyText;
            ul.appendChild(li);
        } else {
            items.forEach(text => {
                const li = document.createElement('li');
                li.textContent = text;
                ul.appendChild(li);
            });
        }

        block.appendChild(ul);
        return block;
    }

    function createChip(label, value, icon = '') {
        const chip = document.createElement('span');
        chip.className = 'meta-chip';

        if (icon) {
            const iconSpan = document.createElement('span');
            iconSpan.textContent = icon;
            chip.appendChild(iconSpan);
        }

        const text = document.createElement('span');
        text.textContent = `${label}: ${value}`;
        chip.appendChild(text);

        return chip;
    }

    function getConversationStats() {
        const userMessages = conversationLog.filter(msg => msg.sender !== 'AI' && msg.sender !== 'System' && msg.sender !== 'Relatorio').length;
        const aiMessages = conversationLog.filter(msg => msg.sender === 'AI').length;
        return {
            total: conversationLog.length,
            user: userMessages,
            ai: aiMessages
        };
    }

    function showSimulatorFeedback(feedbackText) {
        if (!chatWindow || !feedbackText) return;
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'simulator-feedback';
        feedbackDiv.textContent = feedbackText;
        chatWindow.appendChild(feedbackDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function buildLearningFeedbackPayload(turnFeedback, userText, backendData = null) {
        const baseUserText = String(userText || '').trim();
        if (!baseUserText) return null;

        const source = turnFeedback && typeof turnFeedback === 'object' ? turnFeedback : {};
        const kind = String(source.kind || 'none').trim();
        const suggested = String(source.suggested_text || '').trim();
        const reason = String(source.reason || '').trim();
        if (kind && kind !== 'none' && suggested) {
            return {
                kind,
                user_text: String(source.user_text || baseUserText).trim() || baseUserText,
                suggested_text: suggested,
                reason: reason || 'Aqui esta uma forma melhor para esta resposta.'
            };
        }

        const normalizedUser = normalizeComparableText(baseUserText);
        if (/\bi want\b/.test(normalizedUser) && !/\bplease\b/.test(normalizedUser)) {
            let suggestion = baseUserText.replace(/\bi want\b/i, "I'd like").trim();
            suggestion = suggestion.replace(/[.?!]+$/g, '').trim();
            if (!/\bplease\b/i.test(suggestion)) {
                suggestion = `${suggestion}, please`;
            }
            suggestion = `${suggestion}.`;
            return {
                kind: 'style_upgrade',
                user_text: baseUserText,
                suggested_text: suggestion,
                reason: 'Para soar mais natural e educado, prefira "I\'d like ... , please."'
            };
        }

        const mustRetry = Boolean(backendData && backendData.must_retry);
        const suggestedWords = Array.isArray(backendData && backendData.suggested_words)
            ? backendData.suggested_words.map(item => String(item || '').trim()).filter(Boolean)
            : [];
        if (mustRetry && suggestedWords.length) {
            return {
                kind: 'error_correction',
                user_text: baseUserText,
                suggested_text: suggestedWords.join(' '),
                reason: 'Ajuste a estrutura para ficar mais natural neste contexto.'
            };
        }

        return {
            kind: 'ok',
            user_text: baseUserText,
            suggested_text: baseUserText,
            reason: 'Sua resposta esta correta para o contexto.'
        };
    }

    function getIntentFallbackReply(intent = 'general') {
        const pool = questionReplyPools[intent] || questionReplyPools.general;
        if (Array.isArray(pool) && pool.length && pool[0] && pool[0].en) {
            return String(pool[0].en).trim();
        }
        return 'Could you repeat, please?';
    }

    function getIntentMismatchReason(intent = 'general') {
        if (intent === 'size') return 'A resposta precisa indicar um tamanho: small, medium ou large.';
        if (intent === 'coffee_kind') return 'Responda com o tipo da bebida, por exemplo: latte, cappuccino ou coffee.';
        if (intent === 'to_go_here') return 'Responda se e para levar ou para consumir aqui.';
        if (intent === 'hot_iced') return 'Responda se prefere hot ou iced.';
        if (intent === 'milk_sugar') return 'Responda se quer milk/sugar ou sem.';
        if (intent === 'order_request') return 'Responda com a bebida que voce quer pedir.';
        if (intent === 'anything_else') return 'Responda com yes/no ou diga o item extra.';
        return 'Essa resposta nao corresponde a pergunta anterior.';
    }

    function hasIntentCompatibleAnswer(text = '', intent = 'general') {
        const normalized = normalizeComparableText(text);
        if (!normalized) return false;
        if (intent === 'general') return true;
        return replyMatchesIntent({ en: text }, intent);
    }

    function inferLearningFeedbackFromText(userText, questionPrompt = '') {
        const text = String(userText || '').trim();
        if (!text) return null;
        const normalized = normalizeComparableText(text);
        const promptIntent = detectQuestionIntent(questionPrompt);

        if (/\bwater hot coffee\b/i.test(normalized)) {
            return {
                kind: 'error_correction',
                user_text: text,
                suggested_text: "I'd like a hot coffee, please.",
                reason: 'A ordem das palavras ficou incorreta. Use: adjective + drink.'
            };
        }

        const orderPattern = /\b(a|an)\s+([a-z]+)\s+(hot|cold|small|medium|large)\s+(coffee|tea|latte|cappuccino|espresso)\b/i;
        const orderMatch = normalized.match(orderPattern);
        if (orderMatch) {
            const adjective = orderMatch[3];
            const drink = orderMatch[4];
            return {
                kind: 'error_correction',
                user_text: text,
                suggested_text: `I'd like a ${adjective} ${drink}, please.`,
                reason: 'Use primeiro o adjetivo e depois a bebida.'
            };
        }

        if (promptIntent === 'order_request') {
            const knownItems = /\b(coffee|latte|cappuccino|espresso|tea|drink|water|juice|soda|beer|wine|burger|sandwich|salad|cake|pie|muffin|croissant|bagel|toast|pizza|pasta|soup|steak|chicken|fish|fries|cookie|donut|pancake|waffle|omelette|breakfast|lunch|dinner|meal)\b/i;
            const hasKnownItem = knownItems.test(normalized);
            const hasVerb = /\b(i('| )?d like|can i have|i want|i would like|just|give me|get me)\b/i.test(normalized);
            if (hasVerb && !hasKnownItem) {
                // Try to extract the item the user mentioned (noun after verb phrase)
                const itemMatch = normalized.match(/\b(?:like|want|have|get)\s+(?:a|an|some)?\s*(.+?)(?:\s*please)?$/i);
                if (itemMatch && itemMatch[1]) {
                    const userItem = itemMatch[1].trim();
                    return {
                        kind: 'style_upgrade',
                        user_text: text,
                        suggested_text: `I'd like ${/^[aeiou]/i.test(userItem) ? 'an' : 'a'} ${userItem}, please.`,
                        reason: 'Use "I\'d like" + item para soar mais educado.'
                    };
                }
            }
        }

        if (!hasIntentCompatibleAnswer(text, promptIntent)) {
            return {
                kind: 'error_correction',
                user_text: text,
                suggested_text: getIntentFallbackReply(promptIntent),
                reason: getIntentMismatchReason(promptIntent)
            };
        }

        return null;
    }

    function isLikelyQuestionSentence(text) {
        const value = String(text || '').trim();
        if (!value) return false;
        if (value.endsWith('?')) return true;
        return /\b(what|how|when|where|why|who|which|do you|are you|can you|could you|would you|may i|qual|como|quando|onde|por que|voce gostaria|quer|pode)\b/i.test(value);
    }

    function isTeacherSentence(text, isTranslation = false) {
        const value = String(text || '').trim();
        if (!value) return false;
        if (!isTranslation) {
            return /\b(you can (also )?say|you could say|instead of|optional upgrade|a useful phrase|useful model|model sentence|to sound (more )?(polite|natural)|it's very common|this is (more )?(polite|natural)|great job|nice job|polite way|more natural way|try saying)\b/i.test(value);
        }
        return /\b(voce (tamb[eé]m )?pode dizer|voce poderia dizer|em vez de|upgrade opcional|forma mais natural|para soar|e muito comum|otimo trabalho|bom trabalho|modelo|forma educada|maneira mais natural)\b/i.test(value);
    }

    function cleanScenarioSentence(sentence) {
        let clean = String(sentence || '').trim();
        clean = clean.replace(/^[)\]\-\s]+/, '').trim();
        clean = clean.replace(/^\(+\s*/, '').trim();
        clean = clean.replace(/\s*\)+$/, '').trim();
        clean = clean.replace(/\s+/g, ' ');
        return clean;
    }

    function ensureStatementPunctuation(sentence) {
        const value = cleanScenarioSentence(sentence);
        if (!value) return '';
        if (/[.!?]$/.test(value)) return value;
        return `${value}.`;
    }

    function ensureQuestionPunctuation(sentence) {
        const value = cleanScenarioSentence(sentence).replace(/[.!]+$/, '').trim();
        if (!value) return '';
        return value.endsWith('?') ? value : `${value}?`;
    }

    function extractScenarioParts(sentences = []) {
        if (!Array.isArray(sentences) || !sentences.length) {
            return { statement: '', question: '' };
        }
        const clean = sentences.map(cleanScenarioSentence).filter(Boolean);
        if (!clean.length) return { statement: '', question: '' };
        const question = [...clean].reverse().find(sentence => isLikelyQuestionSentence(sentence)) || '';
        const statement = clean.find(sentence => !isLikelyQuestionSentence(sentence)) || '';
        return { statement, question };
    }

    function buildAckTranslation(statementEn = '') {
        const normalized = normalizeComparableText(statementEn);
        if (!normalized) return '';
        if (/^(ok|okay|alright|all right|great|nice|sure)$/.test(normalized)) return 'Certo.';
        if (/^(no problem|sounds good|perfect)$/.test(normalized)) return 'Perfeito.';
        return '';
    }

    function buildQuestionTranslationFallback(questionEn = '') {
        const q = normalizeComparableText(questionEn);
        if (!q) return '';
        if (/(what would you like|what can i get|what can i get started|what do you want)/i.test(q)) return 'O que voce gostaria hoje?';
        if (/(what kind of coffee|which coffee|kind of coffee)/i.test(q)) return 'Que tipo de cafe voce gostaria?';
        if (/(what size|which size|size would you like)/i.test(q)) return 'Qual tamanho voce gostaria?';
        if (/(to go|for here|take away|takeaway)/i.test(q)) return 'Voce gostaria para levar ou para consumir aqui?';
        if (/(hot or iced|iced or hot)/i.test(q)) return 'Voce prefere quente ou gelado?';
        if (/(with sugar|with milk|sugar or milk)/i.test(q)) return 'Voce quer com acucar ou leite?';
        if (/(anything else|something else)/i.test(q)) return 'Mais alguma coisa?';
        return '';
    }

    function simplifyLearningScenarioResponse(text, translation = '') {
        const cleanedText = sanitizeCoachDisplayText(text);
        const rawSentences = splitMessageIntoSentences(cleanedText);
        const filteredSentences = rawSentences.filter(sentence => !isTeacherSentence(sentence, false));
        const selectedEnglish = filteredSentences.length ? filteredSentences : rawSentences;
        const enParts = extractScenarioParts(selectedEnglish);

        let finalText = '';
        const finalTextParts = [];
        if (enParts.statement) finalTextParts.push(ensureStatementPunctuation(enParts.statement));
        if (enParts.question) finalTextParts.push(ensureQuestionPunctuation(enParts.question));
        if (!finalTextParts.length && selectedEnglish.length) {
            finalTextParts.push(cleanScenarioSentence(selectedEnglish[0]));
        }
        finalText = finalTextParts.join(' ').replace(/\([^)]*\)/g, '').replace(/\s+/g, ' ').trim();
        if (!finalText) finalText = cleanedText;

        const cleanedTranslation = sanitizeTranslationDisplayText(translation, cleanedText) || sanitizeCoachDisplayText(translation);
        const ptSentences = splitMessageIntoSentences(cleanedTranslation);
        const filteredPt = ptSentences.filter(sentence => !isTeacherSentence(sentence, true));
        const selectedPt = filteredPt.length ? filteredPt : ptSentences;
        const ptParts = extractScenarioParts(selectedPt);

        const finalTranslationParts = [];
        if (enParts.statement) {
            const ack = buildAckTranslation(enParts.statement);
            if (ack) {
                finalTranslationParts.push(ensureStatementPunctuation(ack));
            } else if (ptParts.statement) {
                finalTranslationParts.push(ensureStatementPunctuation(ptParts.statement));
            }
        } else if (ptParts.statement) {
            finalTranslationParts.push(ensureStatementPunctuation(ptParts.statement));
        }

        if (enParts.question) {
            const questionPt = ptParts.question || buildQuestionTranslationFallback(enParts.question);
            if (questionPt) {
                finalTranslationParts.push(ensureQuestionPunctuation(questionPt));
            }
        } else if (ptParts.question) {
            finalTranslationParts.push(ensureQuestionPunctuation(ptParts.question));
        }

        let finalTranslation = finalTranslationParts.join(' ').replace(/\s+/g, ' ').trim();
        if (!finalTranslation) finalTranslation = cleanedTranslation;

        return {
            text: finalText || cleanedText,
            translation: finalTranslation || cleanedTranslation
        };
    }

    function showLearningFeedbackPopup(feedback, replyOptions = [], aiQuestion = '') {
        if (isFreeConversation || !feedback) return Promise.resolve();
        const kind = String(feedback.kind || 'none').trim();
        const userText = String(feedback.user_text || '').trim();
        const suggested = String(feedback.suggested_text || userText || '').trim();
        const reason = String(feedback.reason || '').trim();
        const replies = normalizeSuggestionItems(replyOptions).slice(0, 3);
        if (!userText || !suggested) return Promise.resolve();
        if (kind === 'none' && !replies.length) return Promise.resolve();

        learningFeedbackPending = true;
        setMicReadyState();
        const aiQuestionDisplay = String(aiQuestion || '').trim();

        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'learning-feedback-overlay';

            const modal = document.createElement('div');
            modal.className = `learning-feedback-modal ${kind === 'error_correction' ? 'error' : (kind === 'style_upgrade' ? 'style' : 'ok')}`;
            modal.classList.add('learning-guidance-modal');

            const title = document.createElement('div');
            title.className = 'learning-feedback-title';
            title.textContent = aiQuestionDisplay
                ? `\u{1F5E3}\uFE0F "${aiQuestionDisplay}"`
                : 'Sobre a sua resposta';
            modal.appendChild(title);

            const stepBadge = document.createElement('div');
            stepBadge.className = 'learning-guidance-step';
            modal.appendChild(stepBadge);

            const contentWrap = document.createElement('div');
            contentWrap.className = 'learning-guidance-content';
            modal.appendChild(contentWrap);

            const steps = ['feedback'];
            if (replies.length) steps.push('answers');
            let currentStepIndex = 0;

            function renderFeedbackStep() {
                contentWrap.innerHTML = '';
                const status = document.createElement('div');
                status.className = 'learning-guidance-status';
                status.textContent = kind === 'error_correction'
                    ? '⚠️ Precisa ajustar'
                    : (kind === 'style_upgrade' ? '💡 Pode melhorar' : '✅ Resposta correta');
                contentWrap.appendChild(status);

                const saidLine = document.createElement('div');
                saidLine.className = 'learning-feedback-line';
                saidLine.innerHTML = `<span>🎤 Você disse:</span> "${escapeHtml(userText)}"`;
                contentWrap.appendChild(saidLine);

                const suggestionLine = document.createElement('div');
                suggestionLine.className = 'learning-feedback-line suggestion';
                suggestionLine.innerHTML = kind === 'error_correction'
                    ? `<span>✨ Forma sugerida:</span> "${escapeHtml(suggested)}"`
                    : (kind === 'style_upgrade'
                        ? `<span>✨ Forma mais natural:</span> "${escapeHtml(suggested)}"`
                        : `<span>✅ Está correto:</span> "${escapeHtml(suggested)}"`);
                contentWrap.appendChild(suggestionLine);

                if (reason) {
                    const reasonEl = document.createElement('div');
                    reasonEl.className = 'learning-feedback-reason';
                    reasonEl.textContent = `💡 ${reason}`;
                    contentWrap.appendChild(reasonEl);
                }

                const useBtn = document.createElement('button');
                useBtn.type = 'button';
                useBtn.className = 'learning-feedback-btn secondary';
                useBtn.textContent = 'Usar frase sugerida';
                useBtn.addEventListener('click', () => {
                    if (textInput) {
                        textInput.value = suggested;
                        textInput.focus();
                    }
                });
                contentWrap.appendChild(useBtn);
            }

            function renderAnswersStep() {
                contentWrap.innerHTML = '';
                const stepTitle = document.createElement('div');
                stepTitle.className = 'learning-guidance-options-title';
                stepTitle.innerHTML = 'Outras formas de responder: <span style="color:#FFD700;font-weight:bold;font-size:0.85em;">(Opcional)</span>';
                contentWrap.appendChild(stepTitle);

                const list = document.createElement('div');
                list.className = 'learning-guidance-options';

                replies.forEach((reply, index) => {
                    const optionBtn = document.createElement('button');
                    optionBtn.type = 'button';
                    optionBtn.className = 'learning-guidance-option';
                    optionBtn.setAttribute('aria-label', `Opcao ${index + 1}`);

                    const en = document.createElement('span');
                    en.className = 'suggested-answer-en';
                    en.textContent = reply.en;
                    optionBtn.appendChild(en);

                    if (reply.pt) {
                        const pt = document.createElement('span');
                        pt.className = 'suggested-answer-pt';
                        pt.textContent = reply.pt;
                        optionBtn.appendChild(pt);
                    }

                    optionBtn.addEventListener('click', () => {
                        if (textInput) {
                            textInput.value = reply.en;
                            textInput.focus();
                        }
                    });

                    list.appendChild(optionBtn);
                });

                contentWrap.appendChild(list);
            }

            const actions = document.createElement('div');
            actions.className = 'learning-feedback-actions';

            const backBtn = document.createElement('button');
            backBtn.type = 'button';
            backBtn.className = 'learning-feedback-btn secondary';
            backBtn.textContent = 'Voltar';
            backBtn.style.display = 'none';
            actions.appendChild(backBtn);

            const nextBtn = document.createElement('button');
            nextBtn.type = 'button';
            nextBtn.className = 'learning-feedback-btn primary';
            nextBtn.textContent = steps.length > 1 ? 'Proximo' : 'Continuar';
            actions.appendChild(nextBtn);

            function closeFlow() {
                overlay.remove();
                learningFeedbackPending = false;
                setMicReadyState();
                resolve();
            }

            function renderStep() {
                const step = steps[currentStepIndex];
                const total = steps.length;
                stepBadge.textContent = `Etapa ${currentStepIndex + 1} de ${total}`;

                if (step === 'feedback') {
                    title.textContent = aiQuestionDisplay
                        ? `\u{1F5E3}\uFE0F "${aiQuestionDisplay}"`
                        : 'Sobre a sua resposta';
                    renderFeedbackStep();
                } else {
                    title.textContent = aiQuestionDisplay
                        ? `\u{1F5E3}\uFE0F "${aiQuestionDisplay}"`
                        : 'Outras formas de responder';
                    renderAnswersStep();
                }

                backBtn.style.display = currentStepIndex > 0 ? 'inline-flex' : 'none';
                nextBtn.textContent = currentStepIndex >= total - 1 ? 'Continuar' : 'Proximo';
            }

            backBtn.addEventListener('click', () => {
                if (currentStepIndex <= 0) return;
                currentStepIndex -= 1;
                renderStep();
            });

            nextBtn.addEventListener('click', () => {
                if (currentStepIndex >= steps.length - 1) {
                    closeFlow();
                    return;
                }
                currentStepIndex += 1;
                renderStep();
            });

            const helper = document.createElement('div');
            helper.className = 'learning-feedback-helper';
            helper.textContent = 'Depois de continuar, a conversa segue normalmente com a proxima pergunta.';
            modal.appendChild(helper);

            modal.appendChild(actions);
            overlay.appendChild(modal);
            document.body.appendChild(overlay);
            renderStep();
        });
    }

    function appendTurnFeedbackCard(messageGroup, feedback) {
        if (!messageGroup || !feedback) return;
        const kind = String(feedback.kind || 'none').trim();
        if (kind === 'none') return;

        const student = String(feedback.user_text || '').trim();
        const suggested = String(feedback.suggested_text || '').trim();
        if (!student || !suggested) return;

        const card = document.createElement('div');
        card.className = kind === 'error_correction' ? 'turn-correction-card' : 'turn-style-card';

        const title = document.createElement('div');
        title.className = kind === 'error_correction' ? 'turn-correction-title' : 'turn-style-title';
        title.textContent = kind === 'error_correction' ? 'Correção da interação' : 'Sugestão de naturalidade';
        card.appendChild(title);

        const studentLine = document.createElement('div');
        studentLine.className = kind === 'error_correction' ? 'turn-correction-line bad' : 'turn-style-line';
        studentLine.innerHTML = kind === 'error_correction'
            ? `<span>❌ Você disse:</span> "${escapeHtml(student)}"`
            : `<span>Você disse:</span> "${escapeHtml(student)}"`;
        card.appendChild(studentLine);

        const suggestedLine = document.createElement('div');
        suggestedLine.className = kind === 'error_correction' ? 'turn-correction-line good' : 'turn-style-line good';
        suggestedLine.innerHTML = `<span>${kind === 'error_correction' ? '✅ Mais natural:' : '✅ Sugestão:'}</span> "${escapeHtml(suggested)}"`;
        card.appendChild(suggestedLine);

        const reason = String(feedback.reason || '').trim();
        if (reason) {
            const note = document.createElement('div');
            note.className = kind === 'error_correction' ? 'turn-correction-note' : 'turn-style-note';
            note.textContent = `💡 ${reason}`;
            card.appendChild(note);
        }

        const useBtn = document.createElement('button');
        useBtn.type = 'button';
        useBtn.className = 'correction-use-btn';
        useBtn.textContent = kind === 'error_correction' ? 'Usar frase corrigida' : 'Usar sugestão';
        useBtn.addEventListener('click', () => {
            if (textInput) {
                textInput.value = suggested;
                textInput.focus();
            }
        });
        card.appendChild(useBtn);

        messageGroup.appendChild(card);
    }

    function splitMessageIntoSentences(text) {
        const compact = String(text || '').replace(/\s+/g, ' ').trim();
        if (!compact) return [];
        const matches = compact.match(/[^.!?]+[.!?]?/g);
        if (!matches || !matches.length) return [compact];
        return matches.map(item => item.trim()).filter(Boolean);
    }

    function sanitizeCoachDisplayText(text) {
        let value = String(text || '');
        if (!value) return '';

        // Remove meta-instructions that confuse beginners in the UI.
        value = value.replace(/\bLearning mode:\s*[^.!?]*[.!?]\s*/gi, '');
        value = value.replace(/\bModo Learning:\s*[^.!?]*[.!?]\s*/gi, '');
        value = value.replace(/\b(let'?s|vamos)\s+(jump|start|get|entrar|comecar)[^.!?]*(real[- ]life|cena real|intera[cç][aã]o real)[^.!?]*[.!?]\s*/gi, '');
        value = value.replace(/\b(i will|i'll|eu vou|vou)\s+(coach|show|give|share|guiar|mostrar|dar)\s+(easy\s+|simple\s+)?(lines?|sentences?|phrases?|frases?)\s+(you|voce)\s+(can\s+)?(say|use|dizer|usar)[^.!?]*[.!?]\s*/gi, '');
        value = value.replace(/\b(real interaction|intera[cç][aã]o real)\b[^.!?]*[.!?]\s*/gi, '');
        value = value.replace(/(^|[.!?]\s+)[)\]]\s+/g, '$1');
        value = value.replace(/^\)\s*/g, '');

        value = value.replace(/\s+/g, ' ').trim();
        return value;
    }

    function normalizeComparableText(value) {
        return String(value || '')
            .toLowerCase()
            .replace(/[^\p{L}\p{N}\s]/gu, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function looksPortugueseSnippet(value) {
        const text = String(value || '').toLowerCase().trim();
        if (!text) return false;
        if (/[ãõçáàâéêíóôú]/i.test(text)) return true;

        const wrapped = ` ${text.replace(/\s+/g, ' ')} `;
        const markers = [
            ' eu ', ' voce ', ' você ', ' por favor ', ' qual ', ' tamanho ', ' agora ', ' nao ', ' não ',
            ' obrigado ', ' obrigada ', ' queria ', ' gostaria ', ' posso ', ' pode ', ' meu ', ' minha ',
            ' com ', ' para ', ' isso ', ' aqui ', ' hoje ', ' bom ', ' boa '
        ];
        let hits = 0;
        markers.forEach(marker => {
            if (wrapped.includes(marker)) hits += 1;
        });
        return hits >= 2;
    }

    function extractPortugueseSentences(value) {
        const sentences = splitMessageIntoSentences(value);
        const picked = [];

        sentences.forEach(sentence => {
            const clean = String(sentence || '').replace(/^[)\]\-\s]+/, '').trim();
            if (!clean) return;

            let selected = '';
            const parenthesisMatches = clean.matchAll(/\(([^)]+)\)/g);
            for (const match of parenthesisMatches) {
                const inner = String(match[1] || '').trim();
                if (looksPortugueseSnippet(inner)) {
                    selected = inner;
                    break;
                }
            }

            if (!selected && looksPortugueseSnippet(clean)) {
                selected = clean;
            }

            if (selected) {
                selected = selected.replace(/^["'“”]+|["'“”]+$/g, '').trim();
                if (selected) picked.push(selected);
            }
        });

        return picked.join(' ');
    }

    function sanitizeTranslationDisplayText(text, assistantText = '') {
        let value = sanitizeCoachDisplayText(text);
        if (!value) return '';

        const ptOnly = extractPortugueseSentences(value);
        const normalizedOriginal = normalizeComparableText(value);
        const normalizedAssistant = normalizeComparableText(assistantText);
        const seemsMixed = /\([^)]+\)/.test(value) || (/[A-Za-z]/.test(value) && looksPortugueseSnippet(value));

        if (ptOnly && (seemsMixed || (normalizedAssistant && normalizedOriginal === normalizedAssistant))) {
            value = ptOnly;
        }

        return value;
    }

    function classifyCoachSegment(text) {
        const value = String(text || '').trim();
        if (!value) return 'tip';

        const lower = value.toLowerCase();
        if (
            value.endsWith('?') ||
            /\b(what|how|when|where|why|who|which)\b/i.test(value) ||
            /\b(do you|are you|can you|could you|would you|may i)\b/i.test(value)
        ) return 'question';

        if (/^(instead of|em vez de|corre[cç][aã]o|correcao|ajuste)/i.test(lower) ||
            /\b(instead of|em vez de|say:|diga:)\b/i.test(lower)) {
            return 'correction';
        }

        if (/^(tip|dica|optional upgrade|upgrade opcional)/i.test(lower) ||
            /\b(more natural|mais natural|more polite|mais educad|sounds better|soa melhor)\b/i.test(lower)) {
            return 'tip';
        }

        return 'tip';
    }

    function mergeCoachSegments(sentences) {
        const merged = [];
        sentences.forEach(sentence => {
            const kind = classifyCoachSegment(sentence);
            const cleanSentence = String(sentence || '').replace(/^[)\]\-\s]+/, '').trim();
            if (!cleanSentence) return;
            const last = merged.length ? merged[merged.length - 1] : null;
            if (last && last.kind === kind) {
                last.text = `${last.text} ${cleanSentence}`.trim();
            } else {
                merged.push({ kind, text: cleanSentence });
            }
        });
        return merged;
    }

    function renderCoachSegments(container, text, options = {}) {
        if (!container) return;
        const isTranslation = options && options.isTranslation === true;
        const baseClass = isTranslation ? 'translation-segment' : 'subtitle-segment';
        const layoutClass = isTranslation ? 'translation-structured' : 'subtitle-structured';
        const cleanedText = sanitizeCoachDisplayText(text);
        const sentences = splitMessageIntoSentences(cleanedText);
        const mergedSegments = mergeCoachSegments(sentences);

        container.textContent = '';
        if (!mergedSegments.length) return;
        container.classList.add(layoutClass);

        mergedSegments.forEach(segmentData => {
            const segment = document.createElement('p');
            segment.className = `${baseClass} ${segmentData.kind}`;
            segment.textContent = segmentData.text;
            container.appendChild(segment);
        });
    }

    function addMessage(sender, text, isAI = false, logMessage = true, translation = "", options = {}) {
        if (!chatWindow) return null;

        // Collapse previous turns' feedback cards and dim old messages for clarity
        if (isAI) {
            chatWindow.querySelectorAll('.turn-correction-card, .turn-style-card, .correction-hint').forEach(card => {
                card.classList.add('previous-turn-feedback');
            });
            chatWindow.querySelectorAll('.subtitle-group').forEach(group => {
                group.classList.add('previous-turn');
            });
            // Add turn divider before new AI response (if there are previous messages)
            const existingGroups = chatWindow.querySelectorAll('.subtitle-group');
            if (existingGroups.length > 0) {
                const divider = document.createElement('div');
                divider.className = 'turn-divider';
                divider.textContent = 'nova pergunta';
                chatWindow.appendChild(divider);
            }
        }

        const messageGroup = document.createElement('div');
        messageGroup.className = 'subtitle-group';
        messageGroup.setAttribute('data-sender', isAI ? 'ai' : 'user');

        const msgDiv = document.createElement('div');
        msgDiv.className = `subtitle-line ${isAI ? 'ai' : 'user'}`;

        // Add fade-in animation styles directly
        msgDiv.style.opacity = '0';
        msgDiv.style.transform = 'translateY(10px)';
        msgDiv.style.transition = 'all 0.5s ease';

        // Store real text and show placeholder when subtitles are off
        const isAssistantMessage = isAI && String(sender || '').toLowerCase() === 'ai';
        const displayText = isAssistantMessage ? sanitizeCoachDisplayText(text) : text;
        msgDiv.setAttribute('data-text', displayText);
        const shouldShowText = (typeof window.subtitlesEnabled !== 'undefined' && window.subtitlesEnabled) ||
            (autoTranslateToggle && autoTranslateToggle.checked);
        if (shouldShowText) {
            if (isAssistantMessage) {
                renderCoachSegments(msgDiv, displayText);
            } else if (!isAI) {
                msgDiv.classList.add('user-structured');
                const label = document.createElement('span');
                label.className = 'user-speech-label';
                label.textContent = '🎤 Você disse:';
                const content = document.createElement('span');
                content.className = 'user-speech-text';
                content.innerText = displayText;
                msgDiv.textContent = '';
                msgDiv.appendChild(label);
                msgDiv.appendChild(content);
            } else {
                msgDiv.innerText = displayText;
            }
        } else {
            msgDiv.innerText = window.obfuscateText ? window.obfuscateText(displayText) : '(... ...)';
        }

        messageGroup.appendChild(msgDiv);

        // Trigger reflow for animation
        void msgDiv.offsetWidth;

        msgDiv.style.opacity = '1';
        msgDiv.style.transform = 'translateY(0)';

        // Always add translation if AI message has one - visibility controlled by CSS/toggle
        if (isAI && translation) {
            const transDiv = document.createElement('div');
            transDiv.className = 'translation-line';
            const rawTranslation = isAssistantMessage ? sanitizeCoachDisplayText(translation) : translation;
            const displayTranslation = isAssistantMessage
                ? (sanitizeTranslationDisplayText(rawTranslation, displayText) || rawTranslation)
                : rawTranslation;
            if (isAssistantMessage) {
                renderCoachSegments(transDiv, displayTranslation, { isTranslation: true });
            } else {
                transDiv.innerText = displayTranslation;
            }

            const forceTranslation = options && options.forceTranslation === true;
            const showTranslation = forceTranslation || (autoTranslateToggle && autoTranslateToggle.checked);
            transDiv.style.display = showTranslation ? 'block' : 'none';

            messageGroup.appendChild(transDiv);

            if (!showTranslation) {
                const toggle = document.createElement('button');
                toggle.type = 'button';
                toggle.className = 'translation-toggle-btn';
                toggle.textContent = 'Mostrar tradução';
                toggle.style.cssText = 'margin-top:6px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);color:#d1d5db;padding:4px 10px;border-radius:999px;font-size:0.72rem;cursor:pointer;';
                toggle.addEventListener('click', () => {
                    const isHidden = transDiv.style.display === 'none';
                    transDiv.style.display = isHidden ? 'block' : 'none';
                    toggle.textContent = isHidden ? 'Ocultar tradução' : 'Mostrar tradução';
                });
                messageGroup.appendChild(toggle);
            }
        }

        const allowInlineFeedback = !(options && options.showInlineFeedback === false);
        if (isAI && allowInlineFeedback && options && options.turnFeedback) {
            appendTurnFeedbackCard(messageGroup, options.turnFeedback);
        } else if (isAI && allowInlineFeedback && options && options.enableLegacyCorrectionFallback && options.turnCorrection) {
            const legacyCorrection = {
                kind: 'error_correction',
                user_text: String(options.turnCorrection.frase_aluno || '').trim(),
                suggested_text: String(options.turnCorrection.frase_natural || '').trim(),
                reason: String(options.turnCorrection.explicacao || '').trim(),
            };
            appendTurnFeedbackCard(messageGroup, legacyCorrection);
        } else if (isAI && allowInlineFeedback && options && options.enableLegacyCorrectionFallback) {
            const correctionPhrase = extractCorrection(text);
            if (correctionPhrase) {
                const correctionWrap = document.createElement('div');
                correctionWrap.className = 'correction-hint';

                const label = document.createElement('div');
                label.className = 'correction-label';
                label.textContent = 'Correção rápida';
                correctionWrap.appendChild(label);

                const phrase = document.createElement('div');
                phrase.className = 'correction-phrase';
                phrase.textContent = correctionPhrase;
                correctionWrap.appendChild(phrase);

                const useBtn = document.createElement('button');
                useBtn.type = 'button';
                useBtn.className = 'correction-use-btn';
                useBtn.textContent = 'Usar essa frase';
                useBtn.addEventListener('click', () => {
                    if (textInput) {
                        textInput.value = correctionPhrase;
                        textInput.focus();
                    }
                });
                correctionWrap.appendChild(useBtn);

                messageGroup.appendChild(correctionWrap);
            }
        }

        chatWindow.appendChild(messageGroup);
        const groups = chatWindow.querySelectorAll('.subtitle-group');
        if (groups.length > MAX_VISIBLE_GROUPS) {
            const removeCount = groups.length - MAX_VISIBLE_GROUPS;
            for (let i = 0; i < removeCount; i++) {
                // Also remove any turn-divider immediately before the group
                const prev = groups[i].previousElementSibling;
                if (prev && prev.classList.contains('turn-divider')) prev.remove();
                groups[i].remove();
            }
        }
        refreshConversationFocusView();

        if (logMessage) {
            conversationLog.push({ sender, text });
        }

        return messageGroup;
    }

    function renderSuggestedWords(words = [], promptText = "", replyOptions = [], aiPromptText = "") {
        if (!chatWindow) return;

        const existing = chatWindow.querySelectorAll('.suggested-words-card');
        existing.forEach(el => el.remove());

        const intentSource = sanitizeCoachDisplayText(aiPromptText || promptText || lastAIMessage) || aiPromptText || promptText || lastAIMessage;
        const normalizedReplies = normalizeSuggestionItems(replyOptions);
        const matchedReplies = getIntentMatchedReplies(normalizedReplies, intentSource);
        const questionFallback = getQuestionSpecificFallbackReplies(intentSource);
        const fallbackReplies = getSuggestionsForContext(context, intentSource);
        const baseReplies = matchedReplies.length ? matchedReplies : questionFallback;
        const replies = dedupeSuggestionItems([
            ...baseReplies,
            ...questionFallback,
            ...fallbackReplies
            , ...normalizedReplies
        ]).slice(0, 3);
        if (!replies.length) return;

        const titleText = '3 formas de responder a pergunta anterior:';

        const groups = chatWindow.querySelectorAll('.subtitle-group');
        const messageGroup = groups.length ? groups[groups.length - 1] : chatWindow;
        const card = document.createElement('div');
        card.className = 'suggested-words-card';

        const isMobile = window.innerWidth <= 768;
        const startExpanded = !isMobile;

        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'suggested-words-toggle';
        toggle.setAttribute('aria-expanded', startExpanded ? 'true' : 'false');
        toggle.innerHTML = `💡 Dica de resposta (${replies.length}) <span style="color:#FFD700;font-weight:bold;font-size:0.85em;margin-left:6px;">(Opcional)</span>`;
        card.appendChild(toggle);

        const details = document.createElement('div');
        details.className = 'suggested-words-details';
        details.style.display = startExpanded ? 'block' : 'none';
        if (startExpanded) card.classList.add('expanded');

        const title = document.createElement('div');
        title.className = 'suggested-words-title';
        title.textContent = titleText;
        details.appendChild(title);

        const answerList = document.createElement('div');
        answerList.className = 'suggested-answers-list';

        replies.forEach((reply, index) => {
            const answerBtn = document.createElement('button');
            answerBtn.type = 'button';
            answerBtn.className = 'suggested-answer-btn';
            answerBtn.setAttribute('aria-label', `Opcao ${index + 1} de resposta`);

            const enLine = document.createElement('span');
            enLine.className = 'suggested-answer-en';
            enLine.textContent = reply.en;
            answerBtn.appendChild(enLine);

            if (reply.pt) {
                const ptLine = document.createElement('span');
                ptLine.className = 'suggested-answer-pt';
                ptLine.textContent = reply.pt;
                answerBtn.appendChild(ptLine);
            }

            answerBtn.addEventListener('click', () => {
                if (textInput && textInput.offsetParent !== null) {
                    textInput.value = reply.en;
                    textInput.focus();
                }
            });

            answerList.appendChild(answerBtn);
        });

        details.appendChild(answerList);

        const hint = document.createElement('div');
        hint.className = 'suggested-words-hint';
        hint.textContent = 'Toque em uma opcao para preencher sua resposta e continuar.';
        details.appendChild(hint);

        toggle.addEventListener('click', () => {
            const expanded = toggle.getAttribute('aria-expanded') === 'true';
            toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
            details.style.display = expanded ? 'none' : 'block';
            card.classList.toggle('expanded', !expanded);
        });

        card.appendChild(details);
        messageGroup.appendChild(card);
    }

    // =============================================
    // STRUCTURED LESSON FUNCTIONS
    // =============================================

    /**
     * Match spoken text to one of the lesson options using word similarity.
     * Returns { index, option } or null if no good match found.
     */
    function matchSpokenToOption(spokenText, options) {
        const normalize = (str) => (str || '').toLowerCase().replace(/[^a-z0-9\s]/gi, '').trim();
        const spokenNorm = normalize(spokenText);
        const spokenWords = spokenNorm.split(/\s+/).filter(w => w.length > 0);

        if (spokenWords.length === 0) return null;

        let bestIndex = -1;
        let bestScore = 0;

        options.forEach((opt, index) => {
            const optText = normalize(opt.en || opt);
            const optWords = optText.split(/\s+/).filter(w => w.length > 0);
            if (optWords.length === 0) return;

            // Count matching words
            let matches = 0;
            for (const sw of spokenWords) {
                if (optWords.some(ow => ow === sw || ow.includes(sw) || sw.includes(ow))) {
                    matches++;
                }
            }

            // Score = proportion of option words matched + proportion of spoken words matched
            const score = (matches / optWords.length) + (matches / spokenWords.length);

            if (score > bestScore) {
                bestScore = score;
                bestIndex = index;
            }
        });

        // Require at least 40% combined match to accept
        if (bestIndex >= 0 && bestScore >= 0.4) {
            return { index: bestIndex, option: options[bestIndex] };
        }

        return null;
    }

    /**
     * Render lesson options as read-aloud cards (student speaks one)
     */
    function renderLessonOptions(options, layerTitle = '') {
        if (!chatWindow) return;

        // Add lesson-mode class to enable scrolling
        chatWindow.classList.add('lesson-mode');

        // Remove any existing options and hide reference card
        const existing = chatWindow.querySelector('.lesson-options-container');
        if (existing) existing.remove();
        const oldRef = document.getElementById('lesson-phrase-ref');
        if (oldRef) oldRef.style.display = 'none';

        if (!Array.isArray(options) || options.length === 0) return;

        // Shuffle option order for this round while keeping original indexes.
        const decoratedOptions = options.map((opt, originalIndex) => {
            if (opt && typeof opt === 'object') {
                return { ...opt, _originalIndex: originalIndex };
            }
            return { en: String(opt || ''), _originalIndex: originalIndex };
        });
        const displayOptions = shuffleArray(decoratedOptions);

        // Store options for voice matching
        lessonState.currentOptions = displayOptions;

        const container = document.createElement('div');
        container.className = 'lesson-options-container';

        // Progress indicator
        if (lessonState.totalLayers > 0) {
            const progress = document.createElement('div');
            progress.className = 'lesson-progress';
            progress.innerHTML = `
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${((lessonState.layer + 1) / lessonState.totalLayers) * 100}%"></div>
                </div>
                <span class="progress-text">Step ${lessonState.layer + 1} of ${lessonState.totalLayers}</span>
            `;
            container.appendChild(progress);
        }

        // Title
        const title = document.createElement('div');
        title.className = 'lesson-options-title';
        title.textContent = layerTitle || 'Read one of the phrases below:';
        container.appendChild(title);

        // Options list (non-clickable, for reading aloud)
        displayOptions.forEach((opt, index) => {
            const card = document.createElement('div');
            card.className = 'lesson-option-card lesson-option-readonly';

            const optionNumber = document.createElement('div');
            optionNumber.className = 'option-number';
            optionNumber.textContent = index + 1;

            const optionContent = document.createElement('div');
            optionContent.className = 'option-content';
            optionContent.innerHTML = `
                <div class="option-en">"${opt.en || opt}"</div>
                ${opt.pt ? `<div class="option-pt">(${opt.pt})</div>` : ''}
            `;

            // Audio button - plays pronunciation
            const audioBtn = document.createElement('button');
            audioBtn.className = 'option-audio-btn';
            audioBtn.innerHTML = '<span class="audio-icon">🔊</span>';
            audioBtn.title = 'Listen to pronunciation';
            audioBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                audioBtn.classList.add('playing');
                try {
                    await playOptionAudio(opt.en || opt);
                } catch (err) {
                    console.error('Audio playback error:', err);
                }
                audioBtn.classList.remove('playing');
            });

            card.appendChild(optionNumber);
            card.appendChild(optionContent);
            card.appendChild(audioBtn);
            container.appendChild(card);
        });

        // Mic hint at the bottom
        const hint = document.createElement('div');
        hint.className = 'lesson-mic-hint';
        hint.innerHTML = '🎤 Use the microphone and read one of the phrases above';
        container.appendChild(hint);

        chatWindow.appendChild(container);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    /**
     * Build a composite phrase from template + filled slots.
     * Unfilled slots are removed, and grammar is cleaned up.
     */
    function buildCompositePhrase(template, slots) {
        let phrase = template;
        for (const [key, value] of Object.entries(slots)) {
            phrase = phrase.replace(`{${key}}`, value);
        }
        // Remove unfilled slot placeholders
        phrase = phrase.replace(/\{[^}]+\}/g, '');
        // Clean up spacing and punctuation
        phrase = phrase.replace(/\s+/g, ' ').trim();
        // Fix "an" before consonant sounds when size is added (e.g. "I'll have an large" → "I'll have a large")
        phrase = phrase.replace(/\ban\s+(small|medium|large|extra-large|big|biggest|hot|iced)/gi, 'a $1');
        // Fix "a" before vowel sounds (e.g. "I'd like a iced" → "I'd like an iced")
        phrase = phrase.replace(/\ba\s+(iced)/gi, 'an $1');
        // Clean up double commas or trailing commas before end punctuation
        phrase = phrase.replace(/ ,/g, ',').replace(/,,+/g, ',');
        phrase = phrase.replace(/,\s*([?!])/g, '$1');
        // Clean up ", ," patterns
        phrase = phrase.replace(/,\s*,/g, ',');
        return phrase;
    }

    /**
     * Handle lesson option selection (click)
     */
    async function selectLessonOption(index, phrase, spokenText) {
        lessonState.selectedOption = index;
        lessonState.selectedPhrase = phrase;

        // Merge slots if this option has them (for composite phrase building)
        const layerId = lessonState.layer + 1; // layers are 1-indexed in DB
        const isCompositeLayer = lessonState.compositeLayers &&
            lessonState.compositeLayers.includes(layerId);

        if (isCompositeLayer && phrase.slots) {
            Object.assign(lessonState.phraseSlots, phrase.slots);
        }

        // Build composite phrase if applicable
        let displayPhrase = phrase.en || phrase;
        let compositePhrase = null;
        if (isCompositeLayer && lessonState.compositeTemplate && Object.keys(lessonState.phraseSlots).length > 0) {
            compositePhrase = buildCompositePhrase(lessonState.compositeTemplate, lessonState.phraseSlots);
            displayPhrase = compositePhrase;
        }

        // Remove options UI
        const existing = chatWindow.querySelector('.lesson-options-container');
        if (existing) existing.remove();

        // Show what was selected
        addMessage('User', `Selected: "${phrase.en || phrase}"`, false, true);

        // Show sticky reference card with the COMPOSITE phrase (or single phrase for non-composite layers)
        const refCard = document.getElementById('lesson-phrase-ref');
        if (refCard) {
            refCard.innerHTML = `
                <div class="ref-header">
                    <span class="ref-label">Frase para praticar:</span>
                    <button class="ref-audio-btn" title="Ouvir / Listen">&#128264;</button>
                </div>
                <div class="ref-phrase-en">"${displayPhrase}"</div>
                ${phrase.pt ? `<div class="ref-phrase-pt">${phrase.pt}</div>` : ''}
            `;
            refCard.style.display = 'block';

            // Audio button on the reference card
            const refAudioBtn = refCard.querySelector('.ref-audio-btn');
            refAudioBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    refAudioBtn.classList.add('playing');
                    const blob = await apiClient.getTTS(displayPhrase, ttsSpeed, 'en', getActiveVoice());
                    await playAudioBlob(blob);
                } catch (err) {
                    console.error('Ref audio error:', err);
                } finally {
                    refAudioBtn.classList.remove('playing');
                }
            });
        }

        // Store the composite phrase for evaluation
        lessonState.compositePhrase = compositePhrase;

        // Call backend to get practice prompt
        showLoadingIndicator();
        try {
            const originalIndex = (phrase && typeof phrase._originalIndex === 'number')
                ? phrase._originalIndex
                : index;
            const data = await apiClient.lesson('select_option', context, {
                layer: lessonState.layer,
                option: originalIndex,
                selected_phrase: phrase
            });

            hideLoadingIndicator();

            // Update state
            lessonState.nextAction = data.next_action;

            // Store skip_to_layer if present (for branching after practice)
            if (data.skip_to_layer !== undefined) {
                lessonState.skipToLayer = data.skip_to_layer;
            } else {
                lessonState.skipToLayer = null;
            }

            // If user already spoke the phrase (voice selection), skip practice prompt
            // and evaluate immediately - no need to repeat
            if (spokenText) {
                // Don't play the "now try saying..." prompt - go straight to evaluation
                await evaluateLessonPractice(spokenText);
            } else {
                // Click-based selection: play practice prompt and wait for speech
                playResponse(data.text, data.translation);
            }

        } catch (error) {
            hideLoadingIndicator();
            console.error('Lesson option error:', error);
            addMessage('System', 'Error loading practice prompt. Please try again.', true);
        }
    }

    /**
     * Start a structured lesson
     */
    async function startStructuredLesson() {
        lessonState.active = true;
        updateSuggestionsVisibility();
        lessonState.layer = 0;
        lessonState.nextAction = 'start';
        lessonState.compositeTemplate = null;
        lessonState.compositeLayers = null;
        lessonState.phraseSlots = {};
        lessonState.compositePhrase = null;

        showLoadingIndicator();
        try {
            const data = await apiClient.lesson('start', context);

            hideLoadingIndicator();

            lessonState.totalLayers = data.total_layers || 0;
            lessonState.lessonTitle = data.lesson_title || context;
            lessonState.nextAction = data.next_action;
            lessonState.compositeTemplate = data.composite_template || null;
            lessonState.compositeLayers = data.composite_layers || null;

            // Play welcome message
            playResponse(data.text, data.translation);

            // After welcome, show "Start" button
            renderLessonStartButton();

        } catch (error) {
            hideLoadingIndicator();
            console.error('Lesson start error:', error);
            lessonState.active = false;
            updateSuggestionsVisibility();
            // Fallback to old conversational mode
            addMessage('System', 'Structured lesson not available. Starting conversation mode.', true);
        }
    }

    /**
     * Render a "Start Lesson" button after welcome
     */
    function renderLessonStartButton() {
        const labels = lessonLang === 'pt'
            ? ['Comecar aula', 'Iniciar pratica', 'Vamos comecar']
            : ['Start Lesson', 'Begin Practice', 'Let\'s Start'];
        const buttonLabel = pickNonRepeatingVariant(`lesson_start_btn_${context}`, labels) || labels[0];
        const container = document.createElement('div');
        container.className = 'lesson-start-container';
        container.innerHTML = `
            <button class="lesson-start-btn">
                ${buttonLabel}
            </button>
        `;
        container.querySelector('.lesson-start-btn').addEventListener('click', async () => {
            container.remove();
            await advanceLesson();
        });
        chatWindow.appendChild(container);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    /**
     * Advance to next lesson step (show options or conclusion)
     */
    async function advanceLesson() {
        showLoadingIndicator();
        try {
            const data = await apiClient.lesson('show_options', context, {
                layer: lessonState.layer
            });

            hideLoadingIndicator();

            lessonState.nextAction = data.next_action;

            if (data.type === 'conclusion') {
                // Lesson complete!
                playResponse(data.text, data.translation);
                lessonState.active = false;
                updateSuggestionsVisibility();
                // Remove lesson-mode class
                if (chatWindow) chatWindow.classList.remove('lesson-mode');
                // Show report button
                updateReportButton();
            } else if (data.type === 'options') {
                // Show options
                playResponse(data.text, data.translation);
                setTimeout(() => {
                    renderLessonOptions(data.options, data.layer_title);
                }, 500);
            }

        } catch (error) {
            hideLoadingIndicator();
            console.error('Lesson advance error:', error);
        }
    }

    /**
     * Evaluate student's practice and advance
     */
    async function evaluateLessonPractice(userText) {
        showLoadingIndicator();
        try {
            const payload = {
                layer: lessonState.layer,
                text: userText,
                selected_phrase: lessonState.selectedPhrase
            };

            // Include composite phrase if built (for evaluation against full sentence)
            if (lessonState.compositePhrase) {
                payload.composite_phrase = lessonState.compositePhrase;
            }

            // Include skip_to_layer if present (for branching)
            if (lessonState.skipToLayer !== null && lessonState.skipToLayer !== undefined) {
                payload.skip_to_layer = lessonState.skipToLayer;
            }

            const data = await apiClient.lesson('evaluate_practice', context, payload);

            hideLoadingIndicator();

            // Update layer state BEFORE playing audio
            lessonState.layer = data.next_layer;
            lessonState.nextAction = data.next_action;

            // Play feedback and WAIT for it to finish
            await playResponse(data.text, data.translation);

            // Only advance if the student's practice was good enough
            if (data.ready_for_next) {
                await advanceLesson();
            } else {
                // Keep in practice mode for retry - student can try again
                lessonState.nextAction = 'evaluate_practice';
            }

        } catch (error) {
            hideLoadingIndicator();
            console.error('Lesson evaluation error:', error);
        }
    }

    /**
     * Check if we should use structured lesson mode
     * Structured mode is opt-in (URL param) or auto-enabled for A1 learners.
     */
    function shouldUseStructuredLesson() {
        if (['0', 'false', 'off'].includes(structuredModeParam)) {
            return false;
        }

        const isForcedStructured = ['1', 'true', 'on'].includes(structuredModeParam);
        const autoStructuredByLevel = studentLevel === 'A1';
        if (!isForcedStructured && !autoStructuredByLevel) {
            return false;
        }

        // List of contexts that have structured lessons (All 33 contexts)
        const structuredLessonContexts = [
            // Fase 1 - Essenciais (10)
            'coffee_shop',
            'restaurant',
            'hotel',
            'airport',
            'supermarket',
            'bank',
            'doctor',
            'clothing_store',
            'job_interview',
            'school',
            // Fase 2 - Importantes (10)
            'pharmacy',
            'train_station',
            'bus_stop',
            'renting_car',
            'bakery',
            'pizza_delivery',
            'hair_salon',
            'gas_station',
            'tech_support',
            'cinema',
            // Fase 3 - Complementares (11)
            'neighbor',
            'street',
            'first_date',
            'dental_clinic',
            'gym',
            'post_office',
            'lost_found',
            'flower_shop',
            'pet_shop',
            'library',
            'museum',
            // Fase 4 - Especiais (2)
            'wedding',
            'graduation'
        ];
        return structuredLessonContexts.includes(context);
    }

    function showLoadingIndicator() {
        const existing = document.getElementById('loading-indicator');
        if (existing) return;

        const loader = document.createElement('div');
        loader.id = 'loading-indicator';
        loader.className = 'message system-message';
        loader.innerHTML = `
            <div class="bubble" style="display: flex; align-items: center; gap: 0.4rem; padding: 0.6rem 1rem;">
                <span class="thinking-dot" style="width:8px;height:8px;border-radius:50%;background:#aaa;animation:thinkPulse 1.2s infinite ease-in-out;"></span>
                <span class="thinking-dot" style="width:8px;height:8px;border-radius:50%;background:#aaa;animation:thinkPulse 1.2s infinite ease-in-out 0.2s;"></span>
                <span class="thinking-dot" style="width:8px;height:8px;border-radius:50%;background:#aaa;animation:thinkPulse 1.2s infinite ease-in-out 0.4s;"></span>
            </div>
            <style>
                @keyframes thinkPulse {
                    0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
                    30% { opacity: 1; transform: scale(1.2); }
                }
            </style>
        `;
        chatWindow.appendChild(loader);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function hideLoadingIndicator() {
        const loader = document.getElementById('loading-indicator');
        if (loader) {
            // Clear interval
            if (loader.dataset.intervalId) {
                clearInterval(parseInt(loader.dataset.intervalId));
            }
            loader.remove();
        }
    }

    // Export functions
    function exportReportJSON(reportData) {
        const dataStr = JSON.stringify(reportData, null, 2);
        const blob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `relatorio_${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // Fallback check replaced by Deepgram/Groq logic
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (recordBtn) recordBtn.style.display = 'none';
        const fallbackInfo = document.createElement('div');
        fallbackInfo.className = 'message system-message';
        fallbackInfo.innerHTML = `
            <div class="bubble">
                <p>⚠️ Voice input not supported in this browser. Please use Chrome or Edge for voice features.</p>
            </div>
        `;
        chatWindow.appendChild(fallbackInfo);
    }

    // Text input intentionally disabled in voice-only practice UI.

    const textInput = document.getElementById('text-input');
    const sendBtn = document.getElementById('send-btn');

    if (sendBtn && textInput) {
        sendBtn.onclick = () => {
            const text = textInput.value.trim();
            if (text && !isProcessing) {
                processUserResponse(text);
                textInput.value = '';
            }
        };

        textInput.onkeypress = (e) => {
            if (e.key === 'Enter' && !isProcessing) {
                sendBtn.click();
            }
        };
    }
    // Stray brace removed from here


    function finishConversation() {
        addMessage("System", "Great job! Conversation complete.", true);
        const resetBtn = document.createElement('button');
        resetBtn.className = 'primary-btn';
        resetBtn.innerText = 'Restart';
        resetBtn.onclick = () => location.reload();

        const logoutBtn = document.createElement('button');
        logoutBtn.className = 'action-btn';
        logoutBtn.style.marginTop = '10px';
        logoutBtn.innerText = 'Logout';
        logoutBtn.onclick = () => {
            localStorage.removeItem('conversation_user');
            location.reload();
        };

        const lastBubble = chatWindow.lastElementChild ? chatWindow.lastElementChild.querySelector('.bubble') : null;
        if (lastBubble) {
            lastBubble.appendChild(resetBtn);
            lastBubble.appendChild(logoutBtn);
        }
    }

    // Helper functions
    function updateMessageCounter() {
        if (messageCounter) {
            const exchanges = Math.floor(conversationLog.filter(m => m.sender !== 'System').length / 2);
            messageCounter.textContent = exchanges === 1 ? '1 exchange' : `${exchanges} exchanges`;
        }
        updateSessionProgress({ quiet: true });
    }

    function updateReportButton() {
        // Only show the report button once the student has had enough turns
        // for a meaningful report (≥3 user messages). Before that, it was
        // competing visually with the mic as the biggest red CTA on screen.
        const MIN_TURNS_FOR_REPORT = 3;
        const reportBar = document.getElementById('report-bar');
        const shouldShow = userMessageCount >= MIN_TURNS_FOR_REPORT;
        if (reportBtn) reportBtn.disabled = !shouldShow;
        if (reportBar) reportBar.style.display = shouldShow ? 'block' : 'none';
        if (reportBarBtn) reportBarBtn.disabled = !shouldShow;
    }

    function showSkipAudioButton() {
        // Remove existing skip button
        const existing = document.querySelector('.skip-audio-btn');
        if (existing) existing.remove();

        const skipBtn = document.createElement('button');
        skipBtn.className = 'skip-audio-btn';
        skipBtn.textContent = '⏭️ Pular áudio';
        skipBtn.title = 'Pular o áudio e continuar';
        skipBtn.onclick = () => {
            ttsCancelled = true;
            if (currentAudio) {
                currentAudio.pause();
                currentAudio.currentTime = 0;
                currentAudio.dispatchEvent(new Event('ended'));
            }
            finalizePlayback(skipBtn);
        };

        const container = document.querySelector('.player-controls') || document.querySelector('.player-overlay') || document.body;
        if (container) {
            container.appendChild(skipBtn);
            return skipBtn;
        }
        return null;
    }
    // Quick replies disabled - students must practice speaking without prompts
    // function getQuickRepliesForContext(contextId) {
    //     const quickRepliesMap = {
    //         'coffee_shop': ["I'd like a coffee", "Can I see the menu?", "What do you recommend?"],
    //         'airport': ["Where is check-in?", "Can I see your passport?", "I have a flight to..."],
    //         'doctor': ["I don't feel well", "I have a headache", "Can you help me?"],
    //         'restaurant': ["Table for two, please", "Can I see the menu?", "I'd like to order"],
    //         'supermarket': ["Where can I find...?", "How much is this?", "Do you have...?"]
    //     };
    //     return quickRepliesMap[contextId] || ["Hello", "Thank you", "Can you help me?"];
    // }

    // function addQuickReplies(replies) {
    //     const existing = chatWindow.querySelector('.quick-replies');
    //     if (existing) existing.remove();
    //     const container = document.createElement('div');
    //     container.className = 'message system-message';
    //     container.innerHTML = `
    //         <div class="bubble">
    //             <p style="margin-bottom: 0.5rem; font-size: 0.85rem; color: #94a3b8;">Quick replies:</p>
    //             <div class="quick-replies" id="quick-replies-container"></div>
    //         </div>
    //     `;
    //     const quickRepliesContainer = container.querySelector('#quick-replies-container');
    //     replies.forEach(reply => {
    //         const btn = document.createElement('button');
    //         btn.className = 'quick-reply-btn';
    //         btn.textContent = reply;
    //         btn.onclick = () => {
    //             processUserResponse(reply);
    //             container.remove();
    //         };
    //         quickRepliesContainer.appendChild(btn);
    //     });
    //     chatWindow.appendChild(container);
    //     chatWindow.scrollTop = chatWindow.scrollHeight;
    // }

    const enableUiTestHooks = (urlParams.get('testHooks') === '1') || window.__ENABLE_UI_TEST_HOOKS__ === true;
    if (enableUiTestHooks) {
        window.__practiceTestHooks = {
            processUserResponse: async (text) => processUserResponse(text),
            getLatestAIQuestionPrompt: () => getLatestAIQuestionPrompt(),
            detectQuestionIntent: (text) => detectQuestionIntent(text),
            buildLearningFeedbackPayload: (turnFeedback, userText, backendData) => buildLearningFeedbackPayload(turnFeedback, userText, backendData),
            inferLearningFeedbackFromText: (userText, questionPrompt) => inferLearningFeedbackFromText(userText, questionPrompt),
            simplifyLearningScenarioResponse: (text, translation) => simplifyLearningScenarioResponse(text, translation)
        };
        console.info('[UI TEST] practice hooks enabled');
    }
});

function handleLogin() {
    const form = document.getElementById('login-form');
    if (!form) return;

    const emailInput = document.getElementById('email');
    const passwordGroup = document.getElementById('password-group');
    const passwordInput = document.getElementById('password');

    // Manual toggle for admin password field (no hardcoded admin email in frontend).
    const adminToggle = document.getElementById('admin-toggle');
    if (adminToggle && passwordGroup) {
        adminToggle.addEventListener('click', (e) => {
            e.preventDefault();
            const isHidden = passwordGroup.style.display === 'none' || passwordGroup.style.display === '';
            if (isHidden) {
                passwordGroup.style.display = 'block';
                if (passwordInput) passwordInput.focus();
            } else {
                passwordGroup.style.display = 'none';
                if (passwordInput) passwordInput.value = '';
            }
        });
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = emailInput.value.trim();
        const password = passwordInput ? passwordInput.value.trim() : '';
        const submitBtn = form.querySelector('button[type="submit"]');

        if (!email) {
            alert('Please enter your email');
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Accessing...';

        try {
            const data = await apiClient.login(email, password);

            // Check if system is in maintenance mode for this user
            if (data.maintenance && data.maintenance.active) {
                alert(data.maintenance.message || 'Sistema em manuten\u00e7\u00e3o. Tente novamente mais tarde.');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Access Platform';
                apiClient.logout();
                return;
            }

            // Redirect based on admin status
            if (data.user && data.user.is_admin) {
                window.location.href = 'admin.html';
            } else {
                window.location.href = 'dashboard.html';
            }
        } catch (err) {
            console.error('Login error:', err);
            let errorMsg = 'Login failed. Please try again.';
            const rawMsg = String((err && err.message) ? err.message : err || '');
            const isNetworkError = (
                rawMsg.includes('Failed to fetch') ||
                rawMsg.includes('NetworkError') ||
                rawMsg.includes('Load failed') ||
                rawMsg.includes('ERR_CONNECTION') ||
                rawMsg.includes('TypeError')
            );

            if (isNetworkError) {
                const apiBase = (apiClient && typeof apiClient.baseURL === 'string' && apiClient.baseURL)
                    ? apiClient.baseURL
                    : window.location.origin;
                errorMsg = `Servidor offline ou URL incorreta. Inicie o backend e tente: ${apiBase || 'http://localhost:8912'}`;
            } else if (rawMsg.includes('not authorized') || rawMsg.includes('not registered')) {
                errorMsg = 'This email is not authorized to access the platform. Please contact support.';
            } else if (rawMsg.includes('Invalid admin password')) {
                errorMsg = 'Invalid admin password. Try again or login without password for regular access.';
            }

            alert(errorMsg);
            submitBtn.disabled = false;
            submitBtn.textContent = 'Access Platform';
        }
    });
}
