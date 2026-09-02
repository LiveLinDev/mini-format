"""Base datasets (12 records each) for every fork shipped in ``forks/``.

Every dataset is a canonical JSON object ``{"header": {...}, "<records_key>":
[...]}`` that validates against its contract.  ``expand(prefix, n)`` cycles
through the base records assigning fresh identifiers, exactly like the
original 12-item benchmark, so that scaling curves measure serialization
length and not semantic diversity.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

# ----------------------------------------------------------------------------
# a  — assessment items (SIMA)  [es]
# ----------------------------------------------------------------------------
A_ITEMS = [
    dict(id='i1', bloom='L1', topic='Biología', statement='¿Dónde ocurre principalmente la fotosíntesis?', options=['cloroplastos', 'núcleo', 'mitocondria', 'ribosoma'], correct=0, irt=dict(a=0.9, b=-1.0, c=0.25), difficulty=1, cat=dict(area='biología', exposure_cap=0.2, demand='low')),
    dict(id='i2', bloom='L2', topic='Química', statement='¿Qué representa el pH de una solución?', options=['acidez o basicidad', 'masa molecular', 'temperatura', 'presión osmótica'], correct=0, irt=dict(a=1.1, b=-0.3, c=0.25), difficulty=2, cat=dict(area='química', exposure_cap=0.2, demand='medium')),
    dict(id='i3', bloom='L3', topic='Matemática', statement='Si 3x+6=18, ¿cuál es el valor de x?', options=['4', '6', '8', '12'], correct=0, irt=dict(a=1.4, b=0.2, c=0.2), difficulty=3, cat=dict(area='matemática', exposure_cap=0.25, demand='medium')),
    dict(id='i4', bloom='L4', topic='Historia', statement='¿Qué factor explica mejor la caída del Imperio romano de Occidente?', options=['presiones militares y crisis internas', 'un solo terremoto', 'la invención de la imprenta', 'la conquista española'], correct=0, irt=dict(a=1.7, b=0.8, c=0.2), difficulty=4, cat=dict(area='historia', exposure_cap=0.18, demand='high')),
    dict(id='i5', bloom='L5', topic='Literatura', statement='Evalúa cuál opción interpreta mejor un narrador no confiable.', options=['su relato debe contrastarse con evidencias', 'siempre dice la verdad', 'solo narra en tercera persona', 'no participa en la trama'], correct=0, irt=dict(a=2.0, b=1.2, c=0.15), difficulty=5, cat=dict(area='literatura', exposure_cap=0.15, demand='high')),
    dict(id='i6', bloom='L6', topic='Computación', statement='¿Qué solución diseñarías para reducir errores en una API?', options=['validación de esquema y pruebas automatizadas', 'eliminar logs', 'usar variables globales', 'evitar documentación'], correct=0, irt=dict(a=2.3, b=1.7, c=0.15), difficulty=5, cat=dict(area='computación', exposure_cap=0.15, demand='high')),
    dict(id='i7', bloom='L1', topic='Física', statement='¿Cuál es la unidad de fuerza en el SI?', options=['newton', 'joule', 'watt', 'pascal'], correct=0, irt=dict(a=0.9, b=-1.2, c=0.25), difficulty=1, cat=dict(area='física', exposure_cap=0.2, demand='low')),
    dict(id='i8', bloom='L2', topic='Geografía', statement='¿Qué describe una cuenca hidrográfica?', options=['territorio drenado por un río', 'altura de una montaña', 'tipo de clima', 'frontera política'], correct=0, irt=dict(a=1.1, b=-0.2, c=0.25), difficulty=2, cat=dict(area='geografía', exposure_cap=0.22, demand='medium')),
    dict(id='i9', bloom='L3', topic='Comunicación', statement='Elige el conector que completa una relación de causa.', options=['porque', 'sin embargo', 'además', 'por ejemplo'], correct=0, irt=dict(a=1.4, b=0.1, c=0.2), difficulty=3, cat=dict(area='comunicación', exposure_cap=0.25, demand='medium')),
    dict(id='i10', bloom='L4', topic='Economía', statement='Analiza qué sucede si sube el precio y baja la demanda.', options=['disminuye la cantidad demandada', 'sube la oferta siempre', 'desaparece el mercado', 'no cambia el equilibrio'], correct=0, irt=dict(a=1.7, b=0.7, c=0.2), difficulty=4, cat=dict(area='economía', exposure_cap=0.18, demand='high')),
    dict(id='i11', bloom='L5', topic='Ética', statement='¿Qué criterio permite evaluar mejor una decisión pública?', options=['impacto, justicia y evidencia', 'popularidad inmediata', 'costo únicamente', 'autoridad del emisor'], correct=0, irt=dict(a=2.0, b=1.3, c=0.15), difficulty=5, cat=dict(area='ética', exposure_cap=0.15, demand='high')),
    dict(id='i12', bloom='L6', topic='Arte', statement='Propón el principio clave para crear una campaña visual coherente.', options=['unidad entre mensaje, color y audiencia', 'usar todos los colores', 'copiar una plantilla', 'evitar bocetos'], correct=0, irt=dict(a=2.3, b=1.8, c=0.15), difficulty=5, cat=dict(area='arte', exposure_cap=0.15, demand='high')),
]
A_HEADER = dict(m='IRT3PL', d='20260603', l='es', t='evaluación transversal', bd=[1, 1, 1, 1, 1, 1],
                cat=dict(theta_init=0, theta_min=-3, theta_max=3, se_stop=0.3, max_items=12, exposure_ctrl='SH'), k=4)

# ----------------------------------------------------------------------------
# q  — formative quiz = a + feedback, hint, objective  [es]
# ----------------------------------------------------------------------------
Q_EXT = [
    ('La fotosíntesis ocurre en los cloroplastos, donde está la clorofila.', 'Piensa en el pigmento verde.', 'Identificar organelos vegetales'),
    ('El pH mide la concentración de iones hidrógeno: acidez o basicidad.', 'Escala de 0 a 14.', 'Interpretar la escala de pH'),
    ('3x = 18 - 6 = 12, por lo tanto x = 4.', 'Despeja el término independiente.', 'Resolver ecuaciones lineales'),
    ('La caída combinó presión externa e inestabilidad interna prolongada.', 'No fue un evento único.', 'Analizar causas multifactoriales'),
    ('Un narrador no confiable exige contrastar su versión con otras evidencias del texto.', 'Sospecha del relato.', 'Evaluar la voz narrativa'),
    ('Validar esquemas y automatizar pruebas reduce errores en interfaces de programación.', 'Piensa en verificación temprana.', 'Diseñar controles de calidad'),
    ('El newton (N) es la unidad SI de fuerza.', 'Segunda ley de Newton.', 'Reconocer unidades SI'),
    ('Una cuenca es el territorio cuyas aguas drenan hacia un mismo río.', 'Piensa en el drenaje.', 'Definir unidades hidrográficas'),
    ('"Porque" introduce la causa de un hecho.', 'Relación causa-efecto.', 'Usar conectores lógicos'),
    ('Con precio mayor y demanda menor, la cantidad demandada disminuye.', 'Ley de la demanda.', 'Analizar el equilibrio de mercado'),
    ('Una decisión pública se evalúa por impacto, justicia y evidencia disponible.', 'Criterios múltiples.', 'Evaluar decisiones con criterios éticos'),
    ('Una campaña coherente mantiene unidad entre mensaje, color y audiencia.', 'Coherencia visual.', 'Proponer principios de diseño'),
]

# ----------------------------------------------------------------------------
# card — flashcards [es]
# ----------------------------------------------------------------------------
CARDS = [
    dict(id='c1', topic='Biología', front='¿Qué organelo realiza la fotosíntesis?', back='El cloroplasto, gracias a la clorofila.', hint='Pigmento verde', tags=['célula', 'plantas'], bloom='L1', ease=2.5),
    dict(id='c2', topic='Química', front='¿Qué mide el pH?', back='La acidez o basicidad de una solución (0-14).', hint='Iones H+', tags=['soluciones', 'ácidos'], bloom='L2', ease=2.5),
    dict(id='c3', topic='Matemática', front='Resuelve 3x+6=18', back='x = 4', hint=None, tags=['álgebra'], bloom='L3', ease=2.6),
    dict(id='c4', topic='Historia', front='Causas de la caída de Roma de Occidente', back='Presiones militares externas y crisis internas (económica, política).', hint='Multicausal', tags=['roma', 'antigüedad'], bloom='L4', ease=2.3),
    dict(id='c5', topic='Literatura', front='¿Qué es un narrador no confiable?', back='Un narrador cuya versión debe contrastarse con otras evidencias del texto.', hint=None, tags=['narrativa'], bloom='L5', ease=2.4),
    dict(id='c6', topic='Computación', front='Dos prácticas para reducir errores en una API', back='Validación de esquema y pruebas automatizadas.', hint='Verificación temprana', tags=['api', 'calidad', 'testing'], bloom='L6', ease=2.5),
    dict(id='c7', topic='Física', front='Unidad SI de fuerza', back='El newton (N) = kg·m/s².', hint=None, tags=['unidades'], bloom='L1', ease=2.7),
    dict(id='c8', topic='Geografía', front='Define cuenca hidrográfica', back='Territorio cuyas aguas drenan hacia un mismo río o lago.', hint='Drenaje', tags=['hidrografía'], bloom='L2', ease=2.5),
    dict(id='c9', topic='Comunicación', front='Conector de causa', back='"Porque" introduce la causa de un hecho.', hint=None, tags=['conectores', 'redacción'], bloom='L3', ease=2.6),
    dict(id='c10', topic='Economía', front='Sube el precio y baja la demanda: ¿qué pasa?', back='Disminuye la cantidad demandada.', hint='Ley de la demanda', tags=['mercado'], bloom='L4', ease=2.4),
    dict(id='c11', topic='Ética', front='Criterios para evaluar una decisión pública', back='Impacto, justicia y evidencia.', hint=None, tags=['ética', 'política'], bloom='L5', ease=2.3),
    dict(id='c12', topic='Arte', front='Principio de una campaña visual coherente', back='Unidad entre mensaje, color y audiencia.', hint='Coherencia', tags=['diseño', 'comunicación'], bloom='L6', ease=2.4),
]
CARD_HEADER = dict(d='20260603', l='es', t='repaso transversal', src='clase-64')

# ----------------------------------------------------------------------------
# sum — microlesson summary segments [es]
# ----------------------------------------------------------------------------
SUMS = [
    dict(id='s1', t_start=0, t_end=180, title='Introducción a la célula', summary='La célula es la unidad básica de la vida; se distinguen procariotas y eucariotas.', keywords=['célula', 'procariota', 'eucariota'], bloom='L1'),
    dict(id='s2', t_start=180, t_end=420, title='Organelos y funciones', summary='Mitocondria produce energía; el cloroplasto realiza la fotosíntesis; el núcleo guarda el ADN.', keywords=['mitocondria', 'cloroplasto', 'núcleo'], bloom='L2'),
    dict(id='s3', t_start=420, t_end=600, title='Membrana plasmática', summary='La membrana regula el intercambio de sustancias mediante transporte pasivo y activo.', keywords=['membrana', 'transporte'], bloom='L2'),
    dict(id='s4', t_start=600, t_end=840, title='Fotosíntesis: fase luminosa', summary='La luz excita la clorofila y se produce ATP y NADPH liberando oxígeno.', keywords=['ATP', 'NADPH', 'clorofila'], bloom='L3'),
    dict(id='s5', t_start=840, t_end=1080, title='Fotosíntesis: ciclo de Calvin', summary='El CO2 se fija en azúcares usando el ATP y NADPH de la fase luminosa.', keywords=['Calvin', 'CO2', 'glucosa'], bloom='L3'),
    dict(id='s6', t_start=1080, t_end=1320, title='Respiración celular', summary='La glucosa se oxida en glucólisis, ciclo de Krebs y cadena de transporte para obtener ATP.', keywords=['glucólisis', 'Krebs', 'ATP'], bloom='L3'),
    dict(id='s7', t_start=1320, t_end=1500, title='Comparación fotosíntesis y respiración', summary='Procesos complementarios: uno almacena energía en glucosa, el otro la libera.', keywords=['comparación', 'energía'], bloom='L4'),
    dict(id='s8', t_start=1500, t_end=1740, title='División celular: mitosis', summary='La mitosis produce dos células idénticas en profase, metafase, anafase y telofase.', keywords=['mitosis', 'ciclo celular'], bloom='L2'),
    dict(id='s9', t_start=1740, t_end=1980, title='Meiosis y variabilidad', summary='La meiosis reduce el número cromosómico a la mitad y genera variabilidad genética.', keywords=['meiosis', 'gametos', 'variabilidad'], bloom='L4'),
    dict(id='s10', t_start=1980, t_end=2160, title='Errores frecuentes', summary='Confundir mitosis con meiosis y atribuir la fotosíntesis a la mitocondria.', keywords=['errores', 'repaso'], bloom='L5'),
    dict(id='s11', t_start=2160, t_end=2400, title='Aplicaciones biotecnológicas', summary='Cultivos celulares y edición genética aprovechan el conocimiento de la célula.', keywords=['biotecnología', 'CRISPR'], bloom='L6'),
    dict(id='s12', t_start=2400, t_end=2520, title='Cierre y síntesis', summary='Recapitulación de estructuras, procesos energéticos y división celular.', keywords=['síntesis'], bloom='L2'),
]
SUM_HEADER = dict(d='20260603', l='es', t='Biología celular', src='clase-64', dur=2520)

# ----------------------------------------------------------------------------
# map — concept map edges [es]
# ----------------------------------------------------------------------------
MAPS = [
    dict(src='célula', rel='has_part', dst='núcleo', weight=0.9, evidence='s2'),
    dict(src='célula', rel='has_part', dst='mitocondria', weight=0.9, evidence='s2'),
    dict(src='célula', rel='has_part', dst='membrana plasmática', weight=0.85, evidence='s3'),
    dict(src='cloroplasto', rel='performs', dst='fotosíntesis', weight=0.95, evidence='s4'),
    dict(src='fotosíntesis', rel='has_part', dst='fase luminosa', weight=0.9, evidence='s4'),
    dict(src='fotosíntesis', rel='has_part', dst='ciclo de Calvin', weight=0.9, evidence='s5'),
    dict(src='fase luminosa', rel='produces', dst='ATP', weight=0.8, evidence='s4'),
    dict(src='mitocondria', rel='performs', dst='respiración celular', weight=0.95, evidence='s6'),
    dict(src='respiración celular', rel='produces', dst='ATP', weight=0.9, evidence='s6'),
    dict(src='fotosíntesis', rel='contrasts', dst='respiración celular', weight=0.7, evidence='s7'),
    dict(src='ciclo celular', rel='has_part', dst='mitosis', weight=0.85, evidence='s8'),
    dict(src='meiosis', rel='causes', dst='variabilidad genética', weight=0.8, evidence=None),
]
MAP_HEADER = dict(d='20260603', l='es', t='Biología celular', src='clase-64')

# ----------------------------------------------------------------------------
# r — rubric criteria [en]
# ----------------------------------------------------------------------------
RUBRIC = [
    dict(id='r1', dimension='Argument', criterion='Thesis clarity', levels=['absent or unclear', 'stated but vague', 'clear and focused', 'clear, focused and original'], weight=0.2, evidence='Introduction paragraph'),
    dict(id='r2', dimension='Argument', criterion='Use of evidence', levels=['no evidence', 'evidence unrelated to claims', 'relevant evidence', 'relevant, well-integrated evidence'], weight=0.2, evidence='Body paragraphs'),
    dict(id='r3', dimension='Argument', criterion='Counterarguments', levels=['ignored', 'mentioned', 'addressed', 'addressed and refuted'], weight=0.1, evidence='Discussion section'),
    dict(id='r4', dimension='Structure', criterion='Organization', levels=['disorganized', 'partially organized', 'logical order', 'logical order with transitions'], weight=0.1, evidence='Whole essay'),
    dict(id='r5', dimension='Structure', criterion='Paragraphing', levels=['no paragraphs', 'inconsistent', 'one idea per paragraph', 'purposeful paragraphing'], weight=0.05, evidence='Whole essay'),
    dict(id='r6', dimension='Language', criterion='Grammar and mechanics', levels=['frequent errors', 'several errors', 'few errors', 'error-free'], weight=0.1, evidence='Whole essay'),
    dict(id='r7', dimension='Language', criterion='Academic register', levels=['informal', 'mixed', 'mostly academic', 'consistently academic'], weight=0.05, evidence='Whole essay'),
    dict(id='r8', dimension='Sources', criterion='Citation accuracy', levels=['missing', 'inconsistent', 'mostly correct', 'correct APA/IEEE'], weight=0.1, evidence='Reference list'),
    dict(id='r9', dimension='Sources', criterion='Source quality', levels=['unreliable', 'mixed', 'reliable', 'peer-reviewed and recent'], weight=0.05, evidence='Reference list'),
    dict(id='r10', dimension='Critical thinking', criterion='Analysis depth', levels=['descriptive only', 'some analysis', 'consistent analysis', 'insightful analysis'], weight=0.03, evidence='Body paragraphs'),
    dict(id='r11', dimension='Critical thinking', criterion='Synthesis', levels=['none', 'lists ideas', 'connects ideas', 'builds new insight'], weight=0.01, evidence='Conclusion'),
    dict(id='r12', dimension='Presentation', criterion='Formatting', levels=['not followed', 'partially', 'mostly', 'fully compliant'], weight=0.01, evidence='Document'),
]
RUBRIC_HEADER = dict(d='20260603', l='en', t='Argumentative essay', k=4, scale='0-3')

# ----------------------------------------------------------------------------
# s — survey items (Likert) [en]
# ----------------------------------------------------------------------------
SURVEY = [
    dict(id='q1', construct='Usefulness', statement='The platform helps me review lectures faster.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=False),
    dict(id='q2', construct='Usefulness', statement='Generated quizzes reflect the lecture content.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=False),
    dict(id='q3', construct='Usefulness', statement='I would not use this tool for other courses.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=True),
    dict(id='q4', construct='Ease of use', statement='Uploading a lecture is simple.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=False),
    dict(id='q5', construct='Ease of use', statement='I needed help to understand the interface.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=True),
    dict(id='q6', construct='Ease of use', statement='The study resources are easy to find.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=False),
    dict(id='q7', construct='Engagement', statement='Adaptive quizzes keep me motivated.', scale=7, anchors=['never', 'always'], reverse=False),
    dict(id='q8', construct='Engagement', statement='I lose interest after a few questions.', scale=7, anchors=['never', 'always'], reverse=True),
    dict(id='q9', construct='Engagement', statement='I come back to review flashcards.', scale=7, anchors=['never', 'always'], reverse=False),
    dict(id='q10', construct='Trust', statement='The generated content is accurate.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=False),
    dict(id='q11', construct='Trust', statement='I double-check the answers with my notes.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=True),
    dict(id='q12', construct='Trust', statement='I trust the difficulty level assigned to me.', scale=5, anchors=['strongly disagree', 'strongly agree'], reverse=False),
]
SURVEY_HEADER = dict(d='20260603', l='en', t='Post-pilot satisfaction survey', k=2)

# ----------------------------------------------------------------------------
# code — programming exercises [en]
# ----------------------------------------------------------------------------
CODE = [
    dict(id='c1', bloom='L3', topic='lists', statement='Write a function maximum(xs) that returns the largest number in a non-empty list.', lang='python', tests=['maximum([2,8,3])==8', 'maximum([-1,-5])==-1'], expected='int or float', hints=['iterate once', 'track the best so far']),
    dict(id='c2', bloom='L3', topic='strings', statement='Write is_palindrome(s) ignoring case and spaces.', lang='python', tests=["is_palindrome('Anita lava la tina')", "not is_palindrome('hello')"], expected='bool', hints=['normalize first']),
    dict(id='c3', bloom='L2', topic='arithmetic', statement='Return the sum of the digits of a positive integer.', lang='python', tests=['digit_sum(1234)==10', 'digit_sum(7)==7'], expected='int', hints=[]),
    dict(id='c4', bloom='L4', topic='recursion', statement='Implement fib(n) iteratively with O(1) memory.', lang='python', tests=['fib(10)==55', 'fib(0)==0'], expected='int', hints=['two variables suffice']),
    dict(id='c5', bloom='L3', topic='dictionaries', statement='Count word frequencies in a text and return a dict.', lang='python', tests=["word_count('a b a')=={'a':2,'b':1}"], expected='dict', hints=['split on whitespace']),
    dict(id='c6', bloom='L5', topic='sorting', statement='Sort a list of (name, score) tuples by score descending, then name.', lang='python', tests=["rank([('b',1),('a',1),('c',2)])==[('c',2),('a',1),('b',1)]"], expected='list', hints=['use a key function']),
    dict(id='c7', bloom='L3', topic='arrays', statement='Return the second largest distinct element of an array.', lang='javascript', tests=['secondLargest([3,1,3,2])===2'], expected='number', hints=['deduplicate first']),
    dict(id='c8', bloom='L2', topic='conditionals', statement='Classify a temperature in Celsius as cold, mild or hot.', lang='javascript', tests=["classify(5)==='cold'", "classify(30)==='hot'"], expected='string', hints=[]),
    dict(id='c9', bloom='L4', topic='regex', statement='Validate an email address with a regular expression.', lang='javascript', tests=["isEmail('a@b.co')===true", "isEmail('a@b')===false"], expected='boolean', hints=['require a dot in the domain']),
    dict(id='c10', bloom='L5', topic='algorithms', statement='Implement binary search returning the index or -1.', lang='java', tests=['binarySearch(new int[]{1,3,5},5)==2', 'binarySearch(new int[]{1,3,5},4)==-1'], expected='int', hints=['halve the interval']),
    dict(id='c11', bloom='L6', topic='design', statement='Design a Stack class with push, pop and peek using an array.', lang='java', tests=['new Stack().push(1).pop()==1'], expected='class', hints=['track the top index', 'throw on empty pop']),
    dict(id='c12', bloom='L3', topic='sql', statement='Return the names of students with an average grade above 14.', lang='sql', tests=['rows==3'], expected='result set', hints=['GROUP BY student', 'HAVING AVG(grade)>14']),
]
CODE_HEADER = dict(d='20260603', l='en', t='Intro programming lab 3')

# ----------------------------------------------------------------------------
# tc — software test cases [en]
# ----------------------------------------------------------------------------
TESTS = [
    dict(id='TC-001', module='auth', title='Login with valid credentials', precondition='User registered and active', steps=['open /login', 'enter valid email and password', 'click Sign in'], expected='Dashboard is shown and session cookie is set', priority='high', type='functional', automated=True),
    dict(id='TC-002', module='auth', title='Login with wrong password', precondition='User registered', steps=['open /login', 'enter valid email and wrong password', 'click Sign in'], expected='Error message; no session created', priority='high', type='functional', automated=True),
    dict(id='TC-003', module='auth', title='Password reset email', precondition='User registered', steps=['open /reset', 'submit registered email'], expected='Reset email delivered within 60 s', priority='medium', type='integration', automated=False),
    dict(id='TC-004', module='courses', title='Create course', precondition='Logged-in student', steps=['open /courses/new', 'fill name, period and topics', 'save'], expected='Course appears in dashboard', priority='high', type='functional', automated=True),
    dict(id='TC-005', module='lessons', title='Upload audio lecture', precondition='Course exists; credits available', steps=['open /api/new', 'select course and upload 20 MB mp3', 'confirm credit estimate'], expected='LessonJob created with status queued', priority='high', type='functional', automated=True),
    dict(id='TC-006', module='lessons', title='Reject unsupported file', precondition='Course exists', steps=['open /api/new', 'upload .exe file'], expected='Validation error; nothing stored', priority='medium', type='security', automated=True),
    dict(id='TC-007', module='pipeline', title='Transcription completes', precondition='Job queued; Whisper available', steps=['run worker', 'wait for stage transcribe'], expected='Transcript stored; stage advances to generate', priority='high', type='integration', automated=True),
    dict(id='TC-008', module='pipeline', title='.mini bank parses', precondition='Generation stage finished', steps=['fetch job output', 'run parser'], expected='All records valid; n equals record lines', priority='high', type='functional', automated=True),
    dict(id='TC-009', module='pipeline', title='Incoherent items repaired', precondition='Bank with declarative items', steps=['run coherence filter', 'run repair'], expected='Items repaired or excluded with trace', priority='medium', type='functional', automated=True),
    dict(id='TC-010', module='quiz', title='Adaptive quiz updates theta', precondition='Lesson ready; profile exists', steps=['start quiz with 6 items', 'answer all'], expected='theta and SE updated; XP awarded', priority='high', type='functional', automated=True),
    dict(id='TC-011', module='quiz', title='Quiz under load', precondition='50 concurrent students', steps=['start 50 quizzes', 'answer concurrently'], expected='p95 latency below 2 s; no errors', priority='medium', type='performance', automated=False),
    dict(id='TC-012', module='admin', title='Credit ledger consistency', precondition='Several jobs processed', steps=['open admin ledger', 'sum entries'], expected='Ledger total equals profile balance', priority='low', type='functional', automated=False),
]
TESTS_HEADER = dict(d='20260603', l='en', t='SIMA release 1.2 regression', proj='SIMA')

# ----------------------------------------------------------------------------
# log — service events / incidents [en]
# ----------------------------------------------------------------------------
LOGS = [
    dict(ts='2026-06-03T08:00:01Z', level='INFO', service='web', code='HTTP200', message='GET /dashboard served', tags=['user:26'], trace='t-1001', duration_ms=42),
    dict(ts='2026-06-03T08:00:05Z', level='INFO', service='worker', code='JOB_START', message='LessonJob 64 started stage transcribe', tags=['job:64', 'stage:transcribe'], trace='t-1002', duration_ms=None),
    dict(ts='2026-06-03T08:02:11Z', level='WARN', service='worker', code='ASR_SLOW', message='Whisper took longer than budget', tags=['job:64'], trace='t-1002', duration_ms=126000),
    dict(ts='2026-06-03T08:02:12Z', level='INFO', service='worker', code='JOB_STAGE', message='stage generate started with 16 chunks', tags=['job:64', 'stage:generate'], trace='t-1002', duration_ms=None),
    dict(ts='2026-06-03T08:05:40Z', level='ERROR', service='llm', code='NUL_CHAR', message='NUL character in model output; sanitized', tags=['job:64', 'chunk:7'], trace='t-1002', duration_ms=None),
    dict(ts='2026-06-03T08:05:41Z', level='INFO', service='worker', code='MINI_PARSE', message='150 records parsed, 22 flagged incoherent', tags=['job:64'], trace='t-1002', duration_ms=310),
    dict(ts='2026-06-03T08:06:02Z', level='INFO', service='verify', code='WEB_CTX', message='6 queries, 4 results, 2 usable sources', tags=['job:64'], trace='t-1002', duration_ms=8900),
    dict(ts='2026-06-03T08:06:30Z', level='ERROR', service='llm', code='CTX_OVERFLOW', message='verification prompt exceeds context; truncated', tags=['job:64'], trace='t-1002', duration_ms=None),
    dict(ts='2026-06-03T08:07:00Z', level='INFO', service='worker', code='JOB_DONE', message='LessonJob 64 finished', tags=['job:64'], trace='t-1002', duration_ms=419000),
    dict(ts='2026-06-03T08:10:15Z', level='WARN', service='web', code='HTTP404', message='GET /clase/999/ not found', tags=['user:12'], trace='t-1003', duration_ms=5),
    dict(ts='2026-06-03T08:12:00Z', level='CRITICAL', service='llm', code='ENDPOINT_DOWN', message='local API base unreachable; retry scheduled', tags=['endpoint:8003'], trace='t-1004', duration_ms=None),
    dict(ts='2026-06-03T08:12:30Z', level='INFO', service='llm', code='ENDPOINT_UP', message='local API base healthy after retry', tags=['endpoint:8003'], trace='t-1004', duration_ms=None),
]
LOGS_HEADER = dict(d='20260603', env='staging', host='sima-app-01')

# ----------------------------------------------------------------------------
# ner — entity annotations [en]
# ----------------------------------------------------------------------------
NER = [
    dict(doc='d1', start=0, end=17, text='Whisper', type='PRODUCT', conf=0.98),
    dict(doc='d1', start=25, end=31, text='OpenAI', type='ORG', conf=0.99),
    dict(doc='d1', start=60, end=64, text='2023', type='DATE', conf=0.97),
    dict(doc='d2', start=4, end=10, text='Django', type='PRODUCT', conf=0.96),
    dict(doc='d2', start=30, end=40, text='PostgreSQL', type='PRODUCT', conf=0.95),
    dict(doc='d3', start=0, end=4, text='Lima', type='LOC', conf=0.99),
    dict(doc='d3', start=6, end=10, text='Perú', type='LOC', conf=0.99),
    dict(doc='d3', start=45, end=48, text='UPC', type='ORG', conf=0.93),
    dict(doc='d4', start=12, end=30, text='Item Response Theory', type='CONCEPT', conf=0.91),
    dict(doc='d4', start=35, end=38, text='CAT', type='CONCEPT', conf=0.88),
    dict(doc='d5', start=0, end=12, text='Adrián Palma', type='PERSON', conf=0.97),
    dict(doc='d5', start=17, end=31, text='Erick Palomino', type='PERSON', conf=0.97),
]
NER_HEADER = dict(d='20260603', l='en', model='ner-base-2026', schema='ontonotes-lite')

# ----------------------------------------------------------------------------
# cat — product catalog [en]
# ----------------------------------------------------------------------------
CATALOG = [
    dict(sku='SKU-1001', name='Wireless headset', category='audio', price=89.9, currency='USD', stock=120, tags=['bluetooth', 'noise-cancelling'], rating=4.5),
    dict(sku='SKU-1002', name='USB-C hub 7-in-1', category='accessories', price=39.99, currency='USD', stock=300, tags=['usb-c', 'hdmi'], rating=4.2),
    dict(sku='SKU-1003', name='Mechanical keyboard', category='input', price=129.0, currency='USD', stock=45, tags=['mechanical', 'rgb', 'wired'], rating=4.7),
    dict(sku='SKU-1004', name='27" 4K monitor', category='display', price=349.0, currency='USD', stock=18, tags=['4k', 'ips'], rating=4.6),
    dict(sku='SKU-1005', name='Laptop stand', category='accessories', price=25.5, currency='USD', stock=500, tags=['aluminium'], rating=4.1),
    dict(sku='SKU-1006', name='Webcam 1080p', category='video', price=59.0, currency='USD', stock=80, tags=['1080p', 'autofocus'], rating=3.9),
    dict(sku='SKU-1007', name='Micrófono condensador', category='audio', price=249.0, currency='PEN', stock=22, tags=['usb', 'cardioide'], rating=4.4),
    dict(sku='SKU-1008', name='Mouse ergonómico', category='input', price=119.0, currency='PEN', stock=64, tags=['ergonómico', 'inalámbrico'], rating=4.3),
    dict(sku='SKU-1009', name='SSD NVMe 1 TB', category='storage', price=99.0, currency='USD', stock=150, tags=['nvme', 'pcie4'], rating=4.8),
    dict(sku='SKU-1010', name='Router Wi-Fi 6', category='network', price=79.0, currency='USD', stock=33, tags=['wifi6', 'mesh'], rating=4.0),
    dict(sku='SKU-1011', name='Cable HDMI 2.1 2 m', category='accessories', price=15.9, currency='USD', stock=900, tags=['hdmi', '8k'], rating=None),
    dict(sku='SKU-1012', name='Silla de oficina', category='furniture', price=899.0, currency='PEN', stock=7, tags=['ergonómica', 'malla'], rating=4.2),
]
CATALOG_HEADER = dict(d='20260603', store='campus-shop', cur='USD')

# ----------------------------------------------------------------------------
# cls — text classification outputs (multi-label) [en]
# ----------------------------------------------------------------------------
LABELS = ['question', 'feedback', 'bug', 'request', 'praise', 'other']
CLS = [
    dict(id='m1', text='The quiz froze after question 4, is that a known issue?', labels=LABELS, selected=[0, 2], conf=0.91, rationale='reports a malfunction and asks'),
    dict(id='m2', text='Great flashcards, they saved my week!', labels=LABELS, selected=[4], conf=0.97, rationale=None),
    dict(id='m3', text='Could you add export to Anki?', labels=LABELS, selected=[3], conf=0.94, rationale='feature request'),
    dict(id='m4', text='Transcription missed the last ten minutes of the lecture.', labels=LABELS, selected=[2], conf=0.9, rationale=None),
    dict(id='m5', text='How is my level computed?', labels=LABELS, selected=[0], conf=0.95, rationale=None),
    dict(id='m6', text='The map view is confusing but the summaries are excellent.', labels=LABELS, selected=[1, 4], conf=0.82, rationale='mixed sentiment'),
    dict(id='m7', text='Please support PDF slides as input.', labels=LABELS, selected=[3], conf=0.93, rationale=None),
    dict(id='m8', text='Nothing to report.', labels=LABELS, selected=[5], conf=0.7, rationale=None),
    dict(id='m9', text='Why does the same question repeat twice?', labels=LABELS, selected=[0, 2], conf=0.86, rationale='possible exposure-control bug'),
    dict(id='m10', text='Love the adaptive difficulty, keep it up.', labels=LABELS, selected=[1, 4], conf=0.9, rationale=None),
    dict(id='m11', text='Credits were deducted twice for one upload.', labels=LABELS, selected=[2], conf=0.96, rationale='billing bug'),
    dict(id='m12', text='Can I share a class with a friend?', labels=LABELS, selected=[0, 3], conf=0.88, rationale=None),
]
CLS_HEADER = dict(d='20260603', l='en', model='cls-support-2026', k=6)

# ----------------------------------------------------------------------------
# us — user stories [en]
# ----------------------------------------------------------------------------
STORIES = [
    dict(id='US-01', epic='EP-01', role='student', goal='upload a recorded lecture', benefit='I can study it later in small pieces', acceptance=['audio up to 200 MB accepted', 'credit estimate shown before confirming'], sp=5, priority='must'),
    dict(id='US-02', epic='EP-01', role='student', goal='paste a transcript instead of audio', benefit='I can skip transcription when I already have notes', acceptance=['plain text accepted', 'same pipeline from generation stage'], sp=3, priority='should'),
    dict(id='US-03', epic='EP-02', role='student', goal='see the generated question bank', benefit='I can check what will be asked', acceptance=['items listed with Bloom level', 'download as JSON'], sp=3, priority='must'),
    dict(id='US-04', epic='EP-02', role='system', goal='generate items in .mini', benefit='token cost per bank drops', acceptance=['n matches record lines', 'parser reports zero errors'], sp=8, priority='must'),
    dict(id='US-05', epic='EP-03', role='reviewer', goal='flag incoherent items', benefit='students never see broken questions', acceptance=['declarative stems detected', 'repair trace stored'], sp=5, priority='must'),
    dict(id='US-06', epic='EP-03', role='reviewer', goal='verify facts against sources', benefit='the bank is trustworthy', acceptance=['web or EduQG context attached', 'report lists weak items'], sp=8, priority='should'),
    dict(id='US-07', epic='EP-04', role='student', goal='keep my progress per course', benefit='I know what to review next', acceptance=['theta stored per profile', 'dashboard shows level'], sp=5, priority='must'),
    dict(id='US-08', epic='EP-05', role='student', goal='take an adaptive quiz', benefit='questions match my level', acceptance=['next item chosen by information', 'stops at SE threshold'], sp=8, priority='must'),
    dict(id='US-09', epic='EP-05', role='student', goal='review flashcards', benefit='I retain key concepts', acceptance=['cards derived from the bank', 'spaced repetition schedule'], sp=5, priority='should'),
    dict(id='US-10', epic='EP-05', role='student', goal='see a concept map', benefit='I understand how topics connect', acceptance=['edges from the bank', 'clickable nodes'], sp=3, priority='could'),
    dict(id='US-11', epic='EP-05', role='student', goal='solve matching and cloze exercises', benefit='I practise in different ways', acceptance=['two exercise types', 'scored instantly'], sp=5, priority='could'),
    dict(id='US-12', epic='EP-04', role='admin', goal='audit credit consumption', benefit='billing is transparent', acceptance=['ledger per user', 'export CSV'], sp=3, priority='should'),
]
STORIES_HEADER = dict(d='20260603', l='en', t='SIMA backlog', sprint='S3')

# ----------------------------------------------------------------------------
BASE: Dict[str, Dict[str, Any]] = {
    'a': {'header': A_HEADER, 'records_key': 'items', 'records': A_ITEMS, 'id': 'id'},
    'q': {'header': dict(A_HEADER, t='cuestionario formativo'), 'records_key': 'items',
          'records': [dict(it, feedback=fb, hint=h, objective=o) for it, (fb, h, o) in zip(A_ITEMS, Q_EXT)], 'id': 'id'},
    'card': {'header': CARD_HEADER, 'records_key': 'cards', 'records': CARDS, 'id': 'id'},
    'sum': {'header': SUM_HEADER, 'records_key': 'segments', 'records': SUMS, 'id': 'id'},
    'map': {'header': MAP_HEADER, 'records_key': 'edges', 'records': MAPS, 'id': None},
    'r': {'header': RUBRIC_HEADER, 'records_key': 'criteria', 'records': RUBRIC, 'id': 'id'},
    's': {'header': SURVEY_HEADER, 'records_key': 'items', 'records': SURVEY, 'id': 'id'},
    'code': {'header': CODE_HEADER, 'records_key': 'exercises', 'records': CODE, 'id': 'id'},
    'tc': {'header': TESTS_HEADER, 'records_key': 'cases', 'records': TESTS, 'id': 'id'},
    'log': {'header': LOGS_HEADER, 'records_key': 'events', 'records': LOGS, 'id': None},
    'ner': {'header': NER_HEADER, 'records_key': 'entities', 'records': NER, 'id': None},
    'cat': {'header': CATALOG_HEADER, 'records_key': 'products', 'records': CATALOG, 'id': 'sku'},
    'cls': {'header': CLS_HEADER, 'records_key': 'messages', 'records': CLS, 'id': 'id'},
    'us': {'header': STORIES_HEADER, 'records_key': 'stories', 'records': STORIES, 'id': 'id'},
}


def base(prefix: str) -> Dict[str, Any]:
    b = BASE[prefix]
    return {'header': copy.deepcopy(b['header']), b['records_key']: copy.deepcopy(b['records'])}


def expand(prefix: str, n: int) -> Dict[str, Any]:
    """Cycle the 12 base records assigning fresh ids (same protocol as TP1)."""
    b = BASE[prefix]
    recs = b['records']
    out: List[Dict[str, Any]] = []
    for i in range(n):
        r = copy.deepcopy(recs[i % len(recs)])
        idk = b['id']
        if idk:
            stem = ''.join(ch for ch in str(recs[0][idk]) if not ch.isdigit()).rstrip('-') or 'r'
            r[idk] = f"{stem}{i + 1}" if not stem.endswith('-') else f"{stem}{i + 1:03d}"
            if str(recs[0][idk]).startswith('TC-'):
                r[idk] = f"TC-{i + 1:03d}"
            elif str(recs[0][idk]).startswith('US-'):
                r[idk] = f"US-{i + 1:02d}"
            elif str(recs[0][idk]).startswith('SKU-'):
                r[idk] = f"SKU-{1000 + i + 1}"
        elif prefix == 'log':
            r['trace'] = f"t-{1000 + i + 1}"
        elif prefix == 'ner':
            r['doc'] = f"d{i // 3 + 1}"
        out.append(r)
    hdr = copy.deepcopy(b['header'])
    if prefix in ('a', 'q') and 'cat' in hdr:
        hdr['cat']['max_items'] = n
    return {'header': hdr, b['records_key']: out}
