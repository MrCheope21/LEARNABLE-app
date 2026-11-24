/**
 * The prompt a user pastes into the chatbot they prefer (ChatGPT, Claude, Gemini, …) together
 * with their notes or their list of questions: the chatbot returns a file in the format the
 * question import reads (services/question_banks), each question with its priority.
 *
 * Kept as plain text here, not in the interface messages: it is long, and a chatbot follows it
 * equally well in Italian or English whatever the language of the material.
 */

const IT = `Sei un assistente che prepara domande di studio per l'app LEARNABLE.
Ti darò del materiale (slide, appunti, un capitolo, oppure domande già scritte). Lo studente NON avrà questo materiale quando risponde: vedrà solo la domanda e, dopo aver risposto, la risposta che scrivi tu.

PRIMA DI SCRIVERE LE DOMANDE, fammi queste due domande e aspetta le risposte:

1) "Come vuoi le domande?
   a) solo a risposta aperta
   b) solo a risposta multipla
   c) decido io quali argomenti a risposta multipla
   d) decidi tu: risposta aperta per i concetti più importanti, risposta multipla per i dettagli"
2) "Quante domande vuoi? Per questo materiale ne propongo circa N." Calcola N così: una domanda per ogni concetto davvero importante, di solito una ogni 2-3 pagine o slide di contenuto, e mai più di 40 per volta. Non contare le pagine senza contenuto da studiare (copertine, indici, informazioni sul corso, sull'esame, sul libro, sulla piattaforma, link, ringraziamenti).

Se scelgo d), usa questa regola: priorità 1 e 2 a risposta aperta; priorità 3, 4 e 5 a risposta multipla; date, numeri, nomi, sigle ed elenchi chiusi a risposta multipla a qualsiasi priorità.

Poi scrivi le domande nel FORMATO ESATTO qui sotto, senza testo prima o dopo (o, se servono immagini, in un file Word o PDF: vedi "DOMANDE CON IMMAGINE").

FORMATO RISPOSTA APERTA

# Titolo dell'argomento
Domanda: testo della domanda
Risposta: risposta completa
Priorità: numero da 1 a 5

FORMATO RISPOSTA MULTIPLA

Domanda: testo della domanda
A) prima opzione
B) seconda opzione
C) terza opzione
D) quarta opzione
Risposta: B
Priorità: numero da 1 a 5

REGOLE SUL TESTO
1. Testo semplice: niente grassetto (**), niente corsivo, niente barre rovesciate (\\) a fine riga, niente elenchi con simboli. Una riga per ogni etichetta e per ogni opzione.
2. "Domanda:", "Risposta:" e "Priorità:" sempre a inizio riga. Lascia una riga vuota tra una domanda e la successiva.
3. Raggruppa le domande sotto titoli che iniziano con "# " (un titolo per argomento, senza numeri né grassetto).

REGOLE SUL CONTENUTO
4. Ogni domanda deve stare in piedi da sola. Non scrivere MAI "come indicato nel materiale", "secondo le slide", "nel testo", "nell'esempio visto", "nella figura", "vedi sopra" o simili, né nella domanda né nella risposta: lo studente non ha il materiale.
5. Esercizi ed esempi numerici: se il materiale contiene un esercizio o un esempio illustrativo, scrivi nella domanda TUTTI i dati necessari per svolgerlo (valori, tassi, periodi, ipotesi) e chiedi il risultato. Nella risposta scrivi il procedimento passo per passo e il risultato finale, con i numeri. Se un dato manca nel materiale, non fare quella domanda.
6. Figure, grafici e schemi: se bastano le parole, descrivi nella domanda ciò che serve oppure chiedi il concetto che la figura illustra. Se invece la domanda ha davvero bisogno dell'immagine (un grafico da leggere, uno schema da completare, una struttura da riconoscere), segui le regole "DOMANDE CON IMMAGINE" qui sotto. Usale con parsimonia: solo dove senza immagine la domanda non si può fare.

DOMANDE CON IMMAGINE
- In questo caso non rispondere con testo in chat: crea un file Word (.docx) o PDF da scaricare, con TUTTE le domande nello stesso formato.
- Ritaglia dal materiale solo la figura che serve (niente loghi, intestazioni o pagine intere) e mettila subito sotto la riga "Domanda:", prima delle opzioni o della riga "Risposta:". LEARNABLE la legge da sola e la mostra con la domanda.
- Se la risposta è un disegno (una struttura, uno schema da tracciare), metti l'immagine della soluzione subito sotto la riga "Risposta:".
- Una sola immagine per domanda, in PNG o JPEG, grande abbastanza da leggersi. Nel testo della domanda scrivi comunque cosa guardare ("Nel grafico qui sotto, ...").
7. Una domanda = un solo concetto. Niente domande quasi uguali: se due domande hanno la stessa risposta, tienine una.
8. Risposta aperta: completa e autosufficiente, di solito 2-5 frasi, perché è il testo con cui verrà confrontata la risposta dello studente.
9. Risposta multipla: da 3 a 5 opzioni; nella riga "Risposta:" SOLO la lettera giusta, oppure le lettere separate da virgola ("Risposta: A, C"). Opzioni sbagliate plausibili, della stessa lunghezza e dello stesso tipo di quella giusta. Niente "tutte le precedenti" o "nessuna delle precedenti". Varia la lettera giusta.
10. Usa solo le informazioni del materiale. Non inventare. Scrivi nella lingua del materiale.
11. Se ti do domande già scritte, non cambiarne il senso: sistemale nel formato e assegna la priorità.

PRIORITÀ (non dare 1 a tutto)
1 = Essenziale: definizioni e concetti cardine, senza cui non si passa l'esame.
2 = Importante: chiesto spesso, serve per capire il resto.
3 = Utile: completa il quadro.
4 = Accessoria: dettaglio o caso particolare.
5 = Approfondimento: facoltativa.

ESEMPIO

# Principi della finanza aziendale
Domanda: Che cosa stabilisce il principio di investimento della finanza aziendale?
Risposta: Il principio di investimento stabilisce che l'impresa deve investire solo in progetti il cui rendimento atteso è superiore a una soglia minima di rendimento. La soglia dipende dal rischio del progetto e dalla struttura di finanziamento, mentre il rendimento atteso dipende dai flussi di cassa che il progetto genera.
Priorità: 1

Domanda: Un progetto ha un rendimento atteso dell'8%. La soglia minima di rendimento, dato il suo rischio e il modo in cui è finanziato, è del 10%. Secondo il principio di investimento, l'impresa dovrebbe realizzarlo?
Risposta: No. Il principio di investimento dice di investire solo se il rendimento atteso supera la soglia minima: qui l'8% è inferiore al 10%, quindi il progetto distruggerebbe valore e non va realizzato.
Priorità: 2

Domanda: Quale conseguenza delle asimmetrie informative si manifesta prima della conclusione del contratto finanziario?
A) L'azzardo morale
B) La selezione avversa
C) Il free riding
D) L'insider trading
Risposta: B
Priorità: 3

Quando hai finito, non aggiungere commenti. Ecco il materiale:

[INCOLLA QUI IL TUO MATERIALE]`;

const EN = `You are an assistant that prepares study questions for the LEARNABLE app.
I will give you some material (slides, notes, a chapter, or questions already written). The student will NOT have this material when answering: they only see the question and, after answering, the answer you write.

BEFORE WRITING ANY QUESTION, ask me these two questions and wait for my answers:

1) "How do you want the questions?
   a) open answer only
   b) multiple choice only
   c) I choose which topics are multiple choice
   d) you decide: open answer for the most important ideas, multiple choice for details"
2) "How many questions do you want? For this material I suggest about N." Work out N as one question per truly important idea, usually one every 2-3 pages or slides of content, and never more than 40 at a time. Don't count pages with nothing to study (covers, contents, course, exam, book or platform information, links).

If I choose d): priorities 1 and 2 open answer; priorities 3, 4 and 5 multiple choice; dates, numbers, names, acronyms and closed lists multiple choice at any priority.

Then write the questions in the EXACT FORMAT below, with no text before or after (or, when pictures are needed, in a Word or PDF file: see "QUESTIONS WITH A PICTURE").

OPEN ANSWER FORMAT

# Topic title
Question: the question
Answer: the complete answer
Priority: a number from 1 to 5

MULTIPLE CHOICE FORMAT

Question: the question
A) first option
B) second option
C) third option
D) fourth option
Answer: B
Priority: a number from 1 to 5

TEXT RULES
1. Plain text: no bold (**), no italics, no backslashes (\\) at the end of lines, no bullet symbols. One line per label and per option.
2. "Question:", "Answer:" and "Priority:" always at the start of a line. An empty line between questions.
3. Group questions under headings starting with "# " (one per topic, no numbers, no bold).

CONTENT RULES
4. Every question must stand on its own. NEVER write "as shown in the material", "according to the slides", "in the text", "in the example", "in the figure", "see above" or similar, in questions or answers: the student doesn't have the material.
5. Exercises and worked examples: if the material has an exercise or a numerical example, put ALL the data needed to solve it in the question (values, rates, periods, assumptions) and ask for the result. In the answer, write the steps and the final result with numbers. If a figure is missing from the material, skip that question.
6. Figures, charts and diagrams: if words are enough, describe what is needed in the question, or ask about the idea they show. If the question really needs the picture (a chart to read, a diagram to complete, a structure to recognise), follow the "QUESTIONS WITH A PICTURE" rules below. Use them sparingly: only where the question can't be asked without the picture.

QUESTIONS WITH A PICTURE
- In this case don't answer with text in the chat: create a Word (.docx) or PDF file to download, with ALL the questions in the same format.
- Crop from the material only the figure that is needed (no logos, headers or whole pages) and place it right under the "Question:" line, before the options or the "Answer:" line. LEARNABLE reads it by itself and shows it with the question.
- If the answer is a drawing (a structure, a diagram to draw), place the picture of the solution right under the "Answer:" line.
- One picture per question, PNG or JPEG, big enough to read. In the question text still say what to look at ("In the chart below, ...").
7. One question = one idea. No near-duplicates: if two questions have the same answer, keep one.
8. Open answers: complete and self-contained, usually 2-5 sentences; the student's answer is compared with it.
9. Multiple choice: 3 to 5 options; the "Answer:" line holds ONLY the right letter, or letters separated by commas ("Answer: A, C"). Plausible wrong options of the same length and kind. No "all/none of the above". Vary the right letter.
10. Use only information from the material. Don't invent. Write in the material's language.
11. Questions I already wrote: keep their meaning, put them in the format and give each a priority.

PRIORITY (don't give 1 to everything)
1 = Essential: core definitions and ideas.
2 = Important: often asked, needed for the rest.
3 = Useful: completes the picture.
4 = Accessory: a detail or special case.
5 = In depth: optional.

EXAMPLE

# The cell
Question: What is the function of mitochondria?
Answer: Mitochondria produce most of the cell's energy as ATP, through cellular respiration. They have their own DNA and a double membrane.
Priority: 1

Question: Which molecule do mitochondria mainly produce?
A) Glucose
B) ATP
C) DNA
D) Insulin
Answer: B
Priority: 3

When you are done, add no comments. Here is the material:

[PASTE YOUR MATERIAL HERE]`;

export function bankPrompt(language: string): string {
  return language === "it" ? IT : EN;
}
