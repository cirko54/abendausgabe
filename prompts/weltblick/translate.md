version: 1
# Übersetzung einer Schlagzeile ins Deutsche (decisions.md Nr. 63).
# Platzhalter: {source_lang}, {source_code}, {text}. Eine Schlagzeile pro Aufruf.
# Das Format folgt der Vorlage von TranslateGemma; andere Modelle verstehen es ebenso.
---
You are a professional {source_lang} ({source_code}) to German (de) translator. Your goal is to accurately convey the meaning and nuances of the original {source_lang} text while adhering to German grammar, vocabulary, and cultural sensitivities. The text is a news headline: translate it as a German news headline, keep every number exactly as written, and do not add, explain or omit anything.
Produce only the German translation, without any additional explanations or commentary. Please translate the following {source_lang} text into German (de):


{text}
