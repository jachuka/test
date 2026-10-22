# Kalkulator formatek

Desktopowa aplikacja dla Windows, z polskim interfejsem. Dwa tryby: prostokąty oraz powielanie jednego nieregularnego obrysu. Domyślny arkusz: 3050 × 2050 mm. Wszystkie wymiary w mm, akceptowany przecinek dziesiętny.

## Uruchomienie z Pythona

Wymagany Python 3.10–3.15 z Tkinter (Tcl/Tk w instalatorze Windows). W folderze projektu:

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install -r requirements.txt
.venv-build\Scripts\python.exe app.py
```

Zależności: PyMuPDF (odczyt i zapis PDF), Shapely (geometria), NumPy (analiza pikseli skanów, bez OpenCV). Instalacja wymaga internetu; obliczenia i import/eksport działają lokalnie.

## Plik EXE dla Windows 11

Pobierz Code → Download ZIP z GitHub, rozpakuj do nowego folderu i uruchom `Zbuduj_EXE.bat`. Skrypt instaluje zależności w `.venv-build`, sprawdza Tkinter, uruchamia testy i buduje `dist\KalkulatorFormatek.exe`.

Jeśli Windows blokuje skrypt BAT, otwórz folder w Eksploratorze, wpisz `cmd` w pasku adresu i wykonaj kolejno:

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install PyInstaller==6.22.3 -r requirements.txt
.venv-build\Scripts\python.exe -m unittest -v
.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name KalkulatorFormatek app.py
```

Po wyniku testów `OK` można uruchomić ostatnie polecenie. Gotowy EXE nie wymaga Pythona. Przy aktualizacji należy ponownie zbudować EXE. Plik nie jest podpisany cyfrowo; Windows może ograniczyć jego uruchomienie. Budowanie EXE wymaga Windows i nie zostało zweryfikowane w linuksowym środowisku chmurowym.

## Prostokąty

Wprowadź wymiary arkusza i jednej formatki, odstęp między krawędziami i margines od wszystkich brzegów. Obrót o 90° można wyłączyć, np. ze względu na kierunek materiału. Kalkulator porównuje poziome i pionowe układy pasowe, również z mieszanymi orientacjami; nie gwarantuje optimum dowolnego pakowania. Limit podglądu: 50 000 formatek.

## Kształty nieregularne / PDF

1. Wybierz zakładkę **Kształty nieregularne / PDF**.
2. Wczytaj **PDF wektorowy 1:1**. Odczytywana jest wyłącznie pierwsza strona i zamknięte, poprawne geometrycznie obrysy mieszczące się w całości na widocznej stronie. Obiekty poza stroną i obrysy przycięte jej brzegiem są pomijane. Z CorelDRAW wyeksportuj sam kontur jako krzywą w PDF 1:1; bez napisów i znaczników. CDR nie jest obsługiwany.
3. Jeśli plik zawiera kilka obrysów, wybierz właściwy z listy. Podgląd i rozmiar pozwalają odróżnić formatkę od ramki strony. Jeden wybrany obrys jest jedną formatką; pozostałe nie są łączone w grupę.
4. Alternatywnie wczytaj skan PDF lub PNG/JPG/BMP: ciemny, zamknięty obrys lub sylwetka na białym tle. Ustaw próg ciemności (domyślnie 180), wybierz kontur i podaj jego **rzeczywistą szerokość w mm**. Skala DPI skanu nie jest uznawana za wiarygodną. Program zachowuje proporcje obrazu; nie koryguje perspektywy ani zniekształceń skanera. Koniecznie sprawdź obrys i wysokość w podglądzie. Gdy kalibracja zostanie anulowana, wybierz obrys ponownie.
5. Ustaw arkusz, odstęp i margines. Włączenie obrotów dopuszcza 0°, 90°, 180°, 270°; odbicie lustrzane nie jest stosowane.
6. Kliknij **Ułóż formatki**. Najpierw powstaje pełny układ regularny. Następnie program sprawdza powtarzalne grupy dopasowanych obrysów i zachowuje wynik z większą liczbą formatek. Czas optymalizacji można wybrać: 15, 30, 60 lub 120 sekund (domyślnie 30). Obliczenia działają w tle, do 1000 kopii; można je przerwać i zachować najlepszy dotychczasowy układ. Limit czasu nie usuwa pełnego układu bazowego. Poszukiwanie nie gwarantuje optimum ani wykorzystania każdego wolnego miejsca.
7. Kliknij **Zapisz układ do PDF 1:1**. PDF ma rozmiar arkusza i czarne obrysy wektorowe; nie zawiera ramki arkusza, wymiarów ani podpisów jako linii cięcia. Eksport zapisuje widoczny wynik z wymiarami podanymi w opisie wyniku, również jeśli później zmienisz pola formularza bez ponownego obliczenia. Maksymalny bok eksportowanego arkusza: 5080 mm. Przy druku wybierz rzeczywisty rozmiar / 100%, bez dopasowania do strony.

Układanie używa geometrii obrysów i sprawdza kolizje oraz odstęp, zamiast traktować każdy obrys jako prostokąt. Jest heurystyczne: nie gwarantuje największej możliwej liczby. Krzywe są przybliżane odcinkami z tolerancją 0,05 mm; dla odstępu stosowany jest dodatkowy zapas 0,1 mm. Otwory są traktowane jako pełny materiał; nie są eksportowane jako wycięcia. Skan jest aproksymacją obrysu, nie dokładnym plikiem produkcyjnym. Przed cięciem zweryfikuj wymiary i geometrię w swoim programie produkcyjnym. W odstępie uwzględnij szerokość cięcia.

Obsługa wielu różnych formatek z zadanymi ilościami, otworów i dowolnych kątów obrotu nie jest częścią tej wersji.

## Weryfikacja

```bat
.venv-build\Scripts\python.exe -m unittest -v
```

Testy obejmują prostokąty, nieregularne wcięcia, układanie trójkątów gęściej niż ich prostokąty otaczające, odstępy i marginesy, obrót, anulowanie, import PDF z krzywymi, skan i skalę eksportu PDF 1:1.

PyMuPDF jest dostępny na licencji AGPL lub komercyjnej. Przed dystrybucją aplikacji uwzględnij warunki licencji jej zależności.
