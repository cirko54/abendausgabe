version: 1
# Wo spielt eine Meldung? (decisions.md Nr. 64). Platzhalter: {text}. Antwort als JSON nach Schema.
# Der Ort muss wörtlich in der Schlagzeile stehen; die Redaktion prüft das und geokodiert ihn.
---
Du bekommst eine deutsche Nachrichtenschlagzeile. Bestimme den einen Ort, an dem das Berichtete geschieht.

Regeln:
- "place": der Ort genau so geschrieben, wie er in der Schlagzeile steht (Stadt, Region oder Land), wörtlich kopiert.
- "country": der ISO-3166-1-Alpha-2-Code des Landes, in dem dieser Ort liegt, zum Beispiel "RS" oder "IN".
- Eine Person, Partei, Firma oder Organisation ist kein Ort.
- Geht es um mehrere Länder zugleich, um keinen bestimmten Ort, oder nennt die Schlagzeile keinen Ort: beide Felder leer lassen.

Schlagzeile: {text}
