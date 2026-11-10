# TravelPlanner-Benchmark (historische Referenzdaten)

Dieser Ordner enthält den vollständigen TravelPlanner-Datensatz mit 1.225 Fällen als lokale Kopie. Der Import braucht deshalb keinen Download.

**Historische Benchmark-Daten:** Alle Reisen liegen im Jahr 2022. Angebote und Preise stammen aus der Sandbox-Datenbank des Benchmarks. Es sind keine aktuellen Reiseangebote.

## Herkunft und Lizenz

| | |
| --- | --- |
| Quelle | [huggingface.co/datasets/osunlp/TravelPlanner](https://huggingface.co/datasets/osunlp/TravelPlanner), Projektseite [osu-nlp-group.github.io/TravelPlanner](https://osu-nlp-group.github.io/TravelPlanner/) |
| Version | Hugging-Face-Revision `8736504ecfc31b7f8b7e40122873c337e83fff7c` (Stand 14.07.2024), abgerufen am 10.11.2026 |
| Lizenz | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (Datensatz). Der Code des Original-Repositorys steht unter MIT, wird hier aber nicht verwendet. |
| Urheber | Jian Xie, Kai Zhang, Jiangjie Chen, Tinghui Zhu, Renze Lou, Yuandong Tian, Yanghua Xiao, Yu Su (2024): *TravelPlanner: A Benchmark for Real-World Planning with Language Agents.* [arXiv:2402.01622](https://arxiv.org/abs/2402.01622) |
| Änderungen | CSV-Dateien mit Python-Literalen in gzip-komprimierte JSON Lines umgewandelt, Zahlen als Text in Ganzzahlen. Stabile Fall-IDs aus Split und Zeilennummer ergänzt. Alle übrigen Werte sind unverändert. |

## Dateien

| Datei | Inhalt |
| --- | --- |
| `manifest.json` | Herkunft, Version, Lizenz und Hinweise des Datensatzes sowie die Datendateien mit Fallanzahl und SHA-256-Prüfsumme. |
| `train.jsonl.gz` | 45 Fälle mit menschlich annotierten Plänen (`annotated_plan`). |
| `validation.jsonl.gz` | 180 Fälle ohne annotierte Pläne. |
| `test.jsonl.gz` | 1.000 Fälle. Im Original fehlen `visiting_city_number`, `people_number`, `local_constraint`, `budget` und `annotated_plan`, um Datenkontamination zu vermeiden. Diese Felder sind `null`. |
| `build_from_source.py` | Erzeugt die Dateien aus den Original-CSVs neu. |

Jede Zeile einer `.jsonl.gz`-Datei ist ein Fall. Die Feldnamen folgen dem Original:

```json
{
  "id": "travelplanner-train-0000", "split": "train", "row": 0,
  "org": "St. Petersburg", "dest": "Rockford", "days": 3, "visiting_city_number": 1,
  "date": ["2022-03-16", "2022-03-17", "2022-03-18"], "people_number": 1,
  "local_constraint": {"house rule": null, "cuisine": null, "room type": null, "transportation": null},
  "budget": 1700, "query": "Please help me plan a trip from St. Petersburg to Rockford …",
  "level": "easy", "annotated_plan": [ … ], "reference_information": [{"Description": "Attractions in Rockford", "Content": "…"}, …]
}
```

- `id` ist stabil und lautet `travelplanner-<split>-<Zeile>`, wobei `row` die Zeile (ab 0) in der jeweiligen CSV-Datei der genannten Revision ist.
- `budget` ist in US-Dollar angegeben und gilt für die gesamte Reise mit allen Reisenden.
- `reference_information` enthält die Daten für den Modus „sole-planning“. Jeder Eintrag besteht aus `Description` und `Content`, wobei `Content` eine Tabelle als Text ist.
- Die strukturierte Fassung derselben Informationen (`*_ref_info.jsonl` im Original) ist nicht enthalten.

## Importieren

```sh
docker compose exec backend python manage.py import_reference_cases
```

Mit `--split train` lassen sich einzelne Splits importieren, mit `--dry-run` prüft der Befehl nur und schreibt nichts. Weitere Details stehen in [docs/DEVELOPMENT.md](../../../../docs/DEVELOPMENT.md#referenzdaten-importieren). Die API für die importierten Fälle beschreibt [docs/API.md](../../../../docs/API.md#get-apiv1reference-cases).

## Neu erzeugen

Die Original-CSVs der Revision von Hugging Face herunterladen (`train.csv`, `validation.csv`, `test.csv`) und dann ausführen:

```sh
python3 build_from_source.py <Ordner mit den CSV-Dateien>
```

Bei unveränderter Quelle entstehen dieselben Dateien und Prüfsummen, geprüft mit Python 3.13 und 3.14. Nur das Abrufdatum im Manifest ändert sich.
