# Neuen Endpunkt ergänzen

Die Anleitung geht Schritt für Schritt durch einen neuen Endpunkt, vom Modell bis zur Oberfläche. Als Beispiel dienen die vorhandenen Planungssitzungen in `backend/planning/`. Alle Befehle laufen im Compose-Setup, siehe [DEVELOPMENT.md](DEVELOPMENT.md).

Reihenfolge: **Beschreiben → Modell → Migration → Serializer → View → URL → Tests → Doku → Frontend.**

## 0. Endpunkt beschreiben, bevor Code entsteht

Jeder neue Endpunkt bekommt einen Eintrag in [API.md](API.md) mit **Methode, URL, Parametern, Validierung, Beispielantwort und Fehlerfällen**. Am einfachsten schreibt man ihn zuerst, er dient dann als Vorlage für Code und Tests:

````markdown
## `POST /api/v1/<ressourcen>/`

Wofür der Endpunkt da ist.

**Body** (`Content-Type: application/json`)

| Feld | Typ | Pflicht | Validierung |
| --- | --- | --- | --- |
| `title` | String | ja | 1–200 Zeichen |

```sh
curl -X POST http://localhost:8000/api/v1/<ressourcen>/ -H 'Content-Type: application/json' -d '{…}'
```

`201 Created`

```json
{"id": "…", "…": "…"}
```

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| Pflichtfeld fehlt | `400` | `{"error": {"code": "validation_error", …}}` |
````

Dabei die [API-Konventionen](API_CONVENTIONS.md) prüfen:
- Pfad im Plural mit Schrägstrich am Ende
- passende Methode und passender Statuscode
- Fehlerformat
- Feldnamen in `snake_case`
- Zeitpunkte in UTC
- Geldbeträge mit Währung und Preisbasis
- Listen mit Seiten

## 1. Modell

```python
# backend/planning/models.py
class PlanningSession(models.Model):
    """A travel planning session; later anchor for trip state and chat history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
```

- **Öffentliche IDs** sind UUIDs, nicht die fortlaufende Datenbank-ID.
- **Zeitpunkte** als `DateTimeField`, Django speichert sie in UTC.
- **Geldbeträge** als `DecimalField` plus Währungsfeld, siehe [Konventionen §7](API_CONVENTIONS.md#7-geldbeträge).
- **Unbekannte Werte** sind `null=True`, kein leerer String und keine `0`.

## 2. Migration

```sh
docker compose exec backend python manage.py makemigrations planning
```

Die neue Datei unter `backend/planning/migrations/` kurz durchsehen und **zusammen mit der Modelländerung einchecken**. Angewendet wird sie sofort mit `docker compose exec backend python manage.py migrate` oder automatisch beim nächsten Start des Backends.

## 3. Serializer

```python
# backend/planning/serializers.py
class PlanningSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanningSession
        fields = ["id", "title", "created_at"]
        read_only_fields = ["id", "created_at"]
```

- **Feldtypen und Längen** übernimmt der `ModelSerializer` aus dem Modell.
- **Weitere Regeln** gehören in `validate_<feld>(self, value)` oder `validate(self, attrs)` und lösen `serializers.ValidationError` aus. Daraus wird automatisch ein `400` im einheitlichen Fehlerformat mit `fields`.
- **Vom Server vergebene Felder** stehen in `read_only_fields`. Gesendete Werte dafür werden dann ignoriert.

## 4. View

```python
# backend/planning/views.py
class PlanningSessionCreateView(generics.CreateAPIView):
    """POST /api/v1/planning-sessions/"""

    queryset = PlanningSession.objects.all()
    serializer_class = PlanningSessionSerializer


class PlanningSessionDetailView(generics.RetrieveAPIView):
    """GET /api/v1/planning-sessions/{id}/"""

    queryset = PlanningSession.objects.all()
    serializer_class = PlanningSessionSerializer
```

- **Passende generische Views** aus `rest_framework.generics` nehmen:
  - `ListAPIView` (Seiten kommen automatisch)
  - `RetrieveAPIView`
  - `CreateAPIView` (`201`)
  - `UpdateAPIView` (`PATCH`)
  - `DestroyAPIView` (`204`)

  Nicht angebotene Methoden beantwortet DRF selbst mit `405`.
- **Fehler werfen, nicht selbst bauen:** `NotFound` und `ValidationError` aus `rest_framework.exceptions`, `Conflict` (`409`) und `ServiceUnavailable` (`503`) aus `config.exceptions`. Den Rest erledigt der zentrale Handler in [`config/exceptions.py`](../backend/config/exceptions.py), auch für unerwartete Fehler.
- **Keine Interna nach außen:** Keine breiten `try/except`, die Fehlermeldungen an den Client weitergeben.

## 5. URL

```python
# backend/planning/urls.py
urlpatterns = [
    path("planning-sessions/", views.PlanningSessionCreateView.as_view(), name="planning-session-list"),
    path("planning-sessions/<uuid:pk>/", views.PlanningSessionDetailView.as_view(), name="planning-session-detail"),
]
```

Für eine **neue App**:
1. `docker compose exec backend python manage.py startapp <name>` ausführen.
2. Die App in `INSTALLED_APPS` in `backend/config/settings.py` eintragen.
3. In `backend/config/urls.py` `path("api/v1/", include("<name>.urls"))` ergänzen, und zwar **vor** der Sammelregel `re_path(r"^api/", views.not_found)`. Die Sammelregel muss die letzte bleiben.

## 6. Tests

```python
# backend/planning/tests.py
class CreatePlanningSessionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_creates_a_session_and_returns_201(self):
        response = self.client.post(LIST_URL, {"title": "Weekend in Leipzig"}, format="json")
        self.assertEqual(response.status_code, 201)
        ...

    def test_rejects_invalid_titles_with_field_errors(self):
        ...
```

**Mindestens testen:**
- den Erfolgsfall
- jede Validierungsregel
- eine unbekannte Ressource (`404`)
- Statuscodes, die für den Endpunkt wichtig sind (`405`, `409`, `503`)

Externe Dienste wie LLM oder Anbieter werden mit `unittest.mock.patch` ersetzt, Tests greifen nie ins Netz. Tests mit Dateien schreiben diese in ein temporäres Verzeichnis, siehe `reference_data/tests/helpers.py`.

```sh
docker compose exec backend python manage.py test
```

## 7. Doku im selben Pull Request

- **API.md:** Eintrag aus Schritt 0 an den tatsächlichen Stand angleichen, mit echten Antworten. Neuen Endpunkt in die Übersichtstabelle aufnehmen.
- **Neue Umgebungsvariablen** mit unkritischem Wert in `.env.example` und in [DEVELOPMENT.md](DEVELOPMENT.md#umgebungsvariablen) eintragen.
- **Neue oder geänderte Regeln**, z. B. ein neuer Fehlercode oder eine neue Preisbasis, in [API_CONVENTIONS.md](API_CONVENTIONS.md) ergänzen.
- **Geplantes** bleibt als „geplant“ markiert, bis es umgesetzt ist.

## 8. Im Frontend einbinden

**Typen und Funktion** kommen in [`frontend/src/api/client.ts`](../frontend/src/api/client.ts). Nur dort stehen API-Pfade:

```ts
export type PlanningSession = {
  id: string;
  title: string;
  /** ISO 8601 timestamp in UTC. */
  created_at: string;
};

export const backend = {
  // …
  getPlanningSession: (id: string, signal?: AbortSignal) =>
    request<PlanningSession>(
      `/planning-sessions/${encodeURIComponent(id)}/`,
      { signal },
    ),
};
```

**Test** in `frontend/tests/api.test.ts` mit Fetch-Mock:

```ts
it('encodes the session ID in the detail path', async () => {
  const fetchMock = stubFetch(
    jsonResponse(200, { id: 'a b', title: 'x', created_at: '' }),
  );
  await backend.getPlanningSession('a b');
  expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/planning-sessions/a%20b/');
});
```

**Verwendung in der Komponente** über `backend.…`. Ein Ladezustand wird angezeigt, Fehler kommen als `ApiError`:
- `kind` ist `unreachable`, `unavailable` oder `http`.
- `code` und `fields` stammen aus dem Fehlerformat.

Ein Beispiel ist die Statusseite [`SystemStatus.tsx`](../frontend/src/features/SystemStatus.tsx):

```tsx
try {
  setSession(await backend.getPlanningSession(sessionId.trim()));
} catch (error) {
  setFailure({ action: 'load', error }); // describeError(error) macht daraus den Text
}
```

Anfragen in `useEffect` erhalten ein `AbortSignal` und werden beim Verlassen der Seite abgebrochen.

**Prüfen:**

```sh
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run lint
docker compose exec frontend npm test
docker compose exec frontend npm run build
```

## Checkliste für den Pull Request

- [ ] Endpunkt in [API.md](API.md) mit Methode, URL, Parametern, Validierung, Beispielantwort und Fehlerfällen
- [ ] [API-Konventionen](API_CONVENTIONS.md) eingehalten, Abweichungen begründet und dort ergänzt
- [ ] Migration erzeugt und eingecheckt
- [ ] Tests für Erfolg, Validierung und Fehlerfälle, `manage.py test` grün
- [ ] Frontend greift nur über `client.ts` zu, Typprüfung, Lint, Tests und Build grün
- [ ] Neue Umgebungsvariablen in `.env.example` und `DEVELOPMENT.md`
- [ ] Alle Doku-Änderungen im selben Pull Request
