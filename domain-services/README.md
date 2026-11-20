# Domain Services

Transportservices nach [DS2 #23](https://github.com/li-minjian/Traveller/issues/23). Pro Verkehrsmittel gibt es einen **eigenständigen** Service, der einzeln mit dem Journey Planner spricht.

```text
                 Journey Planner
        DS1-Vertrag │            │ DS1-Vertrag
                    ▼            ▼
             train-service   flight-service      (kennen sich nicht)
                    │            │
            Bahn-Anbieter    Flug-Anbieter
```

| Service | Ordner | `service_id` | Anbieter (Stand) |
| --- | --- | --- | --- |
| Train Service | [`train-service/`](train-service/README.md) | `train` | `mock-rail` |
| Flight Service | [`flight-service/`](flight-service/README.md) | `flight` | `mock-air` |

## Regeln

- **Keine Abhängigkeiten zwischen Services.** Ein Service importiert nichts aus einem anderen Service, es gibt keinen gemeinsamen Code und keine gemeinsamen Tests. Jeder Service hat eigenen Code, eigene Adapter, eigene Fehlerbehandlung, eigene Konfiguration, eigene Tests und eigene Doku und lässt sich allein ändern, testen und später allein ausliefern.
- **Einzige gemeinsame Schnittstelle ist der [DS1-Vertrag](../journey-planner/docs/DS1_CONTRACT.md)** des Journey Planners. Jeder Service bindet ihn über seine eigene Datei `<service>/contract.py` ein.
- **Ähnlicher Aufbau ist gewollt, geteilter Code nicht.** Beide Services sind nach demselben Muster gebaut (Service-Klasse, Provider-Adapter, Fehlerklassen). Doppelter Code wird bewusst in Kauf genommen, damit sich die Services unabhängig weiterentwickeln können.

## Neuen Service anlegen (z. B. Bus)

1. Ordner `bus-service/` mit Paket `bus_service/` anlegen. Das Muster eines bestehenden Services darf kopiert werden, der neue Service importiert aber nichts daraus.
2. `service_id`, `TransportMode` und Adapter festlegen; der Service erfüllt `TransportService` aus DS1.
3. Eigene Tests unter `bus-service/tests/` und eine eigene `README.md`.
4. Im Journey Planner den Service in die Liste der abgefragten Services aufnehmen.

## Tests

Jeder Service wird in seinem eigenen Ordner getestet:

```sh
cd domain-services/train-service  && python3 -m unittest
cd domain-services/flight-service && python3 -m unittest
```

## Offene Punkte

- **DS1-Vertrag als eigenes Paket:** Die Services finden den Vertrag im Repo unter `journey-planner/`. Für getrennte Container (IN01/IN02) sollte er installierbar werden; je Service ändert sich dann nur `contract.py`.
- **HTTP-Endpunkt und Health-Check** je Service (DS6 #41, IN02 #42), **echte Anbieter** (DS3 #25), **Contract-Tests** (DS4 #26) und **Caching** (DS5 #27) sind **geplant**.
