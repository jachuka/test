# Kalkulator formatek

Desktopowa aplikacja w języku polskim. Wymaga Python 3.10+ z modułem Tkinter (w instalatorze Pythona na Windows zaznacz Tcl/Tk).

Uruchom w katalogu projektu:

```sh
python app.py
```

Na Windows można też użyć `py app.py`. Aplikacja działa lokalnie, bez internetu i dodatkowych bibliotek Python.

## Plik EXE dla Windows 11

1. Pobierz wszystkie pliki projektu do jednego folderu i rozpakuj archiwum, jeśli korzystasz z ZIP.
2. Jednorazowo zainstaluj Python 3.10+ z python.org, z komponentami Tcl/Tk i Python Launcher.
3. Kliknij dwukrotnie `Zbuduj_EXE.bat`. Pierwsze budowanie wymaga internetu do pobrania PyInstaller i jego zależności.
4. Po pomyślnym zakończeniu w folderze `dist` znajdziesz `KalkulatorFormatek.exe`.
5. Przenieś plik EXE np. na pulpit i uruchamiaj dwukrotnym kliknięciem. Komputer uruchamiający gotowy EXE nie potrzebuje Pythona.

Budowanie odbywa się lokalnie na Windows, w osobnym środowisku `.venv-build`. Skrypt sprawdza Tkinter, uruchamia testy i pakuje aplikację bez okna konsoli. Plik nie jest podpisany cyfrowo, więc Windows może wyświetlić komunikat o nieznanym wydawcy. Budowanie i uruchomienie EXE wymagają sprawdzenia na Windows; nie zostały zweryfikowane w linuksowym środowisku chmurowym.

Podaj szerokość i wysokość arkusza, szerokość i wysokość jednej prostokątnej formatki, odstęp między krawędziami formatek i jednakowy margines od czterech brzegów. Wszystkie wartości są w mm; akceptowany jest przecinek dziesiętny. Obrót o 90° można wyłączyć, np. ze względu na kierunek materiału.

Wynik pokazuje liczbę formatek, wykorzystanie całej powierzchni arkusza i podgląd rozmieszczenia. Przerywana linia oznacza margines. Kalkulator porównuje poziome i pionowe układy pasowe, również z mieszanymi orientacjami. Podaje najlepszy znaleziony wynik, bez gwarancji globalnego optimum dowolnego pakowania prostokątów. W odstępie należy uwzględnić wymagany zapas na cięcie. Limit podglądu: 50 000 formatek.

Testy obliczeń:

```sh
python -m unittest -v
```
