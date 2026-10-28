# PyFlow — laboratorium 1

Biblioteka opisuje zadania, sprawdza zależności i tworzy plan wykonania.
Na tym etapie nie uruchamia funkcji zadań.

## Instalacja (PowerShell, Python 3.11+)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Po aktywacji środowiska (`.\.venv\Scripts\Activate.ps1`) testy można też
uruchomić poleceniem `python -m pytest`.

## Przykład

```python
from pyflow import Task, Workflow, execution_layers, topological_order


def extract(inputs, params):
    return [1, 2, 3]


def clean(inputs, params):
    return [value * params["multiplier"] for value in inputs["extract"]]


def report(inputs, params):
    return {"a": inputs["clean_a"], "b": inputs["clean_b"]}


workflow = Workflow()
workflow.add_task(Task("extract", extract))
workflow.add_task(Task("clean_a", clean, frozenset({"extract"}), {"multiplier": 2}))
workflow.add_task(Task("clean_b", clean, frozenset({"extract"}), {"multiplier": 3}))
workflow.add_task(Task("report", report, frozenset({"clean_a", "clean_b"})))
workflow.validate()

print(topological_order(workflow))
# ['extract', 'clean_a', 'clean_b', 'report']
print(execution_layers(workflow))
# [['extract'], ['clean_a', 'clean_b'], ['report']]
```

`inputs` to wyniki bezpośrednich zależności, a `params` to konfiguracja zadania.
Planowanie nie wywołuje funkcji. Dane przekazane do `params` są kopiowane
głęboko, a zależności zamieniane na `frozenset`.

## Algorytm

Używamy algorytmu Kahna: liczymy niespełnione zależności każdego zadania.
Zadania bez zależności tworzą pierwszą warstwę. Po jej przetworzeniu
zmniejszamy liczniki zadań zależnych i budujemy kolejną warstwę.
Nazwy w każdej warstwie sortujemy alfabetycznie, więc kolejność dodawania
zadań nie zmienia wyniku. Kolejność topologiczna to połączone warstwy.

Jeśli nie uda się przetworzyć wszystkich zadań, graf zawiera cykl.
Brakujące zależności wykrywamy przed planowaniem. Błędy zgłaszamy jako
`WorkflowValidationE`, zgodnie z nazwą podaną w instrukcji.

Dla V zadań i E zależności poprawny graf przetwarzamy w czasie
O(V + E + V log V), uwzględniając sortowanie warstw. Pamięć: O(V + E).
