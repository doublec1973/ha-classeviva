# ClasseViva per Home Assistant

Integrazione custom **non ufficiale** per il registro elettronico ClasseViva (Spaggiari).
Mostra voti, medie, assenze, compiti, verifiche, comunicazioni e agenda dentro Home Assistant.

> **Disclaimer:** progetto non affiliato né approvato da Spaggiari. Usa API non documentate
> che possono cambiare o essere chiuse senza preavviso. Usalo a tuo rischio e con le tue credenziali.
> Se la tua scuola passa all'accesso solo con SPID/CIE, il login con username e password
> potrebbe smettere di funzionare.

## Installazione

### HACS (repository personalizzato)
1. HACS → Integrazioni → menu ⋮ → **Repository personalizzati**.
2. Incolla l'URL di questo repository, categoria **Integrazione**.
3. Installa **ClasseViva** e riavvia Home Assistant.

### Manuale
Copia `custom_components/classeviva` in `/config/custom_components/` e riavvia.

## Configurazione
Impostazioni → Dispositivi e servizi → Aggiungi integrazione → **ClasseViva**.
Inserisci il codice personale (o l'email) e la password del registro. Funzionano account
genitore (G…) e studente (S…).

In **Configura** puoi impostare:
- intervallo di aggiornamento (minuti, default 30);
- scuola aperta anche il sabato;
- parole chiave per riconoscere i compiti scritti come annotazione dell'agenda;
- giorni di sospensione extra (date o intervalli, es. `2026-12-07, 2026-12-23..2027-01-06`).

## Entità
**Sensori:** media generale, ultimo voto, media per materia, assenze, ritardi, uscite anticipate,
da giustificare, comunicazioni non lette, note disciplinari, verifiche in programma,
compiti in programma, compiti per il prossimo giorno di scuola utile, 2° e 3° giorno utile,
compiti assegnati di recente.
**Calendario:** Agenda (compiti, annotazioni, verifiche, con testo e nome del docente).

I "giorni utili" saltano domenica (e sabato, se non attivato), le festività nazionali italiane
e i giorni di sospensione impostati. Se il calendario scolastico di Spaggiari risponde in modo
riconoscibile, viene usato anch'esso.

## Esempio: leggere i compiti dall'agenda
```yaml
action: calendar.get_events
target:
  entity_id: calendar.classeviva_NOME_agenda
data:
  start_date_time: "2026-10-19 00:00:00"
  end_date_time: "2026-10-21 00:00:00"
response_variable: agenda
```
Le descrizioni degli eventi riportano il testo della nota e, in fondo, `Docente: Cognome Nome`.

## Note
- I nomi delle entità dipendono dal nome dello studente e dall'eventuale area assegnata.
- La password è salvata nella config entry di Home Assistant (necessaria per rinnovare il token).

## Licenza
MIT
