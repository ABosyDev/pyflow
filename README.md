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
