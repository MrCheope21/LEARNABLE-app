/**
 * The prompt a user pastes into the chatbot they prefer (ChatGPT, Claude, Gemini, …) together
 * with their notes or their list of questions: the chatbot returns a file in the format the
 * question import reads (services/question_banks), each question with its priority.
 *
 * Kept as plain text here, not in the interface messages: it is long, and a chatbot follows it
 * equally well in Italian or English whatever the language of the material.
 */

const IT = `Sei un assistente che prepara domande di studio per l'app Recallable.
Ti darò del materiale (appunti, un capitolo, oppure una lista di domande già scritte). Trasformalo in un elenco di domande e risposte nel FORMATO ESATTO qui sotto, senza aggiungere altro testo prima o dopo.

FORMATO (rispettalo alla lettera):

# Titolo dell'argomento
Domanda: testo della domanda
Risposta: risposta completa
Priorità: numero da 1 a 5

REGOLE
1. Ogni domanda inizia con "Domanda:" a capo riga; la sua risposta con "Risposta:" a capo riga; poi una riga "Priorità:" con un solo numero.
2. Raggruppa le domande sotto titoli che iniziano con "# " (un titolo per argomento). Lascia una riga vuota tra una domanda e la successiva.
3. Una domanda = un solo concetto. Se una domanda ne contiene due, dividila.
4. La risposta deve essere completa e autosufficiente (di solito 2-6 frasi): è il testo con cui verrà confrontata la risposta dello studente. Niente "vedi sopra", niente elenchi puntati con simboli strani: frasi normali.
5. Usa SOLO le informazioni del materiale che ti do. Non inventare. Se nel materiale manca la risposta a una domanda, scrivi "Risposta: [DA COMPLETARE]".
6. Scrivi nella stessa lingua del materiale.
7. Se ti do domande già scritte, non cambiarne il senso: sistemale nel formato e assegna la priorità.
8. Domande a risposta multipla: se il materiale ne contiene, o se te le chiedo, scrivi le opzioni su righe separate sotto la domanda, ciascuna che inizia con una lettera e una parentesi ("A) ", "B) ", …, da 2 a 8 opzioni), e nella riga "Risposta:" metti SOLO la lettera giusta (oppure le lettere giuste, separate da virgola: "Risposta: A, C"). Le opzioni sbagliate devono essere plausibili, non ovviamente false. Non usare mai "A:" o "D:" con i due punti per le opzioni.

PRIORITÀ (scegli con cura, non dare 1 a tutto):
1 = Essenziale: senza questo non si passa l'esame; definizioni e concetti cardine.
2 = Importante: viene chiesto spesso; serve per capire il resto.
3 = Utile: completa il quadro; buona da sapere.
4 = Accessoria: un dettaglio o un caso particolare, non centrale.
5 = Approfondimento: facoltativa, per chi vuole il massimo.

ESEMPIO

# L'imprenditore
Domanda: Chi è imprenditore secondo il codice civile?
Risposta: È imprenditore chi esercita professionalmente un'attività economica organizzata al fine della produzione o dello scambio di beni o di servizi (art. 2082 c.c.).
Priorità: 1

Domanda: Quali sono i requisiti dell'attività d'impresa?
Risposta: I requisiti sono l'attività economica, l'organizzazione, la professionalità e il fine della produzione o dello scambio di beni o servizi.
Priorità: 2

Domanda: Quale articolo del codice civile definisce l'imprenditore?
A) Art. 2082
B) Art. 2135
C) Art. 2195
D) Art. 1321
Risposta: A
Priorità: 2

Quando hai finito, non aggiungere commenti. Ecco il materiale:

[INCOLLA QUI IL TUO MATERIALE]`;

const EN = `You are an assistant that prepares study questions for the Recallable app.
I will give you some material (notes, a chapter, or a list of questions already written). Turn it into a list of questions and answers in the EXACT FORMAT below, with no other text before or after.

FORMAT (follow it to the letter):

# Topic title
Question: the text of the question
Answer: the complete answer
Priority: a number from 1 to 5

RULES
1. Each question starts with "Question:" at the beginning of a line; its answer with "Answer:" at the beginning of a line; then a "Priority:" line with a single number.
2. Group the questions under headings that start with "# " (one heading per topic). Leave an empty line between one question and the next.
3. One question = one idea. If a question holds two, split it.
4. The answer must be complete and stand on its own (usually 2-6 sentences): the student's answer will be compared with it. No "see above", no bullet symbols: plain sentences.
5. Use ONLY the information in the material I give you. Do not invent. If the material lacks the answer to a question, write "Answer: [TO COMPLETE]".
6. Write in the same language as the material.
7. If I give you questions already written, keep their meaning: put them in the format and give each a priority.
8. Multiple-choice questions: if the material has them, or I ask for them, write the options on separate lines under the question, each starting with a letter and a parenthesis ("A) ", "B) ", …, 2 to 8 options), and on the "Answer:" line put ONLY the right letter (or the right letters, separated by commas: "Answer: A, C"). Wrong options must be plausible, not obviously false. Never write "A:" or "D:" with a colon for options.

PRIORITY (choose with care, don't give 1 to everything):
1 = Essential: you can't pass without it; core definitions and ideas.
2 = Important: often asked; needed to understand the rest.
3 = Useful: completes the picture; good to know.
4 = Accessory: a detail or a special case, not central.
5 = In depth: optional, for those who want the most.

EXAMPLE

# The cell
Question: What is the function of mitochondria?
Answer: Mitochondria produce most of the cell's energy in the form of ATP, through cellular respiration. They have their own DNA and a double membrane.
Priority: 1

Question: Who first described mitochondria?
Answer: They were first observed by Richard Altmann in 1890, and named by Carl Benda in 1898.
Priority: 5

Question: Which molecule do mitochondria mainly produce?
A) Glucose
B) ATP
C) DNA
D) Insulin
Answer: B
Priority: 2

When you are done, add no comments. Here is the material:

[PASTE YOUR MATERIAL HERE]`;

export function bankPrompt(language: string): string {
  return language === "it" ? IT : EN;
}
