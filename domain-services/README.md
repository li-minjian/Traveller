# Domain Services

Die Transportservices (Flug, Bahn, Taxi, später Bus, Fähre) und ihre gemeinsame Schnittstelle zum Journey Planner.

```text
                    Journey Planner
                          │  DS1-Vertrag (contract/)
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
      flight-service  train-service    …          (kennen sich nicht)
            │             │
      Flug-Anbieter   Bahn-Anbieter
```

| Ordner | Inhalt |
| --- | --- |
| [`contract/`](contract/README.md) | **DS1-Vertrag**, nur Dokumentation: `openapi.yaml` (verbindlich), `README.md` (Regeln), `examples/` |
| [`services/`](services/) | ein Ordner pro Transportservice, z. B. `services/flight-service/` |

## Regeln

- **Der Vertrag ist die einzige gemeinsame Grundlage, und er enthält keinen Code.** Jeder Service bietet den Endpunkt aus `contract/openapi.yaml` an, der Journey Planner ruft alle Services darüber auf. Änderungen am Vertrag werden mit dem Journey Planner abgestimmt und folgen der Versionierung in [contract/README.md §5](contract/README.md#5-versionierung).
- **Keine Abhängigkeiten zwischen Services.** Ein Service importiert nichts aus einem anderen Service. Jeder hat eigenen Code, eigene Adapter, eigene Konfiguration, eigene Tests und eigene Doku und lässt sich allein ändern, testen und ausliefern.
- **Jeder Service prüft sich selbst gegen den Vertrag**, z. B. indem seine Tests die Antworten gegen `contract/openapi.yaml` validieren und die Beispiele aus `contract/examples/` verwenden.

## Tests

Jeder Service wird in seinem eigenen Ordner unter `services/` getestet. Der Vertrag selbst hat keinen Code und daher keine eigenen Tests.
