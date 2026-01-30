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
    const context = urlParams.get('context') || 'coffee_shop';
    const contextName = urlParams.get('title') || 'Practice';
    const lessonLang = urlParams.get('lessonLang') || 'en'; // 'en' or 'pt' for bilingual
    const isGrammarMode = urlParams.get('type') === 'grammar';
    const isFreeConversation = context === 'free_conversation';
    const user = apiClient.isAuthenticated() ? apiClient.getUser() : { name: 'Visitante', is_admin: false };

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
        compositePhrase: null    // The built composite phrase for current practice
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
    const setStatusText = (text) => {
        if (statusIndicator) {
            statusIndicator.textContent = text;
        }
    };
    const reportBtn = document.getElementById('report-btn');
    const reportBarBtn = document.getElementById('report-bar-btn');
    const micHint = document.getElementById('mic-hint');
    const chatWindow = document.getElementById('chat-window');
    const subtitleToggleBtn = document.getElementById('subtitle-toggle-btn');
    const statusIndicator = document.getElementById('status-indicator');
    const freeQuestionPanel = document.getElementById('free-question-panel');
    const freeQuestionText = document.getElementById('free-question-text');
    const freeQuestionRefresh = document.getElementById('free-question-refresh');
    const freeQuestionOk = document.getElementById('free-question-ok');
    // Barra de relatório agora é gerenciada por updateReportButton()
    const suggestionsToggleBtn = document.getElementById('suggestions-toggle-btn');
    const suggestionsPanel = document.getElementById('suggestions-panel');
    const suggestionsList = document.getElementById('suggestions-list');

    // --- VOICE SELECTION LOGIC (Dynamically Injected) ---
    let currentVoice = localStorage.getItem('preferred_voice') || 'female1';
    const normalizedLessonLang = (lessonLang || '').toLowerCase();
    const isPortugueseLesson = normalizedLessonLang === 'pt' || normalizedLessonLang === 'pt-br' || normalizedLessonLang === 'pt_br';

    // Voice metadata shown in the selector per lesson language
    const voiceDisplaySets = {
        en: [
            { id: 'female1', avatar: '👩', label: 'Sarah', description: 'Warm American accent' },
            { id: 'female2', avatar: '👩‍🦰', label: 'Emma', description: 'Crisp US pronunciation' },
            { id: 'male1', avatar: '👨', label: 'James', description: 'Natural US voice' }
        ],
        pt: [
            { id: 'female1', avatar: '👩', label: 'Bruna', description: 'PT-BR natural & acolhedora' },
            { id: 'female2', avatar: '👩‍🦰', label: 'Camila', description: 'PT-BR calorosa com clareza' },
            { id: 'male1', avatar: '👨', label: 'Rafael', description: 'PT-BR voz grave confiante' }
        ]
    };

    // Inject Voice Selector into voice-selection-step container
    const voiceSelectionStep = document.getElementById('voice-selection-step');

    // In structured lessons, voice is fixed (pre-generated Vivian audio).
    // Voice selector only shown in free conversation mode.
    const lessonVoice = isFreeConversation ? null : 'lesson';
    function getActiveVoice() {
        return lessonVoice || currentVoice;
    }

    if (voiceSelectionStep) {
        if (isFreeConversation) {
            const displaySet = voiceDisplaySets[isPortugueseLesson ? 'pt' : 'en'];
            const selectorHTML = `
                <div style="margin-bottom: 10px; text-align: center;">
                <div class="voice-label" style="color:rgba(255,255,255,0.7); margin-bottom:6px; font-size:0.75rem;">${isPortugueseLesson ? 'Selecione a voz' : 'Select voice'}</div>
                    <div class="voice-selector-container" style="display: flex; gap: 6px; justify-content: center; flex-wrap: wrap;">
                        ${displaySet.map(option => `
                            <div class="voice-option ${currentVoice === option.id ? 'selected' : ''}" data-voice="${option.id}" style="width: 60px; padding: 6px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; cursor: pointer; text-align: center;">
                                <div class="voice-avatar" style="font-size: 1.2rem;">${option.avatar}</div>
                                <div class="voice-name" style="font-size: 0.6rem; color: white;">${option.label}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;

            voiceSelectionStep.innerHTML = selectorHTML;

            voiceSelectionStep.querySelectorAll('.voice-option').forEach(opt => {
                opt.addEventListener('click', () => {
                    currentVoice = opt.dataset.voice;
                    localStorage.setItem('preferred_voice', currentVoice);
                    voiceSelectionStep.querySelectorAll('.voice-option').forEach(o => o.classList.remove('selected'));
                    opt.classList.add('selected');
                });
            });
        } else {
            // Hide voice selector in structured lesson mode
            voiceSelectionStep.style.display = 'none';
        }
    }



    // Função global para ofuscar texto com pontos (legendas ocultas por padrão)
    window.obfuscateText = function () {
        return '(... ...)';
    };

    // TTS Speed Logic
    let ttsSpeed = 1.0;
    const urlSpeed = parseFloat(urlParams.get('speed'));
    if (urlSpeed && !isNaN(urlSpeed)) {
        ttsSpeed = urlSpeed;
    } else if (urlParams.get('type') === 'grammar') {
        ttsSpeed = 0.7;
    }

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

    function getSuggestionsForContext(contextId) {
        return suggestionSets[contextId] || suggestionSets['default'];
    }

    // Fetch dynamic suggestions from API based on AI's last message
    let lastAIMessage = ''; // Store last AI message for suggestions

    async function fetchDynamicSuggestions(aiMessage) {
        if (!suggestionsList || !aiMessage) return;

        // Store for later use
        lastAIMessage = aiMessage;

        try {
            // Show loading state
            suggestionsList.innerHTML = '<div class="suggestions-loading">Gerando sugestões...</div>';

            const response = await apiClient.fetch('/api/suggestions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    aiMessage: aiMessage,
                    context: context,
                    lessonLang: lessonLang
                })
            });

            if (!response.ok) throw new Error('Failed to fetch suggestions');

            const data = await response.json();
            const suggestions = data.suggestions || [];

            // Render suggestions
            suggestionsList.innerHTML = '';
            suggestions.forEach(item => {
                const card = document.createElement('div');
                card.className = 'suggestion-card';
                card.innerHTML = `
                    <div class="suggestion-en">${item.en}</div>
                    <div class="suggestion-pt">${item.pt}</div>
                `;
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

        } catch (error) {
            console.error('[SUGGESTIONS] Error:', error);
            suggestionsList.innerHTML = '<div class="suggestions-error">Erro ao carregar sugestões</div>';
        }
    }

    function setupSuggestionsUI() {
        if (!suggestionsToggleBtn || !suggestionsPanel) return;
        if (!isGrammarMode) {
            suggestionsToggleBtn.style.display = 'none';
            suggestionsPanel.style.display = 'none';
            return;
        }



        suggestionsToggleBtn.addEventListener('click', () => {
            const isActive = suggestionsPanel.classList.toggle('active');
            suggestionsToggleBtn.textContent = isActive ? 'Ocultar sugestoes' : 'Ver sugestoes';
        });
    }

    setupSuggestionsUI();

    if (isFreeConversation) {
        if (chatWindow) chatWindow.style.display = 'none';
        if (subtitleToggleBtn) subtitleToggleBtn.style.display = 'none';
        if (suggestionsToggleBtn) suggestionsToggleBtn.style.display = 'none';
        if (suggestionsPanel) suggestionsPanel.style.display = 'none';
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
                if (!questionBank) return;
                currentMainQuestion = questionBank.confirmPreview();
                if (freeQuestionRefresh) freeQuestionRefresh.disabled = true;
                if (freeQuestionOk) freeQuestionOk.disabled = true;
                showQuestionPicker(currentMainQuestion);
                freeState = FREE_STATES.AI_READS_MAIN_QUESTION;
                const prompt = `Great. Let's practice with this question: ${currentMainQuestion}. Please answer it.`;
                logConversationEntry('AI', prompt);
                await playTtsOnly(prompt);
                freeState = FREE_STATES.STUDENT_ANSWERS_MAIN;
                setStatusText('Listening...');
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
    const autoTranslateToggle = document.getElementById('auto-translate-toggle');

    let isRecording = false;
    let isProcessing = false;
    const conversationLog = [];
    let currentAudio = null; // Track current audio for skip functionality
    let ttsCancelled = false;
    let userMessageCount = 0; // Track user messages for report button

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
        AI_ANSWERS_STUDENT_QUESTION: 'AI_ANSWERS_STUDENT_QUESTION'
    };

    let freeState = null;
    let questionBank = null;
    let currentMainQuestion = '';
    let currentFollowupQuestion = '';
    let lastMainAnswer = '';
    let lastFollowupAnswer = '';

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
            this.remaining = this.remaining.filter(q => q !== confirmed);
            this.used.push(confirmed);
            this.preview = null;
            if (!this.remaining.length) {
                this.resetPool();
            } else {
                this.saveState();
            }
            return confirmed;
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
            'What is a habit that helped you recently?',
            'What do you like to do after work or school?',
            'Describe a place you would like to visit.'
        ];
    }

    function showQuestionPicker(question) {
        if (!freeQuestionPanel || !freeQuestionText) return;
        freeQuestionText.textContent = question;
        if (freeQuestionRefresh) freeQuestionRefresh.disabled = false;
        if (freeQuestionOk) freeQuestionOk.disabled = false;
        freeQuestionPanel.classList.remove('hidden');
    }

    function hideQuestionPicker() {
        if (!freeQuestionPanel) return;
        freeQuestionPanel.classList.add('hidden');
    }

    function logConversationEntry(sender, text) {
        if (!text) return;
        conversationLog.push({ sender, text });
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
            const chunks = splitTtsText(text, 480);
            const skipBtn = showSkipAudioButton();

            for (const chunk of chunks) {
                if (ttsCancelled) break;
                let blob = null;
                try {
                    blob = await apiClient.getTTS(chunk, ttsSpeed, lessonLang, getActiveVoice());
                } catch (err) {
                    console.error("TTS Error:", err);
                    continue;
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
        hideQuestionPicker();
        freeState = FREE_STATES.INTRO_AI_ASK_HOW_ARE_YOU;
        const introQuestion = "How are you today?";
        logConversationEntry('AI', introQuestion);
        await playTtsOnly(introQuestion);
        freeState = FREE_STATES.INTRO_STUDENT_ANSWER;
        setStatusText('Listening...');
    }

    async function handleFreeConversationInput(text) {
        if (!checkUsageLimit()) return;

        try {
            logConversationEntry(user ? user.name : "User", text);

            if (freeState === FREE_STATES.INTRO_STUDENT_ANSWER) {
                freeState = FREE_STATES.SHOW_QUESTION_PICKER;
                const preview = questionBank.getPreview();
                showQuestionPicker(preview);
                setStatusText('Choose a question');
                return;
            }

            if (freeState === FREE_STATES.SHOW_QUESTION_PICKER) {
                const nudge = "Please choose a question and tap OK.";
                logConversationEntry('AI', nudge);
                await playTtsOnly(nudge);
                freeState = FREE_STATES.SHOW_QUESTION_PICKER;
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
                    main_answer: lastMainAnswer,
                    followup_question: currentFollowupQuestion,
                    followup_answer: lastFollowupAnswer
                });
                const opinionText = opinionData.text || opinionData.response || '';
                logConversationEntry('AI', opinionText);
                await playTtsOnly(opinionText);

                freeState = FREE_STATES.AI_ASK_ADDITIONAL_QUESTIONS;
                const additionalPrompt = "Do you have any additional questions for me about this?";
                logConversationEntry('AI', additionalPrompt);
                await playTtsOnly(additionalPrompt);
                freeState = FREE_STATES.STUDENT_ADDITIONAL_INTENT;
                setStatusText('Listening...');
                return;
            }

            if (freeState === FREE_STATES.STUDENT_ADDITIONAL_INTENT) {
                if (isNegativeResponse(text)) {
                    freeState = FREE_STATES.SHOW_QUESTION_PICKER;
                    const preview = questionBank.getPreview();
                    showQuestionPicker(preview);
                    setStatusText('Choose a question');
                    return;
                }

                freeState = FREE_STATES.STUDENT_ASKS_QUESTION;
                const askQuestionPrompt = "Great. What is your question?";
                logConversationEntry('AI', askQuestionPrompt);
                await playTtsOnly(askQuestionPrompt);
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
                    main_answer: lastMainAnswer,
                    followup_question: currentFollowupQuestion,
                    followup_answer: lastFollowupAnswer,
                    student_question: text
                });
                const answerText = answerData.text || answerData.response || '';
                logConversationEntry('AI', answerText);
                await playTtsOnly(answerText);

                const additionalPrompt = "Do you have any additional questions for me about this?";
                logConversationEntry('AI', additionalPrompt);
                await playTtsOnly(additionalPrompt);
                freeState = FREE_STATES.STUDENT_ADDITIONAL_INTENT;
                setStatusText('Listening...');
                return;
            }
        } catch (err) {
            console.error(err);
            setStatusText('Error');
            if (recordBtn) {
                recordBtn.disabled = false;
                setRecordText("🎤 Clique para Falar");
            }
        }
    }

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

    // SUBTITLES OFF BY DEFAULT - do not load saved preference
    // User must explicitly enable subtitles each session
    // Initialize subtitles as disabled (show dots by default)
    if (typeof window.subtitlesEnabled === 'undefined') {
        window.subtitlesEnabled = false;
    }

    if (autoTranslateToggle) {
        autoTranslateToggle.checked = false; // Force OFF
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

        startBtn.addEventListener('click', async () => {
            const startOverlay = document.getElementById('start-overlay');
            if (startOverlay) startOverlay.style.display = 'none';
            const startMessage = document.getElementById('start-message');
            if (startMessage) startMessage.style.display = 'none';
            // Show footer bar now that overlay is hidden
            const footerBar = document.getElementById('footer-bar');
            if (footerBar) footerBar.style.display = '';

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

            // Free Conversation guided cycles
            if (isFreeConversation) {
                if (freeQuestionPanel) hideQuestionPicker();
                await startFreeConversationFlow();
                return;
            }

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

        const micIcon = document.getElementById('mic-icon-inner');

        if (!isRecording) {
            // Start recording
            try {
                const result = await groqRecorder.start();
                if (result.success) {
                    isRecording = true;
                    recordBtn.classList.add('recording');
                    if (micIcon) micIcon.innerText = "⏹️";
                } else {
                    addMessage("System", result.error || "Microphone Error", true);
                }
            } catch (e) { console.error(e); }
        } else {
            // Stop recording and transcribe
            try {
                if (micIcon) micIcon.innerText = "⏳";
                recordBtn.disabled = true;

                const audioBlob = await groqRecorder.stop();
                isRecording = false;
                recordBtn.classList.remove('recording');

                // Transcribe — force English STT when practicing English phrases
                const sttLang = (lessonState.active && lessonState.nextAction === 'evaluate_practice') ? 'en' : lessonLang;
                const transcribeResult = await transcribeWithDeepgram(audioBlob, apiClient.token, sttLang);

                if (transcribeResult.success) {
                    processUserResponse(transcribeResult.transcript);
                } else if (transcribeResult.retry) {
                    if (micIcon) micIcon.innerText = "🤔";
                    setTimeout(() => { if (micIcon) micIcon.innerText = "🎤"; recordBtn.disabled = false; }, 2000);
                } else {
                    throw new Error(transcribeResult.error);
                }

            } catch (err) {
                console.error('[Groq] Transcription error:', err);
                if (micIcon) micIcon.innerText = "❌";
                setTimeout(() => { if (micIcon) micIcon.innerText = "🎤"; }, 2000);
            } finally {
                recordBtn.disabled = false;
                if (!isRecording && micIcon && micIcon.innerText !== "❌" && micIcon.innerText !== "🤔") {
                    micIcon.innerText = "🎤";
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

        if (isFreeConversation) {
            await handleFreeConversationInput(text);
            return;
        }

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

            // If waiting for option selection, ignore voice input
            if (lessonState.nextAction === 'show_options' || lessonState.nextAction === 'select_option') {
                // Don't process voice input - user should click an option
                addMessage('System', 'Please click one of the options above to continue the lesson.', true);
                return;
            }
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
            setRecordText("⏳ Pensando...");
            recordBtn.classList.remove('recording');
        }

        // Show loading indicator with animated messages
        showLoadingIndicator();

        try {
            // 2. Call AI Backend with new API client (pass lessonLang and practiceMode)
            const practiceMode = window.getSelectedMode ? window.getSelectedMode() : 'learning';
            const data = await apiClient.chat(text, context, lessonLang, practiceMode);

            // Hide loading indicator
            hideLoadingIndicator();

            // 3. Play AI Response
            playResponse(data.text, data.translation);
            // Yellow suggestion bar disabled — not helpful for students
            // renderSuggestedWords(data.suggested_words || [], data.retry_prompt || '');

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

    function playAudioBlob(blob) {
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
            let cleaned = false;
            const cleanup = () => {
                if (cleaned) return;
                cleaned = true;
                URL.revokeObjectURL(audioUrl);
                currentAudio = null;
                if (window.stopAvatarTalking) window.stopAvatarTalking();
                // Re-enable microphone after playback ends
                if (recordBtn && !isProcessing) {
                    recordBtn.disabled = false;
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
            recordBtn.disabled = false;
            setRecordText("🎤 Clique para Falar");
        }
        if (window.stopAvatarTalking) window.stopAvatarTalking();
        currentAudio = null;
        if (skipBtn) skipBtn.remove();
    }

    async function playResponse(text, translation = "") {
        // Show text
        addMessage("AI", text, true, true, translation);

        // Save conversation
        saveConversation();

        // Generate Audio in safe chunks to avoid TTS length errors
        try {
            ttsCancelled = false;
            const chunks = splitTtsText(text, 480);
            const skipBtn = showSkipAudioButton();

            for (const chunk of chunks) {
                if (ttsCancelled) break;
                let blob = null;
                try {
                    blob = await apiClient.getTTS(chunk, ttsSpeed, lessonLang, getActiveVoice());
                } catch (err) {
                    console.error("TTS Error:", err);
                    continue;
                }

                if (ttsCancelled) break;
                if (blob && blob.size > 0) {
                    await playAudioBlob(blob);
                }
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
            const data = await apiClient.generateReport(conversationLog, context);
            hideLoadingIndicator();

            // Save report data for export
            window.lastReport = data.report || data;

            const opened = openReportWindow(data, reportWin);
            if (!opened) {
                renderReportCard(data);
            }
        } catch (err) {
            console.error(err);
            hideLoadingIndicator();
            addMessage("System", `Erro ao gerar relat?rio: ${err.message}`, true);
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

        // Phrase-by-phrase analysis block (before corrections)
        if (info.analise_frases && info.analise_frases.length) {
            wrapper.appendChild(buildAnaliseBlock(info.analise_frases));
        }

        // Expandable corrections section (hidden by default)
        if (info.correcoes && info.correcoes.length) {
            const correctionsToggle = document.createElement('button');
            correctionsToggle.className = 'action-btn';
            correctionsToggle.textContent = 'Acessar correções mais detalhadas';
            correctionsToggle.style.cssText = 'width:100%;margin-top:1rem;padding:14px 20px;font-size:1rem;font-weight:700;color:#fff;background:linear-gradient(135deg,#6366f1 0%,#4f46e5 100%);border:none;border-radius:10px;cursor:pointer;box-shadow:0 4px 15px rgba(99,102,241,0.3);transition:all 0.3s ease;';
            correctionsToggle.onmouseenter = () => { correctionsToggle.style.transform = 'translateY(-2px)'; correctionsToggle.style.boxShadow = '0 6px 20px rgba(99,102,241,0.5)'; };
            correctionsToggle.onmouseleave = () => { correctionsToggle.style.transform = 'translateY(0)'; correctionsToggle.style.boxShadow = '0 4px 15px rgba(99,102,241,0.3)'; };
            wrapper.appendChild(correctionsToggle);

            const correctionsPanel = document.createElement('div');
            correctionsPanel.style.cssText = 'display:none;margin-top:1rem;';
            correctionsPanel.appendChild(buildCorrectionsBlock(info.correcoes, info.raw));
            wrapper.appendChild(correctionsPanel);

            correctionsToggle.addEventListener('click', () => {
                if (correctionsPanel.style.display === 'none') {
                    correctionsPanel.style.display = 'block';
                    correctionsToggle.textContent = 'Fechar correções detalhadas';
                    correctionsToggle.style.background = 'linear-gradient(135deg,#64748b 0%,#475569 100%)';
                } else {
                    correctionsPanel.style.display = 'none';
                    correctionsToggle.textContent = 'Acessar correções mais detalhadas';
                    correctionsToggle.style.background = 'linear-gradient(135deg,#6366f1 0%,#4f46e5 100%)';
                }
            });
        }

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

        const resumoItens = [
            ...(info.elogios || []).slice(0, 4),
            ...(info.dicas || []).slice(0, 2)
        ].filter(Boolean);

        const resumoHtml = resumoItens.length
            ? resumoItens.map(item => `<li>${escapeHtml(item)}</li>`).join('')
            : `<li>Sem resumo disponível ainda.</li>`;

        const correctionsHtml = (info.correcoes && info.correcoes.length)
            ? info.correcoes.map((correction) => {
                const badge = escapeHtml(correction.avaliacaoGeral || 'Analisando');
                const tag = correction.tag ? `<span class="tag">${escapeHtml(correction.tag)}</span>` : '';
                const comentario = correction.comentarioBreve ? `<div class="note">${escapeHtml(correction.comentarioBreve)}</div>` : '';
                const original = escapeHtml(correction.fraseOriginal || correction.ruim || '');
                const corrigida = escapeHtml(correction.fraseCorrigida || correction.boa || '');
                const explicacao = escapeHtml(correction.explicacaoDetalhada || correction.explicacao || '');
                const expHtml = explicacao ? `<div class="explain">💡 ${explicacao}</div>` : '';
                return `
                    <div class="correction-card">
                        <div class="badge-row">
                            <span class="badge">${badge}</span>
                            ${tag}
                        </div>
                        ${comentario}
                        <div class="line bad">❌ Você disse: <span>"${original}"</span></div>
                        <div class="line good">✅ Melhor forma: <span>"${corrigida}"</span></div>
                        ${expHtml}
                    </div>
                `;
            }).join('')
            : `<div class="empty">Sem correções relevantes nesta sessão.</div>`;

        const elogiosHtml = (info.elogios && info.elogios.length)
            ? info.elogios.map(item => `<li>${escapeHtml(item)}</li>`).join('')
            : `<li>Sem elogios registrados.</li>`;

        const dicasHtml = (info.dicas && info.dicas.length)
            ? info.dicas.map(item => `<li>${escapeHtml(item)}</li>`).join('')
            : `<li>Sem dicas registradas.</li>`;

        const transcriptHtml = conversationLog.length
            ? conversationLog.map(entry => {
                const sender = escapeHtml(entry.sender || '');
                const text = escapeHtml(entry.text || '');
                return `<div class="transcript-line"><strong>${sender}:</strong> ${text}</div>`;
            }).join('')
            : `<div class="empty">Sem falas registradas.</div>`;

        // Phrase-by-phrase analysis HTML
        const analiseHtml = (info.analise_frases && info.analise_frases.length)
            ? info.analise_frases.map((item) => {
                const nat = typeof item.naturalidade === 'number' ? item.naturalidade : 50;
                let barColor = '#ef4444';
                if (nat >= 80) barColor = '#22c55e';
                else if (nat >= 50) barColor = '#f59e0b';
                const nivelText = escapeHtml(item.nivel || '');
                const explicacao = item.explicacao ? `<div style="font-size:0.85rem;color:var(--muted);padding:8px 10px;background:rgba(255,204,0,0.08);border-radius:6px;border-left:3px solid #f59e0b;margin-top:6px;">💡 ${escapeHtml(item.explicacao)}</div>` : '';
                const naturalLine = item.frase_natural ? `<div style="margin-bottom:6px;font-size:0.95rem;"><span style="color:#22c55e;">✅ Mais natural:</span> <strong>"${escapeHtml(item.frase_natural)}"</strong></div>` : '';
                return `
                    <div class="analise-card">
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

        const reportPayload = {
            report: {
                titulo: info.titulo,
                emoji: info.emoji,
                tom: info.tom,
                correcoes: info.correcoes,
                analise_frases: info.analise_frases,
                elogios: info.elogios,
                dicas: info.dicas,
                frase_pratica: info.frase_pratica
            },
            user_name: userName
        };

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
  padding: 48px 8vw 24px;
  background: linear-gradient(135deg, rgba(229,9,20,0.25), transparent 60%);
}
header h1 {
  font-family: 'Playfair Display', serif;
  font-size: 2.6rem;
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
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}
.summary .card {
  background: var(--panel);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  padding: 16px;
}
.summary .card strong { display:block; margin-bottom: 6px; }
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
.highlight ul { margin: 0; padding-left: 18px; }
.corrections {
  display: grid;
  gap: 12px;
}
.correction-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 14px;
  padding: 16px;
}
.badge-row { display: flex; gap: 8px; align-items: center; }
.badge {
  background: rgba(34,197,94,0.2);
  color: var(--success);
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
  max-height: 320px;
  overflow-y: auto;
}
.transcript-line { margin-bottom: 8px; color: var(--muted); }
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
}
.button.secondary {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.2);
}
.footer-note { color: var(--muted); font-size: 0.9rem; }
.empty { color: var(--muted); }
.analise-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 12px;
}
</style>
</head>
<body>
<header>
  <h1>${escapeHtml(info.emoji)} ${escapeHtml(info.titulo)}</h1>
  <p>${escapeHtml(contextName)} • ${escapeHtml(userName)} • ${escapeHtml(createdAt)}</p>
</header>
<main>
  <section class="summary">
    <div class="card"><strong>Tom da conversa</strong>${escapeHtml(info.tom)}</div>
    <div class="card"><strong>Trocas</strong>${stats.total} falas</div>
    <div class="card"><strong>Mensagens do aluno</strong>${stats.user}</div>
    <div class="card"><strong>Mensagens da IA</strong>${stats.ai}</div>
  </section>

  <section class="highlight">
    <h2>Resumo mais importante</h2>
    <ul>${resumoHtml}</ul>
  </section>

  <section class="highlight">
    <h2>🎯 Análise Frase a Frase</h2>
    <div class="corrections">${analiseHtml}</div>
  </section>

  <section class="highlight" style="text-align:center;">
    <button id="toggle-corrections" style="
      padding:14px 28px;font-size:1rem;font-weight:700;color:#fff;
      background:linear-gradient(135deg,#6366f1 0%,#4f46e5 100%);
      border:none;border-radius:10px;cursor:pointer;
      box-shadow:0 4px 15px rgba(99,102,241,0.3);transition:all 0.3s ease;
    ">Acessar correções mais detalhadas</button>
    <div id="corrections-panel" style="display:none;margin-top:20px;text-align:left;">
      <h2>Correções detalhadas</h2>
      <div class="corrections">${correctionsHtml}</div>
    </div>
  </section>

  <section class="highlight">
    <h2>Transcrição da conversa</h2>
    <div class="transcript">${transcriptHtml}</div>
  </section>

  <section class="highlight">
    <h2>Exportar relatório</h2>
    <div class="action-bar">
      <button class="button" id="download-pdf">Baixar PDF</button>
      <button class="button secondary" id="copy-summary">Copiar resumo</button>
    </div>
    <p class="footer-note">O PDF usa o relatório gerado nesta sessão.</p>
  </section>
</main>
<script>
window.__REPORT_PAYLOAD__ = ${JSON.stringify(reportPayload).replace(/</g, '\u003c')};
window.__SUMMARY_TEXT__ = ${JSON.stringify(resumoItens.join(' • ')).replace(/</g, '\u003c')};

const getAuthHeaders = () => {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem('auth_token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  return headers;
};

document.getElementById('toggle-corrections').addEventListener('click', () => {
  const panel = document.getElementById('corrections-panel');
  const btn = document.getElementById('toggle-corrections');
  if (panel.style.display === 'none') {
    panel.style.display = 'block';
    btn.textContent = 'Fechar correções detalhadas';
    btn.style.background = 'linear-gradient(135deg,#64748b 0%,#475569 100%)';
  } else {
    panel.style.display = 'none';
    btn.textContent = 'Acessar correções mais detalhadas';
    btn.style.background = 'linear-gradient(135deg,#6366f1 0%,#4f46e5 100%)';
  }
});

document.getElementById('download-pdf').addEventListener('click', async () => {
  const btn = document.getElementById('download-pdf');
  btn.disabled = true;
  btn.textContent = 'Gerando PDF...';
  try {
    const res = await fetch('/api/export/pdf', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(window.__REPORT_PAYLOAD__)
    });
    if (!res.ok) throw new Error('Falha ao gerar PDF');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'relatorio_' + new Date().toISOString().slice(0,10) + '.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    alert('Nao foi possivel gerar o PDF agora. Tente novamente.');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Baixar PDF';
  }
});

document.getElementById('copy-summary').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(window.__SUMMARY_TEXT__ || '');
    alert('Resumo copiado!');
  } catch (err) {
    alert('Nao foi possivel copiar o resumo.');
  }
});
</script>
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
                studentLine.innerHTML = `<span style="color:#94a3b8;">🗣️ Você disse:</span> <strong>"${(item.frase_aluno || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}"</strong>`;
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
                    naturalLine.innerHTML = `<span style="color:#22c55e;">✅ Mais natural:</span> <strong>"${(item.frase_natural || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}"</strong>`;
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
                badLine.innerHTML = `<span style="color:#ef4444;">❌ Você disse:</span> "${correction.fraseOriginal || correction.ruim || ''}"`;
                li.appendChild(badLine);

                // 5. Frase Corrigida
                const goodLine = document.createElement('div');
                goodLine.className = 'correction-line good';
                goodLine.innerHTML = `<span style="color:#10b981;">✓ Melhor forma:</span> "${correction.fraseCorrigida || correction.boa || ''}"`;
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
                    explanationLine.innerHTML = `💡 <strong>Por que mudar:</strong> ${correction.explicacaoDetalhada || correction.explicacao}`;
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
        if (!chatWindow) return null;

        // Cinematic Mode: show only the latest message group
        chatWindow.innerHTML = '';

        const messageGroup = document.createElement('div');
        messageGroup.className = 'subtitle-group';

        const msgDiv = document.createElement('div');
        msgDiv.className = `subtitle-line ${isAI ? 'ai' : 'user'}`;

        // Add fade-in animation styles directly
        msgDiv.style.opacity = '0';
        msgDiv.style.transform = 'translateY(10px)';
        msgDiv.style.transition = 'all 0.5s ease';

        // Store real text and show placeholder when subtitles are off
        msgDiv.setAttribute('data-text', text);
        const shouldShowText = (typeof window.subtitlesEnabled !== 'undefined' && window.subtitlesEnabled) ||
            (autoTranslateToggle && autoTranslateToggle.checked);
        msgDiv.innerText = shouldShowText ? text : (window.obfuscateText ? window.obfuscateText(text) : '(... ...)');

        messageGroup.appendChild(msgDiv);

        // Trigger reflow for animation
        void msgDiv.offsetWidth;

        msgDiv.style.opacity = '1';
        msgDiv.style.transform = 'translateY(0)';

        // Always add translation if AI message has one - visibility controlled by CSS/toggle
        if (isAI && translation) {
            const transDiv = document.createElement('div');
            transDiv.className = 'translation-line';
            transDiv.style.cssText = "font-size: 0.9em; color: #aaa; margin-top: 5px; font-style: italic;";
            transDiv.innerText = translation;

            // Check if subtitles are enabled (via checkbox or global var)
            const subtitlesOn = (autoTranslateToggle && autoTranslateToggle.checked) ||
                (typeof window.subtitlesEnabled !== 'undefined' && window.subtitlesEnabled);
            transDiv.style.display = subtitlesOn ? 'block' : 'none';

            messageGroup.appendChild(transDiv);
        }

        chatWindow.appendChild(messageGroup);

        if (logMessage) {
            conversationLog.push({ sender, text });
        }

        return messageGroup;
    }

    function renderSuggestedWords(words = [], promptText = "") {
        if (!chatWindow) return;

        const existing = chatWindow.querySelector('.suggested-words-card');
        if (existing) existing.remove();

        if (!Array.isArray(words) || words.length === 0) return;

        const messageGroup = chatWindow.querySelector('.subtitle-group') || chatWindow;
        const card = document.createElement('div');
        card.className = 'suggested-words-card';

        const title = document.createElement('div');
        title.className = 'suggested-words-title';
        title.textContent = promptText || 'Tente reformular sua resposta usando pelo menos uma dessas 4 palavras abaixo:';
        card.appendChild(title);

        const list = document.createElement('ol');
        list.className = 'suggested-words-list';

        words.slice(0, 4).forEach(word => {
            const li = document.createElement('li');
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'suggested-word-btn';
            btn.textContent = word;
            btn.addEventListener('click', () => {
                if (textInput) {
                    const spacer = textInput.value && !textInput.value.endsWith(' ') ? ' ' : '';
                    textInput.value = `${textInput.value}${spacer}${word}`.trim();
                    textInput.focus();
                }
            });
            li.appendChild(btn);
            list.appendChild(li);
        });

        card.appendChild(list);
        messageGroup.appendChild(card);
    }

    // =============================================
    // STRUCTURED LESSON FUNCTIONS
    // =============================================

    /**
     * Render lesson options as clickable cards
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
        title.textContent = layerTitle || 'Choose a phrase to practice:';
        container.appendChild(title);

        // Options list
        options.forEach((opt, index) => {
            const card = document.createElement('div');
            card.className = 'lesson-option-card';

            const optionNumber = document.createElement('div');
            optionNumber.className = 'option-number';
            optionNumber.textContent = index + 1;

            const optionContent = document.createElement('div');
            optionContent.className = 'option-content';
            optionContent.innerHTML = `
                <div class="option-en">"${opt.en || opt}"</div>
                ${opt.pt ? `<div class="option-pt">(${opt.pt})</div>` : ''}
            `;

            // Audio button - plays pronunciation without selecting the option
            const audioBtn = document.createElement('button');
            audioBtn.className = 'option-audio-btn';
            audioBtn.innerHTML = '<span class="audio-icon">🔊</span>';
            audioBtn.title = 'Listen to pronunciation';
            audioBtn.addEventListener('click', async (e) => {
                e.stopPropagation(); // Prevent card selection
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
            card.addEventListener('click', () => selectLessonOption(index, opt));
            container.appendChild(card);
        });

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
    async function selectLessonOption(index, phrase) {
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
            const data = await apiClient.lesson('select_option', context, {
                layer: lessonState.layer,
                option: index
            });

            hideLoadingIndicator();

            // Play practice prompt
            playResponse(data.text, data.translation);

            // Update state
            lessonState.nextAction = data.next_action;

            // Store skip_to_layer if present (for branching after practice)
            if (data.skip_to_layer !== undefined) {
                lessonState.skipToLayer = data.skip_to_layer;
            } else {
                lessonState.skipToLayer = null;
            }

            // Now enable microphone for practice
            // The user will speak, and processUserResponse will handle it

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
            // Fallback to old conversational mode
            addMessage('System', 'Structured lesson not available. Starting conversation mode.', true);
        }
    }

    /**
     * Render a "Start Lesson" button after welcome
     */
    function renderLessonStartButton() {
        const container = document.createElement('div');
        container.className = 'lesson-start-container';
        container.innerHTML = `
            <button class="lesson-start-btn">
                Start Lesson
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
     * Enabled for all contexts with structured lessons in lessons_db.json
     */
    function shouldUseStructuredLesson() {
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
    if (!document.getElementById('text-input')) {
        const inputContainer = document.createElement('div');
        inputContainer.className = 'text-input-container';
        inputContainer.innerHTML = `
            <input type="text" id="text-input" class="text-input" placeholder="Type your message...">
            <button id="send-btn" class="action-btn send-btn">Send</button>
        `;

        const inputRow = document.getElementById('input-row');
        const controlsContainer = inputRow
            || document.querySelector('.controls')
            || document.querySelector('.player-controls')
            || document.querySelector('.player-overlay')
            || document.body;

        if (controlsContainer) {
            if (inputRow) {
                const micBtn = document.getElementById('record-btn');
                if (micBtn && micBtn.parentElement !== inputRow) {
                    inputRow.appendChild(micBtn);
                }
                if (micBtn && inputRow.contains(micBtn)) {
                    inputRow.insertBefore(inputContainer, micBtn);
                } else {
                    inputRow.appendChild(inputContainer);
                }
            } else {
                controlsContainer.appendChild(inputContainer);
            }
        }
    }

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
    }

    function updateReportButton() {
        const reportBar = document.getElementById('report-bar');
        if (reportBtn) reportBtn.disabled = false;
        if (reportBar) reportBar.style.display = 'block';
        if (reportBarBtn) reportBarBtn.disabled = false;
    }

    function showSkipAudioButton() {
        // Remove existing skip button
        const existing = document.querySelector('.skip-audio-btn');
        if (existing) existing.remove();

        const skipBtn = document.createElement('button');
        skipBtn.className = 'skip-audio-btn';
        skipBtn.textContent = '⏭️ Skip audio';
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

