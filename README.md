# PyFlow — laboratoria 1 i 2

Biblioteka opisuje zadania, sprawdza zależności i synchronicznie wykonuje
workflow w kolejności topologicznej.

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
from pyflow import Task, Workflow, execution_layers, format_report, run

def pobierz(inputs, params):
    return [1, 2, 3]

def zsumuj(inputs, params):
    return sum(inputs["pobierz"]) * params["mnoznik"]

workflow = Workflow()
workflow.add_task(Task("pobierz", pobierz))
workflow.add_task(Task("zsumuj", zsumuj, frozenset({"pobierz"}), {"mnoznik": 2}))
print(execution_layers(workflow))  # [['pobierz'], ['zsumuj']]
result = run(workflow)
print(result.outputs["zsumuj"])  # 12
print(format_report(result))
```

## Wykonanie i statusy

Silnik najpierw sprawdza cały graf. Następnie wywołuje synchroniczne funkcje
`function(inputs, params)`. Słownik `inputs` zawiera wyniki bezpośrednich
zależności. Zadanie bez zależności dostaje pusty słownik. `params` zawiera
konfigurację zapisaną w `Task`.

`RunResult.outputs` przechowuje wartości zwrócone przez zakończone poprawnie
zadania, w tym `None`. Każdy wpis w `RunResult.task_states` ma status
`SUCCEEDED`, `FAILED` albo `SKIPPED`. Dla uruchomionych zadań zapisujemy
początek, koniec i udostępniamy czas trwania w sekundach. Tak samo mierzymy cały
przebieg. `format_report(result)` zwraca raport z czasami, a przy pominiętych
zadaniach wyświetla kreskę. Pusty workflow zwraca pusty wynik z `succeeded=True`.

Po awarii silnik zapisuje oryginalny wyjątek w `task_states[nazwa].error`,
pomija zależne zadania i kończy pozostałe gałęzie. Potem zgłasza
`TaskExecutionError`. Pole `task_name` wskazuje pierwsze zadanie, które
zawiodło, `__cause__` zawiera jego oryginalny wyjątek, a `result` zawiera
raport całego przebiegu z `succeeded=False`.

## Przykład CSV → JSON

Po instalacji uruchom poniższe polecenie z katalogu repozytorium.

```powershell
.\.venv\Scripts\python.exe -m examples.csv_report
```

Przykład czyta `examples/sales.csv`, normalizuje nazwy produktów, sumuje ilości
i wypisuje JSON na stdout. Raport czasów trafia na stderr.

## Algorytm

Użyłem algorytmu Kahna. Najpierw wybieramy zadania bez zależności,
a potem te, których zależności zostały już spełnione. Nazwy w każdej
warstwie sortujemy alfabetycznie, żeby wynik był zawsze taki sam.
Jeśli część zadań pozostanie zablokowana, zgłaszamy błąd cyklu.

Dla V zadań i E zależności czas wynosi O(V + E + V log V),
bo dodatkowo sortujemy nazwy. Pamięć wynosi O(V + E).
