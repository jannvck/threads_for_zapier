# Threads für Zapier auf Google Cloud Run

Dieser Dienst stellt einen leichtgewichtigen HTTP-Endpunkt zur Verfügung, der zwischen Zapier und der Threads-API vermittelt. Er wurde bewusst ohne externe Frameworks implementiert, damit er auch in restriktiven Umgebungen (z. B. ohne Internetzugriff während des Builds) lauffähig bleibt. Der Server nutzt ausschließlich Standardbibliotheken von Python und lässt sich problemlos in einem Docker-Container auf [Google Cloud Run](https://cloud.google.com/run) betreiben.

## Funktionsumfang

- **OAuth-Fluss für Threads**: Endpunkte zum Authorisieren (`/oauth/authorize`), Tauschen (`/oauth/exchange`) und Aktualisieren (`/oauth/refresh`) von Tokens.
- **Zapier Action**: `/zapier/actions/create-thread` zum Erstellen eines neuen Threads.
- **Zapier Trigger**: `/zapier/triggers/new-thread` gibt neue Beiträge eines Users für Polling-Zaps zurück.
- **Signaturprüfung**: Optionaler Header-Abgleich über `THREADS_ZAPIER_ZAPIER_VERIFICATION_TOKEN`.
- **Health Check**: `/healthz` zur schnellen Betriebsprüfung.

## Projektstruktur

```
app/
  config.py         # Einfache Settings via Umgebungsvariablen
  main.py           # HTTP-Server (BaseHTTPRequestHandler)
  schemas.py        # Dataklassen & Serialisierung
  service.py        # Geschäftslogik & Fehlerbehandlung
  storage.py        # Token-Persistenz (in-memory)
  threads_client.py # HTTP-Client zur Threads-API
Dockerfile          # Containerdefinition
requirements.txt    # Optionale Python-Abhängigkeiten (leer zur Laufzeit)
README.md           # Diese Datei
```

## Lokale Entwicklung

1. **Virtuelle Umgebung erstellen (optional)**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Tests ausführen**

   ```bash
   pytest
   ```

3. **Server lokal starten**

   ```bash
   python -m app.main
   ```

   Der Server lauscht standardmäßig auf Port `8080` (anpassbar über `PORT`).

## Konfiguration

Alle Einstellungen erfolgen über Umgebungsvariablen mit dem Präfix `THREADS_ZAPIER_`:

| Variable | Beschreibung | Standardwert |
| --- | --- | --- |
| `THREADS_ZAPIER_THREADS_API_BASE_URL` | Basis-URL der Threads API | `https://graph.threads.net` |
| `THREADS_ZAPIER_THREADS_CLIENT_ID` | OAuth Client ID | `demo-client-id` |
| `THREADS_ZAPIER_THREADS_CLIENT_SECRET` | OAuth Client Secret | `demo-client-secret` |
| `THREADS_ZAPIER_THREADS_AUTHORIZE_URL` | Basis-URL des Threads OAuth-Autorisierungsendpunkts | `https://www.threads.net/oauth/authorize` |
| `THREADS_ZAPIER_THREADS_REDIRECT_URI` | Registrierte Redirect-URL | `https://example.com/oauth/callback` |
| `THREADS_ZAPIER_THREADS_SCOPE` | Optionaler Scope-Parameter für OAuth | leer |
| `THREADS_ZAPIER_ZAPIER_VERIFICATION_TOKEN` | Optionaler Token zur Request-Prüfung | leer |
| `THREADS_ZAPIER_REQUEST_TIMEOUT_SECONDS` | Timeout für Threads-API Aufrufe | `10.0` |

Für den Betrieb auf **Google Cloud Run** (oder andere Plattformen mit Secret-Files) werden zusätzlich automatisch Umgebungsvariablen mit der Endung `_FILE` ausgewertet. Enthält beispielsweise `THREADS_ZAPIER_THREADS_CLIENT_SECRET_FILE` den Pfad zu einer Datei, wird deren Inhalt als Secret geladen. Damit lassen sich Secrets komfortabel über `gcloud run deploy --set-secrets` bereitstellen.

## Docker Build & lokaler Test

```bash
docker build -t threads-zapier:latest .
docker run -it --rm -p 8080:8080 \
  -e THREADS_ZAPIER_THREADS_CLIENT_ID=... \
  -e THREADS_ZAPIER_THREADS_CLIENT_SECRET=... \
  threads-zapier:latest
```

## Deployment auf Google Cloud Run

1. **Artefakt-Registry und Projekt konfigurieren**

   ```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud artifacts repositories create threads-zapier --repository-format=docker --location=europe-west1
   ```

2. **Image bauen und pushen**

   ```bash
gcloud builds submit --tag europe-west1-docker.pkg.dev/<PROJECT_ID>/threads-zapier/service:latest
   ```

3. **Cloud-Run Deployment**

   ```bash
gcloud run deploy threads-zapier \
  --image europe-west1-docker.pkg.dev/<PROJECT_ID>/threads-zapier/service:latest \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars THREADS_ZAPIER_THREADS_CLIENT_ID=... \
  --set-env-vars THREADS_ZAPIER_THREADS_CLIENT_SECRET=... \
  --set-env-vars THREADS_ZAPIER_THREADS_REDIRECT_URI=https://<DOMAIN>/oauth/callback
   ```

4. **Zapier verbinden**: Verwende die Cloud-Run-URL als Basis und ergänze die obigen Pfade für Actions/Trigger.

   Für den OAuth-Autorisierungs-Redirect erwartet Zapier einen öffentlichen Endpunkt `https://<CLOUD_RUN_HOST>/oauth/authorize`,
   der nun automatisch auf die Threads-Anmeldeseite weiterleitet. Stelle sicher, dass in deiner Threads-App die Zapier-Redirect-URL
   (z. B. `https://zapier.com/dashboard/auth/oauth/<APP_ID>/oauth/authorize`) erlaubt ist und optional der gewünschte Scope über
   `THREADS_ZAPIER_THREADS_SCOPE` gesetzt wurde.

## Weiterentwicklung

- Ablage der Tokens in Firestore, Redis oder Secret Manager statt in-memory.
- Zusätzliche Actions (z. B. Bearbeiten/Löschen von Threads) implementieren.
- Upload-Workflow für Medien ergänzen, sobald die Threads-API entsprechende Endpunkte bereitstellt.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Details siehe [LICENSE](LICENSE).
