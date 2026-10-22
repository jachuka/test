# Kalkulator formatek

Desktopowa aplikacja dla Windows, z polskim interfejsem. **Wersja wyłącznie lokalna:** uruchomiony program nie wysyła szkiców ani innych danych do usług internetowych, nie wymaga kluczy API ani abonamentu. Trzy tryby: prostokąty, powielanie jednego nieregularnego obrysu oraz wspomagane odtworzenie konturu z wymiarów szkicu. Domyślny arkusz: 3050 × 2050 mm. Wszystkie wymiary w mm, akceptowany przecinek dziesiętny.

## Uruchomienie z Pythona

Wymagany Python 3.10–3.15 z Tkinter (Tcl/Tk w instalatorze Windows). W folderze projektu:

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install -r requirements.txt
.venv-build\Scripts\python.exe app.py
```

Zależności: PyMuPDF (odczyt i zapis PDF), Shapely (geometria), NumPy (analiza pikseli skanów, bez OpenCV). Pobranie zależności podczas instalacji/budowania wymaga internetu. Gotowy EXE działa bez internetu; obliczenia, podgląd i import/eksport wykonują się wyłącznie na komputerze.

## Plik EXE dla Windows 11

Pobierz Code → Download ZIP z GitHub, rozpakuj do nowego folderu i uruchom `Zbuduj_EXE.bat`. Skrypt instaluje zależności w `.venv-build`, sprawdza Tkinter, uruchamia testy i buduje `dist\KalkulatorFormatek.exe`.

Jeśli Windows blokuje skrypt BAT, otwórz folder w Eksploratorze, wpisz `cmd` w pasku adresu i wykonaj kolejno:

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install PyInstaller==6.22.3 -r requirements.txt
.venv-build\Scripts\python.exe -m unittest -v
.venv-build\Scripts\python.exe build_windows.py
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

## Szkic → dowolny kontur

Wersja lokalna wykrywa zamknięty obrys i narożniki bez listy typów figur. Dla odręcznych skanów usuwa jasną kolorową kratkę, szuka pól zamkniętych tuszem i łączy pola rozdzielone cienką kreską wymiarową. Upraszcza obrys i proponuje wyrównanie prawie poziomych/pionowych odcinków. **To analiza obrazu z ograniczeniami, nie gwarancja poprawnego odczytu każdego szkicu.** Rysunek z przerwanym obrysem, wieloma elementami, gęstymi adnotacjami, bardzo drobnymi detalami, otworami lub krzywymi może wymagać korekty albo przygotowanego PDF wektorowego.

### Automatyczne wykrywanie i pytania o brakujące wymiary

1. Wczytaj szkic PDF (pierwsza strona) lub obraz. Opcja **Odczytuj automatycznie po wczytaniu** jest domyślnie włączona. Możesz też użyć **Wykryj obrys i odczytaj wymiary lokalnie**. Odczyt działa w tle i nie wysyła danych do internetu.
2. Na szkicu pojawi się czerwony obrys z numerami narożników. Sprawdź go. Jeśli wykryto kilka obrysów, wybierz właściwy z listy. Rozpoznane narożniki nie wymagają ręcznego klikania. Program nie dobiera szablonu U/L ani innej figury.
3. Jeśli dostępny jest Tesseract, program odczyta cyfry w czterech orientacjach. Liczbę dopasuje do wymiaru tylko wtedy, gdy w pobliżu znajdzie linię wymiarową, a jej końce odpowiadają poziomom narożników. Numery produktów i luźne napisy bez takiego dopasowania są pomijane. Wartości oznaczone przez OCR oceną co najmniej 85 i bez konkurencyjnych interpretacji trafiają do relacji wymiarowych; słabsze lub sprzeczne odczyty stają się pytaniami. Ocena OCR nie jest gwarancją poprawności — zawsze sprawdź wymiary przed produkcją. Wszystkie odczyty są interpretowane w mm.
4. Kliknij **Uzupełnij tylko brakujące wymiary**. Program pyta o niejednoznaczne odczyty oraz minimalny zestaw pozostałych relacji potrzebnych do określenia konturu. Niebieska strzałka pokazuje na szkicu punkty i oś bieżącego pytania. W przypadku niepewnego OCR proponuje odczytaną liczbę do potwierdzenia lub poprawienia. Nie pyta ponownie o różnicę współrzędnych, która wynika już z innych danych. Anulowanie zachowuje dotychczasową pracę.
5. Długości nie są obliczane ze skali, kratki ani proporcji skanu. Współrzędne obrazu służą do rozpoznania kolejności, kierunków, wyrównania i przypisania opisanych wymiarów. Brakujący wymiar rzeczywisty zawsze wymaga innych danych lub odpowiedzi użytkownika.
6. Po rozwiązaniu wymiarów aplikacja pokazuje dokładny kontur. Sprawdź go i zaznacz **Potwierdzam kontur i wymiary**. Następnie przekaż go do układania albo zapisz PDF 1:1. Każda zmiana danych unieważnia zatwierdzenie.

Na oryginalnym skanie BPV300 sprawdzono rzeczywisty odczyt lokalnym Tesseract: 8 narożników wykrytych automatycznie, odczyty 160 i 30 przypisane bez pytania, niepewne 30 i 60 wymagające potwierdzenia oraz pytanie o nierozpoznane 440. Po trzech odpowiedziach powstaje kontur 440 × 160 mm (w orientacji skanu 160 × 440), o polu 24 900 mm², zgodny z poprawnym PDF użytkownika z odchyleniem poniżej 0,001 mm po obrocie. Wyniku tego nie należy traktować jako oceny niezawodności na innych szkicach.

### Tesseract na Windows — opcjonalny, lokalny OCR

Wykrywanie obrysu działa bez dodatkowego programu. **Do automatycznego odczytu cyfr potrzebny jest Tesseract OCR z językiem angielskim (`eng`).** Nie wymaga klucza API ani opłat za zapytania. Informacje o instalatorach Windows są w dokumentacji projektu: https://tesseract-ocr.github.io/tessdoc/Installation.html (sekcja Windows; projekt wskazuje tam dostępne kompilacje).

Aplikacja szuka Tesseract w PATH oraz standardowych folderach `Tesseract-OCR` w Program Files i LocalAppData/Programs. W typowej instalacji jest to `C:\Program Files\Tesseract-OCR\tesseract.exe`. Jeśli go nie znajdzie albo OCR nie odczyta cyfr, nadal wykryje kontur i poprosi o wymiary. Po instalacji uruchom kalkulator ponownie i ponów odczyt.

Do budowania używaj `Zbuduj_EXE.bat` albo `.venv-build\Scripts\python.exe build_windows.py`. Jeśli Tesseract jest zainstalowany na komputerze budującym, skrypt dołącza jego katalog (program, biblioteki, dane i pliki licencji) do EXE. Powiększa to EXE, ale pozwala używać OCR na innym komputerze bez osobnej instalacji. Bez Tesseract budowany jest EXE z samym wykrywaniem obrysu i pytaniami o wymiary. Dotychczasowe ręczne polecenie PyInstaller nie dołącza Tesseract — na takim komputerze korzystanie z OCR wymaga oddzielnie zainstalowanego silnika. Budowania EXE z Tesseract na Windows nie zweryfikowano w linuksowym środowisku chmurowym.

### Gdy OCR dopasowuje 0 wymiarów

Otwórz **Diagnostyka OCR — pokaż przyczynę** po odczycie szkicu. Raport rozróżnia: brak Tesseract, błąd jego uruchomienia (np. blokada pliku lub brak DLL), brak języka `eng`, błąd odczytu, udany odczyt bez rozpoznanych cyfr oraz rozpoznane cyfry bez dopasowania do linii wymiarowych. Pokazuje ścieżkę i wersję silnika, dostępne języki, liczbę prób i odczytane wartości z ocenami OCR. Możesz zapisać raport do lokalnego pliku TXT.

Jeśli Tesseract jest zainstalowany w niestandardowym folderze, użyj **Wskaż zainstalowany tesseract.exe** i ponów odczyt. Ten wybór obowiązuje w bieżącej sesji. Samo wykrycie pliku EXE nie oznacza, że silnik działa — aplikacja sprawdza jego uruchomienie i język angielski przed analizą obrazu. Błędy procesu nie są już ukrywane jako zwykły wynik „0 wymiarów”.

Na komputerze testowym był zainstalowany Tesseract 5.5.0 z językiem `eng`. Wynik 2 dopasowanych wymiarów dla BPV300 dotyczy tej konfiguracji. Bez silnika program wykrywa narożniki, ale nie odczytuje żadnych cyfr. Inna wersja Tesseract lub danych językowych może również dawać inny wynik.

### Ręczna korekta i dowolny kontur wielokątny

Możesz wyłączyć automatyczny odczyt i wskazać narożniki ręcznie. Obsługiwane są odcinki poziome, pionowe i skośne oraz wklęsłości, maksymalnie 500 narożników. Edytor nie odtwarza dokładnych łuków ani otworów; dla krzywych użyj importu konturu wektorowego PDF.

1. Klikaj narożniki po obwodzie bez linii wymiarowych i bez powtarzania pierwszego punktu. Zamknij kontur. **Podgląd 100% / dopasuj** i paski przewijania ułatwiają pracę. Obróć podgląd przed oznaczaniem punktów.
2. W tabeli podaj **ΔX i ΔY w mm**: w prawo/dół dodatnie, w lewo/górę ujemne. 0 oznacza tę samą współrzędną. Puste pole to wymiar nieznany. Ostatni bok wraca do P1. Podpowiedź H/V wpisuje tylko edytowalne zera kierunków, nigdy długości.
3. Przez **Dodaj wymiar między punktami** można określić całkowitą szerokość, wysokość albo wyrównanie (wartość 0). Dla skosu wpisuj rzuty ΔX/ΔY, nie długość skośną.
4. **Zbuduj i sprawdź kontur** rozwiązuje relacje wymiarowe bez mierzenia zdjęcia. Brak danych, sprzeczność, samoprzecięcia, powtarzające się punkty i zerowe pole są zgłaszane. Tolerancja zgodności wymiarów: 0,001 mm.

Wczytanie innego pliku czyści dotychczasowy kontur. Obrót lub otwarcie zamkniętego konturu do edycji wymaga potwierdzenia utraty przypisanych wymiarów. Zmiana szkicu lub danych podczas odczytu powoduje pominięcie nieaktualnego wyniku.

### Przykład BV300 bez szablonu figury

Zaznacz narożniki w tej kolejności: lewy górny P1, prawy górny P2, prawy dolny P3, wewnętrzny prawy dolny P4, wewnętrzny prawy górny P5, wewnętrzny lewy górny P6, wewnętrzny lewy dolny P7, lewy dolny P8. Po podpowiedzi H/V wpisz:

| Bok | ΔX [mm] | ΔY [mm] |
| --- | ---: | ---: |
| P1 → P2 | 440 | 0 |
| P2 → P3 | 0 | 160 |
| P3 → P4 | -60 | 0 |
| P4 → P5 | 0 | pozostaw puste |
| P5 → P6 | pozostaw puste | 0 |
| P6 → P7 | 0 | pozostaw puste |
| P7 → P8 | -30 | 0 |
| P8 → P1 | 0 | pozostaw puste |

Dodaj dwa wymiary: P1 → P5 w osi Y = 30 mm (poprzeczka) oraz P3 → P7 w osi Y = 0 mm (wspólny dolny poziom). Program obliczy pozostałe wartości: zewnętrzne 440 × 160 mm, wycięcie 350 × 130 mm, pole 24 900 mm². Ten sam mechanizm działa dla dowolnej liczby i układu narożników.

## Weryfikacja

```bat
.venv-build\Scripts\python.exe -m unittest -v
```

Testy obejmują prostokąty, nieregularne wcięcia, układanie trójkątów gęściej niż ich prostokąty otaczające, odstępy i marginesy, obrót, anulowanie, import PDF z krzywymi, skan i skalę eksportu PDF 1:1.

PyMuPDF jest dostępny na licencji AGPL lub komercyjnej. Przed dystrybucją aplikacji uwzględnij warunki licencji jej zależności.
