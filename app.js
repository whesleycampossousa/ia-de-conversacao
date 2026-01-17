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

    if (!apiClient.isAuthenticated() && !isLoginPage) {
        window.location.href = 'login.html';
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
    const context = urlParams.get('context') || 'coffee_shop';
    const contextName = urlParams.get('title') || 'Practice';
    const lessonLang = urlParams.get('lessonLang') || 'en'; // 'en' or 'pt' for bilingual
    const user = apiClient.getUser();

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
    const reportBtn = document.getElementById('report-btn');
    const micHint = document.getElementById('mic-hint');
    const chatWindow = document.getElementById('chat-window');

    // Subtitle Toggle Logic
    window.toggleSubtitles = function () {
        document.body.classList.toggle('subtitles-on');
        const ccBtn = document.getElementById('cc-toggle-btn');
        if (ccBtn) {
            if (document.body.classList.contains('subtitles-on')) {
                ccBtn.classList.add('active');
                ccBtn.title = "Ocultar Legendas";
            } else {
                ccBtn.classList.remove('active');
                ccBtn.title = "Mostrar Legendas";
            }
        }
    };

    // TTS Speed Logic
    let ttsSpeed = 1.0;
    const urlSpeed = parseFloat(urlParams.get('speed'));
    if (urlSpeed && !isNaN(urlSpeed)) {
        ttsSpeed = urlSpeed;
    } else if (urlParams.get('type') === 'grammar') {
        ttsSpeed = 0.7;
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
    const autoTranslateToggle = document.getElementById('auto-translate-toggle');

    let isRecording = false;
    let isProcessing = false;
    const conversationLog = [];
    let currentAudio = null; // Track current audio for skip functionality
    let userMessageCount = 0; // Track user messages for report button

    // Usage tracking variables
    let sessionStartTime = null;
    let currentSessionSeconds = 0;
    let totalUsedToday = 0;
    const DAILY_LIMIT_SECONDS = 600; // 10 minutes
    let usageUpdateInterval = null;
    let remainingSeconds = DAILY_LIMIT_SECONDS;
    let isUsageLimitReached = false;

    // Initialize usage tracking from login response
    const storedUsage = localStorage.getItem('usage_data');
    if (storedUsage && user) {
        try {
            const usageData = JSON.parse(storedUsage);
            totalUsedToday = usageData.seconds_used || 0;
            remainingSeconds = usageData.remaining_seconds || DAILY_LIMIT_SECONDS;
            isUsageLimitReached = remainingSeconds <= 0;
        } catch (e) {
            console.log('Failed to parse usage data:', e);
        }
    }

    // Timer display update function
    function updateTimerDisplay(seconds) {
        const timerDisplay = document.getElementById('timer-display');
        const usageTimer = document.getElementById('usage-timer');

        if (!timerDisplay || !usageTimer) return;

        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        timerDisplay.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;

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
                    await apiClient.trackUsage(currentSessionSeconds);
                    // Reset session counter after successful sync
                    sessionStartTime = Date.now();
                    remainingSeconds = Math.max(0, remainingSeconds - currentSessionSeconds);
                    currentSessionSeconds = 0;
                } catch (err) {
                    console.error('Failed to sync usage:', err);
                }
            }
        }, 30000);
    }

    // Check if user can send message
    function checkUsageLimit() {
        if (isUsageLimitReached || remainingSeconds <= 0) {
            showUsageExceededModal();
            return false;
        }
        return true;
    }

    // Show usage exceeded modal
    function showUsageExceededModal() {
        // Check if already showing
        if (document.getElementById('usage-exceeded-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'usage-exceeded-overlay';
        overlay.className = 'usage-exceeded-overlay';

        overlay.innerHTML = `
            <div class="usage-exceeded-modal">
                <div class="modal-icon">⏰</div>
                <h2>Limite Diário Atingido</h2>
                <p>Você usou seus 10 minutos de prática de hoje!</p>
                <div class="time-info">
                    <p><strong>Tempo usado:</strong> ${Math.floor(totalUsedToday / 60)} minutos</p>
                    <p><strong>Próximo reset:</strong> Amanhã às 00:00 UTC</p>
                </div>
                <p style="font-size: 0.9rem; color: #94a3b8;">Continue praticando amanhã para manter seu progresso! 🚀</p>
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

    // Load auto-translate preference
    const autoTranslatePref = localStorage.getItem('auto_translate');
    if (autoTranslatePref === 'true' && autoTranslateToggle) {
        autoTranslateToggle.checked = true;
    }

    // Save auto-translate preference
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
            parsed.forEach(msg => {
                if (msg.sender && msg.text) {
                    addMessage(msg.sender, msg.text, msg.sender === 'AI', false);
                }
            });
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

    if (startBtn) {
        // Add pulse animation to start button
        startBtn.classList.add('pulse-animation');

        startBtn.addEventListener('click', () => {
            const startMessage = document.getElementById('start-message');
            if (startMessage) startMessage.style.display = 'none';

            // Remove hint and enable buttons
            if (micHint) micHint.style.display = 'none';
            if (recordBtn) recordBtn.disabled = false;

            // Start usage timer
            startUsageTimer();

            // Clear conversation and UI when starting fresh
            conversationLog.length = 0;
            userMessageCount = 0;
            localStorage.removeItem('conversation_backup');

            // Remove all messages except the start message
            const messages = chatWindow.querySelectorAll('.message:not(#start-message)');
            messages.forEach(msg => msg.remove());

            // Initial AI Greeting - context-specific, no generic "how can I help you"
            let greeting = "";
            let translation = "";

            // Educational greetings for Learning/Grammar topics
            const grammarGreetings = {
                'verb_to_be': {
                    en: "Welcome to our lesson on the verb 'To Be'! 🎭 This is one of the most important building blocks in English. Before we start, tell me: what's your experience with 'to be'? Have you studied it before, or is this completely new for you?",
                    pt: "Bem-vindo à nossa aula sobre o verbo 'To Be'! 🎭 Este é um dos principais blocos de construção do inglês. Antes de começarmos, me conte: qual é sua experiência com 'to be'? Você já estudou antes ou é completamente novo para você?"
                },
                'greetings': {
                    en: "Hey there! Welcome to our lesson on Greetings & Introductions! 👋 Learning how to greet people is the first step to any conversation. So tell me, do you already know some ways to say 'hello' in English, or should we start from the basics?",
                    pt: "Olá! Bem-vindo à nossa aula sobre Saudações e Apresentações! 👋 Aprender a cumprimentar pessoas é o primeiro passo para qualquer conversa. Me conta, você já sabe algumas formas de dizer 'olá' em inglês, ou devemos começar do básico?"
                },
                'articles': {
                    en: "Welcome to our lesson on Articles - A, An, and The! 🍎 These little words can be tricky, but they're super important. Quick question before we dive in: have you noticed when English uses 'a' versus 'an'? What's your current understanding?",
                    pt: "Bem-vindo à nossa aula sobre Artigos - A, An e The! 🍎 Essas pequenas palavras podem ser complicadas, mas são super importantes. Pergunta rápida antes de começarmos: você já notou quando o inglês usa 'a' versus 'an'? Qual é seu entendimento atual?"
                },
                'plurals': {
                    en: "Welcome to our lesson on Plural Nouns! 🐈 From cats to babies, English has some interesting patterns for making things plural. Tell me, do you already know some plural rules, or is this your first time learning about them?",
                    pt: "Bem-vindo à nossa aula sobre Substantivos no Plural! 🐈 De gatos a bebês, o inglês tem alguns padrões interessantes para formar plurais. Me conta, você já conhece algumas regras de plural, ou é sua primeira vez aprendendo sobre elas?"
                },
                'demonstratives': {
                    en: "Welcome to our lesson on Demonstratives - This, That, These, Those! 👉 These words help us point to things near and far. Before we start, can you tell me: do you know the difference between 'this' and 'that'? I'd love to know where you're starting from!",
                    pt: "Bem-vindo à nossa aula sobre Demonstrativos - This, That, These, Those! 👉 Essas palavras nos ajudam a apontar para coisas perto e longe. Antes de começarmos, você sabe a diferença entre 'this' e 'that'? Adoraria saber de onde você está começando!"
                },
                'subject_pronouns': {
                    en: "Welcome to our lesson on Subject Pronouns! 👤 I, You, He, She, It, We, They - these are the stars of every sentence! So tell me, which pronouns do you already feel comfortable with, and which ones still confuse you?",
                    pt: "Bem-vindo à nossa aula sobre Pronomes Pessoais! 👤 I, You, He, She, It, We, They - estes são as estrelas de toda frase! Me conta, quais pronomes você já se sente confortável, e quais ainda te confundem?"
                },
                'possessives': {
                    en: "Welcome to our lesson on Possessive Adjectives! 🎒 My, Your, His, Her, Our, Their - these show who owns what. Before we begin, do you know how to say 'my book' and 'your phone' in English? What's your level with possessives?",
                    pt: "Bem-vindo à nossa aula sobre Adjetivos Possessivos! 🎒 My, Your, His, Her, Our, Their - estes mostram quem possui o quê. Antes de começarmos, você sabe dizer 'meu livro' e 'seu telefone' em inglês? Qual é seu nível com possessivos?"
                },
                'present_simple': {
                    en: "Welcome to our lesson on Present Simple! ⏰ This tense is all about habits, routines, and facts. Quick question: do you know the difference between 'I work' and 'He works'? Tell me about your experience with this tense!",
                    pt: "Bem-vindo à nossa aula sobre Present Simple! ⏰ Este tempo verbal é sobre hábitos, rotinas e fatos. Pergunta rápida: você sabe a diferença entre 'I work' e 'He works'? Me conta sobre sua experiência com este tempo verbal!"
                },
                'present_continuous': {
                    en: "Welcome to our lesson on Present Continuous! 🏃 This is about what's happening RIGHT NOW. For example, right now you are learning English! 😊 Tell me, do you already know how to form sentences with 'am/is/are + ing'? What's your current level?",
                    pt: "Bem-vindo à nossa aula sobre Present Continuous! 🏃 Este é sobre o que está acontecendo AGORA MESMO. Por exemplo, agora você está aprendendo inglês! 😊 Me conta, você já sabe formar frases com 'am/is/are + ing'? Qual é seu nível atual?"
                },
                'basic_questions': {
                    en: "Welcome to our lesson on Basic Questions! ❓ What, Where, When, Who, Why, How - these are the magic words that unlock information. Before we dive in, can you already ask simple questions in English, or should we start from scratch?",
                    pt: "Bem-vindo à nossa aula sobre Perguntas Básicas! ❓ What, Where, When, Who, Why, How - essas são as palavras mágicas que desbloqueiam informações. Antes de mergulharmos, você já consegue fazer perguntas simples em inglês, ou devemos começar do zero?"
                },
                // Special training scenario
                'basic_structures': {
                    en: "Welcome to your polite expressions practice! 🎓 Today we'll work on asking for things politely, thanking people, and being courteous. First, tell me: how comfortable are you with saying 'please', 'thank you', and 'excuse me' in conversations?",
                    pt: "Bem-vindo à sua prática de expressões educadas! 🎓 Hoje vamos trabalhar em pedir coisas educadamente, agradecer pessoas e ser cortês. Primeiro, me conte: quão confortável você está em dizer 'please', 'thank you' e 'excuse me' em conversas?"
                }
            };

            // Check if this is a grammar/learning topic
            const isGrammarTopic = grammarGreetings.hasOwnProperty(context);

            if (isGrammarTopic) {
                if (lessonLang === 'pt') {
                    // PT MODE: Create bilingual greeting with [EN] tags for English phrases
                    // This will be read by PT voice with EN voice for tagged parts
                    const bilingualGreetings = {
                        'verb_to_be': "Bem-vindo à nossa aula sobre o verbo [EN]To Be[/EN]! 🎭 Este é um dos principais blocos de construção do inglês. Você vai aprender a dizer coisas como [EN]I am happy[/EN] e [EN]You are wonderful[/EN]. Antes de começarmos, me conte: você já estudou o [EN]verb to be[/EN] antes, ou é completamente novo?",
                        'greetings': "Olá! Bem-vindo à nossa aula sobre Saudações! 👋 Vamos aprender a dizer [EN]Hello, how are you?[/EN] e [EN]Nice to meet you![/EN]. Me conta, você já sabe cumprimentar alguém em inglês?",
                        'articles': "Bem-vindo à nossa aula sobre Artigos! 🍎 Vamos aprender quando usar [EN]a[/EN], [EN]an[/EN] e [EN]the[/EN]. Por exemplo: [EN]I have a dog[/EN] e [EN]I ate an apple[/EN]. Qual é sua experiência com artigos em inglês?",
                        'plurals': "Bem-vindo à nossa aula sobre Plurais! 🐈 Vamos aprender como transformar [EN]cat[/EN] em [EN]cats[/EN] e [EN]baby[/EN] em [EN]babies[/EN]. Você já conhece algumas regras de plural?",
                        'demonstratives': "Bem-vindo à nossa aula sobre Demonstrativos! 👉 Vamos aprender [EN]this[/EN] (isso aqui), [EN]that[/EN] (aquilo lá), [EN]these[/EN] (estes) e [EN]those[/EN] (aqueles). Você já sabe a diferença entre eles?",
                        'subject_pronouns': "Bem-vindo à nossa aula sobre Pronomes! 👤 Vamos aprender [EN]I, you, he, she, it, we, they[/EN]. Por exemplo: [EN]I am Brazilian[/EN] e [EN]She is my friend[/EN]. Quais pronomes você já conhece?",
                        'possessives': "Bem-vindo à nossa aula sobre Possessivos! 🎒 Vamos aprender [EN]my, your, his, her, our, their[/EN]. Por exemplo: [EN]This is my book[/EN] e [EN]That is your phone[/EN]. Você já sabe dizer 'meu' e 'seu' em inglês?",
                        'present_simple': "Bem-vindo à nossa aula sobre [EN]Present Simple[/EN]! ⏰ Este tempo verbal é para hábitos e rotinas. Por exemplo: [EN]I work every day[/EN] e [EN]He works at night[/EN]. Você sabe a diferença entre [EN]I work[/EN] e [EN]He works[/EN]?",
                        'present_continuous': "Bem-vindo à nossa aula sobre [EN]Present Continuous[/EN]! 🏃 Este tempo é para ações acontecendo AGORA. Por exemplo: [EN]I am learning English right now[/EN]. Você já sabe formar frases com [EN]am, is, are[/EN] mais [EN]ing[/EN]?",
                        'basic_questions': "Bem-vindo à nossa aula sobre Perguntas! ❓ Vamos aprender as palavras mágicas: [EN]What, Where, When, Who, Why, How[/EN]. Por exemplo: [EN]What is your name?[/EN] e [EN]Where do you live?[/EN]. Você já sabe fazer perguntas em inglês?",
                        'basic_structures': "Bem-vindo à prática de expressões educadas! 🎓 Vamos aprender a usar [EN]please[/EN], [EN]thank you[/EN] e [EN]excuse me[/EN]. Por exemplo: [EN]Excuse me, can you help me please?[/EN]. Me conte como você está com essas expressões!"
                    };
                    greeting = bilingualGreetings[context] || grammarGreetings[context].pt;
                    translation = '';  // No separate translation in PT mode
                } else {
                    // EN MODE: Full English immersion
                    greeting = grammarGreetings[context].en;
                    translation = grammarGreetings[context].pt;
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
                    }
                };

                const contextGreeting = contextGreetings[context];
                if (contextGreeting) {
                    greeting = contextGreeting.en;
                    translation = contextGreeting.pt;
                } else {
                    // Generic fallback for other scenarios
                    greeting = "Hello! How are you doing today?";
                    translation = "Olá! Como você está hoje?";
                }
            }

            playResponse(greeting, translation);
        });
    }


    // --- Speech Recognition with Groq Whisper ---
    let groqRecorder = null;

    // Initialize Groq Recorder
    if (typeof DeepgramRecorder !== 'undefined') {
        groqRecorder = new DeepgramRecorder();
        if (recordBtn) {
            recordBtn.disabled = false;
        }
        console.log('[Groq] Recorder initialized');
    } else {
        console.error('[Groq] DeepgramRecorder not available');
        if (recordBtn) {
            recordBtn.disabled = true;
        }
    }

    const toggleRecording = async () => {
        if (!recordBtn || recordBtn.disabled || !groqRecorder) return;

        if (!isRecording) {
            // Start recording
            const result = await groqRecorder.start();

            if (result.success) {
                isRecording = true;
                recordBtn.classList.add('recording');
                recordText.innerText = "⏹️ Parar";
            } else {
                recordText.innerText = "❌ Erro no microfone";
                setTimeout(() => {
                    recordText.innerText = "🎤 Clique para Falar";
                }, 2000);

                addMessage("System", result.error || "Não foi possível acessar o microfone. Verifique as permissões.", true);
            }
        } else {
            // Stop recording and transcribe
            try {
                recordText.innerText = "🔄 Transcrevendo...";
                recordBtn.disabled = true;

                const audioBlob = await groqRecorder.stop();
                isRecording = false;
                recordBtn.classList.remove('recording');

                // Transcribe with Groq (pass lessonLang as hint)
                const transcribeResult = await transcribeWithDeepgram(audioBlob, apiClient.token, lessonLang);

                if (transcribeResult.success) {
                    processUserResponse(transcribeResult.transcript);
                } else if (transcribeResult.retry) {
                    // Friendly retry for hallucinations
                    recordText.innerText = "🤔 Não entendi, tente de novo";
                    setTimeout(() => {
                        recordText.innerText = "🎤 Clique para Falar";
                        recordBtn.disabled = false;
                    }, 2500);
                } else {
                    throw new Error(transcribeResult.error);
                }

            } catch (err) {
                console.error('[Groq] Transcription error:', err);
                recordText.innerText = "❌ Erro na transcrição";

                setTimeout(() => {
                    recordText.innerText = "🎤 Clique para Falar";
                }, 2000);

                addMessage("System", "Não consegui transcrever o áudio. Por favor, tente novamente ou use o campo de texto.", true);
            } finally {
                recordBtn.disabled = false;
                if (!isRecording) {
                    recordText.innerText = "🎤 Clique para Falar";
                }
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
        // Check if usage limit has been reached
        if (!checkUsageLimit()) {
            return; // Exit early if limit reached
        }

        // 1. Show User Text
        addMessage(user ? user.name : "User", text);
        userMessageCount++;
        updateMessageCounter();
        updateReportButton();

        // UI State
        isProcessing = true;
        if (recordBtn) {
            recordBtn.disabled = true;
            recordText.innerText = "⏳ Pensando...";
            recordBtn.classList.remove('recording');
        }

        // Show loading indicator with animated messages
        showLoadingIndicator();

        try {
            // 2. Call AI Backend with new API client (pass lessonLang for bilingual mode)
            const data = await apiClient.chat(text, context, lessonLang);

            // Hide loading indicator
            hideLoadingIndicator();

            // 3. Play AI Response
            playResponse(data.text, data.translation);

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

            let errorMessage = "Connection error. Please check your internet and try again.";
            if (err.message.includes('Session expired')) {
                errorMessage = "Your session has expired. Redirecting to login...";
            } else if (err.message.includes('Text too long')) {
                errorMessage = "Your message is too long. Please keep it under 500 characters.";
            }

            addMessage("System", errorMessage, true);
            isProcessing = false;
            if (recordBtn) {
                recordBtn.disabled = false;
                recordText.innerText = "🎤 Clique para Falar";
            }
        }
    }

    async function playResponse(text, translation = "") {
        // Show text
        addMessage("AI", text, true, true, translation);

        // Quick replies disabled - students must practice without prompts

        // Save conversation
        saveConversation();

        // Generate Audio - try TTS, but don't block if it fails
        try {
            const blob = await apiClient.getTTS(text, ttsSpeed, lessonLang);

            // Validate blob before creating audio
            if (blob && blob.size > 0) {
                const audioUrl = URL.createObjectURL(blob);
                const audio = new Audio(audioUrl);
                currentAudio = audio;

                recordText.innerText = "🔊 Falando...";

                // Show skip button
                const skipBtn = showSkipAudioButton();

                audio.onended = () => {
                    isProcessing = false;
                    if (recordBtn) {
                        recordBtn.disabled = false;
                        recordText.innerText = "🎤 Clique para Falar";
                    }
                    URL.revokeObjectURL(audioUrl);
                    currentAudio = null;
                    if (skipBtn) skipBtn.remove();
                };

                audio.onerror = () => {
                    console.error("Audio playback failed");
                    isProcessing = false;
                    if (recordBtn) {
                        recordBtn.disabled = false;
                        recordText.innerText = "🎤 Clique para Falar";
                    }
                    currentAudio = null;
                    if (skipBtn) skipBtn.remove();
                };

                await audio.play();
            } else {
                // Empty blob - no audio available
                throw new Error("No audio data received");
            }

        } catch (e) {
            console.error("TTS Error:", e);
            // Silently continue without audio - don't show error message to user
            // Just enable the microphone so they can continue
            isProcessing = false;
            if (recordBtn) {
                recordBtn.disabled = false;
                recordText.innerText = "🎤 Clique para Falar";
            }
            currentAudio = null;
        }
    }

    async function sendReport() {
        if (!reportBtn) return;
        if (!conversationLog.length) {
            addMessage("System", "Nenhuma conversa para analisar ainda.", true);
            return;
        }

        reportBtn.disabled = true;
        reportBtn.innerText = "Gerando...";
        showLoadingIndicator();

        try {
            const data = await apiClient.generateReport(conversationLog, context);
            hideLoadingIndicator();
            renderReportCard(data);

            // Save report data for export
            window.lastReport = data.report || data;
        } catch (err) {
            console.error(err);
            hideLoadingIndicator();
            addMessage("System", `Erro ao gerar relatório: ${err.message}`, true);
        } finally {
            reportBtn.disabled = false;
            reportBtn.innerText = "Ver relatório";
        }
    }

    function renderReportCard(apiPayload) {
        if (!chatWindow) return;
        const info = normalizeReportData(apiPayload);
        const stats = getConversationStats();

        const wrapper = document.createElement('div');
        wrapper.className = 'report-card';

        const pill = document.createElement('div');
        pill.className = 'report-pill';
        pill.textContent = 'Relatório final';
        wrapper.appendChild(pill);

        // Add export buttons
        const exportButtons = document.createElement('div');
        exportButtons.className = 'export-buttons';
        exportButtons.style.cssText = 'display: flex; gap: 0.5rem; margin-bottom: 1rem;';

        const pdfBtn = document.createElement('button');
        pdfBtn.className = 'action-btn';
        pdfBtn.innerHTML = '📄 Exportar PDF';
        pdfBtn.style.cssText = 'flex: 1; margin-top: 0; padding: 0.6rem;';
        pdfBtn.onclick = () => exportReportPDF(info);
        exportButtons.appendChild(pdfBtn);

        const jsonBtn = document.createElement('button');
        jsonBtn.className = 'action-btn';
        jsonBtn.innerHTML = '💾 Exportar JSON';
        jsonBtn.style.cssText = 'flex: 1; margin-top: 0; padding: 0.6rem; background: linear-gradient(135deg, #10b981 0%, #059669 100%);';
        jsonBtn.onclick = () => exportReportJSON(info);
        exportButtons.appendChild(jsonBtn);

        wrapper.appendChild(exportButtons);

        const titleRow = document.createElement('div');
        titleRow.className = 'report-title-row';

        const title = document.createElement('div');
        title.className = 'report-title';
        title.textContent = `${info.emoji} ${info.titulo}`;
        titleRow.appendChild(title);

        const tone = document.createElement('span');
        tone.className = 'report-tone';
        tone.textContent = `Tom: ${info.tom}`;
        titleRow.appendChild(tone);
        wrapper.appendChild(titleRow);

        const meta = document.createElement('div');
        meta.className = 'report-meta';
        meta.appendChild(createChip('Contexto', contextName, '📍'));
        meta.appendChild(createChip('Trocas', `${stats.total} falas`, '🗣️'));
        meta.appendChild(createChip('Voce', `${stats.user} mensagens`, '👤'));
        meta.appendChild(createChip('AI', `${stats.ai} mensagens`, '🤖'));
        wrapper.appendChild(meta);

        const grid = document.createElement('div');
        grid.className = 'report-grid';
        grid.appendChild(buildCorrectionsBlock(info.correcoes, info.raw));
        grid.appendChild(buildSimpleBlock('Elogios', '⭐', info.elogios, "Sem elogios por enquanto."));
        grid.appendChild(buildSimpleBlock('Dicas', '🎯', info.dicas, "Sem dicas registradas."));
        wrapper.appendChild(grid);

        const practiceCard = document.createElement('div');
        practiceCard.className = 'practice-card';
        const practiceTitle = document.createElement('div');
        practiceTitle.className = 'block-title';
        const practiceIcon = document.createElement('span');
        practiceIcon.className = 'block-icon';
        practiceIcon.textContent = '➡️';
        practiceTitle.appendChild(practiceIcon);
        practiceTitle.appendChild(document.createTextNode('Proxima frase para treinar'));
        practiceCard.appendChild(practiceTitle);

        const practiceText = document.createElement('p');
        practiceText.className = 'practice-text';
        practiceText.textContent = info.frase_pratica || info.raw || "Use o microfone para gerar frases.";
        practiceCard.appendChild(practiceText);
        wrapper.appendChild(practiceCard);

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

    // Function to close report modal
    function closeReportModal() {
        const reportModal = document.getElementById('report-modal');
        if (reportModal) {
            reportModal.style.display = 'none';
        }
    }

    // Make closeReportModal available globally
    window.closeReportModal = closeReportModal;

    function normalizeReportData(payload) {
        const base = {
            titulo: "Resumo da sessao",
            emoji: "✨",
            tom: "positivo",
            correcoes: [],
            elogios: [],
            dicas: [],
            frase_pratica: "",
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

        base.elogios = Array.isArray(source.elogios) ? source.elogios.filter(Boolean) : [];
        base.dicas = Array.isArray(source.dicas) ? source.dicas.filter(Boolean) : [];

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

    function buildCorrectionsBlock(list, fallbackText) {
        const block = document.createElement('div');
        block.className = 'report-block';

        const title = document.createElement('div');
        title.className = 'block-title';
        const icon = document.createElement('span');
        icon.className = 'block-icon';
        icon.textContent = '✏️';
        title.appendChild(icon);
        title.appendChild(document.createTextNode('Correcoes'));
        block.appendChild(title);

        const ul = document.createElement('ul');
        ul.className = 'report-list';

        if (!list.length) {
            const li = document.createElement('li');
            li.className = 'muted';
            li.textContent = fallbackText || 'Nada para corrigir ainda.';
            ul.appendChild(li);
        } else {
            list.forEach(correction => {
                const li = document.createElement('li');
                li.className = 'correction-item';

                const badLine = document.createElement('div');
                badLine.className = 'correction-line bad';
                badLine.textContent = correction.ruim ? `Antes: ${correction.ruim}` : 'Antes: ...';

                const goodLine = document.createElement('div');
                goodLine.className = 'correction-line good';
                goodLine.textContent = correction.boa ? `Melhor: ${correction.boa}` : 'Melhor: ...';

                li.appendChild(badLine);
                li.appendChild(goodLine);

                // Add explanation if available
                if (correction.explicacao) {
                    const explanationLine = document.createElement('div');
                    explanationLine.className = 'correction-line explanation';
                    explanationLine.style.cssText = 'color: #94a3b8; font-size: 0.8rem; margin-top: 0.25rem; font-style: italic;';
                    explanationLine.textContent = `💡 ${correction.explicacao}`;
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

    function addMessage(sender, text, isAI = false, logMessage = true, translation = "") {
        if (!chatWindow) return;
        const msgDiv = document.createElement('div');
        // Use 'ai-message' for AI conversation replies, 'user-message' for user
        // 'system-message' should only be used for actual system UI (errors, buttons, loading)
        msgDiv.className = `message ${isAI ? 'ai-message' : 'user-message'}`;

        const bubble = document.createElement('div');
        bubble.className = 'bubble';

        const p = document.createElement('p');
        p.textContent = text;
        bubble.appendChild(p);

        if (isAI && translation) {
            const transBtn = document.createElement('button');
            transBtn.className = 'trans-btn';
            transBtn.innerHTML = '<span>🌐</span> Ver Tradução';

            const transP = document.createElement('p');
            transP.className = 'translation-text';

            // Check auto-translate preference
            const autoTranslate = autoTranslateToggle && autoTranslateToggle.checked;
            transP.style.display = autoTranslate ? 'block' : 'none';
            if (autoTranslate) {
                transBtn.innerHTML = '<span>🌐</span> Ocultar';
            }
            transP.textContent = translation;

            transBtn.onclick = () => {
                const isHidden = transP.style.display === 'none';
                transP.style.display = isHidden ? 'block' : 'none';
                transBtn.innerHTML = isHidden ? '<span>🌐</span> Ocultar' : '<span>🌐</span> Ver Tradução';
            };

            bubble.appendChild(transBtn);
            bubble.appendChild(transP);
        }

        msgDiv.appendChild(bubble);
        chatWindow.appendChild(msgDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;

        if (logMessage) {
            conversationLog.push({ sender, text });
        }
    }

    // Loading indicator functions with animated messages
    function showLoadingIndicator() {
        const existing = document.getElementById('loading-indicator');
        if (existing) return;

        const loader = document.createElement('div');
        loader.id = 'loading-indicator';
        loader.className = 'message system-message';
        loader.innerHTML = `
            <div class="bubble" style="display: flex; align-items: center; gap: 0.5rem;">
                <div class="spinner"></div>
                <span id="loading-text">Thinking...</span>
            </div>
        `;
        chatWindow.appendChild(loader);
        chatWindow.scrollTop = chatWindow.scrollHeight;

        // Animate loading messages
        const messages = ['Thinking...', 'Preparing response...', 'Almost there...'];
        let msgIndex = 0;
        const loadingText = document.getElementById('loading-text');

        const loadingInterval = setInterval(() => {
            msgIndex = (msgIndex + 1) % messages.length;
            if (loadingText) {
                loadingText.textContent = messages[msgIndex];
            } else {
                clearInterval(loadingInterval);
            }
        }, 1500);

        // Store interval ID for cleanup
        loader.dataset.intervalId = loadingInterval;

        // Show timeout message after 5 seconds
        setTimeout(() => {
            if (loadingText && document.getElementById('loading-indicator')) {
                loadingText.textContent = 'Taking longer than usual, please wait...';
            }
        }, 5000);
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
    async function exportReportPDF(reportData) {
        try {
            const blob = await apiClient.exportPDF(reportData, user.name);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `relatorio_${new Date().toISOString().split('T')[0]}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Export PDF error:', err);
            alert('Erro ao exportar PDF. Tente novamente.');
        }
    }

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

    // Add text input fallback
    const inputContainer = document.createElement('div');
    inputContainer.style.cssText = 'padding: 1rem; display: flex; gap: 0.5rem;';
    inputContainer.innerHTML = `
            <input type="text" id="text-input" placeholder="Type your message..."
                   style="flex: 1; padding: 0.75rem; border-radius: 12px; border: 1px solid var(--glass-border);
                          background: rgba(0,0,0,0.2); color: white; font-size: 1rem;">
            <button id="send-btn" class="action-btn" style="margin: 0; padding: 0.75rem 1.5rem;">Send</button>
        `;
    document.querySelector('.controls').appendChild(inputContainer);

    const textInput = document.getElementById('text-input');
    const sendBtn = document.getElementById('send-btn');

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
    }

    function updateReportButton() {
        if (reportBtn) {
            if (userMessageCount >= 3) {
                reportBtn.disabled = false;
                // Keep static text "Ver Relatório"
            } else {
                reportBtn.disabled = true;
                // Keep static text
            }
        }
    }

    function showSkipAudioButton() {
        // Remove existing skip button
        const existing = document.querySelector('.skip-audio-btn');
        if (existing) existing.remove();

        const skipBtn = document.createElement('button');
        skipBtn.className = 'skip-audio-btn';
        skipBtn.textContent = '⏭️ Skip audio';
        skipBtn.onclick = () => {
            if (currentAudio) {
                currentAudio.pause();
                currentAudio.currentTime = 0;
                currentAudio.dispatchEvent(new Event('ended'));
            }
        };

        document.querySelector('.app-container').appendChild(skipBtn);
        return skipBtn;
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
});

function handleLogin() {
    const form = document.getElementById('login-form');
    if (!form) return;

    const emailInput = document.getElementById('email');
    const passwordGroup = document.getElementById('password-group');
    const passwordInput = document.getElementById('password');

    // Show password field when admin email is detected
    // Show password field when admin email is detected
    if (emailInput) {
        const checkAdminEmail = () => {
            const email = emailInput.value.trim().toLowerCase();
            if (email === 'everydayconversation1991@gmail.com' && passwordGroup) {
                passwordGroup.style.display = 'block';
            } else if (passwordGroup) {
                // Only hide if it's NOT the admin email (and maybe empty)
                // But for safety, let's keep hiding it if mismatch
                passwordGroup.style.display = 'none';
            }
        };

        // Listen to multiple events to catch autofill, paste, etc.
        ['input', 'change', 'blur', 'keyup', 'paste'].forEach(evt => {
            emailInput.addEventListener(evt, checkAdminEmail);
        });

        // Check immediately and after a short delay for autofill
        checkAdminEmail();
        setTimeout(checkAdminEmail, 500);

        // Manual toggle for safety
        const adminToggle = document.getElementById('admin-toggle');
        if (adminToggle) {
            adminToggle.addEventListener('click', (e) => {
                e.preventDefault();
                if (passwordGroup.style.display === 'none') {
                    passwordGroup.style.display = 'block';
                    passwordInput.focus();
                } else {
                    passwordGroup.style.display = 'none';
                }
            });
        }
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

            // Redirect based on admin status
            if (data.user && data.user.is_admin) {
                window.location.href = 'admin.html';
            } else {
                window.location.href = 'dashboard.html';
            }
        } catch (err) {
            console.error('Login error:', err);
            let errorMsg = 'Login failed. Please try again.';

            if (err.message.includes('not authorized') || err.message.includes('not registered')) {
                errorMsg = 'This email is not authorized to access the platform. Please contact support.';
            } else if (err.message.includes('Invalid admin password')) {
                errorMsg = 'Invalid admin password. Try again or login without password for regular access.';
            }

            alert(errorMsg);
            submitBtn.disabled = false;
            submitBtn.textContent = 'Access Platform';
        }
    });
}

