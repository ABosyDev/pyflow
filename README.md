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
from pyflow import Task, Workflow, execution_layers

def pobierz(inputs, params):
    return [1, 2, 3]

def zsumuj(inputs, params):
    return sum(inputs["pobierz"])

workflow = Workflow()
workflow.add_task(Task("pobierz", pobierz))
workflow.add_task(Task("zsumuj", zsumuj, frozenset({"pobierz"})))
workflow.validate()
print(execution_layers(workflow))  # [['pobierz'], ['zsumuj']]
```

Na razie tworzymy tylko plan. Funkcje zadań nie są uruchamiane.

## Algorytm

Użyłem algorytmu Kahna. Najpierw wybieramy zadania bez zależności,
a potem te, których zależności zostały już spełnione. Nazwy w każdej
warstwie sortujemy alfabetycznie, żeby wynik był zawsze taki sam.
Jeśli część zadań pozostanie zablokowana, zgłaszamy błąd cyklu.

Dla V zadań i E zależności czas wynosi O(V + E + V log V),
bo dodatkowo sortujemy nazwy. Pamięć wynosi O(V + E).
